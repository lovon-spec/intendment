// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {IArbitrator, IArbitrable, IRegistry, IWrapperFactory, IMigrationTarget} from "./Interfaces.sol";
import {HostProfiles} from "./HostProfiles.sol";
import {FullMath} from "./FullMath.sol";

/// Stage 1a, spec 0.5: concession or the original court. REVIEW PROTOTYPE.
/// No offers, severity credit, withdrawal/restart, token custody or upgrade path.
contract IntendmentArbitrator is IArbitrator, IArbitrable {
    enum State { Unbound, Open, Forwardable, Forwarded, Conceded, Lapsed }
    enum Attempt { Success, Uncovered, Failed }
    struct Config {
        uint256 window;
        uint256 fundingPeriod;
        uint256 resolverGrace;
        uint256 reserveTimelock;
        uint256 retirementMargin;
    }
    struct Epoch {
        bool exists;
        uint256 quote;
        uint256 premium;
        uint256 maxCost;
        bytes realExtraData;
    }
    struct Case {
        State state;
        uint32 epochId;
        uint256 choices;
        uint256 fee;
        uint256 createdAt;
        uint256 deadline;
        uint256 fundingEnd;
        uint256 earmark;
        uint256 firstForwardFailure;
        uint256 totalFunding;
        uint256 fundingUsed;
        uint256 refundableAmount;
        uint256 claimedFunding;
        uint256 kDisputeID;
        uint256 ruling;
        bool rulingDelivered;
        bool insuredAtCreation;
        bytes32 envelopeHash;
        HostProfiles.Binding binding;
    }
    struct Withdrawal { uint256 amount; address payable to; uint256 announcedAt; bool pending; }

    address public immutable HOST;
    IArbitrator public immutable K;
    address public immutable GOVERNOR;
    address public immutable FACTORY;
    HostProfiles.Profile public immutable PROFILE;
    uint256 public immutable WINDOW;
    uint256 public immutable FUNDING_PERIOD;
    uint256 public immutable RESOLVER_GRACE;
    uint256 public immutable RESERVE_TIMELOCK;
    uint256 public immutable RETIREMENT_MARGIN;
    uint256 public constant MAX_MARGIN_BPS = 2500;
    uint256 public constant MAX_PREMIUM_BPS = 1000;
    uint256 public constant MAX_EXTRA_BYTES = 1024;
    // Bounded calls prevent caller-induced starvation from becoming a lapse option.
    // These budgets are deployment review assumptions, not universal Kleros gas bounds.
    uint256 public constant QUOTE_GAS = 100_000;
    uint256 public constant CREATE_GAS = 1_500_000;
    uint256 public constant POST_CALL_GAS = 400_000;

    uint32 public epochCount;
    uint256 public caseCount;
    uint256 public openCases;
    uint256 public totalEarmarked;
    uint256 public openFees;
    uint256 public refundLiability;
    uint256 public totalClaimable;
    uint256 public principal;
    uint256 public surplus;
    bool public retired;
    uint256 public retiredAt;
    uint256 public retirementUnlockAt;
    Withdrawal public pendingWithdrawal;
    uint256 private entered = 1;
    mapping(uint32 => Epoch) private epochs;
    mapping(uint256 => Case) private cases;
    mapping(uint256 => uint256) private remoteToLocalPlusOne;
    mapping(address => uint256) public claimable;
    mapping(uint256 => mapping(address => uint256)) public contribution;
    mapping(uint256 => mapping(address => bool)) public fundingClaimed;

    error Unauthorized();
    error InvalidInput();
    error InvalidState();
    error NotCovered();
    error QuoteUnavailable();
    error InsufficientCallGas();
    error MalformedResolverReturn();
    error Reentrant();
    error TransferFailed();

    event MetaEvidence(uint256 indexed _metaEvidenceID, string _evidence);
    event Dispute(IArbitrator indexed _arbitrator, uint256 indexed _disputeID, uint256 _metaEvidenceID, uint256 _evidenceGroupID);
    event Ruling(IArbitrator indexed _arbitrator, uint256 indexed _disputeID, uint256 _ruling);
    event EpochRegistered(uint32 indexed id, uint256 quote, uint256 premium, uint256 maxCost, bytes realExtraData);
    event CaseOpened(uint256 indexed id, uint32 epochId, uint256 fee, uint256 deadline, uint256 fundingEnd, uint256 earmark);
    event UnderInsured(uint256 indexed id, uint256 shortfall);
    event CaseBound(uint256 indexed id, bool removal, address requester, address challenger);
    event Settled(uint256 indexed id, uint256 share, uint256 requesterCredit, uint256 challengerCredit, uint256 premium);
    event Escalated(uint256 indexed id, uint256 indexed remoteID, uint256 cost, uint256 fundingUsed, address by);
    event ForwardFailed(uint256 indexed id, uint8 reason);
    event Funded(uint256 indexed id, address indexed funder, uint256 amount);
    event FundingClaimed(uint256 indexed id, address indexed funder, uint256 amount);
    event Lapsed(uint256 indexed id);
    event RulingRelayed(uint256 indexed id, uint256 remoteID, uint256 ruling);
    event Claimed(address indexed creditor, address indexed to, uint256 amount);
    event ReserveFunded(address indexed from, uint256 amount, bool isPrincipal);
    event Deactivated(uint256 at);
    event WithdrawalAnnounced(uint256 amount, address to, uint256 at);
    event WithdrawalCancelled();
    event PrincipalWithdrawn(address to, uint256 amount);
    event SurplusMigrated(address successor, uint256 amount);
    event UnaccountedDonated(uint256 amount);

    modifier nonReentrant() { if (entered != 1) revert Reentrant(); entered = 2; _; entered = 1; }
    modifier onlyGovernor() { if (msg.sender != GOVERNOR) revert Unauthorized(); _; }

    constructor(address host, IArbitrator resolver, address governor, HostProfiles.Profile profile, Config memory config) {
        if (host.code.length == 0 || address(resolver).code.length == 0 || governor == address(0)
            || IRegistry(host).governor() != governor || config.window == 0 || config.fundingPeriod == 0
            || config.resolverGrace == 0 || config.reserveTimelock == 0 || config.retirementMargin == 0) revert InvalidInput();
        HOST = host; K = resolver; GOVERNOR = governor; FACTORY = msg.sender; PROFILE = profile;
        WINDOW = config.window; FUNDING_PERIOD = config.fundingPeriod;
        RESOLVER_GRACE = config.resolverGrace; RESERVE_TIMELOCK = config.reserveTimelock;
        RETIREMENT_MARGIN = config.retirementMargin;
    }

    function reserve() public view returns (uint256) { return principal + surplus; }
    function free() public view returns (uint256) { return reserve() - totalEarmarked; }
    function accountedBalance() public view returns (uint256) { return reserve() + openFees + refundLiability + totalClaimable; }
    function unaccountedBalance() public view returns (uint256) { return address(this).balance - accountedBalance(); }
    function epoch(uint32 id) external view returns (Epoch memory) { return _epoch(id); }
    function caseOf(uint256 id) external view returns (Case memory) { return _case(id); }
    function modeOf(uint256 id) external view returns (bool) { return _case(id).insuredAtCreation; }
    function localDispute(uint256 remoteID) external view returns (uint256) {
        uint256 mapped = remoteToLocalPlusOne[remoteID];
        if (mapped == 0) revert InvalidInput();
        return mapped - 1;
    }
    function _epoch(uint32 id) internal view returns (Epoch storage e) {
        e = epochs[id]; if (!e.exists) revert InvalidInput();
    }
    function _case(uint256 id) internal view returns (Case storage c) {
        if (id >= caseCount) revert InvalidInput(); c = cases[id];
    }
    function _envelope(bytes memory data) internal view returns (uint32 id) {
        if (data.length > MAX_EXTRA_BYTES + 160) revert InvalidInput();
        uint8 version; bytes memory realData;
        (version, id, realData) = abi.decode(data, (uint8, uint32, bytes));
        if (version != 1 || keccak256(realData) != keccak256(_epoch(id).realExtraData)) revert InvalidInput();
        if (keccak256(data) != keccak256(abi.encode(version, id, realData))) revert InvalidInput();
    }

    /// URI arguments make the spec's per-epoch MetaEvidence emission explicit.
    function registerEpoch(bytes calldata realData, uint256 marginBps, uint256 premiumBps, uint256 maxCost,
        string calldata registrationMetaEvidence, string calldata removalMetaEvidence)
        external onlyGovernor nonReentrant returns (uint32 id)
    {
        if (retired || marginBps > MAX_MARGIN_BPS || premiumBps > MAX_PREMIUM_BPS
            || realData.length > MAX_EXTRA_BYTES) revert InvalidInput();
        uint256 cost = K.arbitrationCost(realData);
        uint256 quote = FullMath.mulDiv(cost, 10_000 + marginBps, 10_000);
        if (quote == 0 || maxCost < quote) revert InvalidInput();
        id = ++epochCount;
        uint256 premium = FullMath.mulDiv(quote, premiumBps, 10_000);
        epochs[id] = Epoch(true, quote, premium, maxCost, realData);
        emit EpochRegistered(id, quote, premium, maxCost, realData);
        emit MetaEvidence(uint256(id) * 2, registrationMetaEvidence);
        emit MetaEvidence(uint256(id) * 2 + 1, removalMetaEvidence);
    }

    function arbitrationCost(bytes calldata data) external view override returns (uint256) {
        return epochs[_envelope(data)].quote;
    }
    function createDispute(uint256 choices, bytes calldata data) external payable override nonReentrant returns (uint256 id) {
        if (msg.sender != HOST) revert Unauthorized();
        uint32 eid = _envelope(data); Epoch storage e = epochs[eid];
        if (msg.value != e.quote) revert InvalidInput();
        id = caseCount++; Case storage c = cases[id];
        c.epochId = eid; c.choices = choices; c.fee = msg.value; c.createdAt = block.timestamp;
        c.deadline = block.timestamp + WINDOW; c.fundingEnd = c.deadline + FUNDING_PERIOD;
        c.envelopeHash = keccak256(data);
        uint256 need = e.maxCost - e.quote;
        c.earmark = _min(need, free()); c.insuredAtCreation = c.earmark == need;
        totalEarmarked += c.earmark; openFees += msg.value; openCases++;
        emit CaseOpened(id, eid, msg.value, c.deadline, c.fundingEnd, c.earmark);
        if (!c.insuredAtCreation) emit UnderInsured(id, need - c.earmark);
    }
    function bind(uint256 id) external nonReentrant { _bind(id); }
    function _bind(uint256 id) internal returns (Case storage c) {
        c = _case(id);
        if (c.state == State.Unbound) {
            c.binding = HostProfiles.read(HOST, address(this), id, PROFILE, c.envelopeHash);
            c.state = c.binding.removal ? State.Forwardable : State.Open;
            emit CaseBound(id, c.binding.removal, c.binding.requester, c.binding.challenger);
        }
    }
    function concede(uint256 id, uint256 /*maxShare*/) external nonReentrant {
        Case storage c = _bind(id);
        if (c.state != State.Open) revert InvalidState();
        if (msg.sender != c.binding.requester) revert Unauthorized();
        uint256 premium = epochs[c.epochId].premium;
        _end(c, State.Conceded, 0);
        c.ruling = 2; c.rulingDelivered = true;
        surplus += premium; _credit(c.binding.requester, c.fee - premium);
        emit Settled(id, 0, c.fee - premium, 0, premium);
        IArbitrable(HOST).rule(id, 2);
    }
    function forward(uint256 id) external nonReentrant returns (bool) {
        Case storage c = _bind(id);
        if (c.state != State.Forwardable) revert InvalidState();
        return _requireAttempt(id, c);
    }
    function escalate(uint256 id) external nonReentrant returns (bool) {
        Case storage c = _bind(id);
        if (c.state != State.Open) revert InvalidState();
        if (block.timestamp < c.deadline && msg.sender != c.binding.requester) revert Unauthorized();
        return _requireAttempt(id, c);
    }
    function _requireAttempt(uint256 id, Case storage c) internal returns (bool) {
        Attempt result = _attempt(id, c);
        if (result == Attempt.Uncovered) revert NotCovered();
        return result == Attempt.Success;
    }
    function fund(uint256 id) external payable nonReentrant {
        Case storage c = _bind(id);
        if (!_open(c) || block.timestamp >= c.fundingEnd) revert InvalidState();
        contribution[id][msg.sender] += msg.value; c.totalFunding += msg.value; refundLiability += msg.value;
        emit Funded(id, msg.sender, msg.value);
    }
    function lapse(uint256 id) external nonReentrant {
        Case storage c = _bind(id);
        if (!_open(c) || block.timestamp < c.fundingEnd) revert InvalidState();
        (bool ok, uint256 cost) = _quote(c);
        if (!ok) revert QuoteUnavailable();
        if (_covered(c, cost)) revert InvalidState();
        _lapse(id, c);
    }
    function forwardOrLapse(uint256 id) external nonReentrant returns (bool forwarded) {
        Case storage c = _bind(id);
        if (!_open(c) || block.timestamp < c.fundingEnd || c.firstForwardFailure == 0
            || block.timestamp < c.firstForwardFailure + RESOLVER_GRACE) revert InvalidState();
        Attempt result = _attempt(id, c); // Fresh funded attempt always has priority.
        if (result == Attempt.Uncovered) revert NotCovered();
        if (result == Attempt.Success) return true;
        _lapse(id, c);
    }
    function _lapse(uint256 id, Case storage c) internal {
        _end(c, State.Lapsed, 0); _credit(c.binding.challenger, c.fee);
        c.ruling = 0; c.rulingDelivered = true;
        emit Lapsed(id); IArbitrable(HOST).rule(id, 0);
    }
    function _open(Case storage c) internal view returns (bool) {
        return c.state == State.Open || c.state == State.Forwardable;
    }
    function _covered(Case storage c, uint256 cost) internal view returns (bool) {
        // Subtraction avoids overflow even for adversarial quotes near uint256 max.
        if (cost <= c.fee) return true;
        uint256 gap = cost - c.fee;
        uint256 available = c.earmark + free();
        if (gap <= available) return true;
        return gap - available <= c.totalFunding;
    }
    function covered(uint256 id) external view returns (bool) {
        Case storage c = _case(id);
        if (c.state != State.Unbound && !_open(c)) return false;
        (bool ok, uint256 cost) = _quote(c);
        return ok && _covered(c, cost);
    }
    function _quote(Case storage c) internal view returns (bool ok, uint256 cost) {
        bytes memory payload = abi.encodeCall(IArbitrator.arbitrationCost, (epochs[c.epochId].realExtraData));
        address target = address(K); uint256 budget = QUOTE_GAS; uint256 size;
        if (gasleft() < budget + budget / 63 + POST_CALL_GAS) revert InsufficientCallGas();
        assembly ("memory-safe") {
            let ptr := mload(0x40)
            ok := staticcall(budget, target, add(payload, 32), mload(payload), ptr, 32)
            size := returndatasize()
            cost := mload(ptr)
        }
        if (ok && size != 32) revert MalformedResolverReturn();
    }
    function _attempt(uint256 id, Case storage c) internal returns (Attempt) {
        (bool quoted, uint256 cost) = _quote(c);
        if (!quoted) { _failure(id, c, 1); return Attempt.Failed; }
        if (!_covered(c, cost)) return Attempt.Uncovered;
        bytes memory payload = abi.encodeCall(IArbitrator.createDispute, (c.choices, epochs[c.epochId].realExtraData));
        address target = address(K); uint256 budget = CREATE_GAS;
        if (gasleft() < budget + budget / 63 + POST_CALL_GAS) revert InsufficientCallGas();
        bool ok; uint256 remoteID; uint256 size;
        State previous = c.state; c.state = State.Forwarded;
        assembly ("memory-safe") {
            let ptr := mload(0x40)
            ok := call(budget, target, cost, add(payload, 32), mload(payload), ptr, 32)
            size := returndatasize()
            remoteID := mload(ptr)
        }
        if (!ok) { c.state = previous; _failure(id, c, 2); return Attempt.Failed; }
        // Never lapse after successful acceptance with a malformed return or reused ID.
        // Revert the whole transaction, including the resolver call and payment.
        if (size != 32 || remoteToLocalPlusOne[remoteID] != 0) revert MalformedResolverReturn();
        uint256 reserveDraw;
        uint256 fundingUsed;
        if (cost > c.fee) {
            reserveDraw = _min(cost - c.fee, c.earmark + free());
            fundingUsed = cost - c.fee - reserveDraw;
            uint256 loss = _min(surplus, reserveDraw);
            surplus -= loss; principal -= reserveDraw - loss;
        } else { surplus += c.fee - cost; }
        _end(c, State.Forwarded, fundingUsed);
        c.kDisputeID = remoteID; remoteToLocalPlusOne[remoteID] = id + 1;
        emit Escalated(id, remoteID, cost, fundingUsed, msg.sender);
        emit Dispute(K, remoteID, uint256(c.epochId) * 2 + (c.binding.removal ? 1 : 0), id);
        return Attempt.Success;
    }
    function _failure(uint256 id, Case storage c, uint8 reason) internal {
        if (c.firstForwardFailure == 0) c.firstForwardFailure = block.timestamp;
        emit ForwardFailed(id, reason);
    }
    function _end(Case storage c, State terminal, uint256 fundingUsed) internal {
        totalEarmarked -= c.earmark; c.earmark = 0;
        openFees -= c.fee; openCases--;
        c.state = terminal; c.fundingUsed = fundingUsed;
        c.refundableAmount = c.totalFunding - fundingUsed;
        refundLiability -= fundingUsed;
    }
    function fundingClaimable(uint256 id, address who) public view returns (uint256) {
        Case storage c = _case(id);
        if (c.state < State.Forwarded || fundingClaimed[id][who] || c.totalFunding == 0) return 0;
        return FullMath.mulDiv(contribution[id][who], c.refundableAmount, c.totalFunding);
    }
    function claimFunding(uint256 id) external nonReentrant {
        Case storage c = _case(id);
        if (c.state < State.Forwarded || contribution[id][msg.sender] == 0 || fundingClaimed[id][msg.sender]) revert InvalidState();
        uint256 amount = fundingClaimable(id, msg.sender);
        fundingClaimed[id][msg.sender] = true; c.claimedFunding += amount;
        refundLiability -= amount; _credit(msg.sender, amount);
        emit FundingClaimed(id, msg.sender, amount);
    }
    function _credit(address to, uint256 amount) internal { claimable[to] += amount; totalClaimable += amount; }
    function claim(address payable to) external nonReentrant {
        uint256 amount = claimable[msg.sender];
        if (amount == 0 || to == address(0) || to == address(this)) revert InvalidInput();
        claimable[msg.sender] = 0; totalClaimable -= amount;
        (bool ok,) = to.call{value: amount}(""); if (!ok) revert TransferFailed();
        emit Claimed(msg.sender, to, amount);
    }
    function rule(uint256 remoteID, uint256 ruling) external override nonReentrant {
        if (msg.sender != address(K)) revert Unauthorized();
        uint256 mapped = remoteToLocalPlusOne[remoteID];
        if (mapped == 0) revert InvalidInput();
        uint256 id = mapped - 1; Case storage c = cases[id];
        if (c.state != State.Forwarded || c.rulingDelivered || ruling > c.choices) revert InvalidState();
        c.rulingDelivered = true; c.ruling = ruling;
        emit Ruling(K, id, ruling); emit RulingRelayed(id, remoteID, ruling);
        IArbitrable(HOST).rule(id, ruling);
    }
    function _forwarded(uint256 id) internal view returns (Case storage c) {
        c = _case(id); if (c.state != State.Forwarded || c.rulingDelivered) revert InvalidState();
    }
    function appeal(uint256 id, bytes calldata data) external payable override nonReentrant {
        if (msg.sender != HOST) revert Unauthorized();
        Case storage c = _forwarded(id);
        if (_envelope(data) != c.epochId) revert InvalidInput();
        (uint256 start, uint256 end) = K.appealPeriod(c.kDisputeID);
        if (block.timestamp < start || block.timestamp >= end) revert InvalidState();
        K.appeal{value: msg.value}(c.kDisputeID, epochs[c.epochId].realExtraData);
    }
    function appealCost(uint256 id, bytes calldata data) external view override returns (uint256) {
        Case storage c = _forwarded(id);
        if (_envelope(data) != c.epochId) revert InvalidInput();
        return K.appealCost(c.kDisputeID, epochs[c.epochId].realExtraData);
    }
    function appealPeriod(uint256 id) external view override returns (uint256, uint256) {
        return K.appealPeriod(_forwarded(id).kDisputeID);
    }
    function disputeStatus(uint256 id) external view override returns (DisputeStatus) {
        Case storage c = _case(id);
        if (c.rulingDelivered || c.state == State.Conceded || c.state == State.Lapsed) return DisputeStatus.Solved;
        if (c.state == State.Forwarded) return K.disputeStatus(c.kDisputeID);
        return DisputeStatus.Waiting;
    }
    function currentRuling(uint256 id) external view override returns (uint256) {
        Case storage c = _case(id);
        if (c.rulingDelivered) return c.ruling;
        if (c.state == State.Forwarded) return K.currentRuling(c.kDisputeID);
        return 0;
    }
    function fundReserve() external payable nonReentrant {
        bool isPrincipal = msg.sender == GOVERNOR;
        if (isPrincipal) principal += msg.value; else surplus += msg.value;
        emit ReserveFunded(msg.sender, msg.value, isPrincipal);
    }
    /// Forced/unaccounted ETH is not a party credit; anyone may donate it to surplus.
    function syncSurplus() external nonReentrant {
        uint256 amount = unaccountedBalance(); surplus += amount; emit UnaccountedDonated(amount);
    }
    function deactivate() external onlyGovernor nonReentrant {
        if (retired) revert InvalidState();
        retired = true; retiredAt = block.timestamp;
        retirementUnlockAt = block.timestamp + IRegistry(HOST).challengePeriodDuration() + RETIREMENT_MARGIN;
        emit Deactivated(block.timestamp);
    }
    function announceWithdrawal(uint256 amount, address payable to) external onlyGovernor nonReentrant {
        if (!retired || amount > principal || to == address(0) || to == address(this)) revert InvalidInput();
        pendingWithdrawal = Withdrawal(amount, to, block.timestamp, true);
        emit WithdrawalAnnounced(amount, to, block.timestamp);
    }
    function cancelWithdrawal() external onlyGovernor nonReentrant {
        if (!pendingWithdrawal.pending) revert InvalidState(); delete pendingWithdrawal; emit WithdrawalCancelled();
    }
    function _retirementReady() internal view {
        // Latent requests are NOT knowable here. The spec's governor procedure remains required.
        if (!retired || block.timestamp < retirementUnlockAt || openCases != 0) revert InvalidState();
    }
    function executeWithdrawal() external onlyGovernor nonReentrant {
        _retirementReady(); Withdrawal memory w = pendingWithdrawal;
        if (!w.pending || block.timestamp < w.announcedAt + RESERVE_TIMELOCK
            || w.amount > principal || w.amount > free()) revert InvalidState();
        delete pendingWithdrawal; principal -= w.amount;
        (bool ok,) = w.to.call{value: w.amount}(""); if (!ok) revert TransferFailed();
        emit PrincipalWithdrawn(w.to, w.amount);
    }
    function migrateSurplus(address successor) external onlyGovernor nonReentrant {
        _retirementReady();
        if (successor == address(this) || !IWrapperFactory(FACTORY).isWrapper(successor)
            || IMigrationTarget(successor).HOST() != HOST || IMigrationTarget(successor).FACTORY() != FACTORY) revert InvalidInput();
        uint256 amount = surplus; surplus = 0;
        IMigrationTarget(successor).receiveSurplus{value: amount}(); emit SurplusMigrated(successor, amount);
    }
    function receiveSurplus() external payable nonReentrant {
        if (!IWrapperFactory(FACTORY).isWrapper(msg.sender) || IMigrationTarget(msg.sender).HOST() != HOST
            || IMigrationTarget(msg.sender).FACTORY() != FACTORY || msg.sender == address(this)) revert Unauthorized();
        surplus += msg.value; emit ReserveFunded(msg.sender, msg.value, false);
    }
    function _min(uint256 a, uint256 b) private pure returns (uint256) { return a < b ? a : b; }
}
