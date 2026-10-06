"""Stage 3b: statistics for the window from data/columns.npz + data/disputed_requests.json.
Writes data/stats.json (all numbers) and data/disputes_in_window.json (for the Gamma join).

Window: [2026-07-03T00:00:00Z, 2026-10-01T00:00:00Z), by block timestamp of each event.
USD amounts assume 6-decimal USDC.e (the only currency seen in Polymarket requests).
"""
import collections
import datetime as dt
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
W0, W1 = 1783036800, 1790812800
LABELS = ["MOOV2 UmaCtfAdapter (binary)", "MOOV2 NegRisk UmaCtfAdapter", "MOOV2 PolymarketOOReporter (UMA-owned, PM v2)",
          "OOv2 NegRiskUmaCtfAdapter (legacy)", "OOv2 UmaCtfAdapter v2.0 (legacy)", "OOv2 UmaCtfAdapter v3.0 (legacy)",
          "OOv2 UmaCtfAdapter v3.1 (legacy)"]
PNAMES = {-1: "none", 0: "NO (0)", 1: "YES (1e18)", 2: "50-50 (0.5e18)", 3: "IGNORE / too early (int256 min)", 4: "other"}
QS = (0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1)


def iso(t):
    return dt.datetime.fromtimestamp(int(t), dt.timezone.utc).isoformat() if t else None


def dist(x):
    x = np.asarray(x, dtype=float)
    if x.size == 0:
        return {"n": 0}
    q = np.quantile(x, QS)
    out = {"n": int(x.size), "mean": float(x.mean()), "sum": float(x.sum())}
    for p, v in zip(QS, q):
        out[f"p{int(p * 100)}"] = float(v)
    return out


def vc(x, top=15, scale=1.0):
    vals, cnt = np.unique(np.asarray(x), return_counts=True)
    order = np.argsort(-cnt)[:top]
    return {str(float(vals[i]) / scale if scale != 1.0 else int(vals[i])): int(cnt[i]) for i in order}


def tw(starts, ends, amts, t0=W0, t1=W1):
    """Time-weighted distribution of sum(amount) over intervals [start, end), restricted to [t0, t1)."""
    s = np.maximum(starts, t0)
    e = np.minimum(ends, t1)
    keep = e > s
    s, e, a = s[keep], e[keep], amts[keep].astype(float)
    if s.size == 0:
        return {"max": 0.0, "p50": 0.0, "p95": 0.0, "tw_mean": 0.0, "integral_usd_days": 0.0, "max_at": None}
    t = np.concatenate([s, e, [t0, t1]])
    d = np.concatenate([a, -a, [0.0, 0.0]])
    o = np.argsort(t, kind="stable")
    t, d = t[o], d[o]
    lvl = np.cumsum(d)
    # level after processing all events at the same timestamp: take the last index per unique time
    ut, last = np.unique(t[::-1], return_index=True)
    last = len(t) - 1 - last
    lv = lvl[last]
    dur = np.diff(np.append(ut, t1))
    dur = np.where(ut < t1, dur, 0)
    tot = dur.sum()
    o2 = np.argsort(lv)
    cd = np.cumsum(dur[o2])
    def q(p):
        return float(lv[o2][np.searchsorted(cd, p * tot)])
    i = int(np.argmax(lv))
    return {"max": float(lv.max()), "max_at": iso(ut[i]), "p50": q(0.5), "p95": q(0.95),
            "tw_mean": float((lv * dur).sum() / tot), "integral_usd_days": float((lv * dur).sum() / 86400)}


def main():
    C = dict(np.load(os.path.join(DATA, "columns.npz")))
    meta = json.load(open(os.path.join(DATA, "columns_meta.json")))
    addrs = meta["addresses"]
    disputed = json.load(open(os.path.join(DATA, "disputed_requests.json")))
    n = C["rq"].size
    data_end = int(max(C["settle_ts"].max(), C["prop_ts"].max(), C["disp_ts"].max(), C["req_ts"].max()))

    def inw(col):
        return (C[col] >= W0) & (C[col] < W1)

    has_prop = C["prop_ts"] > 0
    has_disp = C["disp_ts"] > 0
    has_set = C["settle_ts"] > 0
    known = (C["bond"] >= 0) & (C["finalFee"] >= 0)
    stake = np.where(known, C["bond"] + C["finalFee"], -1)
    # stake estimate when params unknown: settled undisputed -> payout - median reward of requester;
    # otherwise the requester's median stake
    stake_est = stake.copy()
    est_src = np.zeros(n, dtype=np.int8)  # 0 exact, 1 payout-based, 2 median, 3 none
    for rq in range(len(LABELS)):
        m = (C["rq"] == rq) & has_prop
        ks = stake[m & known]
        med_s = int(np.median(ks)) if ks.size else 0
        kr = C["reward"][m & (C["reward"] >= 0)]
        med_r = int(np.median(kr)) if kr.size else 0
        a = m & ~known & has_set & ~has_disp
        stake_est[a] = C["payout"][a] - med_r
        est_src[a] = 1
        b = m & ~known & ~a
        stake_est[b] = med_s
        est_src[b] = 2
    usd = 1e6

    # dispute classification (needs question-level history: all disputes in the data on the same question)
    qd = collections.defaultdict(list)
    for d in disputed:
        qd[(d["requester"], d["ancHash"])].append(d["disp_ts"])
    for d in disputed:
        if d.get("reset_in_dispute_tx"):
            d["dclass"] = "first dispute (adapter reset: new request in the dispute tx)"
        elif any(t < d["disp_ts"] for t in qd[(d["requester"], d["ancHash"])]):
            d["dclass"] = "second dispute (no reset; market waits for DVM)"
        else:
            d["dclass"] = "no reset, no earlier dispute seen in data"
        d["outcome"] = ("pending" if "settle_ts" not in d else
                        "proposer right (disputer lost)" if int(d["price"]) == int(d["proposedPrice"]) else
                        "disputer right (proposer lost)")
    disp_w = [d for d in disputed if W0 <= d["disp_ts"] < W1]

    S = {"window": {"start": iso(W0), "end_exclusive": iso(W1), "data_end": iso(data_end),
                    "blocks": "89,554,537 .. 94,738,439 (window); fetched 89,000,000 .. 94,792,499"},
         "rows_total": int(n)}
    S["bond_source_for_window_proposals"] = {
        k: int(((C["bond_src"] == v) & inw("prop_ts")).sum()) for k, v in
        (("unknown", 0), ("BondUpdated event", 1), ("getRequest eth_call", 2), ("solved from undisputed Settle payout", 3),
         ("solved from disputed Settle payout", 4))}
    S["stake_source_for_window_proposals"] = {
        "exact (bond+finalFee known)": int((inw("prop_ts") & known).sum()),
        "estimated payout - median reward": int((inw("prop_ts") & (est_src == 1)).sum()),
        "estimated requester median": int((inw("prop_ts") & (est_src == 2)).sum())}
    # payout identity check where the bond is independent of the payout (BondUpdated or getRequest)
    ind = has_set & ((C["bond_src"] == 1) | (C["bond_src"] == 2)) & (C["finalFee"] >= 0) & (C["reward"] >= 0)
    und = ind & ~has_disp
    ok_u = int((C["payout"][und] == (C["bond"] + C["finalFee"] + C["reward"])[und]).sum())
    dd = ind & has_disp
    exp_d = C["bond"] + (C["bond"] - C["bond"] // 2) + C["finalFee"]
    ok_d1 = int((C["payout"][dd] == (exp_d + C["reward"])[dd]).sum())
    ok_d0 = int((C["payout"][dd] == exp_d[dd]).sum())
    S["payout_identity_check"] = {"undisputed_checked": int(und.sum()), "undisputed_ok": ok_u,
                                  "disputed_checked": int(dd.sum()), "disputed_ok_reward_to_winner": ok_d1,
                                  "disputed_ok_reward_refunded": ok_d0}

    groups = {"ALL Polymarket": np.ones(n, bool), "MOOV2 (all PM requesters)": C["rq"] <= 2,
              "OOv2 legacy (all PM requesters)": C["rq"] >= 3}
    for i, l in enumerate(LABELS):
        groups[l] = C["rq"] == i
    S["groups"] = {}
    for gname, g in groups.items():
        G = {}
        rq_w, pr_w, di_w, se_w = g & inw("req_ts"), g & inw("prop_ts"), g & inw("disp_ts"), g & inw("settle_ts")
        G["requests"] = int(rq_w.sum())
        G["requests_created_by_dispute_reset"] = int((rq_w & (C["reset_req"] == 1)).sum())
        G["requests_in_window_never_proposed_by_data_end"] = int((rq_w & ~has_prop).sum())
        G["proposals"] = int(pr_w.sum())
        G["disputes"] = int(di_w.sum())
        G["settles"] = int(se_w.sum())
        G["dispute_rate_per_proposal"] = G["disputes"] / G["proposals"] if G["proposals"] else None
        selfd = di_w & (C["disputer"] == C["proposer"])
        G["self_disputes(proposer==disputer)"] = int(selfd.sum())
        G["dispute_rate_excl_self_disputes"] = (G["disputes"] - int(selfd.sum())) / G["proposals"] if G["proposals"] else None
        rqset = set(np.unique(C["rq"][g]).tolist())
        dg = [d for d in disp_w if meta["requesters"].index(d["requester"]) in rqset]
        G["dispute_classes"] = dict(collections.Counter(d["dclass"] for d in dg))
        G["dispute_outcomes"] = dict(collections.Counter(d["outcome"] for d in dg))
        G["proposed_price"] = {PNAMES[int(k)]: v for k, v in vc(C["pp"][pr_w]).items()}
        G["settled_price_all"] = {PNAMES[int(k)]: v for k, v in vc(C["sp"][se_w]).items()}
        G["settled_price_disputed"] = {PNAMES[int(k)]: v for k, v in vc(C["sp"][se_w & has_disp]).items()}
        # money
        rw = pr_w & (C["reward"] >= 0)
        G["reward_per_proposal_usd"] = dist(C["reward"][rw] / usd)
        G["reward_values_usd"] = vc(C["reward"][rw], scale=usd)
        G["reward_per_request_usd"] = dist(C["reward"][rq_w & (C["reward"] >= 0)] / usd)
        ff = pr_w & (C["finalFee"] >= 0)
        G["finalFee_values_usd"] = vc(C["finalFee"][ff], scale=usd)
        bb = pr_w & (C["bond"] >= 0)
        G["bond_per_proposal_usd"] = dist(C["bond"][bb] / usd)
        G["bond_values_usd"] = vc(C["bond"][bb], scale=usd)
        G["bond_unknown_proposals"] = int((pr_w & (C["bond"] < 0)).sum())
        se = pr_w & (stake_est >= 0)
        G["stake_per_proposal_usd(bond+finalFee)"] = dist(stake_est[se] / usd)
        G["total_proposer_stake_posted_usd"] = float(stake_est[se].sum() / usd)
        G["total_bond_posted_usd(excl finalFee)"] = float(C["bond"][bb].sum() / usd)
        G["total_disputer_stake_posted_usd"] = float(stake_est[di_w & (stake_est >= 0)].sum() / usd)
        dk = di_w & known
        G["store_fees_from_disputes_usd(finalFee+floor(bond/2))"] = float((C["finalFee"][dk] + C["bond"][dk] // 2).sum() / usd)
        G["store_fee_per_dispute_usd"] = dist((C["finalFee"][dk] + C["bond"][dk] // 2) / usd)
        G["disputes_with_unknown_params"] = int((di_w & ~known).sum())
        G["store_fees_by_dispute_class_usd"] = {}
        for d in dg:
            if d.get("bond") is not None and d.get("finalFee") is not None:
                G["store_fees_by_dispute_class_usd"][d["dclass"]] = G["store_fees_by_dispute_class_usd"].get(d["dclass"], 0) + (d["finalFee"] + d["bond"] // 2) / usd
        dks = dk & has_set
        G["forfeited_by_losers_usd(bond+finalFee, settled disputes)"] = float((C["bond"][dks] + C["finalFee"][dks]).sum() / usd)
        G["of_which_to_winners_usd(bond-floor(bond/2))"] = float((C["bond"][dks] - C["bond"][dks] // 2).sum() / usd)
        G["of_which_to_store_usd"] = float((C["finalFee"][dks] + C["bond"][dks] // 2).sum() / usd)
        su = se_w & ~has_disp & (C["reward"] >= 0)
        G["rewards_paid_to_proposers_on_undisputed_settles_usd"] = float(C["reward"][su].sum() / usd)
        G["payouts_on_settles_usd"] = float(C["payout"][se_w].sum() / usd)
        # time
        liv = (C["exp"] - C["prop_ts"])[pr_w]
        G["liveness_values_s"] = vc(liv)
        G["liveness_h"] = dist(liv / 3600)
        us = pr_w & ~has_disp & has_set
        G["undisputed_settled"] = int(us.sum())
        G["undisputed_unsettled_at_data_end"] = int((pr_w & ~has_disp & ~has_set).sum())
        G["undisputed_propose_to_settle_h"] = dist((C["settle_ts"] - C["prop_ts"])[us] / 3600)
        G["undisputed_settle_lag_after_liveness_h"] = dist((C["settle_ts"] - C["exp"])[us] / 3600)
        ds = di_w & has_set
        G["disputed_dispute_to_settle_h"] = dist((C["settle_ts"] - C["disp_ts"])[ds] / 3600)
        G["disputed_unsettled_at_data_end"] = int((di_w & ~has_set).sum())
        G["disputed_unsettled_age_h"] = dist((data_end - C["disp_ts"])[di_w & ~has_set] / 3600)
        G["proposal_to_dispute_h"] = dist((C["disp_ts"] - C["prop_ts"])[di_w] / 3600)
        for cls in sorted(set(d["dclass"] for d in dg)):
            G[f"dispute_to_settle_h[{cls}]"] = dist([(d["settle_ts"] - d["disp_ts"]) / 3600 for d in dg
                                                     if d["dclass"] == cls and "settle_ts" in d])
        G["first_dispute_to_reset_request_settled_h"] = dist(
            [(d["reset_request"]["settle_ts"] - d["disp_ts"]) / 3600 for d in dg
             if d.get("reset_request") and d["reset_request"].get("settle_ts")])
        # lock-up
        pm = g & has_prop
        ends = np.where(has_set, C["settle_ts"], data_end)
        lock_dur = (ends - C["prop_ts"])[pr_w] / 3600
        G["lock_duration_per_proposal_h"] = dist(lock_dur)
        G["all_proposers_locked_usd"] = {k: (v / usd if isinstance(v, float) and k != "integral_usd_days" else v)
                                         for k, v in tw(C["prop_ts"][pm], ends[pm], np.maximum(stake_est[pm], 0)).items()}
        G["all_proposers_locked_usd"]["integral_usd_days"] /= usd
        G["all_proposers_capital_cost_usd_at_5pct_apr"] = G["all_proposers_locked_usd"]["integral_usd_days"] * 0.05 / 365
        dm = g & has_disp
        G["all_disputers_locked_usd"] = {k: (v / usd if isinstance(v, float) and k != "integral_usd_days" else v)
                                         for k, v in tw(C["disp_ts"][dm], ends[dm], np.maximum(stake_est[dm], 0)).items()}
        G["all_disputers_locked_usd"]["integral_usd_days"] /= usd
        props_idx = C["proposer"][pr_w]
        pc = collections.Counter(props_idx.tolist())
        dc = collections.Counter(C["disputer"][di_w].tolist())
        G["distinct_proposers"] = len(pc)
        G["distinct_disputers"] = len(dc)
        G["top_disputers"] = [(addrs[a], c) for a, c in dc.most_common(10)]
        top = pc.most_common(10)
        G["top10_share_of_proposals"] = sum(c for _, c in top) / G["proposals"] if G["proposals"] else None
        G["top1_share_of_proposals"] = top[0][1] / G["proposals"] if top else None
        tl = []
        for a, c in top:
            m = pm & (C["proposer"] == a)
            q = tw(C["prop_ts"][m], ends[m], np.maximum(stake_est[m], 0))
            mine_u = se_w & ~has_disp & (C["proposer"] == a) & (C["reward"] >= 0)
            mine_d = di_w & (C["proposer"] == a) & has_set & known
            lost = mine_d & (C["sp"] != C["pp"])
            tl.append({"proposer": addrs[a], "proposals": c, "share": c / G["proposals"],
                       "disputed_against": int((di_w & (C["proposer"] == a)).sum()),
                       "self_disputes": int((di_w & (C["proposer"] == a) & (C["disputer"] == a)).sum()),
                       "rewards_earned_usd": float(C["reward"][mine_u].sum() / usd),
                       "disputes_lost": int(lost.sum()),
                       "stake_lost_usd": float((C["bond"][lost] + C["finalFee"][lost]).sum() / usd),
                       "locked_max_usd": q["max"] / usd, "locked_p95_usd": q["p95"] / usd,
                       "locked_median_usd": q["p50"] / usd, "locked_tw_mean_usd": q["tw_mean"] / usd,
                       "capital_time_usd_days": q["integral_usd_days"] / usd, "max_at": q["max_at"]})
        G["top10_proposers"] = tl
        # categories (only rows whose RequestPrice is in the fetched range carry a title)
        cats = meta["categories"]
        G["proposals_by_category"] = {cats[int(k)]: v for k, v in vc(C["cat"][pr_w]).items()}
        G["disputes_by_category"] = {cats[int(k)]: v for k, v in vc(C["cat"][di_w]).items()}
        G["liveness_by_category_s"] = {cats[c]: vc(liv[C["cat"][pr_w] == c], top=5) for c in range(len(cats))
                                       if (C["cat"][pr_w] == c).any()}
        # daily
        day = lambda col, m: collections.Counter((C[col][m] - W0) // 86400)
        rd, pdd, ddd = day("req_ts", rq_w), day("prop_ts", pr_w), day("disp_ts", di_w)
        rwd = collections.Counter()
        for dday, amt in zip(((C["settle_ts"][su] - W0) // 86400).tolist(), C["reward"][su].tolist()):
            rwd[dday] += amt
        G["daily"] = {(dt.date(2026, 7, 3) + dt.timedelta(days=int(k))).isoformat():
                      [rd.get(k, 0), pdd.get(k, 0), ddd.get(k, 0), rwd.get(k, 0) / usd] for k in range(90)}
        G["daily_columns"] = ["requests", "proposals", "disputes", "rewards_paid_usd(undisputed settles)"]
        S["groups"][gname] = G
    # disputes in window, full detail, for the record and the Gamma join
    keep = ("requester", "ancHash", "timestamp", "title", "market_id", "proposer", "disputer", "proposedPrice",
            "price", "prop_ts", "disp_ts", "settle_ts", "bond", "bond_src", "finalFee", "reward_merged", "dclass",
            "outcome", "disp_tx", "prop_tx", "settle_tx", "reset_request_key", "reset_request", "payout", "expiration")
    with open(os.path.join(DATA, "disputes_in_window.json"), "w") as f:
        json.dump([{k: d.get(k) for k in keep} for d in sorted(disp_w, key=lambda d: d["disp_ts"])], f, indent=0)
    with open(os.path.join(DATA, "stats.json"), "w") as f:
        json.dump(S, f, indent=1, default=str)
    A = S["groups"]["ALL Polymarket"]
    print(json.dumps({k: A[k] for k in ("requests", "proposals", "disputes", "settles", "dispute_rate_per_proposal",
                                        "dispute_classes", "dispute_outcomes")}, indent=1))


if __name__ == "__main__":
    main()
