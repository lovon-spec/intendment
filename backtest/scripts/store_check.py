"""Independent check of UMA Store revenue: USDC.e Transfer(from=oracle, to=Store) logs in the window.
(Store.payOracleFeesErc20 pulls finalFee + floor(bond/2) from the oracle at each dispute.)
Note: includes disputes of non-Polymarket requesters on OOv2."""
import json
from eth_utils import keccak
import rpc
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
STORE = "0xE58480CA74f1A819faFd777BEDED4E2D5629943d"
OO = {"MOOV2": "0x2C0367a9DB231dDeBd88a94b4f6461a6e47C58B1", "OOv2": "0xeE3Afe347D5C74317041E2618C49534dAf887c24"}
T = "0x" + keccak(text="Transfer(address,address,uint256)").hex()
pad = lambda a: "0x" + "0" * 24 + a[2:].lower()
B0, B1 = 89554537, 94738439  # window blocks
out = {}
for name, oo in OO.items():
    tot, n, s = 0, 0, B0
    while s <= B1:
        e = min(B1, s + 499999)
        logs = rpc.get_logs(USDC, [T, pad(oo), pad(STORE)], s, e, endpoint="https://polygon.gateway.tenderly.co", timeout=120)
        tot += sum(int(l["data"], 16) for l in logs); n += len(logs)
        s = e + 1
    out[name] = {"transfers_to_store": n, "usd": tot / 1e6}
    print(name, out[name], flush=True)
json.dump(out, open("../data/store_transfers_check.json", "w"), indent=1)
