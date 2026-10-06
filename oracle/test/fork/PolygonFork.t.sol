// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IntendmentReporterModule as M} from "../../src/IntendmentReporterModule.sol";

/// Fork tests against the deployed contracts on Polygon: Polymarket's Protocol V2 OracleAggregator
/// and BinaryModule, UMA's legacy OptimisticOracleV2, its OracleChildTunnel and its proposer
/// whitelist. Nothing on either side is mocked; the only privileged steps impersonate the live role
/// holders (Polymarket's operator and finalizer, the whitelist owner, the bridge's FxChild).
///
///   forge test --match-path 'test/fork/*' --fork-url https://polygon.drpc.org --fork-block-number 95030000 -vv
///
/// The mainnet half of a vote (the bridge relay and VotingV2) is not simulated: the answer arrives
/// on Polygon exactly as the bridge delivers it, as FxChild calling the child tunnel.

interface Vm {
    function prank(address) external;
    function startPrank(address) external;
    function stopPrank() external;
    function warp(uint256) external;
    function skip(bool) external;
}

interface IERC20 {
    function balanceOf(address) external view returns (uint256);
    function transfer(address, uint256) external returns (bool);
    function approve(address, uint256) external returns (bool);
}

interface IAggregator {
    struct ModuleConfig {
        address module;
        bytes initData;
    }

    struct InitParams {
        bytes29 eventId;
        uint8 marketType;
        address targetContract;
        uint16 resultLength;
        ModuleConfig[] reporterModules;
        uint16 reporterThreshold;
        ModuleConfig[] disputerModules;
        uint16 disputerThreshold;
        address arbitratorModule;
        bytes arbitratorInitData;
        uint32 livenessWindow;
        address finalizer;
    }

    function initializeRequest(InitParams calldata params) external;
    function finalize(bytes32 requestId, uint256[] calldata result) external;
    function getRequestState(bytes32 requestId)
        external
        view
        returns (uint8 status, bytes32 proposedResultHash, uint256 disputeWindowEnd, uint256 disputeCount);
}

interface IBinaryModule {
    function getConditionId(bytes calldata data) external view returns (bytes31);
    function getResult(bytes31 conditionId) external view returns (uint256[] memory);
}

interface IAddressWhitelist {
    function owner() external view returns (address);
    function addToWhitelist(address) external;
}

interface IOracleChildTunnel {
    function processMessageFromRoot(uint256 stateId, address rootMessageSender, bytes calldata data) external;
}

contract PolygonForkTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant CONSOLE = 0x000000000000000000636F6e736F6c652e6c6f67;

    uint256 constant PINNED_BLOCK = 95_030_000;

    // Polymarket Protocol V2
    IAggregator constant AGGREGATOR = IAggregator(0x0A0a0A0A8B00C51b7D810501b03F230028C04a87);
    IBinaryModule constant BINARY_MODULE = IBinaryModule(0x1000008dD9001B968442c1000017eaE6E0dA00Ba);
    address constant OPERATOR = 0xAC9930b2AE455a671b62dE86876A7e8587825294;
    address constant FINALIZER = 0x8C7c1a80d8347cc6315dBE8F1271A5ad8c5eA73C;
    address constant DEAD = 0x000000000000000000000000000000000000dEaD;

    // UMA on Polygon
    address constant OOV2 = 0xeE3Afe347D5C74317041E2618C49534dAf887c24; // legacy OptimisticOracleV2
    address constant STORE = 0xE58480CA74f1A819faFd777BEDED4E2D5629943d;
    IOracleChildTunnel constant CHILD_TUNNEL = IOracleChildTunnel(0xac60353a54873c446101216829a6A98cDbbC3f3D);
    address constant FX_CHILD = 0x8397259c983751DAf40400790063935a11afa28a;
    address constant ROOT_TUNNEL = 0x9B40E25dDd4518F36c50ce8AEf53Ee527419D55d;
    IAddressWhitelist constant PROPOSER_WHITELIST = IAddressWhitelist(0x9F35885CE8f67a942D7B2f4Fbf937987DA08c463);
    IERC20 constant USDCE = IERC20(0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174);
    address constant USDCE_HOLDER = 0x2C0367a9DB231dDeBd88a94b4f6461a6e47C58B1; // test funds on the fork only

    address constant ALICE = address(0xA11CE); // whitelisted proposer
    address constant DAVE = address(0xDA7E); // whitelisted proposer
    address constant BOB = address(0xB0B); // disputer
    address constant CAROL = address(0xCA01); // disputer
    address constant VENUE = address(0x7E0E); // stands in for Polymarket's reward vault

    uint128 constant B = 500e6;
    uint128 constant REWARD = 3_500_000;
    uint32 constant LIVENESS = 900;
    uint32 constant AGGREGATOR_LIVENESS = 300;
    bytes32 constant ID = "YES_OR_NO_QUERY";
    bytes constant RULES =
        "q: title: Will the Intendment fork test resolve NO?, description: Fork test market. res_data: p1: 0, p2: 1, p3: 0.5. Where p1 corresponds to No, p2 to Yes, p3 to unknown/50-50.";

    M module;
    uint256 fee;
    uint256 serial;

    // ------------------------------------------------------------------ setup

    function setUp() public {
        if (block.chainid == 31337) {
            vm.skip(true); // no fork given: a plain `forge test` runs the unit tests only
            return;
        }
        require(block.chainid == 137, "fork Polygon: --fork-url <archive RPC>");
        require(block.number == PINNED_BLOCK, "pin the block: --fork-block-number 95030000");
        module = new M(
            M.Config({
                aggregator: address(AGGREGATOR),
                oracle: OOV2,
                currency: address(USDCE),
                venue: VENUE,
                proposerWhitelist: address(PROPOSER_WHITELIST),
                coBackersWhitelisted: false,
                chargeBps: 5000,
                windowNonBlocking: 4 hours,
                windowBlocking: 1 hours,
                grace: 1 days,
                minLiveness: 300,
                maxSettledBlocking: 1
            })
        );
        fee = module.finalFee();
        require(fee == 250e6, "UMA's final fee for USDC.e");
        // UMA's own default proposer whitelist, read in place: its owner adds the test proposers.
        address wlOwner = PROPOSER_WHITELIST.owner();
        vm.startPrank(wlOwner);
        PROPOSER_WHITELIST.addToWhitelist(ALICE);
        PROPOSER_WHITELIST.addToWhitelist(DAVE);
        vm.stopPrank();
        address[5] memory who = [ALICE, DAVE, BOB, CAROL, VENUE];
        for (uint256 i; i < who.length; ++i) {
            vm.prank(USDCE_HOLDER);
            USDCE.transfer(who[i], 10_000e6);
            vm.prank(who[i]);
            USDCE.approve(address(module), type(uint256).max);
        }
        vm.prank(VENUE);
        module.fundRewards(100 * uint256(REWARD));
    }

    // ------------------------------------------------------------------ the three cases

    /// A wrong first proposal is disputed, the market resets at once as today, and the proposer
    /// concedes: UMA receives nothing, and the correct proposal resolves the market.
    function test_fork_first_dispute_conceded_pays_uma_nothing() public {
        bytes32 rid = _newMarket("first-dispute-conceded");
        uint256 store0 = USDCE.balanceOf(STORE);
        int256 yes = module.YES();
        int256 no = module.NO();

        uint64 p1 = _propose(ALICE, rid, yes);
        uint64 c1 = _dispute(BOB, p1);
        uint64 p2 = _propose(DAVE, rid, no); // the market moved on in the dispute transaction
        vm.prank(ALICE);
        module.concede(c1);
        _eq(USDCE.balanceOf(STORE), store0, "UMA's Store received nothing");

        vm.warp(block.timestamp + LIVENESS);
        module.settleProposal(p2);
        _finalize(rid, 0);

        _claimAll();
        _eq(USDCE.balanceOf(BOB), 10_000e6 + B / 2, "disputer: court win, at once");
        _eq(USDCE.balanceOf(ALICE), 10_000e6 - B, "wrong proposer: the bond, not bond and final fee");
        _eq(USDCE.balanceOf(DAVE), 10_000e6 + REWARD, "correct proposer: the reward");
        _eq(USDCE.balanceOf(VENUE), 10_000e6 - 100 * uint256(REWARD) + B / 2, "venue: the half UMA would have burned");
        _buckets();
        _log("first dispute conceded: Store delta 0, disputer +B/2, conceder -B, venue +B/2");
    }

    /// A wrong second proposal holds the market; the proposer concedes inside the window, the market
    /// reopens, and a correct proposal resolves it without a vote.
    function test_fork_blocking_concession_reopens_market_without_a_vote() public {
        bytes32 rid = _newMarket("blocking-concession");
        uint256 store0 = USDCE.balanceOf(STORE);
        int256 yes = module.YES();
        int256 no = module.NO();

        _firstDisputeConceded(rid);
        uint64 p2 = _propose(ALICE, rid, yes);
        uint64 c2 = _dispute(CAROL, p2);
        vm.warp(block.timestamp + 10 minutes);
        vm.prank(ALICE);
        module.concede(c2);
        uint64 p3 = _propose(DAVE, rid, no);
        vm.warp(block.timestamp + LIVENESS);
        module.settleProposal(p3);
        _finalize(rid, 0);
        _eq(USDCE.balanceOf(STORE), store0, "UMA's Store received nothing for either dispute");
        _buckets();
        _log("blocking concession: market reopened 10 min after the dispute, no vote, Store delta 0");
    }

    /// Once the market's settled blocking case is spent, the next dispute goes to UMA in the dispute
    /// transaction. UMA charges its fee, the vote's answer comes back through the bridge, UMA pays
    /// the winning disputer directly, and the module reports UMA's answer.
    function test_fork_unsettled_blocking_case_goes_to_uma_and_the_vote_decides() public {
        bytes32 rid = _newMarket("forwarded-to-uma");
        int256 yes = module.YES();
        int256 no = module.NO();

        _firstDisputeConceded(rid);
        uint64 p2 = _propose(ALICE, rid, yes);
        uint64 c2 = _dispute(CAROL, p2);
        vm.prank(ALICE);
        module.concede(c2); // M = 1 settled blocking case: spent

        uint64 p3 = _propose(ALICE, rid, yes);
        uint256 store0 = USDCE.balanceOf(STORE);
        uint256 disputeBlock = block.number;
        uint64 c3 = _dispute(BOB, p3);
        (,,,,, M.CaseStatus st,) = module.cases(c3);
        require(st == M.CaseStatus.Forwarded, "forwarded in the dispute transaction");
        _eq(USDCE.balanceOf(STORE) - store0, fee + B / 2, "UMA paid for the one case it decides");

        // The vote's answer, NO, arrives through the bridge as FxChild calling the child tunnel. The
        // message is built before time moves: with via-IR a saved block number can be re-read later.
        (,,,, uint64 t,,,,,) = module.proposals(p3);
        bytes memory stamped =
            bytes.concat(module.umaAncillary(c3), ",ooRequester:", _hex(abi.encodePacked(address(module))));
        bytes memory message = abi.encode(ID, uint256(t), _compress(stamped, disputeBlock), no);
        vm.warp(block.timestamp + 3 days);
        vm.prank(FX_CHILD);
        CHILD_TUNNEL.processMessageFromRoot(1, ROOT_TUNNEL, message);

        uint256 bob0 = USDCE.balanceOf(BOB);
        module.resolveCase(c3);
        _eq(USDCE.balanceOf(BOB) - bob0, B + (B - B / 2) + fee, "UMA paid the winning disputer directly");
        _finalize(rid, 0);
        _buckets();
        _log("forwarded case: Store +fee+B/2, vote answered NO via the bridge, UMA paid the disputer");
    }

    // ------------------------------------------------------------------ helpers

    function _newMarket(string memory tag) internal returns (bytes32 rid) {
        bytes31 conditionId = BINARY_MODULE.getConditionId(abi.encode("intendment-fork", tag, ++serial));
        rid = bytes32(conditionId);
        M.Registration[] memory regs = new M.Registration[](1);
        regs[0] = M.Registration({requestId: rid, bond: B, liveness: LIVENESS, reward: REWARD, rules: RULES});
        IAggregator.ModuleConfig[] memory reporters = new IAggregator.ModuleConfig[](1);
        reporters[0] = IAggregator.ModuleConfig({module: address(module), initData: abi.encode(regs)});
        IAggregator.ModuleConfig[] memory disputers = new IAggregator.ModuleConfig[](1);
        disputers[0] = IAggregator.ModuleConfig({module: DEAD, initData: ""});
        vm.prank(OPERATOR);
        AGGREGATOR.initializeRequest(
            IAggregator.InitParams({
                eventId: bytes29(rid),
                marketType: 0,
                targetContract: address(BINARY_MODULE),
                resultLength: 1,
                reporterModules: reporters,
                reporterThreshold: 1,
                disputerModules: disputers,
                disputerThreshold: 1,
                arbitratorModule: DEAD,
                arbitratorInitData: "",
                livenessWindow: AGGREGATOR_LIVENESS,
                finalizer: FINALIZER
            })
        );
    }

    function _firstDisputeConceded(bytes32 rid) internal {
        uint64 p1 = _propose(ALICE, rid, module.YES());
        uint64 c1 = _dispute(BOB, p1);
        vm.prank(ALICE);
        module.concede(c1);
    }

    function _propose(address who, bytes32 rid, int256 price) internal returns (uint64) {
        vm.prank(who);
        return module.propose(rid, price);
    }

    function _dispute(address who, uint64 pid) internal returns (uint64) {
        vm.prank(who);
        return module.dispute(pid);
    }

    /// The aggregator's own window runs out and Polymarket's finalizer finalizes; the real
    /// BinaryModule records the result.
    function _finalize(bytes32 rid, uint256 yesNumerator) internal {
        (, bytes32 proposed, uint256 windowEnd,) = AGGREGATOR.getRequestState(rid);
        uint256[] memory result = new uint256[](1);
        result[0] = yesNumerator;
        require(proposed == keccak256(abi.encode(result)), "the module's answer is the aggregator's proposal");
        vm.warp(windowEnd);
        vm.prank(FINALIZER);
        AGGREGATOR.finalize(rid, result);
        uint256[] memory payout = BINARY_MODULE.getResult(bytes31(rid));
        _eq(payout[0], yesNumerator, "BinaryModule YES numerator");
        _eq(payout[1], 1_000_000 - yesNumerator, "BinaryModule NO numerator");
    }

    function _claimAll() internal {
        address[5] memory who = [ALICE, DAVE, BOB, CAROL, VENUE];
        for (uint256 i; i < who.length; ++i) {
            if (module.credits(who[i]) == 0) continue;
            vm.prank(who[i]);
            module.claim(who[i]);
        }
    }

    function _buckets() internal view {
        _eq(
            USDCE.balanceOf(address(module)),
            module.stakesHeld() + module.rewardsEscrowed() + module.rewardBudget() + module.creditsOwed(),
            "module balance equals its four buckets"
        );
    }

    /// The child tunnel's compressed form of a request (UMA AncillaryDataCompression).
    function _compress(bytes memory stamped, uint256 blockNumber) internal pure returns (bytes memory) {
        return bytes.concat(
            "ancillaryDataHash:",
            _hex(abi.encodePacked(keccak256(stamped))),
            ",childBlockNumber:",
            bytes(_dec(blockNumber)),
            ",childOracle:",
            _hex(abi.encodePacked(address(CHILD_TUNNEL))),
            ",childRequester:",
            _hex(abi.encodePacked(OOV2)),
            ",childChainId:137"
        );
    }

    function _hex(bytes memory data) internal pure returns (bytes memory out) {
        bytes16 digits = "0123456789abcdef";
        out = new bytes(data.length * 2);
        for (uint256 i; i < data.length; i++) {
            out[2 * i] = digits[uint8(data[i]) >> 4];
            out[2 * i + 1] = digits[uint8(data[i]) & 0x0f];
        }
    }

    function _dec(uint256 v) internal pure returns (string memory) {
        if (v == 0) return "0";
        uint256 len;
        for (uint256 j = v; j != 0; j /= 10) len++;
        bytes memory out = new bytes(len);
        // forge-lint: disable-next-line(unsafe-typecast)
        for (; v != 0; v /= 10) out[--len] = bytes1(uint8(48 + v % 10)); // one ASCII digit
        return string(out);
    }

    function _eq(uint256 a, uint256 b, string memory what) internal pure {
        if (a != b) revert(string.concat("not equal: ", what));
    }

    function _log(string memory s) internal view {
        (bool ok,) = CONSOLE.staticcall(abi.encodeWithSignature("log(string)", s));
        ok;
    }
}
