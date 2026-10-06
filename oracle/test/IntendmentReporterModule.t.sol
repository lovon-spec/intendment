// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IntendmentReporterModule as M} from "../src/IntendmentReporterModule.sol";
import {Vm, MockToken, MockStore, MockFinder, MockOO, MockAggregator, MockWhitelist} from "./Mocks.sol";

contract IntendmentReporterModuleTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address constant ALICE = address(0xA11CE);
    address constant BOB = address(0xB0B);
    address constant CAROL = address(0xCA01);
    address constant DAVE = address(0xDA7E);
    address constant VENUE = address(0x7E0E);

    uint128 constant B = 500e6; // bond, the tier most disputes carry
    uint128 constant F = 250e6; // UMA's final fee for USDC.e
    uint128 constant REWARD = 3_500_000;
    uint32 constant L = 900; // liveness
    uint32 constant W_NB = 4 hours;
    uint32 constant W_B = 1 hours;
    uint32 constant GRACE = 1 days;
    bytes32 constant ID = "YES_OR_NO_QUERY";

    MockToken token;
    MockStore store;
    MockFinder finder;
    MockOO oo;
    MockAggregator agg;
    M module;
    uint256 serial;

    // ------------------------------------------------------------------ setup and helpers

    function setUp() public {
        vm.warp(1_790_000_000);
        token = new MockToken();
        store = new MockStore();
        store.setFee(F);
        finder = new MockFinder(address(store));
        oo = new MockOO(token, address(finder), address(store));
        agg = new MockAggregator();
        module = _deploy(5000, address(0), false);
        _fund(ALICE);
        _fund(BOB);
        _fund(CAROL);
        _fund(DAVE);
        _fund(VENUE);
        vm.prank(VENUE);
        module.fundRewards(100 * uint256(REWARD));
    }

    function _deploy(uint16 bps, address wl, bool coWl) internal returns (M m) {
        m = new M(
            M.Config({
                aggregator: address(agg),
                oracle: address(oo),
                currency: address(token),
                venue: VENUE,
                proposerWhitelist: wl,
                coBackersWhitelisted: coWl,
                chargeBps: bps,
                windowNonBlocking: W_NB,
                windowBlocking: W_B,
                grace: GRACE,
                minLiveness: 300,
                maxSettledBlocking: 1
            })
        );
    }

    function _fund(address who) internal {
        token.mint(who, 1e15);
        vm.prank(who);
        token.approve(address(module), type(uint256).max);
    }

    function _register(uint8 marketType) internal returns (bytes32 rid) {
        bytes29 ev = bytes29(keccak256(abi.encode("event", ++serial)));
        rid = bytes32(ev);
        if (marketType == 1) rid = bytes32(uint256(rid) | (uint256(1) << 8)); // condition index 1
        M.Registration[] memory regs = new M.Registration[](1);
        regs[0] = M.Registration({requestId: rid, bond: B, liveness: L, reward: REWARD, rules: bytes("q: Will it happen?")});
        agg.initializeRequest(ev, marketType, address(module), abi.encode(regs));
    }

    function _propose(address who, bytes32 rid, int256 price) internal returns (uint64) {
        vm.prank(who);
        return module.propose(rid, price);
    }

    function _dispute(address who, uint64 pid) internal returns (uint64) {
        vm.prank(who);
        return module.dispute(pid);
    }

    function _status(bytes32 rid) internal view returns (M.RequestStatus st, uint64 active, uint64 held, uint8 settledBlocking) {
        (st,,,, settledBlocking,, active, held,,,,) = module.requests(rid);
    }

    function _caseStatus(uint64 cid) internal view returns (M.CaseStatus st) {
        (,,,,, st,) = module.cases(cid);
    }

    function _proposer(uint64 pid) internal view returns (address p) {
        (, p,,,,,,,,) = module.proposals(pid);
    }

    function _proposedAt(uint64 pid) internal view returns (uint64 t) {
        (,,,, t,,,,,) = module.proposals(pid);
    }

    /// Reach a blocking request: a first dispute on a proposal resets the market.
    function _toBlocking(bytes32 rid) internal returns (uint64 c1) {
        uint64 p1 = _propose(ALICE, rid, module.YES());
        c1 = _dispute(BOB, p1);
        vm.prank(ALICE);
        module.concede(c1);
    }

    function _buckets() internal view {
        eq(
            token.balanceOf(address(module)),
            module.stakesHeld() + module.rewardsEscrowed() + module.rewardBudget() + module.creditsOwed(),
            "balance equals the four buckets"
        );
    }

    function eq(uint256 a, uint256 b, string memory what) internal pure {
        if (a != b) revert(string.concat("not equal: ", what));
    }

    function eqI(int256 a, int256 b, string memory what) internal pure {
        if (a != b) revert(string.concat("not equal: ", what));
    }

    function ok(bool c, string memory what) internal pure {
        if (!c) revert(string.concat("false: ", what));
    }

    // ------------------------------------------------------------------ the happy path

    function test_undisputed_proposal_resolves_and_reports() public {
        bytes32 rid = _register(0);
        uint64 pid = _propose(ALICE, rid, module.YES());
        eq(module.stakesHeld(), B + F, "stake held");
        vm.warp(block.timestamp + L);
        module.settleProposal(pid);
        eq(agg.reported(rid), 1_000_000, "YES reported");
        eq(module.credits(ALICE), B + F + REWARD, "stake and reward credited");
        uint256 before = token.balanceOf(ALICE);
        vm.prank(ALICE);
        module.claim(ALICE);
        eq(token.balanceOf(ALICE) - before, B + F + REWARD, "claimed");
        _buckets();
    }

    // ------------------------------------------------------------------ non-blocking cases

    function test_first_dispute_resets_market_and_concession_pays_uma_nothing() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        uint64 c1 = _dispute(BOB, p1);
        (, uint64 active, uint64 held,) = _status(rid);
        eq(active, 0, "market reset at once");
        eq(held, 0, "not held");
        uint64 p2 = _propose(DAVE, rid, module.NO()); // the market moves on while the case runs
        vm.prank(ALICE);
        module.concede(c1);
        eq(module.credits(ALICE), F, "conceder keeps its final fee");
        eq(module.credits(BOB), B + F + B / 2, "disputer: stake back plus court win");
        eq(module.credits(VENUE), B / 2, "venue receives the burn");
        eq(oo.storeReceived(), 0, "UMA paid nothing");
        vm.warp(block.timestamp + L);
        module.settleProposal(p2);
        eq(agg.reported(rid), 0, "NO reported");
        _buckets();
    }

    function test_withdrawal_on_non_blocking_case() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        uint64 c1 = _dispute(BOB, p1);
        vm.prank(BOB);
        module.withdraw(c1);
        eq(module.credits(BOB), F, "withdrawing disputer keeps its final fee");
        eq(module.credits(ALICE), B + F + B / 2, "proposer: stake back plus court win");
        eq(module.credits(VENUE), B / 2, "venue receives the burn");
        ok(_caseStatus(c1) == M.CaseStatus.Withdrawn, "withdrawn");
        _buckets();
    }

    function test_withdrawal_is_closed_on_blocking_case() public {
        bytes32 rid = _register(0);
        _toBlocking(rid);
        uint64 p2 = _propose(ALICE, rid, module.YES());
        uint64 c2 = _dispute(BOB, p2);
        vm.expectRevert(M.BlockingCase.selector);
        vm.prank(BOB);
        module.withdraw(c2);
    }

    // ------------------------------------------------------------------ blocking cases

    function test_blocking_case_holds_market_and_concession_reopens_it() public {
        bytes32 rid = _register(0);
        _toBlocking(rid);
        uint64 p2 = _propose(ALICE, rid, module.YES());
        uint64 c2 = _dispute(CAROL, p2);
        (,, uint64 held,) = _status(rid);
        eq(held, c2, "market held by the case");
        int256 no = module.NO();
        vm.expectRevert(M.MarketBusy.selector);
        vm.prank(DAVE);
        module.propose(rid, no);
        vm.prank(ALICE);
        module.concede(c2);
        (,, uint64 held2, uint8 settled) = _status(rid);
        eq(held2, 0, "market reopened");
        eq(settled, 1, "one settled blocking case used");
        eq(oo.storeReceived(), 0, "UMA paid nothing");
        uint64 p3 = _propose(DAVE, rid, module.NO());
        vm.warp(block.timestamp + L);
        module.settleProposal(p3);
        eq(agg.reported(rid), 0, "resolved hours after the dispute, without a vote");
        _buckets();
    }

    function test_after_M_the_next_dispute_goes_to_uma_at_once() public {
        bytes32 rid = _register(0);
        _toBlocking(rid);
        uint64 p2 = _propose(ALICE, rid, module.YES());
        uint64 c2 = _dispute(BOB, p2);
        vm.prank(ALICE);
        module.concede(c2); // M = 1 spent
        uint64 p3 = _propose(ALICE, rid, module.YES());
        uint64 c3 = _dispute(BOB, p3);
        ok(_caseStatus(c3) == M.CaseStatus.Forwarded, "forwarded in the dispute transaction");
        eq(oo.storeReceived(), F + B / 2, "UMA paid for the case it decides");
        uint256 bobBefore = token.balanceOf(BOB);
        oo.pushPrice(address(module), ID, _proposedAt(p3), module.umaAncillary(c3), module.NO());
        module.resolveCase(c3);
        eq(token.balanceOf(BOB) - bobBefore, B + (B - B / 2) + F, "UMA paid the winning disputer directly");
        eq(agg.reported(rid), 0, "UMA's answer reported");
        eq(module.credits(VENUE), B / 2 + B / 2 + REWARD, "two burns and the unspent reward to the venue");
        _buckets();
    }

    // ------------------------------------------------------------------ co-backing

    function test_cobacker_carries_the_answer_on() public {
        bytes32 rid = _register(0);
        _toBlocking(rid);
        uint64 p2 = _propose(ALICE, rid, module.YES());
        vm.prank(CAROL);
        module.coBack(p2);
        uint64 c2 = _dispute(BOB, p2);
        (,,, uint64 deadline,,,) = module.cases(c2);
        uint256 venueBefore = module.credits(VENUE);
        uint256 aliceBefore = module.credits(ALICE);
        vm.prank(ALICE);
        module.concede(c2);
        eq(uint160(_proposer(p2)), uint160(CAROL), "co-backer is the proposer of record");
        ok(_caseStatus(c2) == M.CaseStatus.Open, "case runs on");
        (,,, uint64 deadline2,,,) = module.cases(c2);
        eq(deadline2, deadline, "same deadline");
        (,, uint64 held, uint8 settled) = _status(rid);
        eq(held, c2, "market still held, not reopened");
        eq(settled, 0, "M not consumed");
        eq(module.credits(ALICE) - aliceBefore, B + F - B / 2, "leaving proposer pays the charge only");
        eq(module.credits(VENUE) - venueBefore, B / 2, "charge to the venue");
        vm.prank(CAROL);
        module.forward(c2); // the proposer of record may forward at any time
        uint256 carolBefore = token.balanceOf(CAROL);
        oo.pushPrice(address(module), ID, _proposedAt(p2), module.umaAncillary(c2), module.YES());
        module.resolveCase(c2);
        eq(token.balanceOf(CAROL) - carolBefore, B + (B - B / 2) + F, "UMA paid the co-backer that defended YES");
        eq(agg.reported(rid), 1_000_000, "YES stands");
        _buckets();
    }

    function test_last_stake_conceding_ends_the_case() public {
        bytes32 rid = _register(0);
        _toBlocking(rid);
        uint64 p2 = _propose(ALICE, rid, module.YES());
        vm.prank(CAROL);
        module.coBack(p2);
        uint64 c2 = _dispute(BOB, p2);
        vm.prank(ALICE);
        module.concede(c2);
        uint256 bobBefore = module.credits(BOB);
        vm.prank(CAROL);
        module.concede(c2);
        ok(_caseStatus(c2) == M.CaseStatus.Conceded, "conceded");
        eq(module.credits(CAROL), F, "last conceder keeps its final fee");
        eq(module.credits(BOB) - bobBefore, B + F + B / 2, "disputer: stake back plus court win");
        (,, uint64 held, uint8 settled) = _status(rid);
        eq(held, 0, "market reopened");
        eq(settled, 1, "M consumed");
        _buckets();
    }

    function test_other_cobackers_are_released_when_the_proposal_closes() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        vm.prank(CAROL);
        uint32 i0 = module.coBack(p1);
        vm.prank(DAVE);
        uint32 i1 = module.coBack(p1);
        vm.expectRevert(M.NothingToRelease.selector);
        module.releaseCoBacker(p1, i0);
        vm.warp(block.timestamp + L);
        module.settleProposal(p1);
        module.releaseCoBacker(p1, i0);
        module.releaseCoBacker(p1, i1);
        eq(module.credits(CAROL), B + F, "co-backer stake returned");
        eq(module.credits(DAVE), B + F, "co-backer stake returned");
        eq(module.credits(ALICE), B + F + REWARD, "proposer of record paid");
        _buckets();
    }

    // ------------------------------------------------------------------ retraction

    function test_retraction_costs_the_charge_and_reopens() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        vm.prank(ALICE);
        module.retract(p1);
        eq(module.credits(ALICE), B + F - B / 2, "retraction costs the charge");
        eq(module.credits(VENUE), B / 2, "charge to the venue");
        (, uint64 active,,) = _status(rid);
        eq(active, 0, "request reopened");
        _buckets();
    }

    function test_retraction_with_cobacker_keeps_the_answer_and_liveness() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        vm.prank(CAROL);
        module.coBack(p1);
        vm.warp(block.timestamp + L / 2);
        vm.prank(ALICE);
        module.retract(p1);
        eq(uint160(_proposer(p1)), uint160(CAROL), "co-backer carries the answer");
        vm.warp(block.timestamp + L / 2);
        module.settleProposal(p1); // the original liveness, not a fresh one
        eq(module.credits(CAROL), B + F + REWARD, "co-backer paid as proposer of record");
        eq(agg.reported(rid), 1_000_000, "YES reported");
        _buckets();
    }

    // ------------------------------------------------------------------ UMA answers and failures

    function _forwardedBlockingCase(bytes32 rid) internal returns (uint64 p3, uint64 c3) {
        _toBlocking(rid);
        uint64 p2 = _propose(ALICE, rid, module.YES());
        uint64 c2 = _dispute(BOB, p2);
        vm.prank(ALICE);
        module.concede(c2);
        p3 = _propose(ALICE, rid, module.YES());
        c3 = _dispute(BOB, p3);
    }

    function test_too_early_reopens_the_market() public {
        bytes32 rid = _register(0);
        (uint64 p3, uint64 c3) = _forwardedBlockingCase(rid);
        oo.pushPrice(address(module), ID, _proposedAt(p3), module.umaAncillary(c3), module.TOO_EARLY());
        module.resolveCase(c3);
        (M.RequestStatus st, uint64 active, uint64 held,) = _status(rid);
        ok(st == M.RequestStatus.Open, "still open");
        eq(active + held, 0, "reopened");
        eq(module.rewardsEscrowed(), REWARD, "reward kept for the next proposal");
        _propose(DAVE, rid, module.NO());
        _buckets();
    }

    function test_split_on_neg_risk_is_a_visible_failure() public {
        bytes32 rid = _register(1);
        int256 split = module.SPLIT();
        vm.expectRevert(M.BadPrice.selector);
        vm.prank(ALICE);
        module.propose(rid, split);
        (uint64 p3, uint64 c3) = _forwardedBlockingCase(rid);
        oo.pushPrice(address(module), ID, _proposedAt(p3), module.umaAncillary(c3), module.SPLIT());
        module.resolveCase(c3);
        (M.RequestStatus st,,,) = _status(rid);
        ok(st == M.RequestStatus.Failed, "failed, no answer produced");
        ok(!agg.voted(rid), "nothing reported");
        eq(module.rewardsEscrowed(), 0, "reward released");
        _buckets();
    }

    function test_disputer_cannot_forward_before_the_deadline() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        uint64 c1 = _dispute(BOB, p1);
        vm.expectRevert(M.TooEarlyToForward.selector);
        vm.prank(BOB);
        module.forward(c1);
        vm.prank(ALICE);
        module.forward(c1); // the proposer may reject the offer at once
        ok(_caseStatus(c1) == M.CaseStatus.Forwarded, "forwarded");
        _buckets();
    }

    function test_anyone_forwards_from_the_deadline() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        uint64 c1 = _dispute(BOB, p1);
        vm.warp(block.timestamp + W_NB);
        vm.prank(DAVE);
        module.forward(c1);
        ok(_caseStatus(c1) == M.CaseStatus.Forwarded, "forwarded");
        _buckets();
    }

    function test_final_fee_rise_is_paid_by_the_forwarder() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        uint64 c1 = _dispute(BOB, p1);
        store.setFee(F + 50e6);
        vm.warp(block.timestamp + W_NB);
        uint256 daveBefore = token.balanceOf(DAVE);
        vm.prank(DAVE);
        module.forward(c1);
        eq(daveBefore - token.balanceOf(DAVE), 100e6, "forwarder paid both stakes' rise");
        eq(oo.storeReceived(), F + 50e6 + B / 2, "UMA charged at its current fee");
        _buckets();
    }

    function test_final_fee_fall_is_credited_back() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        uint64 c1 = _dispute(BOB, p1);
        store.setFee(F - 50e6);
        vm.prank(ALICE);
        module.forward(c1);
        eq(module.credits(ALICE), 50e6, "proposer credited the fall");
        eq(module.credits(BOB), 50e6, "disputer credited the fall");
        _buckets();
    }

    function test_emergency_path_returns_stakes_when_uma_rejects() public {
        bytes32 rid = _register(0);
        _toBlocking(rid);
        uint64 p2 = _propose(ALICE, rid, module.YES());
        uint64 c2 = _dispute(BOB, p2);
        oo.setRejectAll(true);
        vm.warp(block.timestamp + W_B);
        vm.expectRevert(M.GraceNotOver.selector);
        module.abandon(c2);
        vm.warp(block.timestamp + GRACE);
        uint256 aliceBefore = module.credits(ALICE);
        uint256 bobBefore = module.credits(BOB);
        module.abandon(c2);
        eq(module.credits(ALICE) - aliceBefore, B + F, "proposer's stake returned in full");
        eq(module.credits(BOB) - bobBefore, B + F, "disputer's stake returned in full");
        (M.RequestStatus st,,,) = _status(rid);
        ok(st == M.RequestStatus.Failed, "market goes to the venue's manual resolution");
        ok(!agg.voted(rid), "no answer produced");
        _buckets();
    }

    function test_emergency_path_forwards_when_uma_accepts() public {
        bytes32 rid = _register(0);
        uint64 p1 = _propose(ALICE, rid, module.YES());
        uint64 c1 = _dispute(BOB, p1);
        vm.warp(block.timestamp + W_NB + GRACE);
        module.abandon(c1);
        ok(_caseStatus(c1) == M.CaseStatus.Forwarded, "forward first");
        _buckets();
    }

    // ------------------------------------------------------------------ reporting and access

    function test_report_failure_is_retried_by_relay() public {
        bytes32 rid = _register(0);
        uint64 pid = _propose(ALICE, rid, module.NO());
        agg.setPaused(true);
        vm.warp(block.timestamp + L);
        module.settleProposal(pid);
        ok(!agg.voted(rid), "not delivered while paused");
        agg.setPaused(false);
        module.relay(rid);
        ok(agg.voted(rid), "delivered on relay");
        eq(agg.reported(rid), 0, "NO");
    }

    function test_whitelists() public {
        MockWhitelist wl = new MockWhitelist();
        module = _deploy(5000, address(wl), true);
        _fund(ALICE);
        _fund(CAROL);
        _fund(VENUE);
        vm.prank(VENUE);
        module.fundRewards(uint256(REWARD));
        bytes32 rid = _register(0);
        int256 yes = module.YES();
        vm.expectRevert(M.NotWhitelisted.selector);
        vm.prank(ALICE);
        module.propose(rid, yes);
        wl.set(ALICE, true);
        uint64 pid = _propose(ALICE, rid, module.YES());
        vm.expectRevert(M.NotWhitelisted.selector);
        vm.prank(CAROL);
        module.coBack(pid);
    }

    function test_registration_checks() public {
        vm.expectRevert(M.NotAggregator.selector);
        module.initializeReporterModule(bytes29(0), "");
        bytes29 ev = bytes29(keccak256("other"));
        M.Registration[] memory regs = new M.Registration[](1);
        regs[0] = M.Registration({requestId: bytes32(bytes29(keccak256("wrong"))), bond: B, liveness: L, reward: 0, rules: "q"});
        vm.expectRevert(M.BadRegistration.selector);
        agg.initializeRequest(ev, 0, address(module), abi.encode(regs));
        regs[0].requestId = bytes32(ev);
        vm.expectRevert(M.BadRegistration.selector);
        agg.initializeRequest(ev, 2, address(module), abi.encode(regs)); // atomic neg-risk unsupported
        regs[0].reward = uint128(module.rewardBudget()) + 1;
        vm.expectRevert(M.BadRegistration.selector);
        agg.initializeRequest(ev, 0, address(module), abi.encode(regs));
    }

    // ------------------------------------------------------------------ fuzz

    function testFuzz_concession_conserves_money(uint96 bond, uint96 fee, uint16 bps) public {
        bond = uint96(1e6 + (uint256(bond) % 1e12));
        fee = uint96(uint256(fee) % 1e12);
        bps = uint16(uint256(bps) % 10_001);
        store.setFee(fee);
        module = _deploy(bps, address(0), false);
        _fund(ALICE);
        _fund(BOB);
        _fund(VENUE);
        bytes29 ev = bytes29(keccak256(abi.encode("fuzz", bond, fee, bps)));
        M.Registration[] memory regs = new M.Registration[](1);
        regs[0] = M.Registration({requestId: bytes32(ev), bond: bond, liveness: L, reward: 0, rules: "q"});
        agg.initializeRequest(ev, 0, address(module), abi.encode(regs));
        uint64 pid = _propose(ALICE, bytes32(ev), module.YES());
        uint64 cid = _dispute(BOB, pid);
        vm.prank(ALICE);
        module.concede(cid);
        uint256 charge = (uint256(bond) * bps) / 10_000;
        eq(module.credits(ALICE), fee, "conceder keeps the fee");
        eq(module.credits(BOB), uint256(bond) + fee + bond - charge, "disputer");
        eq(module.credits(VENUE), charge, "venue");
        eq(module.credits(ALICE) + module.credits(BOB) + module.credits(VENUE), 2 * (uint256(bond) + fee), "all money stays");
        _buckets();
    }
}
