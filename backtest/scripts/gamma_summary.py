"""Join disputes in the window with Gamma market data; add current open interest (public
data-api.polymarket.com/oi, no key) for markets whose dispute was still pending at data end.
Output: data/gamma_summary.json
"""
import json
import os
import statistics
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def oi(cond):
    for i in range(4):
        try:
            r = requests.get("https://data-api.polymarket.com/oi", params={"market": cond}, timeout=30)
            if r.status_code == 200:
                j = r.json()
                return float(j[0]["value"]) if j else 0.0
        except (requests.RequestException, ValueError, KeyError):
            pass
        time.sleep(1 + i)
    return None


def summ(vals):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return {"n": 0}
    return {"n": len(v), "sum": sum(v), "median": statistics.median(v), "p90": v[int(0.9 * (len(v) - 1))],
            "max": v[-1]}


def main():
    D = json.load(open(os.path.join(DATA, "disputes_in_window.json")))
    G = json.load(open(os.path.join(DATA, "gamma_disputed_markets.json")))
    for d in D:
        m = G.get(d.get("market_id") or "") or G.get("q:" + d["ancHash"])
        d["gamma"] = m if m and not m.get("missing") else None
    out = {"disputes": len(D), "matched": sum(1 for d in D if d["gamma"])}
    groups = {
        "all disputes": D,
        "first disputes (reset)": [d for d in D if d["dclass"].startswith("first")],
        "second disputes (market waits for DVM)": [d for d in D if d["dclass"].startswith("second")],
        "pending at data end": [d for d in D if d["outcome"] == "pending"],
        "excluding 88 self-disputes by 0xa0B6": [d for d in D if d["disputer"] != d["proposer"]],
    }
    for name, L in groups.items():
        uniq = {}
        for d in L:
            if d["gamma"]:
                uniq[d["gamma"]["conditionId"]] = d["gamma"]
        out[name] = {"disputes": len(L), "unique_markets_matched": len(uniq),
                     "lifetime_volume_usd": summ([m.get("volumeNum") for m in uniq.values()]),
                     "liquidity_usd_now": summ([m.get("liquidityNum") for m in uniq.values()])}
    # current open interest for markets with a dispute still pending at data end
    pend = {}
    for d in groups["pending at data end"]:
        if d["gamma"] and d["gamma"].get("conditionId"):
            pend[d["gamma"]["conditionId"]] = d
    ois = {}
    for c in pend:
        ois[c] = oi(c)
        time.sleep(0.2)
    out["pending_disputes_open_interest_now_usd"] = summ(list(ois.values()))
    out["pending_disputes_open_interest_by_market"] = {c: {"oi": v, "title": pend[c].get("title")} for c, v in
                                                       sorted(ois.items(), key=lambda x: -(x[1] or 0))[:15]}
    # largest disputed markets
    big = sorted({d["gamma"]["conditionId"]: d for d in D if d["gamma"]}.values(),
                 key=lambda d: -(d["gamma"].get("volumeNum") or 0))[:12]
    out["largest_disputed_markets"] = [{"title": d["gamma"]["question"], "volume": d["gamma"].get("volumeNum"),
                                        "dclass": d["dclass"], "outcome": d["outcome"]} for d in big]
    json.dump(out, open(os.path.join(DATA, "gamma_summary.json"), "w"), indent=1)
    print(json.dumps({k: v for k, v in out.items() if k not in ("pending_disputes_open_interest_by_market",)}, indent=1))


if __name__ == "__main__":
    main()
