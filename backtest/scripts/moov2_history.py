"""Upgrade / initialization / role history of the MOOV2 proxy (read-only eth_getLogs)."""
import json, datetime as dt
from eth_utils import keccak
import rpc
M = "0x2C0367a9DB231dDeBd88a94b4f6461a6e47C58B1"
sigs = {"Upgraded(address)": None, "Initialized(uint64)": None, "RoleGranted(bytes32,address,address)": None,
        "RoleRevoked(bytes32,address,address)": None, "DefaultLivenessUpdated(uint256)": None,
        "MinimumDisputeWindowUpdated(uint256)": None, "AllowedBondRangeUpdated(address,uint256,uint256)": None,
        "DefaultProposerWhitelistUpdated(address)": None, "RequesterWhitelistUpdated(address)": None}
T = {"0x" + keccak(text=s).hex(): s for s in sigs}
roles = {"0x" + keccak(text=r).hex(): r for r in ("RESOLVER_ROLE", "RESOLVER_ADMIN_ROLE", "REQUEST_MANAGER", "REQUEST_MANAGER_ROLE", "CONFIG_ADMIN_ROLE", "UPGRADE_ADMIN_ROLE")}
roles["0x" + "00" * 32] = "DEFAULT_ADMIN_ROLE"
out = []
start, end, step = 74677000, 94795000, 500000
s = start
while s <= end:
    e = min(end, s + step - 1)
    for attempt in range(5):
        try:
            logs = rpc.get_logs(M, [list(T)], s, e, endpoint="https://polygon.gateway.tenderly.co", timeout=120)
            break
        except Exception as ex:
            print("retry", s, e, str(ex)[:100]); logs = None
    if logs is None:
        raise SystemExit("failed")
    for l in logs:
        rec = {"block": int(l["blockNumber"], 16), "ts": int(l.get("blockTimestamp", "0x0"), 16), "event": T[l["topics"][0]],
               "topics": l["topics"][1:], "data": l["data"], "tx": l["transactionHash"]}
        rec["utc"] = dt.datetime.fromtimestamp(rec["ts"], dt.timezone.utc).isoformat() if rec["ts"] else None
        if rec["event"].startswith("Role"):
            rec["role"] = roles.get(l["topics"][1], l["topics"][1]); rec["account"] = "0x" + l["topics"][2][-40:]
        if rec["event"] == "Upgraded(address)":
            rec["implementation"] = "0x" + l["topics"][1][-40:]
        out.append(rec)
    s = e + 1
json.dump(out, open("../data/moov2_admin_history.json", "w"), indent=1)
for r in out:
    print(r["utc"], r["block"], r["event"], r.get("implementation") or r.get("role", ""), r.get("account", ""), r["data"][:66] if r["event"] not in ("Upgraded(address)",) and not r["event"].startswith("Role") else "")
