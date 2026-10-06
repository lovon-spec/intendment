# Disputes of the 90 days to 2026-10-01

Recomputed from `data/disputes_in_window.json` and `data/gamma_disputed_markets.json`.

## Section 1: today, measured

| number | value |
|---|---|
| disputes | 1,187 |
| first disputes (the market resets) | 1,126 |
| second disputes (the market waits for the vote) | 61 |
| self-disputes (proposer and disputer the same address) | 143 |
| resolved disputes | 1,097 |
| of which the vote found the proposal wrong | 886 (80.8%) |
| pending at the end of the data | 90 |
| answered "too early" | 567 |
| UMA's take, all disputes | 529,625 |
| of the non-self part, paid by proposers that lost | 374,750 |
| of the non-self part, paid by disputers that lost | 58,125 |
| UMA's take, non-self disputes since 2026-09-01 | 172,375 |
| dispute to settlement, median / p95 hours | 78.4 / 168.8 |
| first dispute to the reset request's settlement, median hours | 2.4 (n = 1,023) |
| second dispute to settlement (the market waits), median hours | 77.9 (n = 58) |

## Section 6: what it changes

Self-disputes are counted apart. A scenario's cases are the disputes whose losing side, as the vote decided, would have ended the case itself.

| scenario | cases settled | UMA's take not paid | final fees kept by the side ending the case | burn paid to the venue | blocked markets reopened | market-hours | lifetime volume |
|---|---|---|---|---|---|---|---|
| only proposals the vote called "too early" are conceded | 542 | 249,250 (47%) | 135,500 | 113,750 | 12 | 946 | 11.8 million |
| every proposal the vote found wrong is conceded | 831 | 374,750 (71%) | 207,750 | 167,000 | 25 | 1,999 | 106.6 million |
| as above, and every wrong disputer on a non-blocking case withdraws | 923 | 417,875 (79%) | 230,750 | 187,125 | 25 | 1,999 | 106.6 million |

Blocked markets in the middle scenario: 25, waiting a median 78.3 hours; 24 have a lifetime volume on record.
The largest: "Will Ronaldo Cry at the World Cup?", 89.2 million lifetime volume, 74 hours.

Honest self-corrections (self-disputes, the configuration accident left out): 57, UMA's take 25,000; as retractions 14,250 stays with the proposers and 10,750 goes to the venue. Self-disputes left out as the configuration accident: 86.

September run rate, middle scenario: 274 cases, UMA's take 121,000; times twelve, 630,000 a year to the venue and 822,000 of final fees kept, 1,452,000 in all.

Stake released early in the third scenario, windows of one and four hours: 3,637,334 USDC.e-days, 498 of interest at 5%.
