"""Stage 2: fill bond / finalFee / reward / currency for requests whose RequestPrice (or BondUpdated)
event predates the fetched block range (markets created long before they resolve).

For each such request that has a ProposePrice in the fetched range:
  1. re-fetch that block's ProposePrice logs to recover the full ancillaryData bytes
     (the compact store keeps only its keccak hash), matching on logIndex;
  2. eth_call getRequest(requester, identifier, timestamp, ancillaryData) on the oracle
     (read-only) and decode RequestSettings.bond, finalFee, reward, currency.
Results are checkpointed to data/enrich_getRequest.jsonl (append-only, resumable).
"""
import gzip
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from eth_abi import decode, encode
from eth_utils import keccak, to_checksum_address

import rpc

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(DATA, "enrich_getRequest.jsonl")
T_PROPOSE = "0x" + keccak(text="ProposePrice(address,address,bytes32,uint256,bytes,int256,uint256,address)").hex()
SEL_GETREQ = keccak(text="getRequest(address,bytes32,uint256,bytes)")[:4]
BIG = ["https://polygon.gateway.tenderly.co", "https://polygon.api.onfinality.io/public"]
W0 = 1783036800  # 2026-07-03T00:00:00Z

_lock = threading.Lock()


W1 = 1790812800  # 2026-10-01T00:00:00Z


def needs(q):
    """Proposal relevant to the window whose finalFee/reward are unknown (RequestPrice before the
    fetched range), or whose bond cannot be derived (no BondUpdated and not settled)."""
    if "prop_ts" not in q:
        return False
    st = q.get("settle_ts")
    relevant = (q["prop_ts"] < W1 and (st is None or st >= W0)) or (q.get("disp_ts") or 0) >= W0
    missing_params = "finalFee" not in q or "reward" not in q
    missing_bond = "bond_ev" not in q and st is None
    return relevant and (missing_params or missing_bond)


_cache = {}


def _block_logs(oo, req_topic, block):
    k = (oo, req_topic, block)
    with _lock:
        if k in _cache:
            return _cache[k]
    logs = None
    for i in range(4):
        try:
            logs = rpc.get_logs(oo, [T_PROPOSE, req_topic], block, block, endpoint=BIG[i % 2])
            break
        except Exception:  # noqa
            logs = None
    if logs is not None:
        with _lock:
            if len(_cache) > 2000:
                _cache.clear()
            _cache[k] = logs
    return logs or []


def fetch_one(q):
    oo = q["oo"]  # checksummed oracle address
    req_topic = "0x" + "0" * 24 + q["requester"][2:].lower()
    anc = None
    for i in range(1):
        try:
            logs = _block_logs(oo, req_topic, q["prop_block"])
            for l in logs:
                if int(l["logIndex"], 16) == q["prop_li"] and l["transactionHash"] == q["prop_tx"]:
                    vals = decode(["bytes32", "uint256", "bytes", "int256", "uint256", "address"], bytes.fromhex(l["data"][2:]))
                    anc = vals[2]
                    break
            if anc is not None:
                break
        except Exception as e:  # noqa
            err = str(e)
    if anc is None:
        return {"key": q["key"], "error": "anc not found"}
    if "0x" + keccak(anc).hex() != q["ancHash"]:
        return {"key": q["key"], "error": "anc hash mismatch"}
    ident = q["identifier"].encode("latin-1").ljust(32, b"\0")
    data = "0x" + (SEL_GETREQ + encode(["address", "bytes32", "uint256", "bytes"],
                                         [q["requester"], ident, q["timestamp"], anc])).hex()
    res = None
    for i in range(4):
        try:
            res = rpc.call("eth_call", [{"to": oo, "data": data}, "latest"], endpoint=BIG[i % 2], timeout=60)
            break
        except Exception as e:  # noqa
            res = None
    if not res:
        return {"key": q["key"], "error": "eth_call failed"}
    b = bytes.fromhex(res[2:])
    words = [b[i:i + 32] for i in range(0, len(b), 32)]
    u = lambda w: int.from_bytes(w, "big")
    s = lambda w: int.from_bytes(w, "big", signed=True)
    rec = {
        "key": q["key"],
        "proposer": to_checksum_address(words[0][-20:]), "disputer": to_checksum_address(words[1][-20:]),
        "currency": to_checksum_address(words[2][-20:]), "settled": bool(u(words[3])),
        "eventBased": bool(u(words[4])), "refundOnDispute": bool(u(words[5])),
        "cbProposed": bool(u(words[6])), "cbDisputed": bool(u(words[7])), "cbSettled": bool(u(words[8])),
        "bond": u(words[9]), "customLiveness": u(words[10]), "proposedPrice": str(s(words[11])),
        "resolvedPrice": str(s(words[12])), "expirationTime": u(words[13]), "reward": u(words[14]),
        "finalFee": u(words[15]), "nwords": len(words),
    }
    if len(words) > 16:
        rec["proposalTime"] = u(words[16])
    return rec


def main():
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT):
            r = json.loads(line)
            if "error" not in r:
                done.add(r["key"])
    todo = []
    with gzip.open(os.path.join(DATA, "requests_polymarket.jsonl.gz"), "rt") as f:
        for line in f:
            q = json.loads(line)
            if needs(q) and q["key"] not in done:
                todo.append(q)
    print(f"to enrich: {len(todo)} (already done {len(done)})", flush=True)
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    n = 0
    with open(OUT, "a") as out, ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fetch_one, q) for q in todo]
        for fu in as_completed(futs):
            try:
                rec = fu.result()
            except Exception as e:  # noqa
                rec = {"key": "?", "error": str(e)[:200]}
            with _lock:
                out.write(json.dumps(rec) + "\n")
                n += 1
                if n % 500 == 0:
                    out.flush()
                    print(f"{n}/{len(todo)}", flush=True)
    print("done", n)


if __name__ == "__main__":
    main()
