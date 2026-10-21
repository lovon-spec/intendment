// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

import {IArbitrator} from "../src/Interfaces.sol";
import {HostProfiles} from "../src/HostProfiles.sol";
import {IntendmentArbitrator} from "../src/IntendmentArbitrator.sol";
import {IntendmentFactory} from "../src/IntendmentFactory.sol";

/// OpenZeppelin 5 TimelockController, as deployed in front of the registry.
interface ITimelock {
    function PROPOSER_ROLE() external view returns (bytes32);
    function EXECUTOR_ROLE() external view returns (bytes32);
    function CANCELLER_ROLE() external view returns (bytes32);
    function hasRole(bytes32 role, address account) external view returns (bool);
    function getMinDelay() external view returns (uint256);
    function getTimestamp(bytes32 id) external view returns (uint256);
    function isOperationPending(bytes32 id) external view returns (bool);
    function isOperationDone(bytes32 id) external view returns (bool);
    function hashOperationBatch(address[] calldata targets, uint256[] calldata values, bytes[] calldata payloads,
        bytes32 predecessor, bytes32 salt) external pure returns (bytes32);
    function scheduleBatch(address[] calldata targets, uint256[] calldata values, bytes[] calldata payloads,
        bytes32 predecessor, bytes32 salt, uint256 delay) external;
    function executeBatch(address[] calldata targets, uint256[] calldata values, bytes[] calldata payloads,
        bytes32 predecessor, bytes32 salt) external payable;
    function cancel(bytes32 id) external;
}

/// Safe 1.4.1.
interface ISafe {
    function nonce() external view returns (uint256);
    function getThreshold() external view returns (uint256);
    function getOwners() external view returns (address[] memory);
    function getTransactionHash(address to, uint256 value, bytes calldata data, uint8 operation, uint256 safeTxGas,
        uint256 baseGas, uint256 gasPrice, address gasToken, address refundReceiver, uint256 nonce)
        external view returns (bytes32);
    function execTransaction(address to, uint256 value, bytes calldata data, uint8 operation, uint256 safeTxGas,
        uint256 baseGas, uint256 gasPrice, address gasToken, address payable refundReceiver, bytes calldata signatures)
        external payable returns (bool);
}

/// Classic Curate (GeneralizedTCR) governance surface.
interface IClassicGovernance {
    function governor() external view returns (address);
    function arbitrator() external view returns (address);
    function arbitratorExtraData() external view returns (bytes memory);
    function changeArbitrator(address arbitrator, bytes calldata arbitratorExtraData) external;
}

interface VmPilot {
    function createSelectFork(string calldata) external returns (uint256);
    function envAddress(string calldata) external view returns (address);
    function envOr(string calldata, string calldata) external view returns (string memory);
    function toString(address) external pure returns (string memory);
    function toString(bytes calldata) external pure returns (string memory);
    function toString(bytes32) external pure returns (string memory);
    function toString(uint256) external pure returns (string memory);
}

/// The timelock batch that moves the Agent Skills Registry onto an Intendment wrapper.
/// The script below prints it; the Gnosis fork test executes exactly this batch.
library AgentSkillsPilot {
    VmPilot internal constant VM = VmPilot(address(uint160(uint256(keccak256("hevm cheat code")))));
    address internal constant REGISTRY = 0x67DBE6A9597635074546e08B92eE617bF02168f9;
    address internal constant TIMELOCK = 0xc8Ba4c0AD3554EDB0a9A4C8D73Bf87410A313ADa;
    address internal constant SAFE = 0x55705C596E087866C2B8e9339D7016b35a32619F;
    address internal constant KLEROS = 0x9C1dA9A04925bDfDedf0f6421bC7EEa8305F9002;
    uint256 internal constant DELAY = 7 days;
    bytes32 internal constant PREDECESSOR = bytes32(0);
    bytes32 internal constant SALT = keccak256("agent-skills-registry intendment pilot");
    uint32 internal constant EPOCH = 1;
    string internal constant PLACEHOLDER_REGISTRATION = "/ipfs/PLACEHOLDER/registration-meta-evidence.json";
    string internal constant PLACEHOLDER_CLEARING = "/ipfs/PLACEHOLDER/clearing-meta-evidence.json";

    struct Plan {
        address factory;
        uint256 deployment;
        address wrapper;
        bytes extra;
        uint256 cost;
        uint256 maxCost;
        uint256 reserve;
        string registrationURI;
        string clearingURI;
    }

    function config() internal pure returns (IntendmentArbitrator.Config memory) {
        return IntendmentArbitrator.Config({window: 1 days, fundingPeriod: 1 days, resolverGrace: 1 days,
            reserveTimelock: 7 days, retirementMargin: 1 days});
    }

    /// Reads the live registry and court. The wrapper's address is the factory's CREATE2 prediction
    /// for the timelock's next deployment for this registry; only the timelock can deploy there.
    /// The factory must already exist: the timelock does not check for code, and a batch run
    /// against an empty factory address would point the registry at an empty address.
    function read(address factory, string memory registrationURI, string memory clearingURI)
        internal view returns (Plan memory p)
    {
        IClassicGovernance registry = IClassicGovernance(REGISTRY);
        require(registry.governor() == TIMELOCK && registry.arbitrator() == KLEROS, "registry is not in its pre-pilot state");
        require(factory.code.length > 0, "deploy the factory first");
        p.factory = factory;
        p.deployment = IntendmentFactory(factory).deployments(REGISTRY);
        p.wrapper = IntendmentFactory(factory).predict(REGISTRY, TIMELOCK, p.deployment, IArbitrator(KLEROS),
            HostProfiles.Profile.Classic, config());
        require(p.wrapper.code.length == 0, "predicted wrapper address is taken");
        p.extra = registry.arbitratorExtraData();
        p.cost = IArbitrator(KLEROS).arbitrationCost(p.extra);
        p.maxCost = (p.cost * 3 + 1) / 2; // 1.5x, rounded up
        p.reserve = p.cost;
        p.registrationURI = registrationURI;
        p.clearingURI = clearingURI;
    }

    function envelope(bytes memory extra) internal pure returns (bytes memory) {
        return abi.encode(uint8(1), EPOCH, extra);
    }

    function calls(Plan memory p)
        internal pure returns (address[] memory targets, uint256[] memory values, bytes[] memory payloads)
    {
        targets = new address[](4);
        values = new uint256[](4);
        payloads = new bytes[](4);
        targets[0] = p.factory;
        payloads[0] = abi.encodeCall(IntendmentFactory.deploy,
            (REGISTRY, IArbitrator(KLEROS), HostProfiles.Profile.Classic, config()));
        targets[1] = p.wrapper;
        payloads[1] = abi.encodeCall(IntendmentArbitrator.registerEpoch,
            (p.extra, 0, 0, p.maxCost, p.registrationURI, p.clearingURI));
        targets[2] = REGISTRY;
        payloads[2] = abi.encodeCall(IClassicGovernance.changeArbitrator, (p.wrapper, envelope(p.extra)));
        // Sent by the timelock, so the wrapper books it as principal.
        targets[3] = p.wrapper;
        values[3] = p.reserve;
        payloads[3] = abi.encodeCall(IntendmentArbitrator.fundReserve, ());
    }

    function operationId(Plan memory p) internal pure returns (bytes32) {
        (address[] memory t, uint256[] memory v, bytes[] memory d) = calls(p);
        return keccak256(abi.encode(t, v, d, PREDECESSOR, SALT));
    }

    function scheduleData(Plan memory p) internal pure returns (bytes memory) {
        (address[] memory t, uint256[] memory v, bytes[] memory d) = calls(p);
        return abi.encodeCall(ITimelock.scheduleBatch, (t, v, d, PREDECESSOR, SALT, DELAY));
    }

    function executeData(Plan memory p) internal pure returns (bytes memory) {
        (address[] memory t, uint256[] memory v, bytes[] memory d) = calls(p);
        return abi.encodeCall(ITimelock.executeBatch, (t, v, d, PREDECESSOR, SALT));
    }

    function cancelData(Plan memory p) internal pure returns (bytes memory) {
        return abi.encodeCall(ITimelock.cancel, (operationId(p)));
    }
}

/// Prints the Safe transaction that schedules the pilot, and the later execute and cancel calls.
/// Read-only; it signs and sends nothing. It forks the chain itself, like the fork tests, so the
/// timelock's post-Paris bytecode runs under the chain's rules rather than the repo's Paris target.
///
///   FACTORY=0x... [REGISTRATION_META_EVIDENCE=/ipfs/...] [CLEARING_META_EVIDENCE=/ipfs/...] \
///     [GNOSIS_RPC_URL=https://rpc.gnosischain.com] forge script contracts/script/AgentSkillsPilot.s.sol
contract AgentSkillsPilotScript {
    VmPilot internal constant VM = AgentSkillsPilot.VM;
    address internal constant CONSOLE = 0x000000000000000000636F6e736F6c652e6c6f67;

    function run() external {
        VM.createSelectFork(VM.envOr("GNOSIS_RPC_URL", string("https://rpc.gnosischain.com")));
        require(block.chainid == 100, "Gnosis only");
        AgentSkillsPilot.Plan memory p = AgentSkillsPilot.read(VM.envAddress("FACTORY"),
            VM.envOr("REGISTRATION_META_EVIDENCE", AgentSkillsPilot.PLACEHOLDER_REGISTRATION),
            VM.envOr("CLEARING_META_EVIDENCE", AgentSkillsPilot.PLACEHOLDER_CLEARING));
        ITimelock timelock = ITimelock(AgentSkillsPilot.TIMELOCK);
        require(timelock.getMinDelay() == AgentSkillsPilot.DELAY, "timelock delay changed");
        require(timelock.hasRole(timelock.PROPOSER_ROLE(), AgentSkillsPilot.SAFE)
            && timelock.hasRole(timelock.CANCELLER_ROLE(), AgentSkillsPilot.SAFE), "Safe is not proposer and canceller");
        bytes32 id = AgentSkillsPilot.operationId(p);
        (address[] memory t, uint256[] memory v, bytes[] memory d) = AgentSkillsPilot.calls(p);
        require(timelock.hashOperationBatch(t, v, d, AgentSkillsPilot.PREDECESSOR, AgentSkillsPilot.SALT) == id,
            "operation id mismatch");
        require(timelock.getTimestamp(id) == 0, "operation already scheduled or done");

        _log(string.concat("Agent Skills Registry -> Intendment wrapper, Gnosis block ", VM.toString(block.number)));
        _log(string.concat("factory ", VM.toString(p.factory), ", registry deployment ", VM.toString(p.deployment)));
        _log(string.concat("wrapper ", VM.toString(p.wrapper), " = factory.predict(registry, timelock, ",
            VM.toString(p.deployment), ", Kleros, Classic, config)"));
        _log(string.concat("court fee ", VM.toString(p.cost), " wei; maxCost ", VM.toString(p.maxCost),
            "; reserve ", VM.toString(p.reserve)));
        _log(string.concat("extra data ", VM.toString(p.extra)));
        _log(string.concat("registration MetaEvidence ", p.registrationURI));
        _log(string.concat("clearing MetaEvidence ", p.clearingURI));
        if (keccak256(bytes(p.registrationURI)) == keccak256(bytes(AgentSkillsPilot.PLACEHOLDER_REGISTRATION))
            || keccak256(bytes(p.clearingURI)) == keccak256(bytes(AgentSkillsPilot.PLACEHOLDER_CLEARING))) {
            _log("WARNING: placeholder MetaEvidence; do not propose this batch");
        }
        string[4] memory names = ["factory.deploy", "wrapper.registerEpoch", "registry.changeArbitrator",
            "wrapper.fundReserve"];
        for (uint256 i; i < t.length; ++i) {
            _log(string.concat("call ", VM.toString(i), " ", names[i], ": to ", VM.toString(t[i]),
                ", value ", VM.toString(v[i]), ", data ", VM.toString(d[i])));
        }
        _log(string.concat("salt ", VM.toString(AgentSkillsPilot.SALT), ", predecessor 0x0, operation id ",
            VM.toString(id)));

        bytes memory schedule = AgentSkillsPilot.scheduleData(p);
        uint256 safeNonce = ISafe(AgentSkillsPilot.SAFE).nonce();
        bytes32 safeTxHash = ISafe(AgentSkillsPilot.SAFE).getTransactionHash(AgentSkillsPilot.TIMELOCK, 0, schedule, 0,
            0, 0, 0, address(0), address(0), safeNonce);
        _log("");
        _log(string.concat("== Safe transaction to propose (Safe ", VM.toString(AgentSkillsPilot.SAFE), ") =="));
        _log(string.concat("to: ", VM.toString(AgentSkillsPilot.TIMELOCK)));
        _log("value: 0");
        _log("operation: 0 (call); safeTxGas, baseGas, gasPrice: 0; gasToken, refundReceiver: 0x0");
        _log(string.concat("nonce: ", VM.toString(safeNonce), " (current; the hash below is for this nonce)"));
        _log(string.concat("safeTxHash: ", VM.toString(safeTxHash)));
        _log(string.concat("data: ", VM.toString(schedule)));
        _log("");
        _log("== After 7 days: executeBatch (anyone may send it; it must carry the reserve) ==");
        _log(string.concat("to: ", VM.toString(AgentSkillsPilot.TIMELOCK)));
        _log(string.concat("value: ", VM.toString(p.reserve)));
        _log(string.concat("data: ", VM.toString(AgentSkillsPilot.executeData(p))));
        _log("");
        _log("== Cancel while pending (Safe transaction) ==");
        _log(string.concat("to: ", VM.toString(AgentSkillsPilot.TIMELOCK), ", value: 0, data: ",
            VM.toString(AgentSkillsPilot.cancelData(p))));
    }

    function _log(string memory line) internal view {
        (bool ok,) = CONSOLE.staticcall(abi.encodeWithSignature("log(string)", line));
        ok;
    }
}
