// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IArbitrator} from "../src/Interfaces.sol";
import {HostProfiles} from "../src/HostProfiles.sol";
import {IntendmentArbitrator} from "../src/IntendmentArbitrator.sol";
import {IntendmentFactory} from "../src/IntendmentFactory.sol";
import {MockResolver, LightHost} from "./Fixtures.sol";

interface VmEvents {
    struct Log { bytes32[] topics; bytes data; address emitter; }
    function deal(address, uint256) external;
    function prank(address) external;
    function warp(uint256) external;
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
}

/// Review regressions. These are mock/ABI tests, not live-host fork tests.
contract Stage1aEventsTest {
    VmEvents constant VM = VmEvents(address(uint160(uint256(keccak256("hevm cheat code")))));
    address constant A = address(0xA11CE);
    address constant B = address(0xB0B);
    bytes32 constant ITEM = keccak256("event-regression");
    bytes32 constant CREATION = keccak256("DisputeCreation(uint256,address)");
    bytes32 constant DECISION = keccak256("AppealDecision(uint256,address)");
    bytes32 constant RULING = keccak256("Ruling(address,uint256,uint256)");
    bytes32 constant POSSIBLE = keccak256("AppealPossible(uint256,address)");
    MockResolver internal k;
    LightHost internal host;
    IntendmentArbitrator internal wrapper;
    bytes internal envelope;

    function setUp() public {
        VM.warp(1000);
        VM.deal(address(this), 1 ether); VM.deal(A, 1 ether); VM.deal(B, 1 ether);
        k = new MockResolver(); host = new LightHost();
        IntendmentFactory factory = new IntendmentFactory();
        wrapper = factory.deploy(address(host), k, HostProfiles.Profile.Light,
            IntendmentArbitrator.Config(20, 20, 20, 20, 20));
        uint32 epoch = wrapper.registerEpoch(bytes("court-data"), 0, 0, 100, "registration", "removal");
        envelope = abi.encode(uint8(1), epoch, bytes("court-data"));
        host.point(wrapper);
    }

    function _case() internal returns (uint256 localID) {
        VM.prank(A); host.submit{value: 130}(ITEM, false, envelope);
        VM.prank(B); localID = host.challenge{value: 100}(ITEM);
    }
    function _forwarded() internal returns (uint256 localID, uint256 remoteID) {
        // Seed the resolver so the namespaces differ; equality hid the original bug.
        k.createDispute{value: 100}(2, bytes("unrelated"));
        localID = _case();
        VM.prank(A); require(wrapper.escalate(localID), "forward");
        remoteID = wrapper.caseOf(localID).kDisputeID;
        require(localID != remoteID, "test must use distinct ids");
    }
    function _find(VmEvents.Log[] memory logs, bytes32 topic) internal view returns (VmEvents.Log memory out) {
        uint256 count;
        for (uint256 i; i < logs.length; ++i) {
            if (logs[i].emitter == address(wrapper) && logs[i].topics.length != 0 && logs[i].topics[0] == topic) {
                out = logs[i]; ++count;
            }
        }
        require(count == 1, "expected exactly one wrapper event");
    }
    function _none(VmEvents.Log[] memory logs, bytes32 topic) internal view {
        for (uint256 i; i < logs.length; ++i) {
            require(logs[i].emitter != address(wrapper) || logs[i].topics.length == 0 || logs[i].topics[0] != topic,
                "unexpected wrapper event");
        }
    }
    function _localEvent(VmEvents.Log memory log, uint256 id) internal view {
        require(log.topics.length == 3 && uint256(log.topics[1]) == id, "local id");
        require(address(uint160(uint256(log.topics[2]))) == address(host), "host arbitrable");
    }

    function testCreationUsesLocalIDAndHost() public {
        VM.recordLogs(); uint256 id = _case();
        _localEvent(_find(VM.getRecordedLogs(), CREATION), id);
        require(k.nextID() == 0, "local creation is not court creation");
    }
    function testConcessionDoesNotFabricateKlerosRuling() public {
        uint256 id = _case(); VM.recordLogs();
        VM.prank(A); wrapper.concede(id, 0);
        VmEvents.Log[] memory logs = VM.getRecordedLogs();
        _none(logs, RULING); _none(logs, DECISION);
        require(k.nextID() == 0 && wrapper.currentRuling(id) == 2, "concession state");
    }
    function testRulingUsesRemoteIDButHostUsesLocalID() public {
        (uint256 id, uint256 remoteID) = _forwarded();
        VM.recordLogs(); k.deliver(remoteID, 2);
        VmEvents.Log memory log = _find(VM.getRecordedLogs(), RULING);
        require(log.topics.length == 3 && address(uint160(uint256(log.topics[1]))) == address(k), "resolver");
        require(uint256(log.topics[2]) == remoteID && abi.decode(log.data, (uint256)) == 2, "remote ruling");
        (, uint256 hostID,, bool resolved,,,,,,) = host.getRequestInfo(ITEM, 0);
        require(hostID == id && resolved && wrapper.localDispute(remoteID) == id, "local callback");
    }
    function testSuccessfulHostAppealEmitsLocalDecision() public {
        (uint256 id, uint256 remoteID) = _forwarded();
        k.setAppealable(remoteID, 2); VM.recordLogs();
        host.appealThroughHost{value: 300}(ITEM);
        _localEvent(_find(VM.getRecordedLogs(), DECISION), id);
        require(k.disputeStatus(remoteID) == IArbitrator.DisputeStatus.Waiting, "appeal forwarded");
    }
    function testFailedAppealDoesNotEmitDecision() public {
        (, uint256 remoteID) = _forwarded();
        k.setAppealable(remoteID, 2); VM.recordLogs();
        (bool ok,) = address(host).call{value: 299}(abi.encodeCall(host.appealThroughHost, (ITEM)));
        require(!ok, "underpaid appeal accepted");
        _none(VM.getRecordedLogs(), DECISION);
        require(k.disputeStatus(remoteID) == IArbitrator.DisputeStatus.Appealable, "rollback");
    }
    function testAppealAvailabilityIsQueriedWithoutSyntheticWindow() public {
        (uint256 id, uint256 remoteID) = _forwarded();
        VM.recordLogs(); k.setAppealable(remoteID, 2);
        _none(VM.getRecordedLogs(), POSSIBLE);
        require(wrapper.disputeStatus(id) == IArbitrator.DisputeStatus.Appealable, "read status");
        (uint256 start, uint256 end) = wrapper.appealPeriod(id);
        require(start == 1000 && end == 1100, "original resolver window");
    }
    function testCallbackRetryKeepsRemoteMapping() public {
        (uint256 id, uint256 remoteID) = _forwarded();
        host.setFailRule(true);
        (bool ok,) = address(k).call(abi.encodeCall(k.deliver, (remoteID, 2)));
        require(!ok && !wrapper.caseOf(id).rulingDelivered, "failed callback latch");
        host.setFailRule(false); VM.recordLogs(); k.deliver(remoteID, 2);
        require(uint256(_find(VM.getRecordedLogs(), RULING).topics[2]) == remoteID, "retry id");
    }
    function testPrincipalUsesImmediateGovernorNotItsController() public {
        // A Safe/controller address distinct from GOVERNOR cannot deposit principal.
        wrapper.fundReserve{value: 11}();
        VM.prank(A); wrapper.fundReserve{value: 17}();
        require(wrapper.principal() == 11 && wrapper.surplus() == 17, "sender classification");
        require(wrapper.accountedBalance() == address(wrapper).balance, "accounting unchanged");
    }
    function testRawTransferIsNotAReserveDeposit() public {
        (bool ok,) = address(wrapper).call{value: 1}("");
        require(!ok && wrapper.principal() == 0 && wrapper.surplus() == 0, "use fundReserve");
    }
}
