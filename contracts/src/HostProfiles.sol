// SPDX-License-Identifier: MIT
pragma solidity 0.8.30;
import {IRegistry, ILightRegistry, IClassicRegistry} from "./Interfaces.sol";

/// Getter ABIs pinned to kleros/tcr commit 72e547ea135d839dc5db34e79e9f94f05c6a92bb.
/// Immutable selection, no router, delegatecall or recoverable tx.origin identity.
library HostProfiles {
    enum Profile { Light, Classic }
    struct Binding {
        bytes32 item;
        uint256 requestIndex;
        address requester;
        address challenger;
        bool removal;
        uint256 metaEvidenceID;
    }
    error InvalidBinding();

    function read(address host, address wrapper, uint256 id, Profile profile, bytes32 envelopeHash)
        internal view returns (Binding memory b)
    {
        uint8 status;
        uint256 count;
        if (profile == Profile.Light) {
            b.item = ILightRegistry(host).arbitratorDisputeIDToItemID(wrapper, id);
            (status, count,) = ILightRegistry(host).getItemInfo(b.item);
        } else {
            b.item = IClassicRegistry(host).arbitratorDisputeIDToItem(wrapper, id);
            (, status, count) = IClassicRegistry(host).getItemInfo(b.item);
        }
        if (count == 0 || (status != 2 && status != 3)) revert InvalidBinding();
        b.requestIndex = count - 1;
        bool disputed;
        bool resolved;
        uint256 reportedID;
        address payable[3] memory parties;
        address arbitrator;
        bytes memory extra;
        (disputed, reportedID,, resolved, parties,,, arbitrator, extra, b.metaEvidenceID) =
            IRegistry(host).getRequestInfo(b.item, b.requestIndex);
        if (!disputed || resolved || reportedID != id || arbitrator != wrapper
            || parties[1] == address(0) || parties[2] == address(0)
            || keccak256(extra) != envelopeHash) revert InvalidBinding();
        b.requester = parties[1];
        b.challenger = parties[2];
        b.removal = status == 3;
    }
}
