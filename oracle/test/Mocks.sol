// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

interface Vm {
    function warp(uint256) external;
    function prank(address) external;
    function startPrank(address) external;
    function stopPrank() external;
    function expectRevert(bytes4) external;
    function expectRevert() external;
}

contract MockToken {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;
    uint8 public constant decimals = 6;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        require(balanceOf[msg.sender] >= amount, "balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        require(allowance[from][msg.sender] >= amount, "allowance");
        require(balanceOf[from] >= amount, "balance");
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

contract MockStore {
    uint256 public fee;

    function setFee(uint256 f) external {
        fee = f;
    }

    function computeFinalFee(address) external view returns (uint256) {
        return fee;
    }
}

contract MockFinder {
    address public store;

    constructor(address s) {
        store = s;
    }

    function getImplementationAddress(bytes32 name) external view returns (address) {
        require(name == "Store", "finder");
        return store;
    }
}

/// Stand-in for UMA's OptimisticOracleV2 with its money rules: both stakes are bond + final fee,
/// the Store receives final fee + floor(bond/2) in the dispute transaction, and the winner later
/// receives bond + (bond - floor(bond/2)) + final fee.
contract MockOO {
    struct Req {
        bool exists;
        address proposer;
        address disputer;
        uint256 bond;
        uint256 fee;
        uint256 liveness;
        uint256 expiration;
        int256 proposed;
        bool resolved;
        int256 price;
        bool settled;
    }

    MockToken public immutable token;
    address public immutable finder;
    address public immutable store;
    mapping(bytes32 => Req) public reqs;
    uint256 public storeReceived;
    bool public rejectAll;

    constructor(MockToken t, address f, address s) {
        token = t;
        finder = f;
        store = s;
    }

    function setRejectAll(bool v) external {
        rejectAll = v;
    }

    function key(address requester, bytes32 id, uint256 t, bytes memory anc) public pure returns (bytes32) {
        return keccak256(abi.encode(requester, id, t, anc));
    }

    function requestPrice(bytes32 id, uint256 t, bytes memory anc, address, uint256 reward) external returns (uint256) {
        require(!rejectAll, "rejected");
        require(t <= block.timestamp, "future");
        Req storage r = reqs[key(msg.sender, id, t, anc)];
        require(!r.exists, "exists");
        require(reward == 0, "reward");
        r.exists = true;
        r.fee = MockStore(store).fee();
        r.liveness = 7200;
        return 0;
    }

    function setBond(bytes32 id, uint256 t, bytes memory anc, uint256 bond) external returns (uint256) {
        Req storage r = reqs[key(msg.sender, id, t, anc)];
        require(r.exists && r.proposer == address(0), "state");
        r.bond = bond;
        return bond + r.fee;
    }

    function setCustomLiveness(bytes32 id, uint256 t, bytes memory anc, uint256 liveness) external {
        Req storage r = reqs[key(msg.sender, id, t, anc)];
        require(r.exists && r.proposer == address(0) && liveness > 0, "state");
        r.liveness = liveness;
    }

    function proposePriceFor(address proposer, address requester, bytes32 id, uint256 t, bytes memory anc, int256 price)
        external
        returns (uint256 total)
    {
        Req storage r = reqs[key(requester, id, t, anc)];
        require(r.exists && r.proposer == address(0), "state");
        total = r.bond + r.fee;
        token.transferFrom(msg.sender, address(this), total);
        r.proposer = proposer;
        r.proposed = price;
        r.expiration = block.timestamp + r.liveness;
    }

    function disputePriceFor(address disputer, address requester, bytes32 id, uint256 t, bytes memory anc)
        external
        returns (uint256 total)
    {
        Req storage r = reqs[key(requester, id, t, anc)];
        require(r.proposer != address(0) && r.disputer == address(0) && block.timestamp < r.expiration, "state");
        total = r.bond + r.fee;
        token.transferFrom(msg.sender, address(this), total);
        r.disputer = disputer;
        uint256 toStore = r.fee + r.bond / 2;
        token.transfer(store, toStore);
        storeReceived += toStore;
    }

    /// Test hook standing in for the vote's answer arriving through the bridge.
    function pushPrice(address requester, bytes32 id, uint256 t, bytes memory anc, int256 price) external {
        Req storage r = reqs[key(requester, id, t, anc)];
        require(r.disputer != address(0), "not disputed");
        r.resolved = true;
        r.price = price;
    }

    function settleAndGetPrice(bytes32 id, uint256 t, bytes memory anc) external returns (int256) {
        Req storage r = reqs[key(msg.sender, id, t, anc)];
        require(r.resolved, "not settleable");
        if (!r.settled) {
            r.settled = true;
            address winner = r.price != r.proposed ? r.disputer : r.proposer;
            token.transfer(winner, r.bond + (r.bond - r.bond / 2) + r.fee);
        }
        return r.price;
    }
}

interface IModule {
    function initializeReporterModule(bytes29 eventId, bytes calldata data) external;
}

/// Stand-in for Polymarket's V2 OracleAggregator: request shapes, one vote per module per request.
contract MockAggregator {
    mapping(bytes29 => address) public reporterOf;
    mapping(bytes29 => uint8) public marketTypeOf;
    mapping(bytes32 => bool) public voted;
    mapping(bytes32 => uint256) public reported;
    bool public paused;

    function setPaused(bool v) external {
        paused = v;
    }

    function initializeRequest(bytes29 eventId, uint8 marketType, address module, bytes calldata data) external {
        require(reporterOf[eventId] == address(0), "exists");
        reporterOf[eventId] = module;
        marketTypeOf[eventId] = marketType;
        IModule(module).initializeReporterModule(eventId, data);
    }

    function getRequestShape(bytes32 requestId) external view returns (uint8, uint16) {
        require(reporterOf[bytes29(requestId)] != address(0), "unknown");
        return (marketTypeOf[bytes29(requestId)], 1);
    }

    function reportResult(bytes32 requestId, uint256[] calldata result) external {
        require(!paused, "paused");
        require(reporterOf[bytes29(requestId)] == msg.sender, "not reporter");
        require(!voted[requestId], "voted");
        require(result.length == 1, "length");
        voted[requestId] = true;
        reported[requestId] = result[0];
    }
}

contract MockWhitelist {
    mapping(address => bool) public isOnWhitelist;

    function set(address who, bool v) external {
        isOnWhitelist[who] = v;
    }
}
