# Experiment 3: the credited model, re-derived payoffs and findings

Model: `intendment/credited.py`; traces: `tests/test_credited.py`. RFC 001 revision 2, section 9, experiment 3. Units in the model are 0.1 xDAI; this note is in xDAI. Every number below is illustrative arithmetic on the Scout parameters (D = 30, q1 = 0.5, D_c = 0, tier prices 10 / 50 / 100 percent of the promise), not a measured return. The model asserts after every transition that wallets, host cash, wrapper balances and fees burned to jurors sum to the money minted; every test asserts it again at its end.

## 1. Payoffs

Notation from design v0.9 section 2, with the award split: `u` prepayment (the host's cash deposit), `P_t` the tier's price of the promise `D − u`, `q1` the first-instance fee each party prepays.

- A's court loss at tier t: `s_A = u + q1 + P_t`; A's court gain `g_A = D_c`.
- B's court loss: `s_B = q1 + D_c`; B's court gain against a paying submitter `g_B = u + P_t`, against a defaulter `g_B = u` (the promise is unpaid; only a bond adds to it).
- Concession at tier t: A nets `−(u + P_t + x_t)`, B nets `+(u + P_t + x_t)`, with `x_t` the tier's share of the held fee (0.05, 0.25, 0.5; the model floors 0.05 to 0).
- Band in Y = A's net loss: `[u + P_t, u + q1 + P_t]`, width `q1` under common beliefs. With differing beliefs the width is `q1 + (E_A[P] − E_B[P])`, the tier analogue of `(p_A − p_B)(D + q + D_c)`.
- B challenges when `p · g_B ≥ (1 − p) · s_B`, i.e. `p ≥ s_B / (s_B + g_B)`.

### Vanilla (design v0.9 section 2): D = 30, q = 21.6, D_c = 0, π = 0

| | value |
|---|---|
| s_A | 51.6 |
| g_A | 0 |
| s_B | 21.6 |
| g_B | 30 |
| band width q − π | 21.6 |
| B's minimum confidence, paying submitter | 41.9% |
| B's minimum confidence against a defaulter with u = 6 at today's fee | 78.3% |

### Credited, u = 6 (promise 24)

| tier | P_t | s_A | g_A | s_B | g_B paying | g_B defaulter | band [low, high] | width | min conf. paying | min conf. defaulter |
|---|---|---|---|---|---|---|---|---|---|---|
| formal | 2.4 | 8.9 | 0 | 0.5 | 8.4 | 6 | [8.4, 8.9] | 0.5 | 5.6% | 7.7% |
| substantive | 12.0 | 18.5 | 0 | 0.5 | 18.0 | 6 | [18.0, 18.5] | 0.5 | 2.7% | 7.7% |
| malicious | 24.0 | 30.5 | 0 | 0.5 | 30.0 | 6 | [30.0, 30.5] | 0.5 | 1.6% | 7.7% |

### Credited, u = 8.4 (promise 21.6)

| tier | P_t | s_A | g_A | s_B | g_B paying | g_B defaulter | band [low, high] | width | min conf. paying | min conf. defaulter |
|---|---|---|---|---|---|---|---|---|---|---|
| formal | 2.16 | 11.06 | 0 | 0.5 | 10.56 | 8.4 | [10.56, 11.06] | 0.5 | 4.5% | 5.6% |
| substantive | 10.8 | 19.7 | 0 | 0.5 | 19.2 | 8.4 | [19.2, 19.7] | 0.5 | 2.5% | 5.6% |
| malicious | 21.6 | 30.5 | 0 | 0.5 | 30.0 | 8.4 | [30.0, 30.5] | 0.5 | 1.6% | 5.6% |

### Credited, u = 12 (promise 18)

| tier | P_t | s_A | g_A | s_B | g_B paying | g_B defaulter | band [low, high] | width | min conf. paying | min conf. defaulter |
|---|---|---|---|---|---|---|---|---|---|---|
| formal | 1.8 | 14.3 | 0 | 0.5 | 13.8 | 12 | [13.8, 14.3] | 0.5 | 3.5% | 4.0% |
| substantive | 9.0 | 21.5 | 0 | 0.5 | 21.0 | 12 | [21.0, 21.5] | 0.5 | 2.3% | 4.0% |
| malicious | 18.0 | 30.5 | 0 | 0.5 | 30.0 | 12 | [30.0, 30.5] | 0.5 | 1.6% | 4.0% |

What the tables say:

- The malicious tier reproduces the vanilla award exactly (g_B = 30, s_A = D + q1 = 30.5) at any u; u only moves how much of it is cash.
- The band is q1 = 0.5 wide at every tier, forty-three times narrower than today's 21.6. The distance between tiers (9.6 between formal and substantive at u = 6) dwarfs it: under tiers the bargaining is over the tier, not the share, and the "concession band" of design section 2 is, for the credited case, the tier ladder plus half an xDAI.
- A defaulter has no band: cash-to-concede makes court its only exit, at a loss of u + q1 plus the standing (6.5 at u = 6).
- The RFC's 1.6% and 7.7% (section 5.4) are reproduced; against a defaulter the threshold falls with u (7.7%, 5.6%, 4.0%) and against a paying submitter it depends on the tier B expects (5.6% at formal, u = 6).

## 2. Traces

All fourteen rows of RFC section 8 have a passing test, plus S1, S2 for a live concession, cash-to-concede, bond withdrawal, the payoff numbers, and a randomized sequence. Two rows pass only with a rule the RFC does not give or with a bound the RFC does not state; both are listed under 3.

Fast-population check (RFC 4.5, per 1000 cases, u = 6): the model gives 8,400 for a formal batch concession (u + 2.4, the 0.05 fee share floors to 0), 18,000 substantive, 30,000 malicious, 6,500 plus 1000 standing points for losing every case and defaulting. Rows match.

## 3. Conflicts, gaps, and unsatisfiable readings

1. **A funding flip has no tier (RFC 3.4 against 4.2).** "If only one side funds, that side wins" is the host's override of the arbitrator's ruling. When K ruled no violation and only the challenger's side funded, the host records a challenger win that no juror tiered, and the wrapper has nothing to price the promise with. Modelled as a parameter `flip_tier`; at its default (none) the challenger gets the prepayment only, so a fooled first instance that the requester does not defend pays 6, not 30. The reverse flip (K rejecting, only the requester funded) forces the wrapper to read the host's outcome before recording a debt: the mapping is one-way, and the ledger must follow the host, not K. The RFC needs a rule; the safest candidate is the tier the funded side named when funding.
2. **Cost shifting is bounded by the promise (RFC 4.3 against S16/S18).** The host pays its whole pot, including the requester's fee, to the winner of any challenger-wins ruling; the wrapper never touches it. "The challenger bears the court cost, its fee unreimbursed" can therefore only be a netting of q1 off wrapper-held money. It works at Scout numbers (2.4 > 0.5) and fails at a tier price below q1 or a zero-priced tier; the model caps the award at zero. Symmetrically, "the requester pays the higher tier plus the burned fee" is the ordinary court outcome, not an extra penalty.
3. **A tiered concession is an offer, not C1 (RFC 4.3 against design section 2 and R1).** The baseline's concession is unilateral and terminal, and its ceiling is what makes exits credible. Under "the challenger accepts, or escalates", a spiteful challenger can drag a requester who conceded at the malicious tier through the first instance. Cost shifting makes that cost the challenger q1 and never costs the requester more than its offer in money, but it costs the first instance's duration in time. The batch move therefore only covers the requester's own absence; a silent challenger's case still escalates at the deadline under S1 (modelled: the concession persists as an executable quote past the deadline, anyone escalates, cost shifting applies to whoever sent it).
4. **"Paid in cash to the challenger in the same transaction" cannot be literal.** Cash paid out cannot be reduced when the court later rules at or below the conceded tier, and S15 forbids a transition that depends on a transfer. Modelled as escrow in the wrapper, credited on acceptance or on the ruling.
5. **The bonding rule is not decidable from wrapper events alone (RFC 5.2 and section 8).** The bond and the standing are; the count of open requests is host data the wrapper cannot see (S16, and unchallenged requests never reach it). The evidence display combines both. A bond posted in the submission's own block is ambiguous; the rule must say "before the submission's log index".
6. **Bond withdrawal has no rule in the RFC.** Modelled with a notice of the challenge period plus a day, no own open case, no unpaid debt, and the display treating an announced amount as already gone. Belongs in open decision 5.
7. **Standing does not follow an arbitrator switch.** Debts, bonds and escrow survive retirement and the switch (the trace passes; K rules each dispute to the instance that created it), but the ledger stays on the old instance and the successor starts empty. A successor's display has to read its predecessors' events or every switch resets every standing. S19 covers the reserve, not a ledger.
8. **R2 is exactly open decision 2.** A thousand challenges on valid items cost the griefer n(q1 + D_c) and nothing else; the victims recover their lock and gain D_c each. R2 holds if and only if q1 + D_c is at least the victim's delay cost, which nothing in the design measures.
9. **The compromised-publisher trace passes on the prepayment alone.** Fifty hunters each risk 0.5 and receive 6 in cash; the fifty promises of 24 are unpaid and the identity's standing falls by fifty. "Tier award" in the RFC's row keeps hunters motivated only through the prepayment, since a compromised identity defaults.
10. **Rounding.** Tier prices and fee shares floor; at the formal tier the fee share of 0.05 xDAI is 0 in 0.1-xDAI units. Conservation holds at every tier price from 0 to 100 percent and at promises of 24, 21.6, 18 and 0.1.
