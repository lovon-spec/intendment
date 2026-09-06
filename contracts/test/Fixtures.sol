// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {IArbitrator, IArbitrable} from "../src/Interfaces.sol";
import {IntendmentArbitrator} from "../src/IntendmentArbitrator.sol";

interface Vm {
    function deal(address, uint256) external;
    function prank(address) external;
    function startPrank(address) external;
    function stopPrank() external;
    function warp(uint256) external;
    function expectRevert() external;
    function expectRevert(bytes4) external;
    function expectRevert(bytes calldata) external;
}

/// Deterministic resolver fixture, NOT Kleros voting or sortition.
contract MockResolver is IArbitrator {
    uint256 public fee = 100;
    uint256 public nextID;
    uint256 public appealFee = 300;
    bool public quoteFailure;
    bool public creationFailure;
    bool public malformed;
    bool public duplicateID;
    bool public attack;
    bool public reentered;
    bytes public lastData;
    struct D { address arb; DisputeStatus status; uint256 ruling; uint256 start; uint256 end; }
    mapping(uint256 => D) public disputes;
    function setFee(uint256 value) external { fee = value; }
    function setFailures(bool quote_, bool creation_) external { quoteFailure = quote_; creationFailure = creation_; }
    function setMalformed(bool value) external { malformed = value; }
    function setDuplicate(bool value) external { duplicateID = value; }
    function setAttack(bool value) external { attack = value; }
    function arbitrationCost(bytes calldata) external view returns (uint256) { require(!quoteFailure, "quote"); return fee; }
    function createDispute(uint256, bytes calldata data) external payable returns (uint256 id) {
        require(!creationFailure && msg.value == fee, "create");
        lastData = data;
        id = duplicateID ? 0 : nextID++;
        disputes[id] = D(msg.sender, DisputeStatus.Waiting, 0, 0, 0);
        if (attack) { (reentered,) = msg.sender.call(abi.encodeWithSignature("fundReserve()")); }
        if (malformed) { assembly ("memory-safe") { return(0, 0) } }
    }
    function setAppealable(uint256 id, uint256 ruling) external {
        D storage d = disputes[id]; d.status = DisputeStatus.Appealable;
        d.ruling = ruling; d.start = block.timestamp; d.end = block.timestamp + 100;
    }
    function appealCost(uint256, bytes calldata) external view returns (uint256) { return appealFee; }
    function appealPeriod(uint256 id) external view returns (uint256, uint256) { return (disputes[id].start, disputes[id].end); }
    function appeal(uint256 id, bytes calldata data) external payable {
        D storage d = disputes[id];
        require(msg.sender == d.arb && d.status == DisputeStatus.Appealable && msg.value == appealFee, "appeal");
        require(block.timestamp < d.end, "period");
        lastData = data; d.status = DisputeStatus.Waiting;
    }
    function disputeStatus(uint256 id) external view returns (DisputeStatus) { return disputes[id].status; }
    function currentRuling(uint256 id) external view returns (uint256) { return disputes[id].ruling; }
    function deliver(uint256 id, uint256 ruling) external {
        D storage d = disputes[id]; d.status = DisputeStatus.Solved; d.ruling = ruling;
        IArbitrable(d.arb).rule(id, ruling);
    }
}

/// ABI-compatible host fixture. Payouts use send; it is NOT a complete GTCR.
abstract contract HostBase {
    address public governor;
    uint256 public challengePeriodDuration = 100;
    IArbitrator public active;
    bool public failRule;
    bool public attack;
    bool public reentered;
    bool public zeroParty;
    bool public wrongID;
    bool public wrongEnvelope;
    struct Req {
        address payable requester; address payable challenger; IArbitrator arb;
        bytes extra; uint256 submitted; uint256 id; uint256 pot; bool disputed; bool resolved; uint8 ruling;
    }
    struct Item { uint8 status; Req[] requests; }
    mapping(bytes32 => Item) internal items;
    mapping(address => mapping(uint256 => bytes32)) internal mappingFor;
    constructor() { governor = msg.sender; }
    function point(IArbitrator value) external { require(msg.sender == governor); active = value; }
    function setPeriod(uint256 value) external { require(msg.sender == governor); challengePeriodDuration = value; }
    function setFailRule(bool value) external { failRule = value; }
    function setAttack(bool value) external { attack = value; }
    function setBadProfile(bool zero_, bool id_, bool envelope_) external { zeroParty = zero_; wrongID = id_; wrongEnvelope = envelope_; }
    function submit(bytes32 item, bool removal, bytes calldata extra) external payable {
        uint256 q = active.arbitrationCost(extra); require(msg.value == 30 + q, "submit fee");
        Item storage i = items[item];
        if (i.requests.length != 0) require(i.requests[i.requests.length - 1].resolved, "pending");
        i.status = removal ? 3 : 2;
        i.requests.push(); Req storage r = i.requests[i.requests.length - 1];
        r.requester = payable(msg.sender); r.arb = active; r.extra = extra; r.pot = msg.value; r.submitted = block.timestamp;
    }
    function challenge(bytes32 item) external payable returns (uint256 id) {
        Item storage i = items[item]; Req storage r = i.requests[i.requests.length - 1];
        require(!r.disputed && !r.resolved, "not challengeable");
        require(block.timestamp <= r.submitted + challengePeriodDuration, "expired");
        uint256 q = r.arb.arbitrationCost(r.extra); require(msg.value == q, "challenge fee");
        r.challenger = payable(msg.sender);
        // Mapping becomes visible only AFTER the wrapper's callback returns.
        id = r.arb.createDispute{value: q}(2, r.extra);
        r.id = id; r.disputed = true; mappingFor[address(r.arb)][id] = item;
    }
    function rule(uint256 id, uint256 ruling) external {
        require(!failRule, "host failure");
        bytes32 item = mappingFor[msg.sender][id]; Item storage i = items[item];
        Req storage r = i.requests[i.requests.length - 1];
        require(msg.sender == address(r.arb) && r.disputed && !r.resolved && r.id == id, "host authority");
        require(ruling <= 2, "ruling");
        r.resolved = true; r.ruling = uint8(ruling);
        i.status = ruling == 1 ? 1 : 0;
        if (attack) { (reentered,) = msg.sender.call(abi.encodeWithSignature("claim(address)", address(this))); }
        uint256 amount = r.pot; r.pot = 0;
        if (ruling == 0) { r.requester.send(amount / 2); r.challenger.send(amount / 2); }
        else if (ruling == 1) r.requester.send(amount); else r.challenger.send(amount);
    }
    function appealThroughHost(bytes32 item) external payable {
        Item storage i = items[item]; Req storage r = i.requests[i.requests.length - 1];
        r.arb.appeal{value: msg.value}(r.id, r.extra);
    }
    function getRequestInfo(bytes32 item, uint256 index) external view returns (
        bool, uint256, uint256, bool, address payable[3] memory parties,
        uint256, uint8, address, bytes memory, uint256
    ) {
        Req storage r = items[item].requests[index];
        parties[1] = zeroParty ? payable(address(0)) : r.requester; parties[2] = r.challenger;
        return (r.disputed, wrongID ? r.id + 1 : r.id, r.submitted, r.resolved, parties, 2,
            r.ruling, address(r.arb), wrongEnvelope ? bytes("bad") : r.extra, 0);
    }
}
contract LightHost is HostBase {
    function arbitratorDisputeIDToItemID(address arb, uint256 id) external view returns (bytes32) { return mappingFor[arb][id]; }
    function getItemInfo(bytes32 item) external view returns (uint8, uint256, uint256) {
        Item storage i = items[item]; return (i.status, i.requests.length, 0);
    }
}
contract ClassicHost is HostBase {
    function arbitratorDisputeIDToItem(address arb, uint256 id) external view returns (bytes32) { return mappingFor[arb][id]; }
    function getItemInfo(bytes32 item) external view returns (bytes memory, uint8, uint256) {
        Item storage i = items[item]; return (bytes("descriptor"), i.status, i.requests.length);
    }
}
contract Rejector { receive() external payable { revert("no push"); } }
contract ClaimReentry {
    IntendmentArbitrator public wrapper;
    bool public reentered;
    constructor(IntendmentArbitrator value) { wrapper = value; }
    receive() external payable { (reentered,) = address(wrapper).call(abi.encodeCall(wrapper.claim, (payable(address(this))))); }
}
contract ForceETH {
    constructor() payable {}
    function force(address payable to) external { selfdestruct(to); }
}
