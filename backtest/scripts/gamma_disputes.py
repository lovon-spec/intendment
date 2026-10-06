"""Optional step: market size of disputed questions from Polymarket's public Gamma API (no key).

Input : data/disputes_in_window.json (from analyze.py)
Output: data/gamma_disputed_markets.json  (market_id -> selected Gamma fields)
Lookup: by market_id parsed from the ancillary data ("market_id: N"); fallback by questionID
(= keccak256(ancillaryData) for the UmaCtfAdapter family) via ?question_ids=.
"""
import json
import os
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
G = "https://gamma-api.polymarket.com/markets"
FIELDS = ("id", "question", "conditionId", "questionID", "negRisk", "negRiskRequestID", "volumeNum", "volume",
          "liquidityNum", "closed", "closedTime", "endDate", "umaResolutionStatuses", "umaResolutionStatus",
          "outcomePrices", "umaBond", "umaReward", "resolvedBy", "slug", "createdAt", "volumeClob")


def get(params):
    for i in range(5):
        try:
            r = requests.get(G, params=params, timeout=40)
            if r.status_code == 200:
                return r.json()
            time.sleep(2 + 2 * i)
        except requests.RequestException:
            time.sleep(2 + 2 * i)
    return []


def main():
    disputes = json.load(open(os.path.join(DATA, "disputes_in_window.json")))
    out_p = os.path.join(DATA, "gamma_disputed_markets.json")
    out = json.load(open(out_p)) if os.path.exists(out_p) else {}
    out = {k: v for k, v in out.items() if not v.get("missing")}  # retry earlier misses
    ids = sorted({d["market_id"] for d in disputes if d.get("market_id")} - set(out))
    # Gamma excludes closed markets unless closed=true is passed, so query both ways
    for closed in ("false", "true"):
        todo = [x for x in ids if x not in out]
        for i in range(0, len(todo), 40):
            batch = todo[i:i + 40]
            res = get([("id", x) for x in batch] + [("limit", 100), ("closed", closed)])
            got = {str(m.get("id")): m for m in res}
            for x in batch:
                m = got.get(x)
                if m:
                    out[x] = {k: m.get(k) for k in FIELDS}
            time.sleep(0.3)
    for x in ids:
        out.setdefault(x, {"missing": True})
    # fallback by questionID for disputes without a market_id
    for d in disputes:
        if d.get("market_id"):
            continue
        k = "q:" + d["ancHash"]
        if k in out:
            continue
        res = get([("question_ids", d["ancHash"])]) or get([("question_ids", d["ancHash"]), ("closed", "true")])
        out[k] = {kk: res[0].get(kk) for kk in FIELDS} if res else {"missing": True}
        time.sleep(0.3)
    json.dump(out, open(out_p, "w"), indent=1)
    print("markets:", len(out), "missing:", sum(1 for v in out.values() if v.get("missing")))


if __name__ == "__main__":
    main()
