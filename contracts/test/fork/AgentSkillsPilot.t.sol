// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IArbitrator, IClassicRegistry} from "../../src/Interfaces.sol";
import {IntendmentArbitrator} from "../../src/IntendmentArbitrator.sol";
import {IntendmentFactory} from "../../src/IntendmentFactory.sol";
import {AgentSkillsPilot as Pilot, ITimelock, ISafe} from "../../script/AgentSkillsPilot.s.sol";
import {IXKleros, DeterministicForkRNG} from "./GnosisStage1a.t.sol";

interface VmPilotFork {
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
    function getNonce(address) external view returns (uint64);
}

interface IAgentSkillsRegistry is IClassicRegistry {
    function arbitrator() external view returns (address);
    function arbitratorExtraData() external view returns (bytes memory);
    function submissionBaseDeposit() external view returns (uint256);
    function submissionChallengeBaseDeposit() external view returns (uint256);
    function itemCount() external view returns (uint256);
    function itemList(uint256) external view returns (bytes32);
    function addItem(bytes calldata) external payable;
    function challengeRequest(bytes32, string calldata) external payable;
}

interface IXKlerosDisputes {
    function disputes(uint256) external view returns (uint96 subcourtID, address arbitrated, uint256 choices,
        uint8 period, uint256 lastPeriodChange, uint256 drawsInRound, uint256 commitsInRound, bool ruled);
}

/// Dress rehearsal of the Agent Skills Registry switching its arbitrator to an Intendment wrapper:
/// the real Safe proposes the scripted batch on the real timelock, waits out the delay and executes it.
/// Opt-in like GnosisStage1a: RUN_GNOSIS_FORK=true, and RPC failure fails.
contract AgentSkillsPilotForkTest {
    VmPilotFork constant VM = VmPilotFork(address(uint160(uint256(keccak256("hevm cheat code")))));
    uint256 constant FORK_BLOCK = 48_859_000;
    uint96 constant COURT = 19;
    IAgentSkillsRegistry constant REGISTRY = IAgentSkillsRegistry(Pilot.REGISTRY);
    ITimelock constant TIMELOCK = ITimelock(Pilot.TIMELOCK);
    ISafe constant SAFE = ISafe(Pilot.SAFE);
    IXKleros constant K = IXKleros(Pilot.KLEROS);
    address constant OWNER = 0x9F4f53194C63541E6930F75Cd9D403CA4D3f6Ca4; // the Safe's only owner
    address constant DEPLOYER = address(0xDE91);
    address constant A = address(0xA11CE);
    address constant B = address(0xB0B);
    address constant BOT = address(0xB07);
    uint256 constant ENDOWMENT = 1_000 ether;
    bytes32 constant CREATION = keccak256("DisputeCreation(uint256,address)");
    bytes32 constant RESERVE_FUNDED = keccak256("ReserveFunded(address,uint256,bool)");
    address constant CONSOLE = 0x000000000000000000636F6e736F6c652e6c6f67;

    Pilot.Plan internal plan;
    IntendmentArbitrator internal wrapper;
    bytes internal envelope;
    uint256 internal q;
    uint256 internal deposit;
    uint256 internal challengeDeposit;
    bytes32 internal item;
    uint256 internal localID;

    function _fork() internal {
        if (!VM.envOr("RUN_GNOSIS_FORK", false)) VM.skip(true);
        VM.createSelectFork(VM.envOr("GNOSIS_RPC_URL", string("https://rpc.gnosischain.com")), FORK_BLOCK);
        require(block.chainid == 100 && block.number == FORK_BLOCK, "wrong fork");
        require(TIMELOCK.getMinDelay() == Pilot.DELAY && TIMELOCK.hasRole(TIMELOCK.PROPOSER_ROLE(), address(SAFE))
            && TIMELOCK.hasRole(TIMELOCK.CANCELLER_ROLE(), address(SAFE))
            && TIMELOCK.hasRole(TIMELOCK.EXECUTOR_ROLE(), address(0)), "timelock roles");
        address[] memory owners = SAFE.getOwners();
        require(SAFE.getThreshold() == 1 && owners.length == 1 && owners[0] == OWNER, "Safe owners");
        require(REGISTRY.governor() == address(TIMELOCK) && REGISTRY.arbitrator() == address(K)
            && keccak256(REGISTRY.arbitratorExtraData()) == keccak256(abi.encode(uint256(COURT), uint256(3))), "registry");
        deposit = REGISTRY.submissionBaseDeposit();
        challengeDeposit = REGISTRY.submissionChallengeBaseDeposit();
        q = K.arbitrationCost(REGISTRY.arbitratorExtraData());
        require(q == 21.6 ether && deposit == 30 ether && challengeDeposit == 0, "pinned registry economics");
        VM.deal(A, ENDOWMENT); VM.deal(B, ENDOWMENT);
    }

    /// Steps 1-2 of the runbook: anyone deploys the factory, the Safe proposes the batch.
    function _schedule() internal returns (bytes32 id) {
        VM.prank(DEPLOYER);
        uint256 gas = gasleft();
        IntendmentFactory factory = new IntendmentFactory();
        _gas("factory deployment", gas - gasleft());
        plan = Pilot.read(address(factory), Pilot.PLACEHOLDER_REGISTRATION, Pilot.PLACEHOLDER_CLEARING);
        require(plan.factoryNonce == 1 && plan.maxCost == 32.4 ether && plan.reserve == q, "plan");
        id = Pilot.operationId(plan);
        (address[] memory t, uint256[] memory v, bytes[] memory d) = Pilot.calls(plan);
        require(TIMELOCK.hashOperationBatch(t, v, d, Pilot.PREDECESSOR, Pilot.SALT) == id, "operation id");
        uint256 nonce = SAFE.nonce();
        _gas("Safe tx scheduleBatch", _safe(address(TIMELOCK), 0, Pilot.scheduleData(plan)));
        require(SAFE.nonce() == nonce + 1 && TIMELOCK.isOperationPending(id)
            && TIMELOCK.getTimestamp(id) == block.timestamp + Pilot.DELAY, "scheduled");
    }

    /// Steps 3-4: wait out the delay; the Safe executes, carrying the reserve as call value.
    function _execute(bytes32 id) internal {
        uint256 submitterCost = deposit + q;
        uint256 safeBalance = address(SAFE).balance;
        VM.deal(address(SAFE), safeBalance + plan.reserve); // the owner tops up the Safe
        bytes memory execute = Pilot.executeData(plan);
        (bool early,) = _trySafe(address(TIMELOCK), plan.reserve, execute);
        require(!early, "executed right after scheduling");
        VM.warp(TIMELOCK.getTimestamp(id) - 1);
        (early,) = _trySafe(address(TIMELOCK), plan.reserve, execute);
        require(!early, "executed a second early");
        VM.warp(block.timestamp + 1);
        VM.recordLogs();
        _gas("Safe tx executeBatch", _safe(address(TIMELOCK), plan.reserve, execute));
        VmPilotFork.Log memory funded = _only(VM.getRecordedLogs(), plan.wrapper, RESERVE_FUNDED);

        wrapper = IntendmentArbitrator(plan.wrapper);
        envelope = Pilot.envelope(plan.extra);
        require(TIMELOCK.isOperationDone(id) && IntendmentFactory(plan.factory).isWrapper(plan.wrapper), "executed");
        require(REGISTRY.arbitrator() == address(wrapper)
            && keccak256(REGISTRY.arbitratorExtraData()) == keccak256(envelope), "registry switched");
        require(wrapper.HOST() == address(REGISTRY) && address(wrapper.K()) == address(K)
            && wrapper.GOVERNOR() == address(TIMELOCK) && wrapper.WINDOW() == 1 days, "wrapper identity");
        require(deposit + IArbitrator(REGISTRY.arbitrator()).arbitrationCost(REGISTRY.arbitratorExtraData())
            == submitterCost, "submitter cost changed");
        require(address(uint160(uint256(funded.topics[1]))) == address(TIMELOCK)
            && keccak256(funded.data) == keccak256(abi.encode(plan.reserve, true))
            && wrapper.principal() == plan.reserve && wrapper.surplus() == 0, "reserve booked as principal");
        require(address(TIMELOCK).balance == 0 && address(SAFE).balance == safeBalance, "reserve passed through");
    }

    function _install() internal {
        _fork();
        _execute(_schedule());
    }

    /// Execution gas as measured inside the test transaction (no intrinsic or calldata gas).
    function _gas(string memory step, uint256 used) internal view {
        (bool ok,) = CONSOLE.staticcall(abi.encodeWithSignature("log(string,uint256)", step, used));
        ok;
    }

    function _safe(address to, uint256 value, bytes memory data) internal returns (uint256 used) {
        bool ok;
        (ok, used) = _trySafe(to, value, data);
        require(ok, "Safe transaction failed");
    }

    /// The 1-of-1 owner executes through the real Safe with its own pre-validated signature (v = 1).
    function _trySafe(address to, uint256 value, bytes memory data) internal returns (bool ok, uint256 used) {
        bytes memory signature = abi.encodePacked(uint256(uint160(OWNER)), uint256(0), uint8(1));
        bytes memory call = abi.encodeCall(ISafe.execTransaction,
            (to, value, data, 0, 0, 0, 0, address(0), payable(address(0)), signature));
        bytes memory ret;
        VM.prank(OWNER);
        used = gasleft();
        (ok, ret) = address(SAFE).call(call);
        used -= gasleft();
        ok = ok && abi.decode(ret, (bool));
    }

    function _only(VmPilotFork.Log[] memory logs, address emitter, bytes32 topic)
        internal pure returns (VmPilotFork.Log memory selected)
    {
        uint256 count;
        for (uint256 i; i < logs.length; ++i) {
            if (logs[i].emitter == emitter && logs[i].topics.length > 0 && logs[i].topics[0] == topic) {
                selected = logs[i]; ++count;
            }
        }
        require(count == 1, "missing/duplicate expected event");
    }

    function _count(VmPilotFork.Log[] memory logs, address emitter, bytes32 topic) internal pure returns (uint256 n) {
        for (uint256 i; i < logs.length; ++i) {
            if (logs[i].emitter == emitter && logs[i].topics.length > 0 && logs[i].topics[0] == topic) ++n;
        }
    }

    function _status() internal view returns (uint8 status) {
        (, status,) = REGISTRY.getItemInfo(item);
    }

    /// A fresh submission with the registry's real deposit, then a challenge.
    function _submitAndChallenge(bytes memory data) internal {
        item = keccak256(data);
        (,, uint256 requests) = REGISTRY.getItemInfo(item);
        require(requests == 0, "fixture item exists");
        VM.prank(A); REGISTRY.addItem{value: deposit + q}(data);
        VM.prank(B); REGISTRY.challengeRequest{value: challengeDeposit + q}(item, "");
        bool disputed;
        (disputed, localID,,,,,,,,) = REGISTRY.getRequestInfo(item, 0);
        require(disputed && _status() == 2, "challenged registration");
        IntendmentArbitrator.Case memory c = wrapper.caseOf(localID);
        require(c.fee == q && c.insuredAtCreation && c.earmark == plan.maxCost - q, "insured case");
        require(A.balance == ENDOWMENT - deposit - q && B.balance == ENDOWMENT - challengeDeposit - q, "paid as today");
    }

    /// Trace 1: the requester admits inside the window; no court case.
    function testConcessionSkipsTheCourt() public {
        _install();
        _submitAndChallenge("agent-skills-pilot/trace-1");
        uint256 courtBalance = address(K).balance;
        VM.recordLogs();
        VM.prank(A); wrapper.concede(localID, 0);
        require(_count(VM.getRecordedLogs(), address(K), CREATION) == 0 && address(K).balance == courtBalance,
            "no Kleros dispute");
        (,,, bool resolved,,, uint8 ruling,,,) = REGISTRY.getRequestInfo(item, 0);
        require(resolved && ruling == 2 && _status() == 0, "registration rejected");
        // The registry pays the challenger what a court win pays: both deposits plus one court fee.
        require(B.balance == ENDOWMENT + deposit, "challenger paid by the registry");
        require(wrapper.claimable(A) == q, "requester credited the court fee");
        VM.prank(A); wrapper.claim(payable(A));
        require(A.balance == ENDOWMENT - deposit, "requester loses only the deposit");
        require(wrapper.openCases() == 0 && wrapper.reserve() == plan.reserve
            && wrapper.accountedBalance() == address(wrapper).balance, "wrapper accounting");
    }

    /// Trace 2: nobody answers; after the window anyone escalates to the real court.
    function testUnansweredChallengeGoesToCourt() public {
        _install();
        _submitAndChallenge("agent-skills-pilot/trace-2");
        VM.warp(wrapper.caseOf(localID).deadline);
        uint256 courtBalance = address(K).balance;
        VM.prank(BOT);
        uint256 gas = gasleft();
        require(wrapper.escalate(localID), "escalation failed");
        _gas("escalate", gas - gasleft());
        uint256 remoteID = wrapper.caseOf(localID).kDisputeID;
        (uint96 court, address arbitrated, uint256 choices,,,,,) = IXKlerosDisputes(address(K)).disputes(remoteID);
        (uint256[] memory jurors,,,,,) = K.getDispute(remoteID);
        require(court == COURT && arbitrated == address(wrapper) && choices == 2
            && jurors.length == 1 && jurors[0] == 3, "court 19, three jurors");
        require(address(K).balance == courtBalance + q && wrapper.reserve() == plan.reserve, "fee paid from the case");

        // Drive the real court as GnosisStage1a does: draw, commit, reveal, appeal period, ruling.
        DeterministicForkRNG rng = new DeterministicForkRNG();
        VM.prank(K.governor()); K.changeRNGenerator(address(rng));
        if (K.phase() == 0) {
            uint256 earliest = K.lastPhaseChange() + K.minStakingTime() + 1;
            if (block.timestamp < earliest) VM.warp(earliest);
            K.passPhase();
        }
        if (K.phase() == 1) { VM.roll(block.number + 2); K.passPhase(); }
        require(K.phase() == 2, "drawing phase");
        K.drawJurors(remoteID, 3);
        (, uint256[4] memory times) = K.getSubcourt(COURT);
        VM.warp(block.timestamp + times[0] + 1); K.passPeriod(remoteID);
        (, bool hidden,,,,) = K.courts(COURT);
        uint256[] memory voteIDs = new uint256[](1);
        if (hidden) {
            for (uint256 i; i < 3; ++i) {
                (address juror,,,) = K.getVote(remoteID, 0, i);
                voteIDs[0] = i;
                VM.prank(juror); K.castCommit(remoteID, voteIDs, keccak256(abi.encodePacked(uint256(2), i)));
            }
            K.passPeriod(remoteID);
        }
        for (uint256 i; i < 3; ++i) {
            (address juror,,,) = K.getVote(remoteID, 0, i);
            voteIDs[0] = i;
            VM.prank(juror); K.castVote(remoteID, voteIDs, 2, i);
        }
        K.passPeriod(remoteID);
        (, uint256 end) = K.appealPeriod(remoteID);
        VM.warp(end); K.passPeriod(remoteID);
        K.executeRuling(remoteID);

        (,,, bool resolved,,, uint8 ruling,,,) = REGISTRY.getRequestInfo(item, 0);
        require(resolved && ruling == 2 && _status() == 0, "court ruling reached the registry");
        require(A.balance == ENDOWMENT - deposit - q && B.balance == ENDOWMENT + deposit, "court payoffs as today");
        require(wrapper.reserve() == plan.reserve && wrapper.accountedBalance() == address(wrapper).balance, "accounting");
    }

    /// Trace 3: the three registered items keep their status, data and Kleros-arbitrated history.
    function testRegisteredItemsUnaffected() public {
        _fork();
        require(REGISTRY.itemCount() == 3, "three items");
        bytes32[3] memory before;
        for (uint256 i; i < 3; ++i) before[i] = _itemState(REGISTRY.itemList(i));
        _execute(_schedule());
        for (uint256 i; i < 3; ++i) {
            bytes32 id = REGISTRY.itemList(i);
            require(_itemState(id) == before[i], "item changed");
            (, uint8 status, uint256 requests) = REGISTRY.getItemInfo(id);
            (,,, bool resolved,,,, address arbitrator,,) = REGISTRY.getRequestInfo(id, requests - 1);
            require(status == 1 && resolved && arbitrator == address(K), "registered under Kleros");
        }
        require(REGISTRY.itemCount() == 3, "no item added");
    }

    /// The runbook's escape hatch: the Safe cancels the pending batch and it can never run.
    function testSafeCancelsThePendingBatch() public {
        _fork();
        bytes32 id = _schedule();
        _safe(address(TIMELOCK), 0, Pilot.cancelData(plan));
        require(TIMELOCK.getTimestamp(id) == 0, "cancelled");
        VM.warp(block.timestamp + Pilot.DELAY);
        VM.deal(address(SAFE), address(SAFE).balance + plan.reserve);
        (bool executed,) = _trySafe(address(TIMELOCK), plan.reserve, Pilot.executeData(plan));
        require(!executed, "cancelled batch executed");
        require(REGISTRY.arbitrator() == address(K), "registry untouched");
    }

    function _itemState(bytes32 id) internal view returns (bytes32) {
        (bytes memory data, uint8 status, uint256 requests) = REGISTRY.getItemInfo(id);
        (bool disputed, uint256 disputeID, uint256 submittedAt, bool resolved, address payable[3] memory parties,
            uint256 rounds, uint8 ruling, address arbitrator, bytes memory extra, uint256 metaEvidenceID) =
            REGISTRY.getRequestInfo(id, requests - 1);
        return keccak256(abi.encode(data, status, requests, disputed, disputeID, submittedAt, resolved, parties,
            rounds, ruling, arbitrator, extra, metaEvidenceID));
    }
}
