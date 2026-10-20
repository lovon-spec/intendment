// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {IArbitrator, IRegistry} from "./Interfaces.sol";
import {HostProfiles} from "./HostProfiles.sol";
import {IntendmentArbitrator} from "./IntendmentArbitrator.sol";

/// Deploys plain instances; only the host's current governor may request one.
contract IntendmentFactory {
    mapping(address => bool) public isWrapper;
    event WrapperDeployed(address indexed host, address indexed wrapper, address governor);
    function deploy(address host, IArbitrator resolver, HostProfiles.Profile profile,
        IntendmentArbitrator.Config calldata config) external returns (IntendmentArbitrator wrapper)
    {
        require(IRegistry(host).governor() == msg.sender, "host governor only");
        wrapper = new IntendmentArbitrator(host, resolver, msg.sender, profile, config);
        isWrapper[address(wrapper)] = true;
        emit WrapperDeployed(host, address(wrapper), msg.sender);
    }
}
