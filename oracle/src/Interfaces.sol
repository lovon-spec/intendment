// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// Minimal interfaces for the contracts the module calls. Only the functions used here are
/// declared; the ABI is what matters, so no upstream source is copied.

interface IERC20Like {
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
    function approve(address spender, uint256 amount) external returns (bool);
    function balanceOf(address who) external view returns (uint256);
}

/// UMA OptimisticOracleV2 (the legacy, permissionless deployment on Polygon).
interface IOptimisticOracleV2Like {
    function requestPrice(bytes32 identifier, uint256 timestamp, bytes memory ancillaryData, address currency, uint256 reward)
        external
        returns (uint256 totalBond);
    function setBond(bytes32 identifier, uint256 timestamp, bytes memory ancillaryData, uint256 bond)
        external
        returns (uint256 totalBond);
    function setCustomLiveness(bytes32 identifier, uint256 timestamp, bytes memory ancillaryData, uint256 customLiveness)
        external;
    function proposePriceFor(
        address proposer,
        address requester,
        bytes32 identifier,
        uint256 timestamp,
        bytes memory ancillaryData,
        int256 proposedPrice
    ) external returns (uint256 totalBond);
    function disputePriceFor(
        address disputer,
        address requester,
        bytes32 identifier,
        uint256 timestamp,
        bytes memory ancillaryData
    ) external returns (uint256 totalBond);
    function settleAndGetPrice(bytes32 identifier, uint256 timestamp, bytes memory ancillaryData)
        external
        returns (int256);
    function finder() external view returns (address);
}

interface IFinderLike {
    function getImplementationAddress(bytes32 interfaceName) external view returns (address);
}

/// UMA Store. `computeFinalFee` returns a FixedPoint.Unsigned, a one-word struct that is
/// ABI-identical to a uint256.
interface IStoreLike {
    function computeFinalFee(address currency) external view returns (uint256);
}

/// UMA AddressWhitelist, the type of UMA's default proposer whitelist.
interface IAddressWhitelistLike {
    function isOnWhitelist(address who) external view returns (bool);
}

/// Polymarket Protocol V2 OracleAggregator: the calls a reporter module makes.
interface IOracleAggregatorLike {
    function reportResult(bytes32 requestId, uint256[] calldata result) external;
    function getRequestShape(bytes32 requestId) external view returns (uint8 marketType, uint16 resultLength);
}

/// Polymarket Protocol V2 reporter-module interface. EventId is a bytes29 value type upstream;
/// its ABI type is bytes29.
interface IReporterModuleLike {
    function initializeReporterModule(bytes29 eventId, bytes calldata data) external;
    function updateRules(bytes32 requestId, bytes calldata updatedRules) external;
}
