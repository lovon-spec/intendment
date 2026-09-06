// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;

/// ERC-792 native-currency arbitrator surface. V2/ERC-20 is deliberately excluded.
interface IArbitrator {
    enum DisputeStatus { Waiting, Appealable, Solved }
    function arbitrationCost(bytes calldata extraData) external view returns (uint256);
    function createDispute(uint256 choices, bytes calldata extraData) external payable returns (uint256);
    function appealCost(uint256 disputeID, bytes calldata extraData) external view returns (uint256);
    function appealPeriod(uint256 disputeID) external view returns (uint256, uint256);
    function appeal(uint256 disputeID, bytes calldata extraData) external payable;
    function disputeStatus(uint256 disputeID) external view returns (DisputeStatus);
    function currentRuling(uint256 disputeID) external view returns (uint256);
}
interface IArbitrable { function rule(uint256 disputeID, uint256 ruling) external; }
interface IRegistry {
    function governor() external view returns (address);
    function challengePeriodDuration() external view returns (uint256);
    function getRequestInfo(bytes32 item, uint256 request) external view returns (
        bool disputed, uint256 disputeID, uint256 submittedAt, bool resolved,
        address payable[3] memory parties, uint256 rounds, uint8 ruling,
        address arbitrator, bytes memory extraData, uint256 metaEvidenceID
    );
}
interface ILightRegistry is IRegistry {
    function arbitratorDisputeIDToItemID(address arbitrator, uint256 id) external view returns (bytes32);
    function getItemInfo(bytes32 item) external view returns (uint8 status, uint256 requests, uint256 unusedDeposit);
}
interface IClassicRegistry is IRegistry {
    function arbitratorDisputeIDToItem(address arbitrator, uint256 id) external view returns (bytes32);
    function getItemInfo(bytes32 item) external view returns (bytes memory data, uint8 status, uint256 requests);
}
interface IWrapperFactory {
    function isWrapper(address wrapper) external view returns (bool);
}
interface IMigrationTarget {
    function HOST() external view returns (address);
    function FACTORY() external view returns (address);
    function receiveSurplus() external payable;
}
