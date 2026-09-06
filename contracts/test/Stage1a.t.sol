// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {IArbitrator} from "../src/Interfaces.sol";
import {HostProfiles} from "../src/HostProfiles.sol";
import {FullMath} from "../src/FullMath.sol";
import {IntendmentArbitrator as W} from "../src/IntendmentArbitrator.sol";
import {IntendmentFactory} from "../src/IntendmentFactory.sol";
import {Vm, MockResolver, HostBase, LightHost, ClassicHost, Rejector, ClaimReentry, ForceETH} from "./Fixtures.sol";

contract Stage1aTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant ALICE = address(0xA11CE);
    address constant BOB = address(0xB0B);
    address constant CAROL = address(0xCA01);
    LightHost host;
    MockResolver k;
    IntendmentFactory factory;
    W w;
    bytes realData;
    bytes env;
    uint256 serial;
    receive() external payable {}

    function setUp() public {
        vm.warp(1000); vm.deal(address(this), 1e24); vm.deal(ALICE, 1e24); vm.deal(BOB, 1e24); vm.deal(CAROL, 1e24);
        host = new LightHost(); k = new MockResolver(); factory = new IntendmentFactory();
        w = factory.deploy(address(host), k, HostProfiles.Profile.Light, W.Config(20, 10, 5, 10, 10));
        host.point(w); realData = abi.encode(uint256(19), uint256(3));
        w.registerEpoch(realData, 0, 0, 150, "ipfs://registration", "ipfs://removal");
        env = abi.encode(uint8(1), uint32(1), realData);
    }
    function eq(uint256 a, uint256 b) internal pure { require(a == b, "not equal"); }
    function accounting() internal view { eq(address(w).balance, w.accountedBalance() + w.unaccountedBalance()); }
    function openCase(bool removal) internal returns (uint256 id, bytes32 item) {
        item = bytes32(++serial);
        vm.prank(ALICE); host.submit{value: 130}(item, removal, env);
        vm.prank(BOB); id = host.challenge{value: 100}(item);
    }
    function endFunding(uint256 id) internal { vm.warp(w.caseOf(id).fundingEnd); }
    function addReserve(uint256 amount) internal { w.fundReserve{value: amount}(); }

    function testConcessionReturnsFeeNotDeposit() public {
        addReserve(50); (uint256 id,) = openCase(false);
        eq(uint256(w.caseOf(id).state), uint256(W.State.Unbound));
        uint256 before = BOB.balance;
        vm.prank(ALICE); w.concede(id, 0);
        eq(w.claimable(ALICE), 100); eq(BOB.balance - before, 130);
        eq(w.principal(), 50); eq(w.free(), 50); eq(w.openCases(), 0);
        eq(uint256(w.disputeStatus(id)), uint256(IArbitrator.DisputeStatus.Solved));
        eq(w.currentRuling(id), 2); eq(k.nextID(), 0); accounting();
    }
    function testPremiumBecomesSurplus() public {
        uint32 eid = w.registerEpoch(realData, 0, 1000, 100, "r", "d");
        bytes memory e = abi.encode(uint8(1), eid, realData);
        vm.prank(ALICE); host.submit{value: 130}(bytes32("p"), false, e);
        vm.prank(BOB); uint256 id = host.challenge{value: 100}(bytes32("p"));
        vm.prank(ALICE); w.concede(id, 0);
        eq(w.claimable(ALICE), 90); eq(w.surplus(), 10); accounting();
    }
    function testNoReserveStillAcceptsChallenge() public {
        (uint256 id,) = openCase(false); require(!w.modeOf(id)); eq(w.caseOf(id).earmark, 0);
        vm.prank(ALICE); require(w.escalate(id)); accounting();
    }
    function testEarlyEscalationOnlyRequester() public {
        (uint256 id,) = openCase(false);
        vm.expectRevert(W.Unauthorized.selector); vm.prank(BOB); w.escalate(id);
        vm.prank(ALICE); require(w.escalate(id)); eq(w.localDispute(0), id);
        require(keccak256(k.lastData()) == keccak256(realData)); accounting();
    }
    function testDeadlineAnyoneCanEscalate() public {
        (uint256 id,) = openCase(false); vm.warp(w.caseOf(id).deadline);
        vm.prank(CAROL); require(w.escalate(id));
    }
    function testRemovalNeverConcedesAndForwardsImmediately() public {
        (uint256 id,) = openCase(true);
        vm.expectRevert(W.InvalidState.selector); vm.prank(ALICE); w.concede(id, 0);
        require(w.forward(id)); eq(k.nextID(), 1); accounting();
    }
    function testBindingValidatesPartiesIDAndEnvelope() public {
        (uint256 id,) = openCase(false);
        host.setBadProfile(true, false, false);
        vm.expectRevert(HostProfiles.InvalidBinding.selector); w.bind(id);
        host.setBadProfile(false, true, false);
        vm.expectRevert(HostProfiles.InvalidBinding.selector); w.bind(id);
        host.setBadProfile(false, false, true);
        vm.expectRevert(HostProfiles.InvalidBinding.selector); w.bind(id);
        host.setBadProfile(false, false, false); w.bind(id);
        require(w.caseOf(id).binding.requester == ALICE); require(w.caseOf(id).binding.challenger == BOB);
    }
    function testWrongCallerCannotCreate() public {
        vm.expectRevert(W.Unauthorized.selector); w.createDispute{value: 100}(2, env);
    }
    function testEnvelopeValidation() public {
        vm.expectRevert(); w.arbitrationCost(abi.encode(uint8(2), uint32(1), realData));
        vm.expectRevert(); w.arbitrationCost(abi.encode(uint8(1), uint32(2), realData));
        vm.expectRevert(); w.arbitrationCost(abi.encode(uint8(1), uint32(1), bytes("wrong")));
        vm.expectRevert(); w.arbitrationCost(bytes.concat(env, bytes("trailing")));
        eq(w.arbitrationCost(env), 100);
    }
    function testEpochDoesNotChangeExistingRequestQuote() public {
        vm.prank(ALICE); host.submit{value: 130}(bytes32("old"), false, env);
        k.setFee(120); w.registerEpoch(realData, 0, 0, 150, "newr", "newd");
        vm.prank(BOB); uint256 id = host.challenge{value: 100}(bytes32("old"));
        eq(w.caseOf(id).fee, 100); eq(w.caseOf(id).epochId, 1);
    }
    function testSurplusFirstThenPrincipalLossWaterfall() public {
        addReserve(100); vm.prank(CAROL); w.fundReserve{value: 10}();
        (uint256 id,) = openCase(false); k.setFee(130);
        vm.prank(ALICE); w.escalate(id);
        eq(w.surplus(), 0); eq(w.principal(), 80); eq(w.free(), 80); accounting();
    }
    function testFeeDecreaseAccumulatesSurplus() public {
        (uint256 id,) = openCase(false); k.setFee(70);
        vm.prank(ALICE); w.escalate(id);
        eq(w.surplus(), 30); eq(address(k).balance, 70); accounting();
    }
    function testFundingPartialRefundAndPermanentDust() public {
        (uint256 id,) = openCase(false);
        vm.prank(BOB); w.fund{value: 2}(id);
        vm.prank(CAROL); w.fund{value: 1}(id);
        k.setFee(101); vm.prank(ALICE); w.escalate(id);
        eq(w.caseOf(id).fundingUsed, 1); eq(w.refundLiability(), 2);
        vm.prank(BOB); w.claimFunding(id); vm.prank(CAROL); w.claimFunding(id);
        eq(w.claimable(BOB), 1); eq(w.claimable(CAROL), 0); eq(w.refundLiability(), 1);
        vm.expectRevert(W.InvalidState.selector); vm.prank(CAROL); w.claimFunding(id);
        w.syncSurplus(); eq(w.surplus(), 0); accounting();
    }
    function testFundingRefundsOnConcession() public {
        (uint256 id,) = openCase(false); vm.prank(CAROL); w.fund{value: 23}(id);
        vm.prank(ALICE); w.concede(id, 0); vm.prank(CAROL); w.claimFunding(id);
        eq(w.claimable(CAROL), 23); eq(w.refundLiability(), 0); accounting();
    }
    function testCannotLapseCoveredCase() public {
        (uint256 id,) = openCase(false); endFunding(id);
        vm.expectRevert(W.InvalidState.selector); w.lapse(id);
        require(w.escalate(id));
    }
    function testUnderfundedLapseAndFundingDeadline() public {
        (uint256 id,) = openCase(false); k.setFee(151); endFunding(id);
        vm.expectRevert(W.InvalidState.selector); w.fund{value: 51}(id);
        w.lapse(id); eq(w.claimable(BOB), 100); eq(w.currentRuling(id), 0); accounting();
    }
    function testLateReserveGiftRescuesUnderfundedCase() public {
        (uint256 id,) = openCase(false); k.setFee(151); endFunding(id);
        vm.prank(CAROL); w.fundReserve{value: 51}();
        vm.expectRevert(W.InvalidState.selector); w.lapse(id);
        require(w.escalate(id)); eq(w.surplus(), 0); accounting();
    }
    function testCreateFailureRetainsAccountingThenRecoveredCourtWins() public {
        addReserve(50); (uint256 id,) = openCase(false); k.setFee(130); k.setFailures(false, true);
        vm.prank(ALICE); require(!w.escalate(id));
        eq(w.openFees(), 100); eq(w.principal(), 50); eq(w.totalEarmarked(), 50); eq(address(k).balance, 0);
        eq(w.caseOf(id).firstForwardFailure, 1000); accounting();
        endFunding(id); k.setFailures(false, false);
        require(w.forwardOrLapse(id)); eq(uint256(w.caseOf(id).state), uint256(W.State.Forwarded));
        eq(w.principal(), 20); accounting();
    }
    function testPersistentQuoteFailureHasGraceAndForwardFirstFallback() public {
        (uint256 id,) = openCase(false); k.setFailures(true, false);
        vm.prank(ALICE); require(!w.escalate(id));
        vm.expectRevert(W.InvalidState.selector); w.forwardOrLapse(id);
        endFunding(id); vm.expectRevert(W.QuoteUnavailable.selector); w.lapse(id);
        require(!w.forwardOrLapse(id)); eq(uint256(w.caseOf(id).state), uint256(W.State.Lapsed)); accounting();
    }
    function testLowGasCannotLatchFailureOrAuthorizeLapse() public {
        (uint256 id,) = openCase(false); w.bind(id);
        vm.prank(ALICE);
        (bool ok,) = address(w).call{gas: 300_000}(abi.encodeCall(w.escalate, (id)));
        require(!ok); eq(w.caseOf(id).firstForwardFailure, 0); eq(k.nextID(), 0); accounting();
    }
    function testMalformedSuccessRevertsBackendAcceptance() public {
        (uint256 id,) = openCase(false); k.setMalformed(true);
        vm.expectRevert(W.MalformedResolverReturn.selector); vm.prank(ALICE); w.escalate(id);
        eq(k.nextID(), 0); eq(address(k).balance, 0); eq(w.caseOf(id).firstForwardFailure, 0); accounting();
    }
    function testDuplicateRemoteIDCannotOverwriteEarlierMapping() public {
        (uint256 first,) = openCase(false); vm.prank(ALICE); w.escalate(first);
        (uint256 second,) = openCase(false); k.setDuplicate(true);
        vm.expectRevert(W.MalformedResolverReturn.selector); vm.prank(ALICE); w.escalate(second);
        eq(w.localDispute(0), first); eq(address(k).balance, 100); accounting();
    }
    function testHostCallbackRevertRollsBackConcession() public {
        addReserve(50); (uint256 id,) = openCase(false); host.setFailRule(true);
        vm.expectRevert(); vm.prank(ALICE); w.concede(id, 0);
        eq(w.claimable(ALICE), 0); eq(w.openFees(), 100); eq(w.totalEarmarked(), 50);
        host.setFailRule(false); vm.prank(ALICE); w.concede(id, 0); accounting();
    }
    function testRulingAuthorityReplayAndCallbackRetry() public {
        (uint256 id,) = openCase(false); vm.prank(ALICE); w.escalate(id);
        vm.expectRevert(W.Unauthorized.selector); w.rule(0, 2);
        host.setFailRule(true); vm.expectRevert(); k.deliver(0, 2);
        require(!w.caseOf(id).rulingDelivered);
        host.setFailRule(false); k.deliver(0, 2);
        vm.expectRevert(W.InvalidState.selector); k.deliver(0, 2); accounting();
    }
    function testAppealOnlyThroughHostAndRealExtraData() public {
        (uint256 id, bytes32 item) = openCase(false); vm.prank(ALICE); w.escalate(id);
        k.setAppealable(0, 2); eq(w.appealCost(id, env), 300);
        vm.expectRevert(W.Unauthorized.selector); vm.prank(ALICE); w.appeal{value: 300}(id, env);
        host.appealThroughHost{value: 300}(item);
        require(keccak256(k.lastData()) == keccak256(realData)); accounting();
    }
    function testCrossCaseEpochCannotAppeal() public {
        (uint256 id,) = openCase(false); vm.prank(ALICE); w.escalate(id); k.setAppealable(0, 2);
        uint32 eid = w.registerEpoch(realData, 0, 0, 100, "r", "d");
        bytes memory other = abi.encode(uint8(1), eid, realData);
        vm.expectRevert(W.InvalidInput.selector); w.appealCost(id, other);
    }
    function testReentryDuringHostAndResolverCallsRejected() public {
        (uint256 id,) = openCase(false); host.setAttack(true);
        vm.prank(ALICE); w.concede(id, 0); require(!host.reentered());
        (uint256 next,) = openCase(false); k.setAttack(true);
        vm.prank(ALICE); w.escalate(next); require(!k.reentered()); accounting();
    }
    function testClaimReceiverFailureAndReentry() public {
        (uint256 id,) = openCase(false); vm.prank(ALICE); w.concede(id, 0);
        Rejector bad = new Rejector();
        vm.expectRevert(W.TransferFailed.selector); vm.prank(ALICE); w.claim(payable(address(bad)));
        eq(w.claimable(ALICE), 100);
        ClaimReentry receiver = new ClaimReentry(w);
        vm.prank(ALICE); w.claim(payable(address(receiver)));
        require(!receiver.reentered()); eq(address(receiver).balance, 100); eq(w.claimable(ALICE), 0); accounting();
    }
    function testWithdrawalRechecksPrincipalAndConsumesAnnouncement() public {
        addReserve(100); (uint256 id,) = openCase(false);
        w.deactivate(); w.announceWithdrawal(100, payable(address(this)));
        k.setFee(120); vm.prank(ALICE); w.escalate(id);
        vm.warp(w.retirementUnlockAt());
        vm.expectRevert(W.InvalidState.selector); w.executeWithdrawal();
        w.announceWithdrawal(80, payable(address(this))); vm.warp(block.timestamp + 10); w.executeWithdrawal();
        eq(w.principal(), 0);
        vm.expectRevert(W.InvalidState.selector); w.executeWithdrawal(); accounting();
    }
    function testRetirementKeepsOldRequestsChallengeable() public {
        vm.prank(ALICE); host.submit{value: 130}(bytes32("old"), false, env);
        w.deactivate();
        vm.expectRevert(W.InvalidInput.selector); w.registerEpoch(realData, 0, 0, 100, "r", "d");
        vm.prank(BOB); uint256 id = host.challenge{value: 100}(bytes32("old"));
        vm.prank(ALICE); w.concede(id, 0); accounting();
    }
    function testSurplusOnlyMigratesToRegisteredSameHostSuccessor() public {
        vm.prank(CAROL); w.fundReserve{value: 25}(); addReserve(40);
        W successor = factory.deploy(address(host), k, HostProfiles.Profile.Light, W.Config(20,10,5,10,10));
        w.deactivate(); vm.warp(w.retirementUnlockAt());
        vm.expectRevert(W.InvalidInput.selector); w.migrateSurplus(CAROL);
        w.migrateSurplus(address(successor)); eq(successor.surplus(), 25); eq(successor.principal(), 0);
        eq(w.principal(), 40); eq(w.surplus(), 0); accounting();
    }
    function testForcedETHNeverBecomesRefundOrPrincipal() public {
        ForceETH f = new ForceETH{value: 17}(); f.force(payable(address(w)));
        eq(w.unaccountedBalance(), 17); eq(w.free(), 0); w.syncSurplus();
        eq(w.surplus(), 17); eq(w.unaccountedBalance(), 0); accounting();
    }
    function testClassicGetterProfileAndPartyIdentity() public {
        ClassicHost classic = new ClassicHost();
        W cw = factory.deploy(address(classic), k, HostProfiles.Profile.Classic, W.Config(20,10,5,10,10));
        classic.point(cw); cw.registerEpoch(realData, 0, 0, 100, "r", "d");
        vm.prank(ALICE); classic.submit{value: 130}(bytes32("classic"), false, env);
        vm.prank(BOB); uint256 id = classic.challenge{value: 100}(bytes32("classic"));
        cw.bind(id); require(cw.caseOf(id).binding.requester == ALICE);
        vm.prank(ALICE); cw.concede(id, 0); eq(cw.claimable(ALICE), 100);
    }
    function testFuzzReserveWaterfall(uint64 p, uint64 gift, uint64 increase) public {
        uint256 capital = uint256(p) + gift;
        addReserve(p); vm.prank(CAROL); w.fundReserve{value: gift}();
        (uint256 id,) = openCase(false);
        uint256 draw = capital == 0 ? 0 : uint256(increase) % (capital + 1);
        k.setFee(100 + draw); vm.prank(ALICE); w.escalate(id);
        uint256 fromSurplus = draw < gift ? draw : gift;
        eq(w.surplus(), gift - fromSurplus); eq(w.principal(), p - (draw - fromSurplus)); accounting();
    }
    function testFuzzFundingRefund(uint64 first, uint64 second, uint64 usedSeed) public {
        if (first == 0 || second == 0) return;
        (uint256 id,) = openCase(false);
        vm.prank(BOB); w.fund{value: first}(id); vm.prank(CAROL); w.fund{value: second}(id);
        uint256 total = uint256(first) + second; uint256 used = uint256(usedSeed) % (total + 1);
        k.setFee(100 + used); vm.prank(ALICE); w.escalate(id);
        vm.prank(BOB); w.claimFunding(id); vm.prank(CAROL); w.claimFunding(id);
        eq(w.claimable(BOB), uint256(first) * (total - used) / total);
        eq(w.claimable(CAROL), uint256(second) * (total - used) / total);
        eq(w.refundLiability(), total - used - w.claimable(BOB) - w.claimable(CAROL)); accounting();
    }
    function testFullPrecisionMultiplication() public pure {
        eq(FullMath.mulDiv(1 << 200, 1 << 100, 1 << 80), 1 << 220);
        eq(FullMath.mulDiv(type(uint256).max, type(uint256).max, type(uint256).max), type(uint256).max);
    }
}
