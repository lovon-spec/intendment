"""Second completeness spot-check: OOv2 chunks via publicnode (1000-block pieces) and one MOOV2
chunk via drpc (100-block pieces). Appends to data/crosscheck.json."""
import gzip, json, os, random
import rpc
from fetch_logs import TOPIC, OO
random.seed(11)
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
topics = [[TOPIC[e] for e in ("RequestPrice", "ProposePrice", "DisputePrice", "Settle", "BondUpdated", "CustomBondSet", "PayoutDeferred")]]
prev = json.load(open(os.path.join(D, "crosscheck.json"))) if os.path.exists(os.path.join(D, "crosscheck.json")) else []
res = []
def count(oo, a, b, ep, piece):
    n, s = 0, a
    while s <= b:
        e = min(b, s + piece - 1)
        n += len(rpc.get_logs(OO[oo], topics, s, e, endpoint=ep, timeout=90))
        s = e + 1
    return n
plan = []
oof = sorted(f for f in os.listdir(os.path.join(D, "raw", "OOv2")) if f.endswith(".jsonl.gz"))
# pick OOv2 chunks that actually contain logs
nonempty = [f for f in oof if os.path.getsize(os.path.join(D, "raw", "OOv2", f)) > 200]
plan += [("OOv2", f, "https://polygon-bor-rpc.publicnode.com", 1000) for f in random.sample(nonempty, 4)]
mf = sorted(f for f in os.listdir(os.path.join(D, "raw", "MOOV2")) if f.endswith(".jsonl.gz"))
plan += [("MOOV2", random.choice(mf), "https://polygon.drpc.org", 100)]
for oo, f, ep, piece in plan:
    a, b = int(f.split("-")[0]), int(f.split("-")[1].split(".")[0])
    stored = sum(1 for _ in gzip.open(os.path.join(D, "raw", oo, f), "rt"))
    try:
        n = count(oo, a, b, ep, piece)
        r = {"oo": oo, "range": f"{a}-{b}", "stored": stored, ep.split("/")[2]: n, "match": stored == n}
    except Exception as e:
        r = {"oo": oo, "range": f"{a}-{b}", "stored": stored, "error": str(e)[:200]}
    print(r, flush=True); res.append(r)
json.dump(prev + res, open(os.path.join(D, "crosscheck.json"), "w"), indent=1)
