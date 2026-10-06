"""Stage 3a: turn data/requests_polymarket.jsonl.gz (+ enrichment) into compact numpy columns
(data/columns.npz) plus full detail for every disputed request (data/disputed_requests.json).
Needed because one dict per request (2.2M requests) does not fit in 8 GB of RAM.

Parameter merge rules (per request key):
  finalFee, reward, currency : RequestPrice event if in the fetched range, else getRequest() (enrichment)
  bond : BondUpdated event (only emitted by the MOOV2 implementation live since 2026-09-22),
         else getRequest(), else solved from the Settle payout with the OO payout rules:
           undisputed: payout = bond + finalFee + reward
           disputed  : payout = bond + (bond - floor(bond/2)) + finalFee  (+ reward only if not refunded;
                       refundOnDispute is set on these requests, so reward 0 is tried first)
"""
import gzip
import json
import os
import re
from array import array

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
REQUESTERS = [
    "0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7",  # 0 MOOV2 UmaCtfAdapter (binary)
    "0x69c47De9D4D3Dad79590d61b9e05918E03775f24",  # 1 MOOV2 NegRisk UmaCtfAdapter
    "0x53703Dd6129d723066b6362510E5aE2fECd48218",  # 2 MOOV2 PolymarketOOReporter (UMA-owned, PM v2)
    "0x2F5e3684cb1F318ec51b00Edba38d79Ac2c0aA9d",  # 3 OOv2 NegRiskUmaCtfAdapter (legacy)
    "0x6A9D222616C90FcA5754cd1333cFD9b7fb6a4F74",  # 4 OOv2 UmaCtfAdapter v2.0 (legacy)
    "0x71392E133063CC0D16F40E1F9B60227404Bc03f7",  # 5 OOv2 UmaCtfAdapter v3.0 (legacy)
    "0x157Ce2d672854c848c9b79C49a8Cc6cc89176a49",  # 6 OOv2 UmaCtfAdapter v3.1 (legacy)
]
RQI = {a: i for i, a in enumerate(REQUESTERS)}
YES, NO, HALF, IGNORE = 10 ** 18, 0, 5 * 10 ** 17, -(2 ** 255)
PCODE = {NO: 0, YES: 1, HALF: 2, IGNORE: 3}
CATS = ["unknown(no RequestPrice in range)", "sports/esports", "crypto price", "weather", "mentions/social", "other"]
RE_SPORT = re.compile(r" vs\.? | vs |spread|o/u|over/under|total|handicap|win on|moneyline|map \d|game \d|set \d|points|"
                      r"rebounds|assists|goals|touchdown|draw|exact score|halftime|half|inning|quarter|period|"
                      r"advance|qualify|match|fc |united|league|cup|open|grand prix|tournament|champion|series")
RE_CRYPTO = re.compile(r"bitcoin|ethereum|solana|xrp|btc|eth |dogecoin|bnb|hype|price of|up or down")
RE_WEATHER = re.compile(r"temperature|°f|°c|rain|weather|snow|precipitation|hurricane")
RE_MENTION = re.compile(r"tweet|post |posts|say \"|say '|mention")


def cat(title):
    if not title:
        return 0
    t = title.lower()
    if RE_CRYPTO.search(t):
        return 2
    if RE_WEATHER.search(t):
        return 3
    if RE_MENTION.search(t):
        return 4
    if RE_SPORT.search(t):
        return 1
    return 5


def pcode(p):
    if p is None:
        return -1
    return PCODE.get(int(p), 4)


def main():
    enrich = {}
    for line in open(os.path.join(DATA, "enrich_getRequest.jsonl")):
        r = json.loads(line)
        if "error" not in r:
            enrich[r["key"]] = r
    src = os.path.join(DATA, "requests_polymarket.jsonl.gz")
    # pre-pass: disputed rows in full, keys of requests created by dispute resets, dispute txs
    disputed, reset_keys, disp_txs = {}, set(), set()
    with gzip.open(src, "rt") as f:
        for line in f:
            if '"disp_ts"' in line:
                r = json.loads(line)
                disputed[r["key"]] = r
                disp_txs.add(r["disp_tx"])
                if r.get("reset_request_key"):
                    reset_keys.add(r["reset_request_key"])
    reset_info = {}
    cols = {n: array("q") for n in ("req_ts", "prop_ts", "exp", "disp_ts", "settle_ts", "reward", "finalFee", "bond",
                                    "payout")}
    small = {n: array("b") for n in ("rq", "bond_src", "pp", "sp", "reset_req", "cat", "has_title")}
    idx = {n: array("i") for n in ("proposer", "disputer")}
    addr_index, addrs = {}, []

    def ai(a):
        if a is None:
            return -1
        if a not in addr_index:
            addr_index[a] = len(addrs)
            addrs.append(a)
        return addr_index[a]

    with gzip.open(src, "rt") as f:
        for line in f:
            r = json.loads(line)
            k = r["key"]
            e = enrich.get(k)
            fee = r.get("finalFee", e["finalFee"] if e else None)
            rew = r.get("reward", e["reward"] if e else None)
            bond, bsrc = None, 0
            if "bond_ev" in r:
                bond, bsrc = r["bond_ev"], 1
            elif e:
                bond, bsrc = e["bond"], 2
            elif "settle_ts" in r and fee is not None and rew is not None:
                pay = r["payout"]
                if "disp_ts" not in r:
                    if pay - fee - rew >= 0:
                        bond, bsrc = pay - fee - rew, 3
                else:
                    # reward is refunded to the requester on dispute (refundOnDispute is set for these
                    # event-based requests; verified on all disputed rows with an independent bond), so try 0 first
                    for ww in (0, rew):
                        x = pay - fee - ww
                        for b in ((2 * x) // 3, (2 * x - 1) // 3, (2 * x) // 3 + 1):
                            if bond is None and b >= 0 and 2 * b - b // 2 == x:
                                bond, bsrc = b, 4
            if k in reset_keys:
                reset_info[k] = {"settle_ts": r.get("settle_ts"), "prop_ts": r.get("prop_ts"),
                                 "disp_ts": r.get("disp_ts"), "price": r.get("price")}
            if k in disputed:
                disputed[k].update(bond=bond, bond_src=bsrc, finalFee=fee, reward_merged=rew,
                                   refundOnDispute=(e or {}).get("refundOnDispute"))
            small["rq"].append(RQI[r["requester"]])
            cols["req_ts"].append(r.get("req_ts") or 0)
            cols["prop_ts"].append(r.get("prop_ts") or 0)
            cols["exp"].append(r.get("expiration") or 0)
            cols["disp_ts"].append(r.get("disp_ts") or 0)
            cols["settle_ts"].append(r.get("settle_ts") or 0)
            cols["reward"].append(-1 if rew is None else rew)
            cols["finalFee"].append(-1 if fee is None else fee)
            cols["bond"].append(-1 if bond is None else bond)
            cols["payout"].append(r.get("payout", -1))
            small["bond_src"].append(bsrc)
            small["pp"].append(pcode(r.get("proposedPrice")))
            small["sp"].append(pcode(r.get("price")))
            small["reset_req"].append(1 if r.get("req_tx") in disp_txs else 0)
            small["cat"].append(cat(r.get("title")))
            small["has_title"].append(1 if r.get("title") else 0)
            idx["proposer"].append(ai(r.get("proposer")))
            idx["disputer"].append(ai(r.get("disputer")))
    out = {n: np.frombuffer(a, dtype=np.int64) for n, a in cols.items()}
    out.update({n: np.frombuffer(a, dtype=np.int8) for n, a in small.items()})
    out.update({n: np.frombuffer(a, dtype=np.int32) for n, a in idx.items()})
    np.savez_compressed(os.path.join(DATA, "columns.npz"), **out)
    json.dump({"addresses": addrs, "requesters": REQUESTERS, "categories": CATS},
              open(os.path.join(DATA, "columns_meta.json"), "w"))
    for k, r in disputed.items():
        if r.get("reset_request_key"):
            r["reset_request"] = reset_info.get(r["reset_request_key"])
    json.dump(list(disputed.values()), open(os.path.join(DATA, "disputed_requests.json"), "w"), indent=0)
    print("rows", len(out["rq"]), "disputed", len(disputed), "reset keys", len(reset_keys), "addresses", len(addrs))


if __name__ == "__main__":
    main()
