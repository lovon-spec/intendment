// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IArbitrator, IRegistry, IClassicRegistry, ILightRegistry} from "../../src/Interfaces.sol";
import {IntendmentArbitrator} from "../../src/IntendmentArbitrator.sol";
import {IntendmentFactory} from "../../src/IntendmentFactory.sol";
import {HostProfiles} from "../../src/HostProfiles.sol";

interface VmGnosis {
    struct Log { bytes32[] topics; bytes data; address emitter; }
    function envOr(string calldata, bool) external returns (bool);
    function envOr(string calldata, string calldata) external returns (string memory);
    function createSelectFork(string calldata, uint256) external returns (uint256);
    function skip(bool) external;
    function deal(address, uint256) external;
    function prank(address) external;
    function warp(uint256) external;
    function roll(uint256) external;
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
}

interface IRealGTCRFactory {
    function count() external view returns (uint256);
    function instances(uint256) external view returns (address);
    function deploy(address, bytes calldata, address, string calldata, string calldata,
        address, uint256, uint256, uint256, uint256, uint256, uint256[3] calldata) external;
}
interface IRealHost is IRegistry {
    function arbitrator() external view returns (address);
    function arbitratorExtraData() external view returns (bytes memory);
    function submissionBaseDeposit() external view returns (uint256);
    function submissionChallengeBaseDeposit() external view returns (uint256);
    function winnerStakeMultiplier() external view returns (uint256);
    function loserStakeMultiplier() external view returns (uint256);
    function addItem(bytes calldata) external payable;
    function challengeRequest(bytes32, string calldata) external payable;
    function executeRequest(bytes32) external;
    function fundAppeal(bytes32, uint8) external payable;
    function withdrawFeesAndRewards(address payable, bytes32, uint256, uint256) external;
    function changeArbitrator(address, bytes calldata) external;
    function changeArbitrationParams(address, bytes calldata, string calldata, string calldata) external;
}

/// The live V1 ABI. No mock rule()/vote counters or host storage replacement.
interface IXKleros is IArbitrator {
    function governor() external view returns (address);
    function changeRNGenerator(address) external;
    function phase() external view returns (uint8);
    function lastPhaseChange() external view returns (uint256);
    function minStakingTime() external view returns (uint256);
    function passPhase() external;
    function drawJurors(uint256, uint256) external;
    function passPeriod(uint256) external;
    function executeRuling(uint256) external;
    function castCommit(uint256, uint256[] calldata, bytes32) external;
    function castVote(uint256, uint256[] calldata, uint256, uint256) external;
    function courts(uint256) external view returns (uint96, bool, uint256, uint256, uint256, uint256);
    function getSubcourt(uint96) external view returns (uint256[] memory, uint256[4] memory);
    function getVote(uint256, uint256, uint256) external view returns (address, bytes32, uint256, bool);
    function getDispute(uint256) external view returns (
        uint256[] memory, uint256[] memory, uint256[] memory,
        uint256[] memory, uint256[] memory, uint256[] memory);
}

/// FORK ONLY: removes an external RNG service dependency, not jury/ruling logic.
/// Installed via the real Kleros governor method on the ephemeral fork.
contract DeterministicForkRNG {
    function requestRN(uint256) external {}
    function getUncorrelatedRN(uint256 requestBlock) external view returns (uint256) {
        require(block.number > requestBlock, "advance RNG block");
        return uint256(keccak256(abi.encode("Intendment fork RNG", requestBlock))) | 1;
    }
}

/// Pinned integration tests. Opt-in so an ordinary offline test run does not need RPC.
/// RUN_GNOSIS_FORK=true makes RPC failure FAIL; it never falls back to mocks/latest.
contract GnosisStage1aForkTest {
    VmGnosis constant VM = VmGnosis(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 constant FORK_BLOCK = 48_112_715;
    uint96 constant COURT = 19;
    address constant KLEROS = 0x9C1dA9A04925bDfDedf0f6421bC7EEa8305F9002;
    address constant GTCR_FACTORY = 0x794Cee5a6e1501b633eC13b8c1e327d9860FE039;
    address constant SCOUT_TAGS = 0x66260C69d03837016d88c9877e61e08Ef74C59F2;
    address constant A = address(0xA11CE);
    address constant B = address(0xB0B);
    address constant FUNDER_A = address(0xF001);
    address constant FUNDER_B = address(0xF002);
    uint256 constant ENDOWMENT = 10_000 ether;
    bytes32 constant CREATION = keccak256("DisputeCreation(uint256,address)");
    bytes32 constant DISPUTE = keccak256("Dispute(address,uint256,uint256,uint256)");
    bytes32 constant POSSIBLE = keccak256("AppealPossible(uint256,address)");
    bytes32 constant DECISION = keccak256("AppealDecision(uint256,address)");
    bytes32 constant RULING = keccak256("Ruling(address,uint256,uint256)");

    IXKleros internal k;
    IRealHost internal host;
    IntendmentArbitrator internal wrapper;
    HostProfiles.Profile internal profile;
    bytes internal realExtra;
    bytes internal envelope;
    bytes internal descriptor;
    bytes32 internal item;
    uint256 internal q;
    uint256 internal deposit;
    uint256 internal challengeDeposit;
    uint256 internal localID;
    uint256 internal remoteID;
    uint256 internal initialReserve;
    uint256 internal initialCourtBalance;

    event ForkIdentity(uint256 blockNumber, address resolver, bytes32 resolverCodeHash,
        address host, bytes32 hostCodeHash, bool classic);
    event ForwardGas(uint256 gasUsed, uint256 configuredCreateBudget);
    event JuryRound(uint256 remoteID, uint256 round, uint256 jurors, uint256 ruling);

    function _setup(bool classic) internal {
        if (!VM.envOr("RUN_GNOSIS_FORK", false)) VM.skip(true);
        string memory rpc = VM.envOr("GNOSIS_RPC_URL", string("https://rpc.gnosischain.com"));
        VM.createSelectFork(rpc, FORK_BLOCK);
        require(block.chainid == 100 && block.number == FORK_BLOCK, "wrong fork");
        require(KLEROS.code.length > 0 && GTCR_FACTORY.code.length > 0 && SCOUT_TAGS.code.length > 0, "missing deployment");
        VM.deal(address(this), ENDOWMENT); VM.deal(A, ENDOWMENT); VM.deal(B, ENDOWMENT);
        VM.deal(FUNDER_A, ENDOWMENT); VM.deal(FUNDER_B, ENDOWMENT);
        k = IXKleros(KLEROS);
        realExtra = abi.encode(uint256(COURT), uint256(3));
        q = k.arbitrationCost(realExtra);
        require(q == 21.6 ether, "court-19 quote differs from pinned experiment");
        profile = classic ? HostProfiles.Profile.Classic : HostProfiles.Profile.Light;

        if (classic) {
            IRealGTCRFactory factory = IRealGTCRFactory(GTCR_FACTORY);
            uint256 beforeCount = factory.count();
            uint256[3] memory multipliers = [uint256(10000), uint256(10000), uint256(20000)];
            factory.deploy(KLEROS, realExtra, address(0), "ipfs://fork-registration", "ipfs://fork-removal",
                address(this), 30 ether, 30 ether, 0, 0, 302400, multipliers);
            require(factory.count() == beforeCount + 1, "real factory creation");
            host = IRealHost(factory.instances(beforeCount));
        } else {
            host = IRealHost(SCOUT_TAGS);
        }
        address governor = host.governor();
        require(governor != address(0), "governor");
        VM.deal(governor, ENDOWMENT);
        IntendmentFactory wrapperFactory = new IntendmentFactory();
        VM.prank(governor);
        wrapper = wrapperFactory.deploy(address(host), k, profile,
            IntendmentArbitrator.Config(2 days, 1 days, 1 days, 7 days, 1 days));
        VM.prank(governor);
        uint32 epoch = wrapper.registerEpoch(realExtra, 0, 0, q, "ipfs://fork-display-register", "ipfs://fork-display-remove");
        envelope = abi.encode(uint8(1), epoch, realExtra);
        VM.prank(governor);
        if (classic) host.changeArbitrator(address(wrapper), envelope);
        else host.changeArbitrationParams(address(wrapper), envelope, "ipfs://fork-registration", "ipfs://fork-removal");
        VM.prank(governor); wrapper.fundReserve{value: q}();
        initialReserve = q;
        require(host.arbitrator() == address(wrapper), "host adoption");
        require(keccak256(host.arbitratorExtraData()) == keccak256(envelope), "host envelope");
        deposit = host.submissionBaseDeposit(); challengeDeposit = host.submissionChallengeBaseDeposit();
        descriptor = abi.encode("intendment/pinned-fork/stage1a", classic);
        item = keccak256(descriptor);
        require(_count() == 0, "fixture item collision");
        initialCourtBalance = KLEROS.balance;
        emit ForkIdentity(FORK_BLOCK, KLEROS, KLEROS.codehash, address(host), address(host).codehash, classic);
    }

    function _count() internal view returns (uint256 count) {
        if (profile == HostProfiles.Profile.Classic) (,, count) = IClassicRegistry(address(host)).getItemInfo(item);
        else (, count,) = ILightRegistry(address(host)).getItemInfo(item);
    }
    function _status() internal view returns (uint8 status) {
        if (profile == HostProfiles.Profile.Classic) (, status,) = IClassicRegistry(address(host)).getItemInfo(item);
        else (status,,) = ILightRegistry(address(host)).getItemInfo(item);
    }
    function _event(VmGnosis.Log[] memory logs, address emitter, bytes32 topic)
        internal pure returns (VmGnosis.Log memory selected)
    {
        uint256 count;
        for (uint256 i; i < logs.length; ++i) {
            if (logs[i].emitter == emitter && logs[i].topics.length > 0 && logs[i].topics[0] == topic) {
                selected = logs[i]; ++count;
            }
        }
        require(count == 1, "missing/duplicate expected event");
    }
    function _submit() internal {
        VM.prank(A); host.addItem{value: deposit + q}(descriptor);
        require(_count() == 1 && _status() == 2, "pending registration");
    }
    function _challenge() internal {
        _submit(); VM.recordLogs();
        VM.prank(B); host.challengeRequest{value: challengeDeposit + q}(item, "ipfs://fork-challenge-evidence");
        bool disputed; bool resolved; address payable[3] memory parties; address arb; bytes memory extra;
        (disputed, localID,, resolved, parties,,, arb, extra,) = host.getRequestInfo(item, 0);
        require(disputed && !resolved && parties[1] == A && parties[2] == B && arb == address(wrapper), "host request");
        require(keccak256(extra) == keccak256(envelope), "stored envelope");
        VmGnosis.Log[] memory logs = VM.getRecordedLogs();
        VmGnosis.Log memory creation = _event(logs, address(wrapper), CREATION);
        require(uint256(creation.topics[1]) == localID
            && address(uint160(uint256(creation.topics[2]))) == address(host), "local creation namespace");
        VmGnosis.Log memory dispute = _event(logs, address(host), DISPUTE);
        require(address(uint160(uint256(dispute.topics[1]))) == address(wrapper)
            && uint256(dispute.topics[2]) == localID, "host dispute namespace");
        wrapper.bind(localID);
        IntendmentArbitrator.Case memory c = wrapper.caseOf(localID);
        require(c.binding.item == item && c.binding.requestIndex == 0
            && c.binding.requester == A && c.binding.challenger == B && !c.binding.removal, "real getter binding");
        require(c.fee == q && wrapper.accountedBalance() == address(wrapper).balance, "creation accounting");
    }
    function _forward() internal {
        VM.recordLogs(); VM.prank(A);
        uint256 beforeGas = gasleft();
        require(wrapper.escalate(localID), "real resolver forwarding failed");
        emit ForwardGas(beforeGas - gasleft(), wrapper.CREATE_GAS());
        remoteID = wrapper.caseOf(localID).kDisputeID;
        require(remoteID != localID && wrapper.localDispute(remoteID) == localID, "distinct namespaces");
        VmGnosis.Log[] memory logs = VM.getRecordedLogs();
        VmGnosis.Log memory creation = _event(logs, KLEROS, CREATION);
        require(uint256(creation.topics[1]) == remoteID
            && address(uint160(uint256(creation.topics[2]))) == address(wrapper), "court arbitrable");
        VmGnosis.Log memory dispute = _event(logs, address(wrapper), DISPUTE);
        require(address(uint160(uint256(dispute.topics[1]))) == KLEROS
            && uint256(dispute.topics[2]) == remoteID, "remote dispute namespace");
        require(KLEROS.balance == initialCourtBalance + q, "actual court payment");
        require(wrapper.reserve() == initialReserve && wrapper.openFees() == 0, "fixed-quote reserve");
    }

    function _enableDeterministicRNG() internal {
        DeterministicForkRNG rng = new DeterministicForkRNG();
        address governor = k.governor();
        VM.prank(governor); k.changeRNGenerator(address(rng));
    }
    function _drawing() internal {
        if (k.phase() == 0) {
            uint256 earliest = k.lastPhaseChange() + k.minStakingTime() + 1;
            if (block.timestamp < earliest) VM.warp(earliest);
            k.passPhase();
        }
        if (k.phase() == 1) {
            VM.roll(block.number + 2); k.passPhase();
        }
        require(k.phase() == 2, "drawing phase");
    }
    function _roundToAppeal(uint256 desiredRuling, uint256 expectedRound, uint256 expectedJurors) internal {
        (uint256[] memory lengths,,,,,) = k.getDispute(remoteID);
        require(lengths.length == expectedRound + 1 && lengths[expectedRound] == expectedJurors, "real juror count");
        _drawing(); k.drawJurors(remoteID, expectedJurors);
        (, uint256[4] memory times) = k.getSubcourt(COURT);
        VM.warp(block.timestamp + times[0] + 1); k.passPeriod(remoteID);
        (, bool hidden,,,,) = k.courts(COURT);
        uint256[] memory voteIds = new uint256[](1);
        if (hidden) {
            for (uint256 i; i < expectedJurors; ++i) {
                (address juror,,,) = k.getVote(remoteID, expectedRound, i);
                require(juror != address(0), "real drawn juror");
                voteIds[0] = i;
                uint256 salt = uint256(keccak256(abi.encode(remoteID, expectedRound, i)));
                VM.prank(juror); k.castCommit(remoteID, voteIds, keccak256(abi.encodePacked(desiredRuling, salt)));
            }
            k.passPeriod(remoteID);
        }
        for (uint256 i; i < expectedJurors; ++i) {
            (address juror,,,) = k.getVote(remoteID, expectedRound, i);
            voteIds[0] = i;
            uint256 salt = uint256(keccak256(abi.encode(remoteID, expectedRound, i)));
            VM.prank(juror); k.castVote(remoteID, voteIds, desiredRuling, salt);
        }
        VM.recordLogs(); k.passPeriod(remoteID);
        VmGnosis.Log memory possible = _event(VM.getRecordedLogs(), KLEROS, POSSIBLE);
        require(uint256(possible.topics[1]) == remoteID
            && address(uint160(uint256(possible.topics[2]))) == address(wrapper), "remote appeal notification");
        require(wrapper.disputeStatus(localID) == IArbitrator.DisputeStatus.Appealable
            && wrapper.currentRuling(localID) == desiredRuling, "wrapper appeal views");
        (uint256 start, uint256 end) = wrapper.appealPeriod(localID);
        (uint256 kStart, uint256 kEnd) = k.appealPeriod(remoteID);
        require(start == kStart && end == kEnd && end > start, "unmodified appeal window");
        emit JuryRound(remoteID, expectedRound, expectedJurors, desiredRuling);
    }
    function _finish(uint256 rawRuling, uint256 hostRuling) internal {
        (, uint256 end) = k.appealPeriod(remoteID);
        VM.warp(end); k.passPeriod(remoteID);
        VM.recordLogs(); k.executeRuling(remoteID);
        VmGnosis.Log memory ruling = _event(VM.getRecordedLogs(), address(wrapper), RULING);
        require(address(uint160(uint256(ruling.topics[1]))) == KLEROS && uint256(ruling.topics[2]) == remoteID
            && abi.decode(ruling.data, (uint256)) == rawRuling, "final event mapping");
        require(wrapper.currentRuling(localID) == rawRuling
            && wrapper.disputeStatus(localID) == IArbitrator.DisputeStatus.Solved, "remote finality");
        _assertHost(hostRuling);
        require(wrapper.accountedBalance() == address(wrapper).balance && wrapper.reserve() == initialReserve, "final accounting");
    }
    function _assertHost(uint256 expectedRuling) internal view {
        (, uint256 id,, bool resolved,,, uint8 ruling,,,) = host.getRequestInfo(item, 0);
        require(id == localID && resolved && ruling == expectedRuling, "host final result");
        require(_status() == (expectedRuling == 1 ? 1 : 0), "host membership");
    }
    function _concession(bool classic) internal {
        _setup(classic); _challenge();
        VM.prank(A); wrapper.concede(localID, 0);
        VM.prank(A); wrapper.claim(payable(A));
        _assertHost(2);
        require(A.balance == ENDOWMENT - deposit && B.balance == ENDOWMENT + deposit, "concession payoffs");
        require(KLEROS.balance == initialCourtBalance && wrapper.reserve() == initialReserve, "no court fee");
        require(wrapper.openCases() == 0 && wrapper.accountedBalance() == address(wrapper).balance, "concession accounting");
    }
    function _court(bool classic) internal {
        _setup(classic); _challenge(); _forward(); _enableDeterministicRNG();
        _roundToAppeal(2, 0, 3); _finish(2, 2);
        require(A.balance == ENDOWMENT - deposit - q && B.balance == ENDOWMENT + deposit, "court payoffs");
    }
    function _appeal(bool classic) internal {
        _setup(classic); _challenge(); _forward(); _enableDeterministicRNG();
        _roundToAppeal(2, 0, 3);
        uint256 fee = wrapper.appealCost(localID, envelope);
        uint256 amountA = fee + fee * host.loserStakeMultiplier() / 10000;
        uint256 amountB = fee + fee * host.winnerStakeMultiplier() / 10000;
        VM.prank(FUNDER_A); host.fundAppeal{value: amountA}(item, 1);
        VM.recordLogs(); VM.prank(FUNDER_B); host.fundAppeal{value: amountB}(item, 2);
        VmGnosis.Log[] memory logs = VM.getRecordedLogs();
        VmGnosis.Log memory localDecision = _event(logs, address(wrapper), DECISION);
        require(uint256(localDecision.topics[1]) == localID
            && address(uint160(uint256(localDecision.topics[2]))) == address(host), "local appeal decision");
        VmGnosis.Log memory remoteDecision = _event(logs, KLEROS, DECISION);
        require(uint256(remoteDecision.topics[1]) == remoteID, "remote appeal decision");
        require(KLEROS.balance == initialCourtBalance + q + fee, "appeal payment");
        _roundToAppeal(1, 1, 7); _finish(1, 1);
        require(A.balance == ENDOWMENT + challengeDeposit && B.balance == ENDOWMENT - challengeDeposit - q, "reversed host payoffs");
        uint256 beforeA = FUNDER_A.balance; uint256 beforeB = FUNDER_B.balance;
        host.withdrawFeesAndRewards(payable(FUNDER_A), item, 0, 1);
        host.withdrawFeesAndRewards(payable(FUNDER_B), item, 0, 1);
        require(FUNDER_A.balance == beforeA + amountA + amountB - fee && FUNDER_B.balance == beforeB, "real appeal rewards");
    }
    function _unchallenged(bool classic) internal {
        _setup(classic); _submit();
        uint256 period = host.challengePeriodDuration();
        VM.warp(block.timestamp + period + 1); host.executeRequest(item);
        require(_status() == 1 && A.balance == ENDOWMENT, "unchallenged acceptance/refund");
        require(wrapper.caseCount() == 0 && wrapper.reserve() == initialReserve, "no invented wrapper case");
    }

    function testClassicConcession() public { _concession(true); }
    function testLightScoutConcession() public { _concession(false); }
    function testClassicCourtRuling() public { _court(true); }
    function testLightScoutCourtRuling() public { _court(false); }
    function testClassicHostCrowdfundedAppealReversal() public { _appeal(true); }
    function testLightScoutHostCrowdfundedAppealReversal() public { _appeal(false); }
    function testClassicUnchallengedExecution() public { _unchallenged(true); }
    function testLightScoutUnchallengedExecution() public { _unchallenged(false); }
}
