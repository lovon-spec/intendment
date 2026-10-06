"""The oracle design's dispute numbers, recomputed from the dispute dataset.

Reads data/disputes_in_window.json and data/gamma_disputed_markets.json, built by the pipeline in
scripts/, and prints as Markdown every number that sections 0, 1 and 6 of
docs/intendment-oracle-design-v0.5.md take from the disputes of the 90 days to 2026-10-01.

    python3 scenarios.py data > report/scenarios.md

Money is in USDC.e. UMA's take on a dispute is what OOv2 pays the Store in the dispute
transaction: the final fee plus half the bond, floor(B/2).
"""

import collections
import json
import statistics
import sys
from pathlib import Path

TOO_EARLY = str(-(2**255))  # UMA's "too early" price, int256 min
SEPTEMBER = 1788566400  # 2026-09-01T00:00:00Z
# Self-disputes on requests whose liveness had been set to a billion seconds, all by one proposer:
# a configuration accident, left out of the honest self-corrections.
ACCIDENT_LIVENESS = 10**9


def kind(d):
    return "second" if d["dclass"].startswith("second") else "first"


def outcome(d):
    if d["outcome"].startswith("disputer right"):
        return "proposal wrong"
    if d["outcome"].startswith("proposer right"):
        return "proposal right"
    return "pending"


def self_dispute(d):
    return d["proposer"].lower() == d["disputer"].lower()


def accident(d):
    return d["expiration"] - d["prop_ts"] >= ACCIDENT_LIVENESS


def uma_take(d):
    return d["finalFee"] + d["bond"] // 2


def usd(micro):
    return f"{micro / 1e6:,.0f}"


def hours(d):
    return (d["settle_ts"] - d["disp_ts"]) / 3600


def p95(xs):
    return statistics.quantiles(xs, n=20, method="inclusive")[18]  # linear interpolation, as numpy


def main(base):
    disputes = json.load(open(base / "disputes_in_window.json"))
    gamma = json.load(open(base / "gamma_disputed_markets.json"))

    def volume(d):
        return (gamma.get(str(d.get("market_id"))) or {}).get("volumeNum") or 0

    others = [d for d in disputes if not self_dispute(d)]
    selfs = [d for d in disputes if self_dispute(d)]
    kinds = collections.Counter(kind(d) for d in disputes)
    outcomes = collections.Counter(outcome(d) for d in disputes)
    resolved = outcomes["proposal wrong"] + outcomes["proposal right"]
    too_early = [d for d in disputes if d["price"] == TOO_EARLY]
    settled = [d for d in disputes if d.get("settle_ts")]

    out = []
    w = out.append
    w("# Disputes of the 90 days to 2026-10-01\n")
    w("Recomputed from `data/disputes_in_window.json` and `data/gamma_disputed_markets.json`.\n")
    w("## Section 1: today, measured\n")
    w("| number | value |")
    w("|---|---|")
    w(f"| disputes | {len(disputes):,} |")
    w(f"| first disputes (the market resets) | {kinds['first']:,} |")
    w(f"| second disputes (the market waits for the vote) | {kinds['second']:,} |")
    w(f"| self-disputes (proposer and disputer the same address) | {len(selfs):,} |")
    w(f"| resolved disputes | {resolved:,} |")
    w(f"| of which the vote found the proposal wrong | {outcomes['proposal wrong']:,} ({outcomes['proposal wrong'] / resolved:.1%}) |")
    w(f"| pending at the end of the data | {outcomes['pending']:,} |")
    w(f"| answered \"too early\" | {len(too_early):,} |")
    w(f"| UMA's take, all disputes | {usd(sum(map(uma_take, disputes)))} |")
    w(f"| of the non-self part, paid by proposers that lost | {usd(sum(uma_take(d) for d in others if outcome(d) == 'proposal wrong'))} |")
    w(f"| of the non-self part, paid by disputers that lost | {usd(sum(uma_take(d) for d in others if outcome(d) == 'proposal right'))} |")
    w(f"| UMA's take, non-self disputes since 2026-09-01 | {usd(sum(uma_take(d) for d in others if d['disp_ts'] >= SEPTEMBER))} |")
    w(f"| dispute to settlement, median / p95 hours | {statistics.median(map(hours, settled)):.1f} / {p95(list(map(hours, settled))):.1f} |")
    resets = [
        (d["reset_request"]["settle_ts"] - d["disp_ts"]) / 3600
        for d in disputes
        if kind(d) == "first" and (d.get("reset_request") or {}).get("settle_ts")
    ]
    w(f"| first dispute to the reset request's settlement, median hours | {statistics.median(resets):.1f} (n = {len(resets):,}) |")
    held = [hours(d) for d in settled if kind(d) == "second"]
    w(f"| second dispute to settlement (the market waits), median hours | {statistics.median(held):.1f} (n = {len(held):,}) |")
    w("")

    # Section 6: the backtest. A case settles when the side the vote found wrong ends it itself.
    s1 = [d for d in others if d["price"] == TOO_EARLY]
    s2 = [d for d in others if outcome(d) == "proposal wrong"]
    s3 = s2 + [d for d in others if kind(d) == "first" and outcome(d) == "proposal right"]
    corrections = [d for d in selfs if not accident(d)]

    def blocked(cases):
        b = [d for d in cases if kind(d) == "second"]
        return len(b), sum(map(hours, b)), sum(map(volume, b)), b

    w("## Section 6: what it changes\n")
    w("Self-disputes are counted apart. A scenario's cases are the disputes whose losing side, as the vote decided, would have ended the case itself.\n")
    w("| scenario | cases settled | UMA's take not paid | final fees kept by the side ending the case | burn paid to the venue | blocked markets reopened | market-hours | lifetime volume |")
    w("|---|---|---|---|---|---|---|---|")
    for name, cases in [
        ("only proposals the vote called \"too early\" are conceded", s1),
        ("every proposal the vote found wrong is conceded", s2),
        ("as above, and every wrong disputer on a non-blocking case withdraws", s3),
    ]:
        fees = sum(d["finalFee"] for d in cases)
        burn = sum(d["bond"] // 2 for d in cases)
        total = sum(map(uma_take, disputes))
        n, mh, vol, _ = blocked(cases)
        w(f"| {name} | {len(cases):,} | {usd(fees + burn)} ({(fees + burn) / total:.0%}) | {usd(fees)} | {usd(burn)} | {n} | {mh:,.0f} | {vol / 1e6:,.1f} million |")
    w("")
    n, mh, vol, b = blocked(s2)
    w(f"Blocked markets in the middle scenario: {n}, waiting a median {statistics.median(map(hours, b)):.1f} hours; {sum(1 for d in b if volume(d) > 0)} have a lifetime volume on record.")
    top = max(b, key=volume)
    w(f"The largest: \"{top['title']}\", {volume(top) / 1e6:,.1f} million lifetime volume, {hours(top):.0f} hours.\n")
    fees = sum(d["finalFee"] for d in corrections)
    burn = sum(d["bond"] // 2 for d in corrections)
    w(f"Honest self-corrections (self-disputes, the configuration accident left out): {len(corrections)}, "
      f"UMA's take {usd(fees + burn)}; as retractions {usd(fees)} stays with the proposers and {usd(burn)} goes to the venue. "
      f"Self-disputes left out as the configuration accident: {sum(1 for d in selfs if accident(d))}.\n")
    sept = [d for d in s2 if d["disp_ts"] >= SEPTEMBER]
    fees = sum(d["finalFee"] for d in sept)
    burn = sum(d["bond"] // 2 for d in sept)
    w(f"September run rate, middle scenario: {len(sept)} cases, UMA's take {usd(fees + burn)}; "
      f"times twelve, {usd(12 * burn)} a year to the venue and {usd(12 * fees)} of final fees kept, {usd(12 * (fees + burn))} in all.\n")
    released = 0.0
    for d in s3:
        if not d.get("settle_ts"):
            continue
        window = 1 if kind(d) == "second" else 4
        released += 2 * (d["bond"] + d["finalFee"]) / 1e6 * max(0.0, hours(d) - window)
    w(f"Stake released early in the third scenario, windows of one and four hours: {released / 24:,.0f} USDC.e-days, "
      f"{released / 24 * 0.05 / 365:,.0f} of interest at 5%.")
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "data"))
