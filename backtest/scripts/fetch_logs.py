"""Pull and decode OO events from Polygon with eth_getLogs, chunked + checkpointed.

Usage:
  python3 fetch_logs.py --oo MOOV2 --from 90161323 --to 94791000 --chunk 2500 --workers 4

Each completed chunk is written atomically to data/raw/<OO>/<from>-<to>.jsonl.gz (decoded,
compact records, one JSON object per line). A chunk whose file exists is skipped, so the
script can be killed and re-run to resume. Failed chunks are retried with smaller ranges.

Records keep the keccak256 of ancillaryData (ancHash, == Polymarket questionID for the
UmaCtfAdapter family) rather than the full text, except for RequestPrice where a short
extract (title, market_id, initializer) is kept. Full text is not needed for the stats and
would be ~2 KB x several million events.
"""
import argparse
import gzip
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from eth_abi import decode
from eth_utils import keccak, to_checksum_address

import rpc

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

OO = {
    "MOOV2": "0x2C0367a9DB231dDeBd88a94b4f6461a6e47C58B1",  # ManagedOptimisticOracleV2 proxy (UMA)
    "OOv2": "0xeE3Afe347D5C74317041E2618C49534dAf887c24",   # OptimisticOracleV2 (UMA networks/137.json)
}

SIGS = {
    "RequestPrice": ("RequestPrice(address,bytes32,uint256,bytes,address,uint256,uint256)",
                     ["requester"],
                     [("bytes32", "identifier"), ("uint256", "timestamp"), ("bytes", "anc"), ("address", "currency"),
                      ("uint256", "reward"), ("uint256", "finalFee")]),
    "ProposePrice": ("ProposePrice(address,address,bytes32,uint256,bytes,int256,uint256,address)",
                     ["requester", "proposer"],
                     [("bytes32", "identifier"), ("uint256", "timestamp"), ("bytes", "anc"), ("int256", "proposedPrice"),
                      ("uint256", "expirationTimestamp"), ("address", "currency")]),
    "DisputePrice": ("DisputePrice(address,address,address,bytes32,uint256,bytes,int256)",
                     ["requester", "proposer", "disputer"],
                     [("bytes32", "identifier"), ("uint256", "timestamp"), ("bytes", "anc"), ("int256", "proposedPrice")]),
    "Settle": ("Settle(address,address,address,bytes32,uint256,bytes,int256,uint256)",
               ["requester", "proposer", "disputer"],
               [("bytes32", "identifier"), ("uint256", "timestamp"), ("bytes", "anc"), ("int256", "price"),
                ("uint256", "payout")]),
    # Emitted by the managed-oracle OOv2 base on setBond (present on MOOV2; absent on the 2022 OOv2).
    "BondUpdated": ("BondUpdated(address,bytes32,uint256,bytes,uint256,uint256)",
                    ["requester"],
                    [("bytes32", "identifier"), ("uint256", "timestamp"), ("bytes", "anc"), ("uint256", "oldBond"),
                     ("uint256", "newBond")]),
    # MOOV2 request-manager overrides (applied at proposal time) and blacklisted-recipient deferrals.
    "CustomBondSet": ("CustomBondSet(bytes32,address,bytes32,bytes,address,uint256)",
                      ["managedRequestId", "requester"],
                      [("bytes32", "identifier"), ("bytes", "anc"), ("address", "currency"), ("uint256", "bond")]),
    "PayoutDeferred": ("PayoutDeferred(address,address,uint256)",
                       ["currency", "recipient"],
                       [("uint256", "amount")]),
}
TOPIC = {k: "0x" + keccak(text=v[0]).hex() for k, v in SIGS.items()}
NAME = {v: k for k, v in TOPIC.items()}

RE_MID = re.compile(rb"market_id:\s*(\d+)")
RE_INIT = re.compile(rb"initializer:\s*(?:0x)?([0-9a-fA-F]{40})")
RE_TITLE = re.compile(rb"title:\s*(.{0,160}?)(?:, description:|\",\"description\"|$)", re.S)


def _extract(anc: bytes):
    out = {"ancLen": len(anc)}
    m = RE_MID.search(anc)
    if m:
        out["market_id"] = m.group(1).decode()
    m = RE_INIT.search(anc)
    if m:
        out["initializer"] = "0x" + m.group(1).decode().lower()
    m = RE_TITLE.search(anc)
    if m:
        out["title"] = m.group(1).decode("utf-8", "replace").strip()[:160]
    else:
        out["title"] = anc[:120].decode("utf-8", "replace")
    return out


def decode_log(l):
    t0 = l["topics"][0]
    ev = NAME[t0]
    sig, indexed, data = SIGS[ev]
    vals = decode([t for t, _ in data], bytes.fromhex(l["data"][2:]))
    rec = {"ev": ev, "oo": to_checksum_address(l["address"]), "block": int(l["blockNumber"], 16),
           "tx": l["transactionHash"], "li": int(l["logIndex"], 16)}
    if l.get("blockTimestamp"):
        rec["bts"] = int(l["blockTimestamp"], 16)
    for i, n in enumerate(indexed):
        raw = l["topics"][1 + i]
        rec[n] = raw if n == "managedRequestId" else to_checksum_address("0x" + raw[-40:])
    for (t, n), v in zip(data, vals):
        if n == "identifier":
            rec[n] = v.rstrip(b"\0").decode("latin-1")
        elif n == "anc":
            rec["ancHash"] = "0x" + keccak(v).hex()
            if ev == "RequestPrice":
                rec.update(_extract(v))
        elif t == "address":
            rec[n] = to_checksum_address(v)
        else:
            rec[n] = int(v)
    return rec


# Endpoint plan for big ranges. publicnode / drpc / 1rpc cap eth_getLogs ranges far below
# what this log density needs, so they are only used for small sub-ranges as a last resort.
BIG = ["https://polygon.gateway.tenderly.co", "https://polygon.api.onfinality.io/public"]
SMALL = [("https://polygon.drpc.org", 100), ("https://polygon-bor-rpc.publicnode.com", 10),
         ("https://1rpc.io/matic", 50)]

_stats_lock = threading.Lock()
STATS = {"chunks": 0, "logs": 0, "bytes": 0, "errors": 0, "split": 0}


def fetch_range(addr, topics, a, b, depth=0):
    """Return raw logs for [a, b]; tries big-range endpoints, splitting on range/size errors."""
    errs = []
    for attempt in range(6):
        ep = BIG[attempt % len(BIG)]
        try:
            return rpc.get_logs(addr, topics, a, b, endpoint=ep, timeout=120)
        except rpc.RpcError as e:
            errs.append(f"{ep.split('/')[2]}: {str(e)[:120]}")
            with _stats_lock:
                STATS["errors"] += 1
            msg = str(e).lower()
            if any(k in msg for k in ("range", "too many", "limit", "exceed", "size")) and b > a:
                break  # split
            time.sleep(2 + attempt * 2)
        except Exception as e:  # noqa
            errs.append(f"{ep.split('/')[2]}: {type(e).__name__} {str(e)[:120]}")
            time.sleep(2 + attempt * 2)
    if b - a + 1 > 200 and depth < 6:
        with _stats_lock:
            STATS["split"] += 1
        mid = (a + b) // 2
        return fetch_range(addr, topics, a, mid, depth + 1) + fetch_range(addr, topics, mid + 1, b, depth + 1)
    # last resort: small-range endpoints
    out = []
    for ep, cap in SMALL:
        try:
            out = []
            s = a
            while s <= b:
                e = min(b, s + cap - 1)
                out += rpc.get_logs(addr, topics, s, e, endpoint=ep, timeout=60)
                s = e + 1
            return out
        except Exception as e:  # noqa
            errs.append(f"{ep.split('/')[2]}: {str(e)[:120]}")
    raise RuntimeError(f"range {a}-{b} failed: {errs[-4:]}")


def run_chunk(oo_name, addr, topics, a, b, outdir):
    path = os.path.join(outdir, f"{a}-{b}.jsonl.gz")
    if os.path.exists(path):
        return a, b, -1
    t0 = time.time()
    logs = fetch_range(addr, topics, a, b)
    recs = []
    for l in logs:
        if l.get("removed"):
            continue
        recs.append(decode_log(l))
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt") as f:
        for r in recs:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    os.replace(tmp, path)
    with _stats_lock:
        STATS["chunks"] += 1
        STATS["logs"] += len(recs)
    return a, b, len(recs), time.time() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--oo", required=True, choices=list(OO))
    ap.add_argument("--from", dest="frm", type=int, required=True)
    ap.add_argument("--to", type=int, required=True)
    ap.add_argument("--chunk", type=int, default=2500)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--events", default="RequestPrice,ProposePrice,DisputePrice,Settle,BondUpdated,CustomBondSet,PayoutDeferred")
    args = ap.parse_args()
    addr = OO[args.oo]
    topics = [[TOPIC[e] for e in args.events.split(",")]]
    outdir = os.path.join(DATA, "raw", args.oo)
    os.makedirs(outdir, exist_ok=True)
    # chunk boundaries aligned to multiples of chunk so re-runs with the same chunk size line up
    ranges = []
    s = args.frm
    while s <= args.to:
        e = min(args.to, (s // args.chunk + 1) * args.chunk - 1)
        ranges.append((s, e))
        s = e + 1
    todo = [r for r in ranges if not os.path.exists(os.path.join(outdir, f"{r[0]}-{r[1]}.jsonl.gz"))]
    print(f"{args.oo} {addr}: {len(ranges)} chunks, {len(todo)} to do", flush=True)
    t0 = time.time()
    failed = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_chunk, args.oo, addr, topics, a, b, outdir): (a, b) for a, b in todo}
        done = 0
        for f in as_completed(futs):
            a, b = futs[f]
            done += 1
            try:
                res = f.result()
                if done % 20 == 0 or done == len(todo):
                    el = time.time() - t0
                    print(f"[{done}/{len(todo)}] {a}-{b} n={res[2]} {el:.0f}s elapsed, eta {el/done*(len(todo)-done):.0f}s "
                          f"stats={STATS}", flush=True)
            except Exception as e:
                failed.append((a, b, str(e)[:300]))
                print(f"FAILED {a}-{b}: {str(e)[:300]}", flush=True)
    with open(os.path.join(outdir, "_failed.json"), "w") as f:
        json.dump(failed, f)
    print(f"done. failed={len(failed)} stats={STATS} in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
