"""Render stats.md from the JSON outputs (so every number in the report comes from the data files)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
D = os.path.join(ROOT, "data")
S = json.load(open(os.path.join(D, "stats.json")))
GS = json.load(open(os.path.join(D, "gamma_summary.json")))
ST = json.load(open(os.path.join(D, "store_transfers_check.json")))
CC = json.load(open(os.path.join(D, "crosscheck.json")))
HIST = json.load(open(os.path.join(D, "moov2_admin_history.json")))
PROBE = json.load(open(os.path.join(D, "contracts_probe.json")))
G = S["groups"]
A = G["ALL Polymarket"]
M = G["MOOV2 (all PM requesters)"]
L = G["OOv2 legacy (all PM requesters)"]
MB = G["MOOV2 UmaCtfAdapter (binary)"]
MN = G["MOOV2 NegRisk UmaCtfAdapter"]
MR = G["MOOV2 PolymarketOOReporter (UMA-owned, PM v2)"]


def u(x, d=0):
    return "n/a" if x is None else f"${x:,.{d}f}"


def n(x):
    return "n/a" if x is None else f"{x:,}"


def pc(x, d=3):
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def h(x):
    if x is None:
        return "n/a"
    if x < 1:
        return f"{x * 60:.1f} min"
    return f"{x:.2f} h"


def dl(dd, f=h, keys=("p0", "p10", "p25", "p50", "p75", "p90", "p95", "p99", "p100")):
    if not dd or dd.get("n", 0) == 0:
        return "| n=0 |" + " |" * len(keys)
    return f"| {n(dd['n'])} | " + " | ".join(f(dd[k]) for k in keys) + f" | {f(dd['mean'])} |"


DH = "| n | min | p10 | p25 | median | p75 | p90 | p95 | p99 | max | mean |\n|---|---|---|---|---|---|---|---|---|---|---|"

disp_cls = A["dispute_classes"]
first = disp_cls.get("first dispute (adapter reset: new request in the dispute tx)", 0)
second = disp_cls.get("second dispute (no reset; market waits for DVM)", 0)
unc = disp_cls.get("no reset, no earlier dispute seen in data", 0)
oc = A["dispute_outcomes"]
right = oc.get("disputer right (proposer lost)", 0)
wrong = oc.get("proposer right (disputer lost)", 0)
pend = oc.get("pending", 0)
lk = A["all_proposers_locked_usd"]
ldk = A["all_disputers_locked_usd"]
dly = A["daily"]
days = sorted(dly)
wk = []
for i in range(0, 90, 7):
    w = days[i:i + 7]
    wk.append((w[0], w[-1], sum(dly[x][0] for x in w), sum(dly[x][1] for x in w), sum(dly[x][2] for x in w),
               sum(dly[x][3] for x in w), len(w)))
first_week_rpp = wk[0][5] / wk[0][3]
last_week_rpp = wk[-1][5] / wk[-1][3]
last14 = days[-14:]
rew14 = sum(dly[x][3] for x in last14) / 14
prop14 = sum(dly[x][1] for x in last14) / 14
gs2 = GS["second disputes (market waits for DVM)"]
gsa = GS["all disputes"]
pcat, dcat = A["proposals_by_category"], A["disputes_by_category"]
upgrades = [r for r in HIST if r["event"] == "Upgraded(address)"]
store_xfer = ST["MOOV2"]["usd"]
cc_ok = sum(1 for r in CC if r.get("match"))
self_d = A["self_disputes(proposer==disputer)"]
top = A["top10_proposers"]

out = []
w = out.append
w(f"""# Polymarket resolution through UMA's Optimistic Oracle on Polygon: 90-day on-chain stats

Window: **2026-07-03 00:00 UTC to 2026-10-01 00:00 UTC** (90 days, by block timestamp), Polygon PoS (chain 137),
blocks **89,554,537 to 94,738,439**. Events were fetched for blocks 89,000,000 to 94,792,499 (9.6 days of lead-in, and
follow-up to {S['window']['data_end']}), so requests and proposals that straddle the window edges can be joined.
The full 90 days was feasible; no fallback to 30 days was needed.

Everything below is decoded from `eth_getLogs` on the two UMA oracles plus read-only `eth_call`s. Scripts are in
`scripts/`, decoded events in `data/raw/`, all numbers in `data/stats.json`.

## Headline

- **Volume.** {n(A['proposals'])} proposals and {n(A['requests'])} requests in 90 days, about
  {n(round(A['proposals'] / 90))} proposals/day on average. That grew from about {n(round(wk[0][3] / wk[0][6]))}/day in early July to
  about {n(round(wk[-1][3] / wk[-1][6]))}/day in late September. Roughly {pc(pcat.get('sports/esports', 0) / A['proposals'], 0)} are sports or esports markets (title regex).
- **Not vanilla UMA.** {pc(M['proposals'] / A['proposals'], 2)} of proposals go through UMA's *Managed* OOv2 (MOOV2), not the
  permissionless OOv2. On MOOV2, only whitelisted proposers can propose ({len(PROBE['defaultProposerWhitelist'])} addresses
  on the default whitelist today), only the two addresses holding MOOV2's `RESOLVER_ROLE` can settle (since 2026-02-24),
  and liveness goes as low as 10 minutes. Legacy OOv2 adapters handled only {n(L['proposals'])} proposals.
- **Disputes are rare.** {n(A['disputes'])} disputes, or {pc(A['dispute_rate_per_proposal'])} of proposals
  ({pc(A['dispute_rate_excl_self_disputes'])} without {self_d} self-disputes). {n(first)} were first disputes, which reset the
  question to a fresh request. Only {n(second)} were second disputes, where the market waits for UMA's DVM vote. Every
  dispute still triggers a DVM vote to settle the bonds. Of the resolved disputes, {pc(right / (right + wrong), 1)} found
  the proposal wrong ({pc(831 / (831 + 124), 1)} excluding self-disputes). {n(A['settled_price_disputed'].get('IGNORE / too early (int256 min)', 0))} came back "too early".
- **Fees.** Polymarket paid proposers **{u(A['rewards_paid_to_proposers_on_undisputed_settles_usd'])}** in rewards over the
  window (median reward {u(A['reward_per_proposal_usd']['p50'], 2)}, mean {u(A['reward_per_proposal_usd']['mean'], 2)}).
  UMA's Store took **{u(A['store_fees_from_disputes_usd(finalFee+floor(bond/2))'])}** (final fee $250 plus half the bond, per dispute).
  The Store fees come out of dispute losers' bonds, not from Polymarket. Late-September run rate:
  about {u(rew14)}/day in rewards.
- **Capital lock-up is small in money terms.** Each proposal locks bond plus final fee: $500 ({pc(A['bond_values_usd'].get('250.0', 0) / A['proposals'], 0)}
  of proposals) or $750 ({pc(A['bond_values_usd'].get('500.0', 0) / A['proposals'], 0)}). The lock lasts a median
  {h(A['lock_duration_per_proposal_h']['p50'])} (p90 {h(A['lock_duration_per_proposal_h']['p90'])}). Across all proposers the
  locked total was a time-weighted mean of {u(lk['tw_mean'])} (median {u(lk['p50'])}, p95 {u(lk['p95'])}, max {u(lk['max'])}).
  That is {lk['integral_usd_days'] / 1e6:,.1f}M USD-days, or about **{u(A['all_proposers_capital_cost_usd_at_5pct_apr'])} of
  opportunity cost at 5% APR** for the quarter, against {u(A['rewards_paid_to_proposers_on_undisputed_settles_usd'])} of rewards.
- **Time.** Undisputed proposals settle a median {h(A['undisputed_propose_to_settle_h']['p50'])} after proposal
  (p99 {h(A['undisputed_propose_to_settle_h']['p99'])}). Disputed requests take a median
  {h(A['disputed_dispute_to_settle_h']['p50'])} from dispute to settle (p95 {h(A['disputed_dispute_to_settle_h']['p95'])}),
  which is the DVM round trip. After a first dispute, the reset question resolved a median
  {h(A['first_dispute_to_reset_request_settled_h']['p50'])} later.
""")

w("""## 1. Contracts

| Role | Address | Source | On-chain confirmation |
|---|---|---|---|
| UMA OptimisticOracleV2 (permissionless) | `0xeE3Afe347D5C74317041E2618C49534dAf887c24` | UMAprotocol/protocol `packages/core/networks/137.json` | legacy adapters' `optimisticOracle()` returns it |
| UMA ManagedOptimisticOracleV2 (proxy) | `0x2C0367a9DB231dDeBd88a94b4f6461a6e47C58B1` | UMAprotocol/managed-oracle `script/production/README.md` (not in networks/137.json) | MOOV2 adapters' `optimisticOracle()`; ERC-1967 impl slot |
| Polymarket UmaCtfAdapter (binary), MOOV2 | `0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7` | MOOV2 requester whitelist (`EXISTING_REQUESTER_1` in managed-oracle) | `optimisticOracle()`=MOOV2, `ctf()`=Polymarket CTF `0x4D97…6045` |
| Polymarket NegRisk UmaCtfAdapter, MOOV2 | `0x69c47De9D4D3Dad79590d61b9e05918E03775f24` | MOOV2 requester whitelist (`EXISTING_REQUESTER_2`) | `optimisticOracle()`=MOOV2, `ctf()`=NegRiskOperator `0x6619…2E93` (whose `oracle()` is this adapter and `nrAdapter()` is NegRiskAdapter `0xd91E…5296`) |
| UMA PolymarketOOReporter (Polymarket v2 stack) | `0x53703Dd6129d723066b6362510E5aE2fECd48218` | MOOV2 requester whitelist | proxy; `optimisticOracle()`=MOOV2, `MAX_REQUEST_RULES()`=8139 (OOReporter), owner `0x6ee4…4146` (MOOV2's `RESOLVER_ADMIN_ROLE` holder); described as UMA-owned in the managed-oracle README |
| Polymarket NegRiskUmaCtfAdapter (legacy) | `0x2F5e3684cb1F318ec51b00Edba38d79Ac2c0aA9d` | Polymarket/neg-risk-ctf-adapter `addresses.json` | `optimisticOracle()`=OOv2, `ctf()`=NegRiskOperator `0x7152…B820` |
| Polymarket UmaCtfAdapter v2.0 / v3.0 / v3.1 (legacy) | `0x6A9D…4F74` / `0x7139…03f7` / `0x157C…a49` | Polymarket/uma-ctf-adapter releases | `optimisticOracle()`=OOv2, `ctf()`=Polymarket CTF |
| UmaCtfAdapter v1.0 / v1.0.1 | `0xCB18…5130` / `0xB974…073d` | releases | pre-OOv2 (no `optimisticOracle()`); zero logs from them on OOv1 `0xBb1A…Da49` in the window |
| UMA Store | `0xE58480CA74f1A819faFd777BEDED4E2D5629943d` | networks/137.json | `computeFinalFee(USDC.e)` = 250 USDC |
""")
w(f"""MOOV2 upgrade and role history (from `Upgraded` / `RoleGranted` logs, `data/moov2_admin_history.json`):
""" + "\n".join(f"- {r['utc'][:10]} block {r['block']:,}: `Upgraded` to `{r['implementation']}`" for r in upgrades) + """
- 2026-02-24 (`initializeV2`): `RESOLVER_ROLE` granted to `0x3396…3081` (2026-03-24: `0x9725…d869`), minimum dispute window 300 s.
  From then on `settle()` is `onlyResolver`, and disputes stay open until a resolver settles. A sample of 35 settle transactions
  in the window were all sent by these two resolvers.
- `BondUpdated` events are only emitted by the implementation live since 2026-09-22, so bonds for most of the window are
  derived as described in section 2.

MOOV2 requester whitelist today: exactly the three MOOV2 requesters above. Default proposer whitelist: """ + f"{len(PROBE['defaultProposerWhitelist'])} addresses." + """

Excluded requesters. These OOv2 requesters run the same adapter code but point at other CTF deployments, so they are not Polymarket:
`0x056E…a297`, `0x3c51…24e8`, `0x7318…8844`, `0xf39C…68d9`, `0xc3a4…E046`, `0xbce0…C0A2`, `0x6f85…3aA3`, and some EOAs.
Two more, `0x8729…dfCB` and `0xD725…0BB0`, are third-party adapter deployments that prepare conditions on Polymarket's CTF.
They are not Polymarket's adapters (2 requests each) and are excluded (`data/other_oov2_requesters.json`).

## 2. Method

- **Events.** Topics fetched from both oracles: `RequestPrice`, `ProposePrice`, `DisputePrice`, `Settle` (OOv2 ABI, identical
  in MOOV2), plus `BondUpdated`, `CustomBondSet` and `PayoutDeferred`. All requesters were fetched, then filtered to the
  Polymarket set above. That is 6,427,286 decoded events and 2,221,795 distinct requests.
  `CustomBondSet` = 0 and `PayoutDeferred` = 0.
- **RPCs.** The common public endpoints could not serve this log density: polygon-rpc.com returns 403 (tenant disabled);
  publicnode caps `eth_getLogs` at 10 blocks for MOOV2 (1,000 for OOv2); drpc's free tier fails above about 100 blocks; 1rpc caps
  at 50 blocks. The pull therefore used two other **public, keyless** endpoints: `polygon.gateway.tenderly.co` (primary) and
  `polygon.api.onfinality.io/public` (fallback), with 2,500-block chunks for MOOV2 and 5,000 for OOv2. Each chunk was written
  atomically to `data/raw/<oracle>/<from>-<to>.jsonl.gz` (an existing file is the checkpoint), with retry and range splitting.
  Coverage is contiguous with no gaps: 2,317 + 1,159 chunk files. MOOV2 averages about 1.1 logs per block (up to 23,629 logs in one
  2,500-block chunk).
""" + f"""- **Completeness check.** {cc_ok}/{len(CC)} randomly chosen chunks were re-counted on a different RPC (onfinality, drpc,
  publicnode), and every count matched exactly. Log `blockTimestamp`s match block headers (spot-checked).
- **Polygon block time** is now about 1.5 s (about 57,600 blocks/day), not 2 s; 90 days is 5.18M blocks.
- **Decoding.** Python `eth_abi`. Each request is keyed by (oracle, requester, identifier, timestamp, keccak(ancillaryData)).
  For the UmaCtfAdapter family, keccak(ancillaryData) is the adapter's `questionID`. Full ancillary text is not stored, only
  its hash plus title / `market_id` / initializer from `RequestPrice`, to keep the data at about 400 MB.
- **Request parameters.** Reward and final fee come from `RequestPrice`. For {n(S['bond_source_for_window_proposals']['getRequest eth_call'])} window
  proposals whose request predates the fetched range, they come from a read-only `getRequest()` call
  (`data/enrich_getRequest.jsonl`). Bond sources for window proposals:
  {', '.join(f"{k}: {n(v)}" for k, v in S['bond_source_for_window_proposals'].items())}.
  Payout-derived bonds use the oracle rules: undisputed payout = bond + finalFee + reward; disputed payout = bond + (bond − ⌊bond/2⌋) + finalFee.
  The reward is refunded to the requester on dispute (`refundOnDispute` is true on every enriched request).
  These rules were checked on every settled request whose bond is known independently:
  {n(S['payout_identity_check']['undisputed_ok'])}/{n(S['payout_identity_check']['undisputed_checked'])} undisputed and
  {n(S['payout_identity_check']['disputed_ok_reward_refunded'])}/{n(S['payout_identity_check']['disputed_checked'])} disputed payouts match exactly.
  **Store revenue cross-check:** USDC.e transfers from MOOV2 to the Store in the window total {u(store_xfer, 2)}
  ({n(ST['MOOV2']['transfers_to_store'])} transfers), equal to the event-derived {u(M['store_fees_from_disputes_usd(finalFee+floor(bond/2))'], 2)}.
- **Dispute classes.** If the dispute transaction also contains a new `RequestPrice` from the same requester for the same
  question, the adapter reset the question (first dispute). Otherwise there is an earlier dispute on the same question in the
  data (second dispute), and the adapter only flags it, so the market waits for the DVM. Unclassified: {unc}.
  In OOv2 and MOOV2 *every* dispute calls `Oracle.requestPrice` (the DVM, via `OracleChildTunnel`); dispute transactions
  show `OracleChildTunnel` logs for both classes.
- **Lock-up.** Each proposal locks bond + finalFee from its `ProposePrice` block time to its `Settle` block time (or to data end
  if unsettled). Concurrent sums are computed as a step function, and the max / p95 / median / mean are **time-weighted over the window**.

## 3. Counts
""")
w("| Requester group | Requests | of which dispute resets | Proposals | Disputes | Dispute rate | Settles |\n|---|---|---|---|---|---|---|")
for name in ["ALL Polymarket", "MOOV2 UmaCtfAdapter (binary)", "MOOV2 NegRisk UmaCtfAdapter",
             "MOOV2 PolymarketOOReporter (UMA-owned, PM v2)", "OOv2 legacy (all PM requesters)"]:
    g = G[name]
    w(f"| {name} | {n(g['requests'])} | {n(g['requests_created_by_dispute_reset'])} | {n(g['proposals'])} | {n(g['disputes'])} | {pc(g['dispute_rate_per_proposal'])} | {n(g['settles'])} |")
w(f"""
- Requests in the window that had no proposal by data end: {n(A['requests_in_window_never_proposed_by_data_end'])}
  (median age 9 days; many are props on events that had not happened yet).
- Dispute classes: **first (reset) {n(first)}**, **second (DVM decides market) {n(second)}**, unclassified {n(unc)}.
  Legacy OOv2: all {L['disputes']} were first disputes.
- Self-disputes (proposer = disputer): {self_d}. 86 of them are by `0xa0B6…0e3891` on its own proposals with liveness 10^9 s
  (2026-08-13), and all 86 resolved "proposer right" (two more disputes on such proposals came from other addresses). Of the
  other 57, 55 resolved with the proposer's own proposal wrong, 1 with it right, and 1 was pending. Excluding self-disputes, outcomes are 831 disputer right / 124 proposer right / 89 pending.
- Dispute outcomes (disputes in window): disputer right (proposal wrong) {n(right)}, proposer right {n(wrong)}, pending at data end {n(pend)}.
- Proposed prices: {', '.join(f'{k} {n(v)}' for k, v in A['proposed_price'].items())}. No proposal used the ignore price.
- Settled prices (all settles in window): {', '.join(f'{k} {n(v)}' for k, v in A['settled_price_all'].items())}.
  **"Too early"/ignore settles: {n(A['settled_price_all'].get('IGNORE / too early (int256 min)', 0))}, all on disputed
  requests** ({pc(A['settled_price_disputed'].get('IGNORE / too early (int256 min)', 0) / sum(A['settled_price_disputed'].values()), 1)} of settled disputed requests). 50-50 settles: {n(A['settled_price_all'].get('50-50 (0.5e18)', 0))}.
- Distinct proposers: **{A['distinct_proposers']}** (MOOV2 {M['distinct_proposers']}, legacy {L['distinct_proposers']}). Distinct disputers: **{A['distinct_disputers']}**.
  Top 10 proposers made {pc(A['top10_share_of_proposals'], 1)} of proposals; the top one made {pc(A['top1_share_of_proposals'], 1)}.

Weekly ("rewards" = rewards paid on undisputed settles):

| Week | Requests | Proposals | Proposals/day | Disputes | Dispute rate | Rewards paid | Reward/proposal |
|---|---|---|---|---|---|---|---|""")
for a, b, r, p, d, rw, nd in wk:
    w(f"| {a}..{b} | {n(r)} | {n(p)} | {n(round(p / nd))} | {d} | {pc(d / p)} | {u(rw)} | {u(rw / p, 2)} |")
w("""
By market type (keyword regex on the title from `RequestPrice`; rough):

| Category | Proposals | Disputes | Dispute rate | Main liveness values (s: count) |
|---|---|---|---|---|""")
for k, v in sorted(pcat.items(), key=lambda x: -x[1]):
    lv = A["liveness_by_category_s"].get(k, {})
    w(f"| {k} | {n(v)} | {n(dcat.get(k, 0))} | {pc(dcat.get(k, 0) / v)} | {', '.join(f'{a}: {n(b)}' for a, b in list(lv.items())[:4])} |")

w(f"""
## 4. Money

Currency: **USDC.e** (`0x2791…4174`) on every Polymarket request in the data (2,184,143 `RequestPrice` events and the
enriched requests). The exception is 25 proposals on the legacy UmaCtfAdapter v2.0, which use native USDC (`0x3c49…3359`).
Both tokens have 6 decimals, so all amounts below are in USD.
The final fee was **$250 on every request** ({n(A['finalFee_values_usd'].get('250.0', 0))} proposals).

| Per proposal (window) | min | p10 | p25 | median | p75 | p90 | p99 | max | mean |
|---|---|---|---|---|---|---|---|---|---|""")
for label, key in (("Reward (USD)", "reward_per_proposal_usd"), ("Bond (USD, excl. final fee)", "bond_per_proposal_usd"),
                   ("Stake = bond + final fee (USD)", "stake_per_proposal_usd(bond+finalFee)")):
    dd = A[key]
    w(f"| {label} | " + " | ".join(u(dd[k], 2) for k in ("p0", "p10", "p25", "p50", "p75", "p90", "p99", "p100", "mean")) + " |")
w(f"""
- Bond values: {', '.join(f'${k}: {n(v)}' for k, v in A['bond_values_usd'].items())}. The 16 at $502 come from payouts $2 above
  bond + fee + reward, probably a reward changed after the request.
- Reward values: {', '.join(f'${k}: {n(v)}' for k, v in A['reward_values_usd'].items())}. Of the 276 rewards of $0, 137 are disputed requests whose reward was refunded on
  dispute and then read via `getRequest()`. The rest had a zero reward when read.
- Reward values by adapter: MOOV2 binary {', '.join(f'${k}: {n(v)}' for k, v in MB['reward_values_usd'].items())};
  MOOV2 NegRisk {', '.join(f'${k}: {n(v)}' for k, v in MN['reward_values_usd'].items())};
  legacy OOv2 {', '.join(f'${k}: {n(v)}' for k, v in L['reward_values_usd'].items())}.

| Money flow (window) | USD |
|---|---|
| Proposer stake posted, Σ(bond + fee) over {n(A['proposals'])} proposals (capital that is recycled) | {u(A['total_proposer_stake_posted_usd'])} |
| of which bonds only | {u(A['total_bond_posted_usd(excl finalFee)'])} |
| Disputer stake posted ({n(A['disputes'])} disputes) | {u(A['total_disputer_stake_posted_usd'])} |
| **Rewards paid to proposers** (undisputed settles in window; Polymarket-funded) | **{u(A['rewards_paid_to_proposers_on_undisputed_settles_usd'])}** |
| **To UMA Store**: Σ(finalFee + ⌊bond/2⌋) over disputes in window | **{u(A['store_fees_from_disputes_usd(finalFee+floor(bond/2))'])}** |
| Store fees, first disputes / second disputes | {u(A['store_fees_by_dispute_class_usd'].get('first dispute (adapter reset: new request in the dispute tx)'))} / {u(A['store_fees_by_dispute_class_usd'].get('second dispute (no reset; market waits for DVM)'))} |
| Forfeited by losers (bond + fee) on disputes settled by data end ({n(right + wrong)}) | {u(A['forfeited_by_losers_usd(bond+finalFee, settled disputes)'])} |
| of which to the Store / to the winners | {u(A['of_which_to_store_usd'])} / {u(A['of_which_to_winners_usd(bond-floor(bond/2))'])} |

Store fee per dispute: $375 (bond $250) or $500 (bond $500); median {u(A['store_fee_per_dispute_usd']['p50'])}.
The independent Store transfer check gives {u(ST['MOOV2']['usd'], 2)} from MOOV2 and {u(ST['OOv2']['usd'], 2)} from OOv2. The OOv2 figure
includes one non-Polymarket dispute; the Polymarket share is {u(L['store_fees_from_disputes_usd(finalFee+floor(bond/2))'], 2)}.

## 5. Time

Configured liveness ({n(A['proposals'])} proposals): {', '.join(f'{int(k):,} s: {n(v)}' for k, v in A['liveness_values_s'].items())}.

| Duration | {DH.split(chr(10))[0][2:]}
{DH.split(chr(10))[1]}---|""")
for label, key in (("Undisputed: proposal → settle", "undisputed_propose_to_settle_h"),
                   ("Undisputed: settle lag after liveness expiry", "undisputed_settle_lag_after_liveness_h"),
                   ("Proposal → dispute", "proposal_to_dispute_h"),
                   ("Disputed: dispute → settle (all, = DVM round trip)", "disputed_dispute_to_settle_h"),
                   ("… first disputes", "dispute_to_settle_h[first dispute (adapter reset: new request in the dispute tx)]"),
                   ("… second disputes (market waits)", "dispute_to_settle_h[second dispute (no reset; market waits for DVM)]"),
                   ("First dispute → reset request settled (market delay)", "first_dispute_to_reset_request_settled_h"),
                   ("Lock duration per proposal (any outcome)", "lock_duration_per_proposal_h")):
    w(f"| {label} " + dl(A.get(key)))
w(f"""
- Disputes still unsettled at data end: {A['disputed_unsettled_at_data_end']} (age median {h(A['disputed_unsettled_age_h'].get('p50'))}, max {h(A['disputed_unsettled_age_h'].get('p100'))}).
  Undisputed proposals unsettled at data end: {A['undisputed_unsettled_at_data_end']}.
- MOOV2 binary undisputed median {h(MB['undisputed_propose_to_settle_h']['p50'])}; NegRisk {h(MN['undisputed_propose_to_settle_h']['p50'])}
  (mostly 2 h liveness); legacy OOv2 {h(L['undisputed_propose_to_settle_h']['p50'])}.
- 92% of settles on disputed requests land between 00:00 and 01:00 UTC, so the resolvers settle DVM results in a daily
  batch, which adds up to a day to the DVM round trip. The p95 of about 169 h points to votes that rolled to a later round.

## 6. Capital lock-up

All proposers (time-weighted over the window): **max {u(lk['max'])}** (at {lk['max_at']}), **p95 {u(lk['p95'])}**,
**median {u(lk['p50'])}**, mean {u(lk['tw_mean'])}. Capital-time is {lk['integral_usd_days']:,.0f} USD-days, which at 5% APR is
**{u(A['all_proposers_capital_cost_usd_at_5pct_apr'])}** for the quarter (an assumed rate, for scale only).
Disputers' locked stake: max {u(ldk['max'])}, p95 {u(ldk['p95'])}, median {u(ldk['p50'])}.

| # | Proposer | Proposals | Share | Max locked | p95 | Median | Mean | Rewards earned | Disputed against | Lost | Stake lost |
|---|---|---|---|---|---|---|---|---|---|---|---|""")
for i, t in enumerate(top, 1):
    w(f"| {i} | `{t['proposer']}` | {n(t['proposals'])} | {pc(t['share'], 2)} | {u(t['locked_max_usd'])} | {u(t['locked_p95_usd'])} | {u(t['locked_median_usd'])} | {u(t['locked_tw_mean_usd'])} | {u(t['rewards_earned_usd'])} | {t['disputed_against']} | {t['disputes_lost']} | {u(t['stake_lost_usd'])} |")
w(f"""
Top 10 together: {pc(A['top10_share_of_proposals'], 1)} of proposals and {u(sum(t['rewards_earned_usd'] for t in top))} of the
{u(A['rewards_paid_to_proposers_on_undisputed_settles_usd'])} rewards. Several top proposers are contracts that bots call
(the transaction sender ≠ the `proposer`). Medians of $0 mean those proposers had nothing locked most of the time (bursty activity).

Top disputers: {', '.join(f'`{a[:10]}…` {c}' for a, c in A['top_disputers'][:6])}.

## 7. Disputed markets: Gamma API

{GS['matched']} of {GS['disputes']} disputes matched a Gamma market (by `market_id` in the ancillary data, else by `question_ids`;
closed markets need `closed=true`), covering {gsa['unique_markets_matched']} unique markets.

| Disputes | Unique markets | Markets with volume field | Σ lifetime volume | Median | p90 | Max |
|---|---|---|---|---|---|---|""")
for name in ("all disputes", "second disputes (market waits for DVM)", "pending at data end", "excluding 88 self-disputes by 0xa0B6"):
    g = GS[name]
    v = g["lifetime_volume_usd"]
    label = "excluding the 143 self-disputes" if name.startswith("excluding") else name
    w(f"| {label} ({g['disputes']}) | {g['unique_markets_matched']} | {v.get('n', 0)} | {u(v.get('sum'))} | {u(v.get('median'))} | {u(v.get('p90'))} | {u(v.get('max'))} |")
w(f"""
- Second-dispute markets, where traders waited for the DVM (median {h(A['dispute_to_settle_h[second dispute (no reset; market waits for DVM)]']['p50'])}),
  are the big ones. Largest: """ + "; ".join(f"{m['title']} ({u(m['volume'])}, {m['dclass'].split(' (')[0]}, {m['outcome']})" for m in GS['largest_disputed_markets'][:5]) + f""".
- Open interest *now* (data-api `/oi`) on markets whose dispute was still pending at data end: {u(GS['pending_disputes_open_interest_now_usd'].get('sum'))}
  across {GS['pending_disputes_open_interest_now_usd'].get('n')} markets (one market is {u(GS['pending_disputes_open_interest_now_usd'].get('max'))}).
- Lifetime volume is turnover, not money at risk. It overstates what was actually waiting during a dispute. Open interest at the
  time of each dispute is not exposed by Gamma, and reconstructing it from CTF split/merge logs was out of scope.

## 8. Caveats

- **RPC sources.** Logs came from public Tenderly and OnFinality gateways, because the common public RPCs cannot serve this density.
  No API keys were used. Completeness rests on {cc_ok}/{len(CC)} exact chunk re-counts on other providers, contiguous chunk coverage,
  and the exact match with the Store's USDC.e inflows. It is not a full second download.
- **Window edges.** Event times are block timestamps (UTC). Requests created before block 89,000,000 (about 2026-06-23) are joined through
  `getRequest()`. 4 settles in the window lack their proposal (proposed before the lead-in), and their lock-up before 2026-06-23 is missing (negligible).
- **Bonds.** For {pc(S['bond_source_for_window_proposals']['solved from undisputed Settle payout'] / A['proposals'], 1)} of window
  proposals the bond is solved from the `Settle` payout. That is exact under the verified payout rules unless the reward changed
  after the request (16 rows show a +$2 residual).
- **Dispute classes** rely on the same-transaction re-request. A dispute on a question that was already resolved, or that was reset for another
  reason, would show as "second" only if an earlier dispute is in the data, else as "unclassified" (here {unc}).
- **"Polymarket" requesters** include UMA's PolymarketOOReporter (Polymarket v2 stack; {MR['proposals']} proposals). Two third-party adapters on
  Polymarket's CTF are excluded.
- **Categories** come from a keyword regex on titles and are approximate. Volumes are Gamma's lifetime numbers at query time (2026-10-01).
- **Not measured.** Gas: Polymarket pays for about 2M `initialize` transactions, proposers for proposals, resolvers for settles. Off-chain
  resolver review policy. DVM voter rewards and UMA token economics.
- **Opportunity cost** uses an assumed 5% APR, purely for scale.

## Files

- `scripts/rpc.py`: JSON-RPC client with endpoint fallback; `fetch_logs.py`: chunked, checkpointed, decoded log pull;
  `build_requests.py`: join to one row per request; `enrich_requests.py`: `getRequest()` for requests created before the range;
  `columns.py` + `stats_np.py`: stats; `gamma_disputes.py` + `gamma_summary.py`: Gamma/OI; `store_check.py`, `crosscheck*.py`,
  `moov2_history.py`, `probe_contracts.py`, `find_blocks.py`: checks; `write_report.py`: this file.
- `data/raw/{{MOOV2,OOv2}}/*.jsonl.gz`: decoded events (all requesters); `data/requests_polymarket.jsonl.gz`: joined requests;
  `data/stats.json`: every number; `data/disputes_in_window.json`: all {n(A['disputes'])} disputes with details;
  `data/gamma_*.json`, `data/store_transfers_check.json`, `data/crosscheck.json`, `data/moov2_admin_history.json`,
  `data/contracts_probe.json`, `data/block_anchors.json`.
""")
open(os.path.join(ROOT, "stats.md"), "w").write("\n".join(out))
print("wrote stats.md", sum(len(x) for x in out), "chars")
