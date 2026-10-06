"""Stage 1: join decoded OO events into one row per OO price request, Polymarket requesters only.

Input : data/raw/{MOOV2,OOv2}/*.jsonl.gz   (from fetch_logs.py)
Output: data/requests_polymarket.jsonl.gz  (one row per request key)
        data/requester_counts.json         (all requesters seen, incl. non-Polymarket, for the record)

Request key = (oo, requester, identifier, timestamp, keccak(ancillaryData)); in OOv2 a key can be
requested, proposed, disputed and settled at most once each.
"""
import collections
import glob
import gzip
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")

POLY = {
    "0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7": "UmaCtfAdapter (binary) on MOOV2",
    "0x69c47De9D4D3Dad79590d61b9e05918E03775f24": "NegRisk UmaCtfAdapter on MOOV2",
    "0x53703Dd6129d723066b6362510E5aE2fECd48218": "UMA PolymarketOOReporter on MOOV2",
    "0x2F5e3684cb1F318ec51b00Edba38d79Ac2c0aA9d": "NegRiskUmaCtfAdapter on OOv2 (legacy)",
    "0x6A9D222616C90FcA5754cd1333cFD9b7fb6a4F74": "UmaCtfAdapter v2.0 on OOv2 (legacy)",
    "0x71392E133063CC0D16F40E1F9B60227404Bc03f7": "UmaCtfAdapter v3.0 on OOv2 (legacy)",
    "0x157Ce2d672854c848c9b79C49a8Cc6cc89176a49": "UmaCtfAdapter v3.1 on OOv2 (legacy)",
}


def load():
    for oo in ("MOOV2", "OOv2"):
        for f in sorted(glob.glob(os.path.join(DATA, "raw", oo, "*.jsonl.gz"))):
            with gzip.open(f, "rt") as fh:
                for line in fh:
                    yield json.loads(line)


def key(r):
    return f'{r["oo"]}|{r["requester"]}|{r["identifier"]}|{r["timestamp"]}|{r["ancHash"]}'


def main():
    reqs = {}
    counts = collections.Counter()
    deferred = []
    custom_bonds = []
    tx_requests = collections.defaultdict(list)  # tx -> [(requester, ancHash, key)] for reset detection
    n = 0
    for r in load():
        n += 1
        ev = r["ev"]
        if ev == "PayoutDeferred":
            deferred.append(r)
            continue
        counts[(r["oo"], r["requester"], ev)] += 1
        if ev == "CustomBondSet":
            custom_bonds.append(r)
            continue
        if r["requester"] not in POLY:
            continue
        k = key(r)
        q = reqs.setdefault(k, {"key": k, "oo": r["oo"], "requester": r["requester"], "identifier": r["identifier"],
                                "timestamp": r["timestamp"], "ancHash": r["ancHash"]})
        if ev == "RequestPrice":
            q.update(req_block=r["block"], req_ts=r.get("bts"), req_tx=r["tx"], currency=r["currency"],
                     reward=r["reward"], finalFee=r["finalFee"], title=r.get("title"), market_id=r.get("market_id"),
                     initializer=r.get("initializer"), ancLen=r.get("ancLen"))
            tx_requests[r["tx"]].append((r["requester"], r["ancHash"], k))
        elif ev == "BondUpdated":
            q["bond_ev"] = r["newBond"]
            q["bond_ev_block"] = r["block"]
        elif ev == "ProposePrice":
            if "prop_ts" in q:
                q.setdefault("dup", []).append("ProposePrice")
            q.update(proposer=r["proposer"], proposedPrice=str(r["proposedPrice"]), prop_ts=r.get("bts"),
                     prop_block=r["block"], prop_tx=r["tx"], prop_li=r["li"], expiration=r["expirationTimestamp"],
                     prop_currency=r["currency"])
        elif ev == "DisputePrice":
            if "disp_ts" in q:
                q.setdefault("dup", []).append("DisputePrice")
            q.update(disputer=r["disputer"], disp_ts=r.get("bts"), disp_block=r["block"], disp_tx=r["tx"],
                     disp_proposer=r["proposer"], disp_proposedPrice=str(r["proposedPrice"]))
        elif ev == "Settle":
            if "settle_ts" in q:
                q.setdefault("dup", []).append("Settle")
            q.update(settle_ts=r.get("bts"), settle_block=r["block"], settle_tx=r["tx"], price=str(r["price"]),
                     payout=r["payout"], settle_proposer=r["proposer"], settle_disputer=r["disputer"])
    # dispute -> did the requester re-request the same question inside the dispute tx (adapter reset)?
    for q in reqs.values():
        if "disp_tx" in q:
            same = [k for (rq, ah, k) in tx_requests.get(q["disp_tx"], [])
                    if rq == q["requester"] and ah == q["ancHash"] and k != q["key"]]
            q["reset_in_dispute_tx"] = bool(same)
            if same:
                q["reset_request_key"] = same[0]
    out = os.path.join(DATA, "requests_polymarket.jsonl.gz")
    with gzip.open(out, "wt") as f:
        for q in reqs.values():
            f.write(json.dumps(q, separators=(",", ":")) + "\n")
    rc = collections.defaultdict(dict)
    for (oo, rq, ev), c in counts.items():
        rc[f"{oo}|{rq}"][ev] = c
    json.dump({"events_read": n, "requesters": rc, "polymarket": POLY, "payout_deferred": deferred,
               "custom_bond_set": custom_bonds[:50], "custom_bond_set_count": len(custom_bonds)},
              open(os.path.join(DATA, "requester_counts.json"), "w"), indent=1)
    print(f"events read {n}; polymarket requests {len(reqs)}; deferred payouts {len(deferred)}; "
          f"CustomBondSet {len(custom_bonds)}")


if __name__ == "__main__":
    main()
