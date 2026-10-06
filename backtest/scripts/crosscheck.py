"""Completeness spot-check: re-count a sample of chunks on a second public RPC and compare with
the stored chunk files (same address/topics/range)."""
import gzip, json, os, random, sys
import rpc
from fetch_logs import TOPIC, OO
random.seed(7)
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw")
topics = [[TOPIC[e] for e in ("RequestPrice", "ProposePrice", "DisputePrice", "Settle", "BondUpdated", "CustomBondSet", "PayoutDeferred")]]
res = []
for oo in ("MOOV2", "OOv2"):
    files = sorted(f for f in os.listdir(os.path.join(D, oo)) if f.endswith(".jsonl.gz"))
    for f in random.sample(files, 6 if oo == "MOOV2" else 4):
        a, b = int(f.split("-")[0]), int(f.split("-")[1].split(".")[0])
        stored = sum(1 for _ in gzip.open(os.path.join(D, oo, f), "rt"))
        # second source: onfinality (public), split into 500-block pieces to keep responses small
        n = 0
        s = a
        while s <= b:
            e = min(b, s + 499)
            n += len(rpc.get_logs(OO[oo], topics, s, e, endpoint="https://polygon.api.onfinality.io/public", timeout=120))
            s = e + 1
        res.append({"oo": oo, "range": f"{a}-{b}", "stored": stored, "onfinality": n, "match": stored == n})
        print(res[-1], flush=True)
json.dump(res, open(os.path.join(D, "..", "crosscheck.json"), "w"), indent=1)
