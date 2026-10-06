// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {
    IERC20Like,
    IOptimisticOracleV2Like,
    IFinderLike,
    IStoreLike,
    IAddressWhitelistLike,
    IOracleAggregatorLike,
    IReporterModuleLike
} from "./Interfaces.sol";

/// @title IntendmentReporterModule
/// @notice A reporter module for Polymarket's Protocol V2 OracleAggregator that runs the optimistic
///         proposal and dispute game itself, puts a settlement window between every dispute and
///         UMA, and forwards only unsettled disputes to UMA's OptimisticOracleV2 as the court.
///         A dispute the parties settle pays UMA nothing. Design: docs/intendment-oracle-design-v0.4.md.
/// @dev Non-upgradeable; every parameter is fixed at deployment. Payouts are claimable credits.
///      No function iterates over co-backers, cases or credits.
contract IntendmentReporterModule is IReporterModuleLike {
    // ----------------------------------------------------------------- constants

    bytes32 public constant IDENTIFIER = "YES_OR_NO_QUERY";
    int256 public constant NO = 0;
    int256 public constant YES = 1e18;
    int256 public constant SPLIT = 0.5e18;
    int256 public constant TOO_EARLY = type(int256).min;
    uint256 public constant RESULT_DENOMINATOR = 1_000_000;
    uint8 public constant BINARY = 0;
    uint8 public constant INCREMENTAL_NEGRISK = 1;
    /// UMA's OOv2 takes at most 8,139 bytes of ancillary data (8,192 less the 53 it stamps), and a
    /// forwarded case adds ",intendmentCase:" and up to 20 digits to the question.
    uint256 public constant MAX_RULES = 8_139 - 36;

    // ----------------------------------------------------------------- configuration

    struct Config {
        address aggregator; // Polymarket V2 OracleAggregator
        address oracle; // UMA OptimisticOracleV2 that decides unsettled cases
        address currency; // bond and reward currency; must be on UMA's collateral whitelist
        address venue; // non-party recipient of the settlement charge and of unspent rewards
        address proposerWhitelist; // zero: anyone may propose
        bool coBackersWhitelisted; // co-backing restricted to the proposer whitelist
        uint16 chargeBps; // the non-party charge, in basis points of the bond (5000 = UMA's burn)
        uint32 windowNonBlocking; // settlement window when the market has already reset
        uint32 windowBlocking; // settlement window when the market waits on the case
        uint32 grace; // after a case's deadline, before the emergency path may run
        uint32 minLiveness; // lower bound on a request's liveness
        uint8 maxSettledBlocking; // M: settled blocking cases per question
    }

    IOracleAggregatorLike public immutable aggregator;
    IOptimisticOracleV2Like public immutable oracle;
    IERC20Like public immutable currency;
    address public immutable venue;
    IAddressWhitelistLike public immutable proposerWhitelist;
    bool public immutable coBackersWhitelisted;
    uint16 public immutable chargeBps;
    uint32 public immutable windowNonBlocking;
    uint32 public immutable windowBlocking;
    uint32 public immutable grace;
    uint32 public immutable minLiveness;
    uint8 public immutable maxSettledBlocking;

    // ----------------------------------------------------------------- state

    enum RequestStatus {
        None,
        Open,
        Resolved,
        Failed
    }

    enum CaseStatus {
        None,
        Open,
        Conceded,
        Withdrawn,
        Forwarded,
        Resolved,
        Abandoned
    }

    struct Request {
        RequestStatus status;
        uint8 marketType;
        bool blocking; // set by the first dispute: later disputes hold the market
        bool reported; // the result reached the aggregator
        uint8 settledBlocking;
        uint32 liveness;
        uint64 activeProposal; // the live proposal the market waits on, if any
        uint64 heldBy; // the blocking case the market waits on, if any
        uint128 bond;
        uint128 reward;
        int256 price; // the final answer, as a UMA price
        bytes rules; // the question as UMA's voters will read it
    }

    struct Proposal {
        bytes32 requestId;
        address proposer; // the proposer of record
        uint128 proposerFee; // the final fee inside the proposer of record's stake
        int256 price;
        uint64 proposedAt;
        uint64 expiresAt;
        uint64 caseId;
        bool closed;
        uint32 head; // next co-backer to promote
        uint32 count; // co-backers queued
    }

    struct CoBacker {
        address backer;
        uint128 fee;
        bool done; // promoted to proposer of record, or released
    }

    struct Case {
        uint64 proposalId;
        address disputer;
        uint128 disputerFee;
        uint64 deadline;
        bool blocking;
        bool forwardOnly; // M was spent: the case can only go to UMA (forwarding is retried if it failed)
        CaseStatus status;
        int256 umaPrice;
    }

    mapping(bytes32 => Request) public requests;
    mapping(uint64 => Proposal) public proposals;
    mapping(uint64 => mapping(uint32 => CoBacker)) public coBackers;
    mapping(uint64 => Case) public cases;
    mapping(address => uint256) public credits;
    uint64 public proposalCount;
    uint64 public caseCount;

    // Money buckets: the module's balance always equals the sum of these four (design 4.10).
    uint256 public stakesHeld;
    uint256 public rewardsEscrowed;
    uint256 public rewardBudget;
    uint256 public creditsOwed;

    uint256 private _locked = 1;

    // ----------------------------------------------------------------- events

    event RequestRegistered(bytes32 indexed requestId, uint8 marketType, uint128 bond, uint32 liveness, uint128 reward);
    event RulesUpdated(bytes32 indexed requestId, bytes rules);
    event RewardsFunded(address indexed from, uint256 amount);
    event Proposed(bytes32 indexed requestId, uint64 indexed proposalId, address indexed proposer, int256 price, uint64 expiresAt);
    event CoBacked(uint64 indexed proposalId, uint32 index, address indexed backer);
    event ProposerReplaced(uint64 indexed proposalId, address indexed leaving, address indexed next);
    event Retracted(uint64 indexed proposalId, address indexed proposer);
    event Disputed(uint64 indexed proposalId, uint64 indexed caseId, address indexed disputer, bool blocking, uint64 deadline);
    event Conceded(uint64 indexed caseId, address indexed proposer);
    event Withdrawn(uint64 indexed caseId, address indexed disputer);
    event Forwarded(uint64 indexed caseId, uint256 umaTime, bytes ancillaryData);
    event ForwardFailed(uint64 indexed caseId, bytes reason);
    event CaseResolved(uint64 indexed caseId, int256 umaPrice);
    event Abandoned(uint64 indexed caseId);
    event ProposalSettled(uint64 indexed proposalId, address indexed proposer);
    event RequestReopened(bytes32 indexed requestId);
    event RequestResolved(bytes32 indexed requestId, int256 price);
    event RequestFailed(bytes32 indexed requestId, int256 umaPrice);
    event ResultReported(bytes32 indexed requestId, uint256 result);
    event ResultReportFailed(bytes32 indexed requestId, bytes reason);
    event CoBackerReleased(uint64 indexed proposalId, uint32 index, address indexed backer);
    event Credited(address indexed who, uint256 amount);
    event Claimed(address indexed who, address indexed to, uint256 amount);

    // ----------------------------------------------------------------- errors

    error NotAggregator();
    error BadConfig();
    error BadRegistration();
    error UnknownRequest();
    error MarketBusy();
    error NotWhitelisted();
    error BadPrice();
    error NotLive();
    error NotProposer();
    error NotDisputer();
    error CaseNotOpen();
    error TooEarlyToForward();
    error NotForwarded();
    error BlockingCase();
    error NothingToRelease();
    error TopUpNeeded();
    error GraceNotOver();
    error Reentrancy();
    error TransferFailed();
    error NotSelf();
    error ForwardOnly();

    // ----------------------------------------------------------------- modifiers

    modifier nonReentrant() {
        if (_locked != 1) revert Reentrancy();
        _locked = 2;
        _;
        _locked = 1;
    }

    modifier onlyAggregator() {
        if (msg.sender != address(aggregator)) revert NotAggregator();
        _;
    }

    constructor(Config memory c) {
        if (
            c.aggregator == address(0) || c.oracle == address(0) || c.currency == address(0)
                || c.venue == address(0) || c.chargeBps > 10_000 || c.minLiveness == 0
                || (c.coBackersWhitelisted && c.proposerWhitelist == address(0))
        ) revert BadConfig();
        aggregator = IOracleAggregatorLike(c.aggregator);
        oracle = IOptimisticOracleV2Like(c.oracle);
        currency = IERC20Like(c.currency);
        venue = c.venue;
        proposerWhitelist = IAddressWhitelistLike(c.proposerWhitelist);
        coBackersWhitelisted = c.coBackersWhitelisted;
        chargeBps = c.chargeBps;
        windowNonBlocking = c.windowNonBlocking;
        windowBlocking = c.windowBlocking;
        grace = c.grace;
        minLiveness = c.minLiveness;
        maxSettledBlocking = c.maxSettledBlocking;
    }

    // ----------------------------------------------------------------- registration (V2 shell)

    /// @notice One request to register: the Polymarket request id (a condition id padded to 32
    ///         bytes), its bond, liveness, proposer reward, and the question for UMA's voters.
    struct Registration {
        bytes32 requestId;
        uint128 bond;
        uint32 liveness;
        uint128 reward;
        bytes rules;
    }

    /// @inheritdoc IReporterModuleLike
    /// @dev Called by the aggregator inside `initializeRequest`, after it has stored the request
    ///      configuration, so the market type can be read back. The reward is earmarked from the
    ///      budget the venue funded with `fundRewards`.
    function initializeReporterModule(bytes29 eventId, bytes calldata data) external onlyAggregator {
        Registration[] memory regs = abi.decode(data, (Registration[]));
        if (regs.length == 0) revert BadRegistration();
        for (uint256 i; i < regs.length; ++i) {
            Registration memory g = regs[i];
            // the request must belong to the event and be a canonical condition id (outcome byte clear)
            if (bytes29(g.requestId) != eventId || uint8(uint256(g.requestId)) != 0) revert BadRegistration();
            if (g.bond == 0 || g.liveness < minLiveness || g.rules.length == 0 || g.rules.length > MAX_RULES) {
                revert BadRegistration();
            }
            Request storage r = requests[g.requestId];
            if (r.status != RequestStatus.None) revert BadRegistration();
            (uint8 marketType, uint16 resultLength) = aggregator.getRequestShape(g.requestId);
            if (resultLength != 1 || marketType > INCREMENTAL_NEGRISK) revert BadRegistration();
            if (g.reward > rewardBudget) revert BadRegistration();
            rewardBudget -= g.reward;
            rewardsEscrowed += g.reward;
            r.status = RequestStatus.Open;
            r.marketType = marketType;
            r.bond = g.bond;
            r.liveness = g.liveness;
            r.reward = g.reward;
            r.rules = g.rules;
            emit RequestRegistered(g.requestId, marketType, g.bond, g.liveness, g.reward);
        }
    }

    /// @inheritdoc IReporterModuleLike
    /// @dev Rule updates are announced; a forwarded case carries the original question, and
    ///      voters read clarifications where they read them today.
    function updateRules(bytes32 requestId, bytes calldata updatedRules) external onlyAggregator {
        if (requests[requestId].status == RequestStatus.None) return;
        emit RulesUpdated(requestId, updatedRules);
    }

    /// @notice Funds proposer rewards. Anyone may fund; the venue normally does.
    function fundRewards(uint256 amount) external nonReentrant {
        _pull(msg.sender, amount);
        rewardBudget += amount;
        emit RewardsFunded(msg.sender, amount);
    }

    // ----------------------------------------------------------------- proposals

    /// @notice Propose an answer, staking the bond plus UMA's current final fee.
    function propose(bytes32 requestId, int256 price) external nonReentrant returns (uint64 pid) {
        Request storage r = requests[requestId];
        if (r.status != RequestStatus.Open) revert UnknownRequest();
        if (r.activeProposal != 0 || r.heldBy != 0) revert MarketBusy();
        if (address(proposerWhitelist) != address(0) && !proposerWhitelist.isOnWhitelist(msg.sender)) {
            revert NotWhitelisted();
        }
        if (!_validPrice(r.marketType, price)) revert BadPrice();
        uint128 fee = _finalFee();
        _pull(msg.sender, uint256(r.bond) + fee);
        stakesHeld += uint256(r.bond) + fee;
        pid = ++proposalCount;
        Proposal storage p = proposals[pid];
        p.requestId = requestId;
        p.proposer = msg.sender;
        p.proposerFee = fee;
        p.price = price;
        p.proposedAt = uint64(block.timestamp);
        p.expiresAt = uint64(block.timestamp + r.liveness);
        r.activeProposal = pid;
        emit Proposed(requestId, pid, msg.sender, price, p.expiresAt);
    }

    /// @notice Put a standby stake behind a live proposal's answer. It is at risk only once it
    ///         becomes the proposer of record, and it pays nothing (design 4.9).
    function coBack(uint64 pid) external nonReentrant returns (uint32 index) {
        Proposal storage p = proposals[pid];
        if (p.proposer == address(0) || p.closed) revert NotLive();
        if (p.caseId == 0) {
            if (block.timestamp >= p.expiresAt) revert NotLive();
        } else if (cases[p.caseId].status != CaseStatus.Open) {
            revert NotLive();
        }
        if (coBackersWhitelisted && !proposerWhitelist.isOnWhitelist(msg.sender)) revert NotWhitelisted();
        Request storage r = requests[p.requestId];
        uint128 fee = p.proposerFee; // the fee recorded with the proposal; a forward settles any change
        _pull(msg.sender, uint256(r.bond) + fee);
        stakesHeld += uint256(r.bond) + fee;
        index = p.count++;
        coBackers[pid][index] = CoBacker({backer: msg.sender, fee: fee, done: false});
        emit CoBacked(pid, index, msg.sender);
    }

    /// @notice The proposer of record takes its live, undisputed proposal back for the non-party
    ///         charge. A co-backer, if any, carries the answer on with the same liveness.
    function retract(uint64 pid) external nonReentrant {
        Proposal storage p = proposals[pid];
        if (p.closed || p.caseId != 0 || block.timestamp >= p.expiresAt) revert NotLive();
        if (msg.sender != p.proposer) revert NotProposer();
        Request storage r = requests[p.requestId];
        uint256 b = r.bond;
        uint256 charge = _charge(b);
        stakesHeld -= b + p.proposerFee;
        _credit(msg.sender, b + p.proposerFee - charge);
        _credit(venue, charge);
        emit Retracted(pid, msg.sender);
        if (_promote(pid, p)) return;
        p.closed = true;
        r.activeProposal = 0;
        emit RequestReopened(p.requestId);
    }

    /// @notice Settle a proposal that survived its liveness undisputed: the market resolves.
    function settleProposal(uint64 pid) external nonReentrant {
        Proposal storage p = proposals[pid];
        if (p.proposer == address(0) || p.closed || p.caseId != 0 || block.timestamp < p.expiresAt) revert NotLive();
        Request storage r = requests[p.requestId];
        uint256 b = r.bond;
        stakesHeld -= b + p.proposerFee;
        uint256 reward = r.reward;
        rewardsEscrowed -= reward;
        r.reward = 0;
        _credit(p.proposer, b + p.proposerFee + reward);
        p.closed = true;
        r.activeProposal = 0;
        emit ProposalSettled(pid, p.proposer);
        _resolve(p.requestId, r, p.price);
    }

    // ----------------------------------------------------------------- disputes and cases

    /// @notice Dispute a live proposal, staking the bond plus the final fee recorded with the
    ///         proposal, so that no call to UMA stands between a challenger and its case. The first
    ///         dispute on a question resets the market at once and the case concerns only the stakes;
    ///         a later dispute holds the market for the window, or goes straight to UMA once M is
    ///         spent. If UMA refuses that forward, the dispute still stands and holds the market: the
    ///         case can only go to UMA, anyone may retry, and the emergency path follows after the
    ///         grace period.
    function dispute(uint64 pid) external nonReentrant returns (uint64 cid) {
        Proposal storage p = proposals[pid];
        if (p.proposer == address(0) || p.closed || p.caseId != 0 || block.timestamp >= p.expiresAt) revert NotLive();
        Request storage r = requests[p.requestId];
        uint128 fee = p.proposerFee; // UMA's current fee is read only when the case is forwarded
        _pull(msg.sender, uint256(r.bond) + fee);
        stakesHeld += uint256(r.bond) + fee;
        cid = ++caseCount;
        Case storage c = cases[cid];
        c.proposalId = pid;
        c.disputer = msg.sender;
        c.disputerFee = fee;
        c.status = CaseStatus.Open;
        p.caseId = cid;
        r.activeProposal = 0;
        if (!r.blocking) {
            r.blocking = true;
            c.deadline = uint64(block.timestamp + windowNonBlocking);
            emit Disputed(pid, cid, msg.sender, false, c.deadline);
            emit RequestReopened(p.requestId);
            return cid;
        }
        c.blocking = true;
        r.heldBy = cid;
        if (r.settledBlocking < maxSettledBlocking) {
            c.deadline = uint64(block.timestamp + windowBlocking);
            emit Disputed(pid, cid, msg.sender, true, c.deadline);
            return cid;
        }
        c.forwardOnly = true;
        c.deadline = uint64(block.timestamp);
        emit Disputed(pid, cid, msg.sender, true, c.deadline);
        try this.forwardFromSelf(cid, msg.sender) {}
        catch (bytes memory reason) {
            emit ForwardFailed(cid, reason);
        }
    }

    /// @notice The proposer of record gives up. With a co-backer behind the answer only the
    ///         caller leaves, for the non-party charge, and the case runs on to the same deadline.
    ///         Otherwise the case ends: the caller forfeits its bond, the disputer receives its
    ///         court win plus the burn less the charge, and the caller keeps its final fee.
    function concede(uint64 cid) external nonReentrant {
        Case storage c = cases[cid];
        if (c.status != CaseStatus.Open) revert CaseNotOpen();
        if (c.forwardOnly) revert ForwardOnly();
        Proposal storage p = proposals[c.proposalId];
        if (msg.sender != p.proposer) revert NotProposer();
        Request storage r = requests[p.requestId];
        uint256 b = r.bond;
        uint256 charge = _charge(b);
        if (p.head < p.count) {
            stakesHeld -= b + p.proposerFee;
            _credit(msg.sender, b + p.proposerFee - charge);
            _credit(venue, charge);
            _promote(c.proposalId, p);
            return;
        }
        stakesHeld -= 2 * b + p.proposerFee + c.disputerFee;
        _credit(msg.sender, p.proposerFee);
        _credit(c.disputer, b + c.disputerFee + (b - charge));
        _credit(venue, charge);
        c.status = CaseStatus.Conceded;
        p.closed = true;
        if (c.blocking) {
            r.heldBy = 0;
            r.settledBlocking += 1;
            emit RequestReopened(p.requestId);
        }
        emit Conceded(cid, msg.sender);
    }

    /// @notice The disputer gives up, on a non-blocking case only (design 5.4): it forfeits its
    ///         bond and keeps its final fee; the proposer of record receives its court win plus
    ///         the burn less the charge.
    function withdraw(uint64 cid) external nonReentrant {
        Case storage c = cases[cid];
        if (c.status != CaseStatus.Open) revert CaseNotOpen();
        if (c.blocking) revert BlockingCase();
        if (msg.sender != c.disputer) revert NotDisputer();
        Proposal storage p = proposals[c.proposalId];
        uint256 b = requests[p.requestId].bond;
        uint256 charge = _charge(b);
        stakesHeld -= 2 * b + p.proposerFee + c.disputerFee;
        _credit(msg.sender, c.disputerFee);
        _credit(p.proposer, b + p.proposerFee + (b - charge));
        _credit(venue, charge);
        c.status = CaseStatus.Withdrawn;
        p.closed = true;
        emit Withdrawn(cid, msg.sender);
    }

    /// @notice Send an open case to UMA. The proposer of record may do it at any time, anyone else
    ///         from the deadline. If UMA's final fee rose since the stakes were posted, the caller
    ///         pays the rise; if it fell, each party is credited the difference.
    function forward(uint64 cid) external nonReentrant {
        Case storage c = cases[cid];
        if (c.status != CaseStatus.Open) revert CaseNotOpen();
        Proposal storage p = proposals[c.proposalId];
        if (block.timestamp < c.deadline && msg.sender != p.proposer) revert TooEarlyToForward();
        _forward(cid, msg.sender, true);
    }

    /// @notice Read UMA's answer for a forwarded case. UMA pays the winner directly; for a blocking
    ///         case the answer decides the market, "too early" reopens it, and an answer the market
    ///         type cannot take is a visible failure left to the venue's manual resolution.
    function resolveCase(uint64 cid) external nonReentrant {
        Case storage c = cases[cid];
        if (c.status != CaseStatus.Forwarded) revert NotForwarded();
        Proposal storage p = proposals[c.proposalId];
        Request storage r = requests[p.requestId];
        int256 umaPrice = oracle.settleAndGetPrice(IDENTIFIER, p.proposedAt, _umaAncillary(r.rules, cid));
        c.status = CaseStatus.Resolved;
        c.umaPrice = umaPrice;
        emit CaseResolved(cid, umaPrice);
        if (!c.blocking || r.heldBy != cid) return;
        r.heldBy = 0;
        if (umaPrice == TOO_EARLY) {
            emit RequestReopened(p.requestId);
        } else if (_validPrice(r.marketType, umaPrice)) {
            _releaseReward(r);
            _resolve(p.requestId, r, umaPrice);
        } else {
            _releaseReward(r);
            _fail(p.requestId, r, umaPrice);
        }
    }

    /// @notice Emergency path (design 4.11): a grace period after the deadline, anyone may try to
    ///         forward again; if UMA rejects it in the same transaction, both stakes return in full
    ///         and a blocking market goes to the venue's manual resolution.
    function abandon(uint64 cid) external nonReentrant {
        Case storage c = cases[cid];
        if (c.status != CaseStatus.Open) revert CaseNotOpen();
        if (block.timestamp < uint256(c.deadline) + grace) revert GraceNotOver();
        try this.forwardFromSelf(cid, address(0)) {
            return;
        } catch (bytes memory reason) {
            // a selector is the first four bytes of the revert data; shorter data never matches
            // forge-lint: disable-next-line(unsafe-typecast)
            if (bytes4(reason) == TopUpNeeded.selector) revert TopUpNeeded();
        }
        Proposal storage p = proposals[c.proposalId];
        Request storage r = requests[p.requestId];
        uint256 b = r.bond;
        stakesHeld -= 2 * b + p.proposerFee + c.disputerFee;
        _credit(p.proposer, b + p.proposerFee);
        _credit(c.disputer, b + c.disputerFee);
        c.status = CaseStatus.Abandoned;
        p.closed = true;
        emit Abandoned(cid);
        if (c.blocking && r.heldBy == cid) {
            r.heldBy = 0;
            _releaseReward(r);
            _fail(p.requestId, r, TOO_EARLY);
        }
    }

    /// @dev Self-call target for `dispute` and `abandon`, so a UMA rejection rolls back only this
    ///      attempt. A zero payer cannot cover a rise in UMA's final fee.
    function forwardFromSelf(uint64 cid, address payer) external {
        if (msg.sender != address(this)) revert NotSelf();
        _forward(cid, payer, payer != address(0));
    }

    // ----------------------------------------------------------------- results and money

    /// @notice Retry delivering a resolved request's result to the aggregator.
    function relay(bytes32 requestId) external nonReentrant {
        Request storage r = requests[requestId];
        if (r.status != RequestStatus.Resolved || r.reported) revert UnknownRequest();
        _report(requestId, r);
    }

    /// @notice Return a standby stake once its proposal has closed.
    function releaseCoBacker(uint64 pid, uint32 index) external nonReentrant {
        Proposal storage p = proposals[pid];
        CoBacker storage cb = coBackers[pid][index];
        if (!p.closed || index >= p.count || cb.done) revert NothingToRelease();
        cb.done = true;
        uint256 stake = uint256(requests[p.requestId].bond) + cb.fee;
        stakesHeld -= stake;
        _credit(cb.backer, stake);
        emit CoBackerReleased(pid, index, cb.backer);
    }

    function claim(address to) external nonReentrant returns (uint256 amount) {
        amount = credits[msg.sender];
        credits[msg.sender] = 0;
        creditsOwed -= amount;
        _push(to, amount);
        emit Claimed(msg.sender, to, amount);
    }

    // ----------------------------------------------------------------- views

    /// @notice The exact ancillary data a forwarded case carries to UMA: the question, tagged with
    ///         the case id so that every forwarded request is unique.
    function umaAncillary(uint64 cid) external view returns (bytes memory) {
        return _umaAncillary(requests[proposals[cases[cid].proposalId].requestId].rules, cid);
    }

    function finalFee() external view returns (uint256) {
        return _finalFee();
    }

    // ----------------------------------------------------------------- internals

    function _forward(uint64 cid, address payer, bool allowTopUp) internal {
        Case storage c = cases[cid];
        Proposal storage p = proposals[c.proposalId];
        Request storage r = requests[p.requestId];
        uint256 b = r.bond;
        uint256 fNow = _finalFee();
        uint256 topUp;
        if (fNow > p.proposerFee) topUp += fNow - p.proposerFee;
        else if (fNow < p.proposerFee) _credit(p.proposer, p.proposerFee - fNow);
        if (fNow > c.disputerFee) topUp += fNow - c.disputerFee;
        else if (fNow < c.disputerFee) _credit(c.disputer, c.disputerFee - fNow);
        if (topUp != 0) {
            if (!allowTopUp) revert TopUpNeeded();
            _pull(payer, topUp);
        }
        stakesHeld -= 2 * b + p.proposerFee + c.disputerFee;
        c.status = CaseStatus.Forwarded;
        p.closed = true;
        bytes memory anc = _umaAncillary(r.rules, cid);
        uint256 t = p.proposedAt;
        uint256 total = 2 * (b + fNow);
        _approve(address(oracle), total);
        oracle.requestPrice(IDENTIFIER, t, anc, address(currency), 0);
        oracle.setBond(IDENTIFIER, t, anc, b);
        oracle.setCustomLiveness(IDENTIFIER, t, anc, 1);
        oracle.proposePriceFor(p.proposer, address(this), IDENTIFIER, t, anc, p.price);
        oracle.disputePriceFor(c.disputer, address(this), IDENTIFIER, t, anc);
        _approve(address(oracle), 0);
        emit Forwarded(cid, t, anc);
    }

    /// @dev Promote the earliest co-backer to proposer of record. Returns false if none remains.
    function _promote(uint64 pid, Proposal storage p) internal returns (bool) {
        if (p.head >= p.count) return false;
        CoBacker storage cb = coBackers[pid][p.head];
        cb.done = true;
        p.head += 1;
        address leaving = p.proposer;
        p.proposer = cb.backer;
        p.proposerFee = cb.fee;
        emit ProposerReplaced(pid, leaving, cb.backer);
        return true;
    }

    function _resolve(bytes32 requestId, Request storage r, int256 price) internal {
        r.status = RequestStatus.Resolved;
        r.price = price;
        emit RequestResolved(requestId, price);
        _report(requestId, r);
    }

    function _fail(bytes32 requestId, Request storage r, int256 umaPrice) internal {
        r.status = RequestStatus.Failed;
        emit RequestFailed(requestId, umaPrice);
    }

    function _releaseReward(Request storage r) internal {
        uint256 reward = r.reward;
        if (reward == 0) return;
        r.reward = 0;
        rewardsEscrowed -= reward;
        _credit(venue, reward);
    }

    function _report(bytes32 requestId, Request storage r) internal {
        uint256[] memory result = new uint256[](1);
        result[0] = _toResult(r.price);
        try aggregator.reportResult(requestId, result) {
            r.reported = true;
            emit ResultReported(requestId, result[0]);
        } catch (bytes memory reason) {
            emit ResultReportFailed(requestId, reason);
        }
    }

    function _validPrice(uint8 marketType, int256 price) internal pure returns (bool) {
        if (price == YES || price == NO) return true;
        return price == SPLIT && marketType == BINARY;
    }

    function _toResult(int256 price) internal pure returns (uint256) {
        if (price == YES) return RESULT_DENOMINATOR;
        if (price == SPLIT) return RESULT_DENOMINATOR / 2;
        return 0;
    }

    function _charge(uint256 bond) internal view returns (uint256) {
        return (bond * chargeBps) / 10_000;
    }

    function _finalFee() internal view returns (uint128) {
        address store = IFinderLike(oracle.finder()).getImplementationAddress("Store");
        return uint128(IStoreLike(store).computeFinalFee(address(currency)));
    }

    function _umaAncillary(bytes memory rules, uint64 cid) internal pure returns (bytes memory) {
        return abi.encodePacked(rules, ",intendmentCase:", _toString(cid));
    }

    function _credit(address who, uint256 amount) internal {
        if (amount == 0) return;
        credits[who] += amount;
        creditsOwed += amount;
        emit Credited(who, amount);
    }

    function _pull(address from, uint256 amount) internal {
        if (amount == 0) return;
        _call(abi.encodeCall(IERC20Like.transferFrom, (from, address(this), amount)));
    }

    function _push(address to, uint256 amount) internal {
        if (amount == 0) return;
        _call(abi.encodeCall(IERC20Like.transfer, (to, amount)));
    }

    function _approve(address spender, uint256 amount) internal {
        _call(abi.encodeCall(IERC20Like.approve, (spender, amount)));
    }

    /// @dev Token call that accepts both bool-returning and non-returning ERC-20s.
    function _call(bytes memory data) internal {
        (bool ok, bytes memory ret) = address(currency).call(data);
        if (!ok || (ret.length != 0 && !abi.decode(ret, (bool)))) revert TransferFailed();
    }

    function _toString(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 len;
        for (uint256 x = v; x != 0; x /= 10) ++len;
        bytes memory out = new bytes(len);
        for (; v != 0; v /= 10) out[--len] = bytes1(uint8(48 + (v % 10)));
        return string(out);
    }
}
