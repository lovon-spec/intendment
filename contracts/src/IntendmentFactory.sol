// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {IArbitrator, IRegistry} from "./Interfaces.sol";
import {HostProfiles} from "./HostProfiles.sol";
import {IntendmentArbitrator} from "./IntendmentArbitrator.sol";

/// Deploys plain instances; only the host's current governor may request one.
/// CREATE2 salted by host, governor and a per-host counter that only deploy() advances, so a
/// governor can schedule calls to its wrapper before it exists and nobody else can take that address.
contract IntendmentFactory {
    mapping(address => bool) public isWrapper;
    mapping(address => uint256) public deployments;
    event WrapperDeployed(address indexed host, address indexed wrapper, address governor);
    function deploy(address host, IArbitrator resolver, HostProfiles.Profile profile,
        IntendmentArbitrator.Config calldata config) external returns (IntendmentArbitrator wrapper)
    {
        require(IRegistry(host).governor() == msg.sender, "host governor only");
        bytes32 salt = keccak256(abi.encode(host, msg.sender, deployments[host]++));
        wrapper = new IntendmentArbitrator{salt: salt}(host, resolver, msg.sender, profile, config);
        isWrapper[address(wrapper)] = true;
        emit WrapperDeployed(host, address(wrapper), msg.sender);
    }
    /// The address of the host's n-th wrapper (counting from 0) if `governor` deploys it with these arguments.
    function predict(address host, address governor, uint256 n, IArbitrator resolver, HostProfiles.Profile profile,
        IntendmentArbitrator.Config calldata config) external view returns (address)
    {
        bytes32 initCode = keccak256(abi.encodePacked(type(IntendmentArbitrator).creationCode,
            abi.encode(host, resolver, governor, profile, config)));
        bytes32 salt = keccak256(abi.encode(host, governor, n));
        return address(uint160(uint256(keccak256(abi.encodePacked(bytes1(0xff), address(this), salt, initCode)))));
    }
}
