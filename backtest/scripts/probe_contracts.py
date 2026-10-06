"""Step 1 probe: confirm on-chain which oracle each Polymarket adapter uses, and read the
MOOV2 whitelists. Read-only eth_call / eth_getCode only."""
import json, sys
from eth_utils import keccak, to_checksum_address
from eth_abi import decode
import rpc

def sel(sig): return "0x" + keccak(text=sig)[:4].hex()

ADAPTERS = {
  "UmaCtfAdapter v1.0.0": "0xCB1822859cEF82Cd2Eb4E6276C7916e692995130",
  "UmaCtfAdapter v1.0.1": "0xB97455fcF78eb37375e8be6f26df895341CA073d",
  "UmaCtfAdapter v2.0.0": "0x6A9D222616C90FcA5754cd1333cFD9b7fb6a4F74",
  "UmaCtfAdapter v3.0.0": "0x71392E133063CC0D16F40E1F9B60227404Bc03f7",
  "UmaCtfAdapter v3.1.0": "0x157Ce2d672854c848c9b79C49a8Cc6cc89176a49",
  "NegRiskUmaCtfAdapter (neg-risk repo addresses.json)": "0x2F5e3684cb1F318ec51b00Edba38d79Ac2c0aA9d",
  "MOOV2 EXISTING_REQUESTER_1": "0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7",
  "MOOV2 EXISTING_REQUESTER_2": "0x69c47De9D4D3Dad79590d61b9e05918E03775f24",
}
out = {}
for name, a in ADAPTERS.items():
    rec = {"address": a}
    code = rpc.call("eth_getCode", [a, "latest"])
    rec["codesize"] = (len(code) - 2) // 2
    for fn in ("optimisticOracle()", "ctf()", "nrAdapter()", "collateral()" ):
        try:
            r = rpc.eth_call(a, sel(fn))
            rec[fn] = to_checksum_address("0x" + r[-40:]) if len(r) >= 66 else r
        except Exception as e:
            rec[fn] = f"ERR {str(e)[:60]}"
    out[name] = rec
    print(name, json.dumps(rec))

for wname, w in (("requesterWhitelist", "0x0f79d0039956D58a7d5d006a6Dd64a35616Aa2c6"),
                 ("defaultProposerWhitelist", "0x9F35885CE8f67a942D7B2f4Fbf937987DA08c463")):
    r = rpc.eth_call(w, sel("getWhitelist()"))
    (lst,) = decode(["address[]"], bytes.fromhex(r[2:]))
    out[wname] = [to_checksum_address(x) for x in lst]
    print(wname, len(lst), out[wname])

# MOOV2 config reads
M = "0x2C0367a9DB231dDeBd88a94b4f6461a6e47C58B1"
for fn in ("defaultLiveness()", "minimumDisputeWindow()", "requesterWhitelist()", "defaultProposerWhitelist()", "finder()"):
    try:
        r = rpc.eth_call(M, sel(fn)); out["MOOV2 " + fn] = r; print("MOOV2", fn, r)
    except Exception as e:
        print("MOOV2", fn, "ERR", str(e)[:80])
# EIP-1967 implementation slot
impl = rpc.call("eth_getStorageAt", [M, "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc", "latest"])
out["MOOV2 implementation"] = "0x" + impl[-40:]
print("MOOV2 implementation", "0x" + impl[-40:])
json.dump(out, open("../data/contracts_probe.json", "w"), indent=1)
