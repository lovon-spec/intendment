# Polymarket resolution through UMA's Optimistic Oracle on Polygon: 90-day on-chain stats

Window: **2026-07-03 00:00 UTC to 2026-10-01 00:00 UTC** (90 days, by block timestamp), Polygon PoS (chain 137),
blocks **89,554,537 to 94,738,439**. Events were fetched for blocks 89,000,000 to 94,792,499 (9.6 days of lead-in, and
follow-up to 2026-10-01T22:30:56+00:00), so requests and proposals that straddle the window edges can be joined.
The full 90 days was feasible; no fallback to 30 days was needed.

Everything below is decoded from `eth_getLogs` on the two UMA oracles plus read-only `eth_call`s. Scripts are in
`scripts/`, decoded events in `data/raw/`, all numbers in `data/stats.json`.

## Headline

- **Volume.** 1,845,259 proposals and 2,059,616 requests in 90 days, about
  20,503 proposals/day on average. That grew from about 9,296/day in early July to
  about 30,966/day in late September. Roughly 85% are sports or esports markets (title regex).
- **Not vanilla UMA.** 99.86% of proposals go through UMA's *Managed* OOv2 (MOOV2), not the
  permissionless OOv2. On MOOV2, only whitelisted proposers can propose (339 addresses
  on the default whitelist today), only the two addresses holding MOOV2's `RESOLVER_ROLE` can settle (since 2026-02-24),
  and liveness goes as low as 10 minutes. Legacy OOv2 adapters handled only 2,673 proposals.
- **Disputes are rare.** 1,187 disputes, or 0.064% of proposals
  (0.057% without 143 self-disputes). 1,126 were first disputes, which reset the
  question to a fresh request. Only 61 were second disputes, where the market waits for UMA's DVM vote. Every
  dispute still triggers a DVM vote to settle the bonds. Of the resolved disputes, 80.8% found
  the proposal wrong (87.0% excluding self-disputes). 589 came back "too early".
- **Fees.** Polymarket paid proposers **$2,673,876** in rewards over the
  window (median reward $0.80, mean $1.45).
  UMA's Store took **$529,625** (final fee $250 plus half the bond, per dispute).
  The Store fees come out of dispute losers' bonds, not from Polymarket. Late-September run rate:
  about $30,838/day in rewards.
- **Capital lock-up is small in money terms.** Each proposal locks bond plus final fee: $500 (72%
  of proposals) or $750 (28%). The lock lasts a median
  34.5 min (p90 2.03 h). Across all proposers the
  locked total was a time-weighted mean of $598,774 (median $439,500, p95 $1,705,750, max $3,497,500).
  That is 53.9M USD-days, or about **$7,382 of
  opportunity cost at 5% APR** for the quarter, against $2,673,876 of rewards.
- **Time.** Undisputed proposals settle a median 34.5 min after proposal
  (p99 2.69 h). Disputed requests take a median
  78.38 h from dispute to settle (p95 168.82 h),
  which is the DVM round trip. After a first dispute, the reset question resolved a median
  2.40 h later.

## 1. Contracts

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

MOOV2 upgrade and role history (from `Upgraded` / `RoleGranted` logs, `data/moov2_admin_history.json`):
- 2025-08-01 block 74,677,419: `Upgraded` to `0x3555e39a1264f5f8febc129ebbb909f3ea299936`
- 2026-02-24 block 83,411,124: `Upgraded` to `0x7d660195ed02ac61a42408780233f06ddd6a2e42`
- 2026-09-22 block 94,239,432: `Upgraded` to `0x8c7556a42135f6a74d096d5992b33d5ebe0a5f76`
- 2026-02-24 (`initializeV2`): `RESOLVER_ROLE` granted to `0x3396…3081` (2026-03-24: `0x9725…d869`), minimum dispute window 300 s.
  From then on `settle()` is `onlyResolver`, and disputes stay open until a resolver settles. A sample of 35 settle transactions
  in the window were all sent by these two resolvers.
- `BondUpdated` events are only emitted by the implementation live since 2026-09-22, so bonds for most of the window are
  derived as described in section 2.

MOOV2 requester whitelist today: exactly the three MOOV2 requesters above. Default proposer whitelist: 339 addresses.

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
- **Completeness check.** 10/10 randomly chosen chunks were re-counted on a different RPC (onfinality, drpc,
  publicnode), and every count matched exactly. Log `blockTimestamp`s match block headers (spot-checked).
- **Polygon block time** is now about 1.5 s (about 57,600 blocks/day), not 2 s; 90 days is 5.18M blocks.
- **Decoding.** Python `eth_abi`. Each request is keyed by (oracle, requester, identifier, timestamp, keccak(ancillaryData)).
  For the UmaCtfAdapter family, keccak(ancillaryData) is the adapter's `questionID`. Full ancillary text is not stored, only
  its hash plus title / `market_id` / initializer from `RequestPrice`, to keep the data at about 400 MB.
- **Request parameters.** Reward and final fee come from `RequestPrice`. For 14,855 window
  proposals whose request predates the fetched range, they come from a read-only `getRequest()` call
  (`data/enrich_getRequest.jsonl`). Bond sources for window proposals:
  unknown: 0, BondUpdated event: 159,424, getRequest eth_call: 14,855, solved from undisputed Settle payout: 1,669,965, solved from disputed Settle payout: 1,015.
  Payout-derived bonds use the oracle rules: undisputed payout = bond + finalFee + reward; disputed payout = bond + (bond − ⌊bond/2⌋) + finalFee.
  The reward is refunded to the requester on dispute (`refundOnDispute` is true on every enriched request).
  These rules were checked on every settled request whose bond is known independently:
  187,674/187,674 undisputed and
  101/101 disputed payouts match exactly.
  **Store revenue cross-check:** USDC.e transfers from MOOV2 to the Store in the window total $517,625.00
  (1,163 transfers), equal to the event-derived $517,625.00.
- **Dispute classes.** If the dispute transaction also contains a new `RequestPrice` from the same requester for the same
  question, the adapter reset the question (first dispute). Otherwise there is an earlier dispute on the same question in the
  data (second dispute), and the adapter only flags it, so the market waits for the DVM. Unclassified: 0.
  In OOv2 and MOOV2 *every* dispute calls `Oracle.requestPrice` (the DVM, via `OracleChildTunnel`); dispute transactions
  show `OracleChildTunnel` logs for both classes.
- **Lock-up.** Each proposal locks bond + finalFee from its `ProposePrice` block time to its `Settle` block time (or to data end
  if unsettled). Concurrent sums are computed as a step function, and the max / p95 / median / mean are **time-weighted over the window**.

## 3. Counts

| Requester group | Requests | of which dispute resets | Proposals | Disputes | Dispute rate | Settles |
|---|---|---|---|---|---|---|
| ALL Polymarket | 2,059,616 | 1,126 | 1,845,259 | 1,187 | 0.064% | 1,844,808 |
| MOOV2 UmaCtfAdapter (binary) | 1,576,280 | 969 | 1,433,347 | 1,024 | 0.071% | 1,432,985 |
| MOOV2 NegRisk UmaCtfAdapter | 483,270 | 130 | 409,216 | 135 | 0.033% | 409,114 |
| MOOV2 PolymarketOOReporter (UMA-owned, PM v2) | 41 | 3 | 23 | 4 | 17.391% | 21 |
| OOv2 legacy (all PM requesters) | 25 | 24 | 2,673 | 24 | 0.898% | 2,688 |

- Requests in the window that had no proposal by data end: 239,474
  (median age 9 days; many are props on events that had not happened yet).
- Dispute classes: **first (reset) 1,126**, **second (DVM decides market) 61**, unclassified 0.
  Legacy OOv2: all 24 were first disputes.
- Self-disputes (proposer = disputer): 143. 86 of them are by `0xa0B6…0e3891` on its own proposals with liveness 10^9 s
  (2026-08-13), and all 86 resolved "proposer right" (two more disputes on such proposals came from other addresses). Of the
  other 57, 55 resolved with the proposer's own proposal wrong, 1 with it right, and 1 was pending. Excluding self-disputes, outcomes are 831 disputer right / 124 proposer right / 89 pending.
- Dispute outcomes (disputes in window): disputer right (proposal wrong) 886, proposer right 211, pending at data end 90.
- Proposed prices: NO (0) 1,207,902, YES (1e18) 607,044, 50-50 (0.5e18) 30,313. No proposal used the ignore price.
- Settled prices (all settles in window): NO (0) 1,207,250, YES (1e18) 606,632, 50-50 (0.5e18) 30,337, IGNORE / too early (int256 min) 589.
  **"Too early"/ignore settles: 589, all on disputed
  requests** (51.5% of settled disputed requests). 50-50 settles: 30,337.
- Distinct proposers: **308** (MOOV2 232, legacy 130). Distinct disputers: **153**.
  Top 10 proposers made 74.4% of proposals; the top one made 28.7%.

Weekly ("rewards" = rewards paid on undisputed settles):

| Week | Requests | Proposals | Proposals/day | Disputes | Dispute rate | Rewards paid | Reward/proposal |
|---|---|---|---|---|---|---|---|
| 2026-07-03..2026-07-09 | 68,278 | 65,069 | 9,296 | 70 | 0.108% | $140,910 | $2.17 |
| 2026-07-10..2026-07-16 | 69,248 | 60,657 | 8,665 | 61 | 0.101% | $133,593 | $2.20 |
| 2026-07-17..2026-07-23 | 100,635 | 70,297 | 10,042 | 72 | 0.102% | $154,515 | $2.20 |
| 2026-07-24..2026-07-30 | 140,919 | 106,757 | 15,251 | 66 | 0.062% | $210,238 | $1.97 |
| 2026-07-31..2026-08-06 | 137,980 | 118,003 | 16,858 | 49 | 0.042% | $207,057 | $1.75 |
| 2026-08-07..2026-08-13 | 170,591 | 133,643 | 19,092 | 210 | 0.157% | $199,488 | $1.49 |
| 2026-08-14..2026-08-20 | 156,943 | 137,697 | 19,671 | 74 | 0.054% | $221,990 | $1.61 |
| 2026-08-21..2026-08-27 | 165,801 | 156,152 | 22,307 | 80 | 0.051% | $223,443 | $1.43 |
| 2026-08-28..2026-09-03 | 175,835 | 169,552 | 24,222 | 83 | 0.049% | $237,949 | $1.40 |
| 2026-09-04..2026-09-10 | 234,778 | 214,231 | 30,604 | 77 | 0.036% | $286,083 | $1.34 |
| 2026-09-11..2026-09-17 | 184,879 | 201,421 | 28,774 | 137 | 0.068% | $256,724 | $1.27 |
| 2026-09-18..2026-09-24 | 241,538 | 225,982 | 32,283 | 78 | 0.035% | $217,511 | $0.96 |
| 2026-09-25..2026-09-30 | 212,191 | 185,798 | 30,966 | 130 | 0.070% | $184,374 | $0.99 |

By market type (keyword regex on the title from `RequestPrice`; rough):

| Category | Proposals | Disputes | Dispute rate | Main liveness values (s: count) |
|---|---|---|---|---|
| sports/esports | 1,563,760 | 986 | 0.063% | 7200: 750,130, 1800: 430,120, 900: 364,166, 3600: 14,929 |
| crypto price | 105,988 | 6 | 0.006% | 600: 101,603, 7200: 2,414, 900: 1,680, 1800: 286 |
| weather | 82,389 | 16 | 0.019% | 900: 76,749, 7200: 4,588, 1800: 687, 21600: 120 |
| other | 69,854 | 120 | 0.172% | 7200: 50,395, 900: 16,489, 600: 2,407, 21600: 563 |
| unknown(no RequestPrice in range) | 14,845 | 48 | 0.323% | 7200: 13,807, 1800: 651, 900: 366, 600: 21 |
| mentions/social | 8,423 | 11 | 0.131% | 7200: 8,423 |

## 4. Money

Currency: **USDC.e** (`0x2791…4174`) on every Polymarket request in the data (2,184,143 `RequestPrice` events and the
enriched requests). The exception is 25 proposals on the legacy UmaCtfAdapter v2.0, which use native USDC (`0x3c49…3359`).
Both tokens have 6 decimals, so all amounts below are in USD.
The final fee was **$250 on every request** (1,845,259 proposals).

| Per proposal (window) | min | p10 | p25 | median | p75 | p90 | p99 | max | mean |
|---|---|---|---|---|---|---|---|---|---|
| Reward (USD) | $0.00 | $0.80 | $0.80 | $0.80 | $2.00 | $3.50 | $5.00 | $20.00 | $1.45 |
| Bond (USD, excl. final fee) | $250.00 | $250.00 | $250.00 | $250.00 | $500.00 | $500.00 | $500.00 | $2,500.00 | $319.58 |
| Stake = bond + final fee (USD) | $500.00 | $500.00 | $500.00 | $500.00 | $750.00 | $750.00 | $750.00 | $2,750.00 | $569.58 |

- Bond values: $250.0: 1,331,879, $500.0: 513,342, $2500.0: 22, $502.0: 16. The 16 at $502 come from payouts $2 above
  bond + fee + reward, probably a reward changed after the request.
- Reward values: $0.8: 1,076,964, $3.5: 263,565, $2.0: 200,672, $0.6: 155,992, $1.5: 97,601, $5.0: 50,155, $0.0: 276, $20.0: 22, $0.5: 12. Of the 276 rewards of $0, 137 are disputed requests whose reward was refunded on
  dispute and then read via `getRequest()`. The rest had a zero reward when read.
- Reward values by adapter: MOOV2 binary $0.8: 831,413, $3.5: 243,092, $2.0: 155,361, $1.5: 97,505, $0.6: 88,683, $5.0: 17,127, $0.0: 166;
  MOOV2 NegRisk $0.8: 245,551, $0.6: 67,309, $2.0: 45,308, $5.0: 30,407, $3.5: 20,462, $1.5: 96, $0.0: 61, $20.0: 22;
  legacy OOv2 $5.0: 2,621, $0.0: 49, $2.0: 3.

| Money flow (window) | USD |
|---|---|
| Proposer stake posted, Σ(bond + fee) over 1,845,259 proposals (capital that is recycled) | $1,051,018,532 |
| of which bonds only | $589,703,782 |
| Disputer stake posted (1,187 disputes) | $762,500 |
| **Rewards paid to proposers** (undisputed settles in window; Polymarket-funded) | **$2,673,876** |
| **To UMA Store**: Σ(finalFee + ⌊bond/2⌋) over disputes in window | **$529,625** |
| Store fees, first disputes / second disputes | $500,875 / $28,750 |
| Forfeited by losers (bond + fee) on disputes settled by data end (1,097) | $716,500 |
| of which to the Store / to the winners | $495,375 / $221,125 |

Store fee per dispute: $375 (bond $250) or $500 (bond $500); median $500.
The independent Store transfer check gives $517,625.00 from MOOV2 and $12,250.50 from OOv2. The OOv2 figure
includes one non-Polymarket dispute; the Polymarket share is $12,000.00.

## 5. Time

Configured liveness (1,845,259 proposals): 7,200 s: 829,757, 900 s: 459,450, 1,800 s: 431,744, 600 s: 108,358, 3,600 s: 15,024, 21,600 s: 683, 57,600 s: 120, 1,000,000,000 s: 88, 90,000 s: 35.

| Duration | n | min | p10 | p25 | median | p75 | p90 | p95 | p99 | max | mean |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Undisputed: proposal → settle | 1,844,070 | 10.3 min | 16.0 min | 21.8 min | 34.5 min | 2.02 h | 2.03 h | 2.06 h | 2.69 h | 25.02 h | 1.19 h |
| Undisputed: settle lag after liveness expiry | 1,844,070 | 0.0 min | 0.7 min | 0.9 min | 1.3 min | 2.1 min | 6.4 min | 14.1 min | 1.49 h | 23.91 h | 5.4 min |
| Proposal → dispute | 1,187 | 0.1 min | 1.4 min | 2.9 min | 12.3 min | 54.1 min | 4.96 h | 57.84 h | 60.99 h | 68.86 h | 5.06 h |
| Disputed: dispute → settle (all, = DVM round trip) | 1,097 | 53.49 h | 57.37 h | 63.87 h | 78.38 h | 88.61 h | 99.84 h | 168.82 h | 168.95 h | 450.38 h | 84.11 h |
| … first disputes | 1,039 | 53.49 h | 57.70 h | 63.83 h | 78.71 h | 88.11 h | 100.19 h | 168.82 h | 168.95 h | 450.38 h | 84.40 h |
| … second disputes (market waits) | 58 | 54.19 h | 56.02 h | 67.28 h | 77.93 h | 94.41 h | 99.02 h | 99.76 h | 100.36 h | 100.44 h | 78.91 h |
| First dispute → reset request settled (market delay) | 1,023 | 11.5 min | 36.1 min | 44.1 min | 2.40 h | 7.34 h | 64.80 h | 99.99 h | 607.77 h | 1427.52 h | 27.07 h |
| Lock duration per proposal (any outcome) | 1,845,259 | 10.3 min | 16.0 min | 21.9 min | 34.5 min | 2.02 h | 2.03 h | 2.06 h | 2.73 h | 450.39 h | 1.25 h |

- Disputes still unsettled at data end: 90 (age median 67.00 h, max 221.41 h).
  Undisputed proposals unsettled at data end: 0.
- MOOV2 binary undisputed median 31.6 min; NegRisk 2.02 h
  (mostly 2 h liveness); legacy OOv2 2.22 h.
- 92% of settles on disputed requests land between 00:00 and 01:00 UTC, so the resolvers settle DVM results in a daily
  batch, which adds up to a day to the DVM round trip. The p95 of about 169 h points to votes that rolled to a later round.

## 6. Capital lock-up

All proposers (time-weighted over the window): **max $3,497,500** (at 2026-09-27T21:37:57+00:00), **p95 $1,705,750**,
**median $439,500**, mean $598,774. Capital-time is 53,889,660 USD-days, which at 5% APR is
**$7,382** for the quarter (an assumed rate, for scale only).
Disputers' locked stake: max $99,000, p95 $71,750, median $24,750.

| # | Proposer | Proposals | Share | Max locked | p95 | Median | Mean | Rewards earned | Disputed against | Lost | Stake lost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `0xd9aa1A620F692Eedee28F267C9D448cF86f3b5D3` | 529,400 | 28.69% | $1,062,500 | $712,500 | $92,250 | $197,911 | $592,633 | 72 | 71 | $36,000 |
| 2 | `0x4A1DF1565a7704BbFa61e9Cd543DD0265CC48bC0` | 230,477 | 12.49% | $754,500 | $340,000 | $4,750 | $52,550 | $209,013 | 100 | 40 | $21,750 |
| 3 | `0x94f7eF03eC6B2028bF80FAcABF8c997bfDe36faF` | 148,790 | 8.06% | $328,750 | $104,500 | $14,000 | $28,235 | $289,509 | 167 | 153 | $109,250 |
| 4 | `0x1c128F11d776b4B966177C0BCef5c84b6b0DFE44` | 107,206 | 5.81% | $626,500 | $244,500 | $0 | $41,560 | $91,427 | 6 | 4 | $2,000 |
| 5 | `0xa0B6210f5B522b97bbcE9B8E617627105c0e3891` | 97,457 | 5.28% | $298,000 | $105,250 | $25,500 | $36,986 | $179,249 | 130 | 34 | $20,250 |
| 6 | `0xB7AD15ad3457D8b4A3f9C5007bBF27c1f80092bd` | 75,314 | 4.08% | $495,000 | $150,500 | $0 | $25,150 | $91,929 | 55 | 54 | $31,500 |
| 7 | `0x89e4e7578cB813fd2E9bF0daada9A72fA70Aa8b5` | 49,944 | 2.71% | $100,500 | $68,500 | $750 | $12,589 | $109,698 | 69 | 51 | $34,750 |
| 8 | `0x0215598391674d05C6fE0A1e8FD646b2a1FF4B66` | 45,892 | 2.49% | $493,250 | $58,500 | $0 | $11,472 | $98,901 | 28 | 28 | $21,000 |
| 9 | `0x8E0e95504Db4F909324b30Ce2b1001120d9153Db` | 44,994 | 2.44% | $183,000 | $65,000 | $12,750 | $20,146 | $71,923 | 22 | 22 | $12,000 |
| 10 | `0xc9Ffd41C7500d34606606246D8fb6242BFb6b04E` | 43,159 | 2.34% | $147,500 | $34,250 | $1,000 | $7,983 | $49,874 | 4 | 4 | $3,000 |

Top 10 together: 74.4% of proposals and $1,784,155 of the
$2,673,876 rewards. Several top proposers are contracts that bots call
(the transaction sender ≠ the `proposer`). Medians of $0 mean those proposers had nothing locked most of the time (bursty activity).

Top disputers: `0xc816F934…` 146, `0xa0B6210f…` 106, `0xE0d478a2…` 97, `0xD903f521…` 64, `0x8E0e9550…` 38, `0xA0276d26…` 37.

## 7. Disputed markets: Gamma API

1162 of 1187 disputes matched a Gamma market (by `market_id` in the ancillary data, else by `question_ids`;
closed markets need `closed=true`), covering 1102 unique markets.

| Disputes | Unique markets | Markets with volume field | Σ lifetime volume | Median | p90 | Max |
|---|---|---|---|---|---|---|
| all disputes (1187) | 1102 | 821 | $180,829,098 | $957 | $117,658 | $89,210,514 |
| second disputes (market waits for DVM) (61) | 60 | 56 | $152,135,687 | $353,440 | $1,929,815 | $89,210,514 |
| pending at data end (90) | 84 | 74 | $1,725,565 | $74 | $9,765 | $499,683 |
| excluding the 143 self-disputes (1044) | 962 | 766 | $180,093,791 | $980 | $142,263 | $89,210,514 |

- Second-dispute markets, where traders waited for the DVM (median 77.93 h),
  are the big ones. Largest: Will Ronaldo Cry at the World Cup? ($89,210,514, second dispute, disputer right (proposer lost)); Will Trump be in the WC Champions Photo? ($26,990,138, second dispute, proposer right (disputer lost)); US announces halt in Iran offensive operations by July 31? ($4,009,713, second dispute, proposer right (disputer lost)); Will AfD win the most seats in the 2026 Berlin state elections? ($2,611,971, first dispute, disputer right (proposer lost)); US x Iran Effective Ceasefire by September 4? ($2,565,026, second dispute, proposer right (disputer lost)).
- Open interest *now* (data-api `/oi`) on markets whose dispute was still pending at data end: $1,812
  across 84 markets (one market is $1,171).
- Lifetime volume is turnover, not money at risk. It overstates what was actually waiting during a dispute. Open interest at the
  time of each dispute is not exposed by Gamma, and reconstructing it from CTF split/merge logs was out of scope.

## 8. Caveats

- **RPC sources.** Logs came from public Tenderly and OnFinality gateways, because the common public RPCs cannot serve this density.
  No API keys were used. Completeness rests on 10/10 exact chunk re-counts on other providers, contiguous chunk coverage,
  and the exact match with the Store's USDC.e inflows. It is not a full second download.
- **Window edges.** Event times are block timestamps (UTC). Requests created before block 89,000,000 (about 2026-06-23) are joined through
  `getRequest()`. 4 settles in the window lack their proposal (proposed before the lead-in), and their lock-up before 2026-06-23 is missing (negligible).
- **Bonds.** For 90.5% of window
  proposals the bond is solved from the `Settle` payout. That is exact under the verified payout rules unless the reward changed
  after the request (16 rows show a +$2 residual).
- **Dispute classes** rely on the same-transaction re-request. A dispute on a question that was already resolved, or that was reset for another
  reason, would show as "second" only if an earlier dispute is in the data, else as "unclassified" (here 0).
- **"Polymarket" requesters** include UMA's PolymarketOOReporter (Polymarket v2 stack; 23 proposals). Two third-party adapters on
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
- `data/raw/{MOOV2,OOv2}/*.jsonl.gz`: decoded events (all requesters); `data/requests_polymarket.jsonl.gz`: joined requests;
  `data/stats.json`: every number; `data/disputes_in_window.json`: all 1,187 disputes with details;
  `data/gamma_*.json`, `data/store_transfers_check.json`, `data/crosscheck.json`, `data/moov2_admin_history.json`,
  `data/contracts_probe.json`, `data/block_anchors.json`.
