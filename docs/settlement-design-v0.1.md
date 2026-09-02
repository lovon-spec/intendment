# Pre-dispute settlement for Kleros arbitrables

Design document v0.1, 2026-09-02. Status: draft to be argued with. Nothing here is decided.

## 0. Purpose, ambition, non-goals

**Problem.** In Curate, a challenge creates the dispute in the same transaction. Every challenge pays jurors, including the ones the requester would concede on the spot and the ones the challenger would take back after seeing the evidence. Today there is no way to concede, no way to withdraw a challenge, and no way to settle.

**Ambition.** A settlement layer that sits between "a challenge exists" and `createDispute`, in which the two parties can end the case by paying each other instead of paying jurors, and which reaches court only when they still disagree at a deadline. Designed as a reusable module so that any arbitrable with two parties and two outcomes can adopt it: Curate V2, Permanent GTCR, Escrow, Proof of Humanity.

**Non-goals for v1.** Settling after a dispute exists (the arbitrator has no cancellation), appeals, more than two parties, changing the arbitrator, changing deposits or challenge periods.

**Precedent.** Kleros Escrow already resolves without jurors when one party fails to pay its fee share within a timeout. That is a degenerate settlement module with a single, fixed, silent outcome. This document generalizes it.

## 1. Setting and notation

Two parties. **A** made a claim (in Curate: the requester of a registration or removal). **B** contests it (the challenger). If nothing else happens, an arbitrator decides who is right.

| symbol | meaning | Curate value (Scout lists, Gnosis) |
|---|---|---|
| D | A's base deposit | 30 xDAI |
| F | arbitration fee, fronted by B, consumed by jurors in court | 21.6 xDAI |
| D_c | B's challenge deposit, often zero | 0 |
| s_A = D + F | what A loses if A loses in court | 51.6 |
| g_A = D_c | what A gains if A wins in court | 0 |
| s_B = F + D_c | what B loses if B loses in court | 21.6 |
| g_B = D | what B gains if B wins in court | 30 |
| p | probability that B wins in court, privately estimated by each side | private |
| v_A, v_B | A's private value of the claim standing; B's private value of the claim falling (including any curator reward) | private |

Two settlement outcomes, each with a price paid by the party that exits to the party that stays:

- **O_A, "A withdraws the claim"** at price Y paid by A to B. In Curate: the request is withdrawn; a registration request leaves the item Absent, a removal request leaves it Registered.
- **O_B, "B withdraws the challenge"** at price X paid by B to A. In Curate: the request continues and the challenge period restarts in full.

In both outcomes the fee is not consumed: no juror sat.

## 2. Requirements

| id | requirement | why |
|---|---|---|
| R1 | Voluntary: no party ends worse off than in court by participating | otherwise nobody adopts it |
| R2 | No free griefing: any delay or forced court costs its cause at least what it costs the victim | the two parties are the only enforcers of each other's behavior |
| R3 | Passivity-safe: silence yields the court outcome, never worse | most failures will be absence, not spite |
| R4 | No price is revealed before both sides are committed | a revealed reservation price is a free option for the other side |
| R5 | Prices can respond to evidence that arrives during the window | beliefs move; a price fixed before the evidence is a wrong price |
| R6 | Junk stays as expensive as today, for claims and for challenges | the deterrents are the list's, not the parties' |
| R7 | No settlement registers anything without a full, unchallenged review period | the list is a third party that no negotiator represents |
| R8 | Budget balance: nothing created, nothing burned that need not be | the saved fee is the only surplus; it must go to the parties |
| R9 | Front-running resistant | prices and acceptances are on-chain |
| R10 | No lever held by one side only | symmetry is what makes R2 hold |
| R11 | One page of rules | Kleros audits what it can explain |
| R12 | Reusable: the arbitrable defines the outcomes, the module runs the bargaining | otherwise this is a Curate patch, not a standard |

## 3. What no design can have

This is bilateral trade under private information. Myerson and Satterthwaite (1983) show that no mechanism is at once budget-balanced, voluntary, immune to manipulation, and always trades when a gain from trade exists. Some cases that should settle will not. The design chooses which inefficiency to accept, and this document says so at each choice. The realistic target is: settle the large majority of cases with a clear surplus, never create a case that is exploitable, and never lower the list's accuracy relative to today.

## 4. The payoff structure

Court, from each side, with money only (values v_A, v_B added in section 5):

| | B wins, probability p | A wins, probability 1−p |
|---|---|---|
| A | −s_A | +g_A |
| B | +g_B | −s_B |

Expected court value: A gets (1−p)g_A − p·s_A, B gets p·g_B − (1−p)s_B.

**Bargaining bands.** A accepts O_A at price Y if Y ≤ p·s_A − (1−p)g_A. B accepts O_A if Y ≥ p·g_B − (1−p)s_B. The band's width is p(s_A − g_B) + (1−p)(s_B + g_A). With Curate's stakes, s_A − g_B = F and s_B + g_A = F + 2D_c, so the width is F + 2(1−p)D_c, and exactly F when D_c = 0. The same computation for O_B gives (1−p)(s_B − g_A) + p(s_A − g_B) = F for any D_c.

**The proposition that organizes everything:** with money only, the surplus available to a settlement is the juror fee, in both outcomes, for every belief p, whenever the challenge deposit is zero. Private values shift the bands and can open or close them, but the fee is the only money that court would destroy and settlement preserves. Every design choice below is about who gets that fee, and about whether the machinery for splitting it introduces any new lever.

Worked numbers for Scout lists (D = 30, F = 21.6):

| p | A pays at most for O_A | B accepts at least for O_A | B pays at most for O_B | A accepts at least for O_B |
|---|---|---|---|---|
| 0 | 0 | −21.6 (B would pay to be released) | 21.6 | 0 |
| 0.2 | 10.3 | −11.3 | 11.3 | 0 |
| 0.42 | 21.6 | 0 | 0 | 0 |
| 0.8 | 41.3 | 19.7 | none (band closed) | 0 |
| 1 | 51.6 | 30 | none (band closed) | 0 |

Reading: below p ≈ 0.42 the natural settlement is B withdrawing; above it, A conceding. Around it, both bands are open and both outcomes are rational, which is the case that needs a tie rule.

## 5. Private values, and the third party

v_A is what A loses if the claim is withdrawn: the value of the listing, minus the option to resubmit a corrected item. v_B is what B gains if the claim falls: for a Scout curator, the program's reward for a successful challenge; for a competitor, more. These values widen or narrow the bands and they are private, which is what makes the problem hard.

They also expose the party that is not at the table. A settlement of O_B for money means B was paid to let the claim proceed. If v_B included a curator reward, B gave up a public-good action for a private payment. Nothing in the two parties' bargaining protects the list; only two structural rules do:

- **The restart rule (R7):** O_B returns the claim to a full review period, so a paid-off challenger is equivalent to a challenger who never challenged, and the whole challenger market gets another turn. Each further buy-out costs A the next challenger's court value again, which for a clearly wrong claim is at least D. Conceding is always cheaper than buying two challengers.
- **The market of challengers:** the rule above is worth exactly as much as the supply of challengers. On Scout lists it is strong; on a dormant list it is weak, and a dormant list has the same exposure today.

An explicit per-list switch that forbids money flowing from A to B under O_B is possible and cheap. Position: do not add it in v1; measure the accuracy effect in the simulation; add it if the simulation shows harm.

## 6. Decision axes

For each axis: the options, the analysis, the position taken, what would change it, and how the simulation tests it.

### A1. Commitment versus flexibility

Options: (a) one sealed price per side, fixed for the window; (b) open bargaining, prices changed freely; (c) several sealed rounds inside the window, each opening together, with a hard deadline.

Analysis. (a) satisfies R4 and R9 but violates R5: evidence arrives after the challenge and a price set at hour one is wrong by hour twenty. (b) satisfies R5 but violates R4: whoever posts first gives the other a free option, and both wait. (c) gives R4 within each round and R5 across rounds; the price is opened prices from earlier rounds becoming public, an auction-style leakage chosen on purpose.

Position: (c). What would change it: a simulation showing that leakage across rounds costs more surplus than a single round plus open bargaining after it. Test: settlement rate and surplus split under (a), (b), (c) with the same agents.

### A2. Rounds and window

Options: window length 24 to 72 hours; 2 to 4 rounds; last round at the deadline.

Analysis. Longer windows help offline parties and evidence; they delay registration on contested claims by the same amount, against court cases that take weeks. Fewer rounds are easier to explain. A final round at the deadline gives both sides one last simultaneous chance before court.

Position: 48 hours, three rounds opening at 16, 32 and 48 hours, court at 48 if the last round does not cross. Governor-settable window, fixed round structure. Not a simulation question; a UX judgment to revisit with Kleros.

### A3. Pricing rule when a bid meets an ask

Options: settle at the asker's price; at the bidder's price; at the midpoint (the k-double auction with k = ½).

Analysis. The midpoint is symmetric and standard (Chatterjee and Samuelson, 1983); it induces both sides to shade, which loses some deals at the margin but takes no side. The asker's price makes the bid a pure commitment to accept and hands the asker the surplus.

Position: midpoint. What would change it: nothing on principle; the simulation reports the efficiency loss from shading.

### A4. Sealing technology

Options: hash commitments with a reveal phase; time-lock encryption with automatic opening (Shutter).

Analysis. Hash commitments let the second opener look and decline to open, retreating to the default price: a bounded free option, nobody worse than court, but a lever held by whoever moves second. Time-lock encryption opens both prices at a block regardless of anyone's wishes; anyone can submit the plaintexts; withholding is impossible. Kleros already runs Shutter for sealed juror votes and Gnosis Chain runs Shutter natively; on other chains a keyper set must exist.

Position: time-lock encryption where available, hash commitment with "non-reveal equals default" as the documented fallback. The fallback's asymmetry is accepted and stated.

### A5. Defaults for a silent party

This is the axis most likely to be argued, because it decides who keeps an unspent juror fee when nobody negotiates.

Options for B's concession ask (the price at which A may exit): the deposit D (B's court gain), or D + F (A's court loss). Options for A's withdrawal ask (the price at which B may exit): F + D_c (B's court loss) or lower.

Analysis. A's withdrawal ask must default to B's full court loss, or a silent A makes spam challenges cheaper than today (R6). For B's concession ask, D makes conceding financially attractive, which is the purpose of the whole mechanism, at the cost of lowering the junk-claim deterrent from D + F to D whenever B stays silent; D + F preserves today's deterrent exactly and makes conceding financially neutral, so passive junk claimants keep going to court. The asymmetry between the two defaults mirrors the asymmetry in stakes: B's only stake is the fee, A's is the deposit.

Position: concession ask defaults to D, withdrawal ask defaults to F + D_c; B raises the concession ask in the challenge transaction if they want part of the fee. What would change it: a simulation showing the junk rate rising materially under the D default with realistic challenger activity, or Kleros preferring the deterrent unchanged, in which case the default becomes a per-list parameter. Test: junk registration rate and settlement rate under both defaults.

### A6. Early escalation

Options: nobody may create the dispute before the deadline; either side may; only A may.

Analysis. Any early-escalation right is a lever (R10). Under court-loss-priced unilateral exits, the party that would use it early gains nothing over waiting: A is paid F + D_c if B withdraws, B is paid at least D if A concedes, and both can simply wait for the deadline. The earlier defense against extortion, immediate escalation by A, is no longer needed: a challenger demanding money to withdraw faces a submitter whose outside option is one window of waiting followed by the challenger losing the fee.

Position: nobody early; anyone calls `executeChallenge` at the deadline. Cost: genuinely disputed cases reach court one window later.

### A7. Unilateral exits

Options: none, all exits negotiated; each side may exit at any time by paying its own court loss to the other.

Analysis. Without a unilateral exit, a party can be held up for its full court loss by a counterparty that refuses every offer, and the refusal is free. With unilateral exits priced at the court loss, holdup is impossible, and the price is one the counterparty always accepts because it exceeds their court gain. Unilateral exits are also the passivity floor: a silent counterparty can still be paid off at their default ask.

Position: both unilateral exits exist, priced at the exiting party's court loss, available in every state before the dispute exists.

### A8. The list's accuracy

Covered in section 5. Position: restart rule mandatory; no per-list ban on paid O_B in v1; simulation decides.

### A9. The court's share

Options: settlements pay the court nothing; a small settlement fee to the court, for example a fixed fraction of the saved fee.

Analysis. Jurors lose exactly the cases nobody wanted argued, which is the point. But PNK holders vote on Kleros changes, and a mechanism that visibly removes juror revenue needs a constituency. Escrow already settles without paying jurors, so there is precedent for zero.

Position: zero in v1, and the question is put to Kleros explicitly. A settlement fee is a one-line addition if governance wants it.

### A10. Module boundary

Position: a `SettlementModule` that, for one case, holds both stakes, knows the two court-loss prices and two court-gain prices, runs the rounds and the matching, pays out on a cross or a unilateral exit, and at the deadline calls the arbitrable back with either the settled outcome or an instruction to create the dispute. The arbitrable implements only: what O_A and O_B mean, the restart rule, and fee top-up at escalation. Curate V2 and Permanent GTCR are the first two integrations; Escrow's existing timeout maps onto the same interface with one outcome disabled.

### A11. Fee changes during the window

Position: the module reads the arbitration cost at escalation; the caller of `executeChallenge` supplies any shortfall and any surplus in escrow returns to B. Same shape as Classic's handling.

### A12. Evidence, talk, and the subgraph

Evidence stays public and flows as today; it is the information the mechanism should transmit. Off-chain talk is expected and harmless because prices are sealed. Every settlement, its outcome and its price are events, so the subgraph and the UI show them as case history, and a paid O_B is visible to the next challenger.

## 7. Attack catalogue

| attack | lever | cost to the attacker | what stops it | residual |
|---|---|---|---|---|
| spam challenge on a good claim | fee lockup only | F, paid to A on withdrawal or to jurors at the deadline | A's withdrawal ask defaults to B's court loss (A5); no early escalation needed | one window of delay |
| extortion: "pay me to withdraw" | none | F if refused | A waits; B's better move is to withdraw at full price, paying A | none |
| serial delay: challenge, withdraw, repeat | window plus restart per cycle | at least F per cycle, paid to A | pricing (A5, A7) | A is paid for each cycle |
| self-challenge as a shield | blocks other challengers | gas and lockup | restart rule (R7) | none |
| buying a wrong claim in | pay B to withdraw under O_B | at least the next challenger's court value, again per challenger | restart rule plus the challenger market; visibility of paid O_B | weak on lists with no challengers, as today |
| squeezing a revealed price | second-mover option | none | sealed rounds (A1, A4) | bounded under the hash-commit fallback |
| forcing court out of spite | waiting | the payment the other side would have made | court-loss-priced unilateral exits (A7) | none that is free |
| front-running an acceptance | reordering | none | acceptance carries the expected price; sealed rounds open by block | none |
| collusion, same person on both sides | self-settlement | gas | every self-deal is a transfer to oneself plus a restart | none |
| keyper leak (time-lock variant) | early decryption | reputational | falls back to hash-commit behavior | bounded as A4 |

## 8. Passivity matrix

| who acts | outcome | versus today |
|---|---|---|
| nobody | court at the deadline | same, one window later |
| A with a wrong claim acts, B silent | A concedes at B's default ask | better for both |
| A with a good claim acts, B silent | nothing to settle, court | same |
| B with a wrong challenge acts, A silent | B withdraws at A's default ask, A is paid | better for both |
| B with a good challenge acts, A silent | nothing to force, court | same |
| both act | rounds and bargaining | better whenever a band is open |

The property to claim, and to verify in the simulation: no configuration of activity makes any party worse off than today, and any single active party makes both better off whenever a settlement band exists.

## 9. Game-theoretic pass, to be done

1. Formalize types: (p_A, p_B, v_A, v_B, δ_A, δ_B), with correlated beliefs since both see the same evidence.
2. Derive the round-1 equilibrium of the k-double auction over the two outcomes with the given defaults, for uniform and for evidence-correlated priors. The known linear-strategy result should carry over per outcome; the tie rule at a double cross needs its own argument.
3. Show the four unilateral-exit prices are dominant fallbacks: no party prefers court to the counterparty's court-loss payment.
4. State the accepted inefficiency: deals with surplus below the shading margin of round 1 that also fail in rounds 2 and 3.
5. Prove the passivity claims of section 8 from the defaults.

## 10. Simulation plan

Agent-based, Python, deterministic seeds, checked-in outputs.

- **Agents:** submitters and challengers with private (p, v, δ), drawn from distributions parameterized by list type (Scout-like, dormant, adversarial).
- **Strategies:** truthful shading, aggressive shading, passivity with a probability, spam, extortion, serial delay, self-challenge, buy-out, and a best-response search for exploits against each fixed rule set.
- **Rule sets:** A1 variants (a)(b)(c); A3 midpoint versus asker's price; A5 both defaults; with and without the A8 switch.
- **Metrics:** settlement rate among cases with an open band; surplus split; juror cases avoided; mean delay to resolution; junk claims registered; junk challenges made; exploitability (any strategy's gain over truthful play); list accuracy relative to the court-only baseline.
- **Deliverable:** one page of charts and a table per rule set, plus the exploit search log.

## 11. Open questions for Kleros

1. Should settled concessions count as successful challenges in the Scout incentive program? If not, Scout curators will never settle and the mechanism is dead on the lists where it matters most.
2. Concession-ask default: the deposit (settlement-favoring) or the deposit plus fee (deterrent-preserving)?
3. A settlement fee to the court: none, or a fixed fraction of the saved fee?
4. Shutter availability on the chains they care about; whether the hash-commit fallback is acceptable there.
5. Whether a per-list ban on paid O_B should exist from day one.
6. Whether Escrow should migrate onto the module, or stay as is.

## 12. Roadmap and effort

| step | output | effort |
|---|---|---|
| this document argued to v1.0 | positions confirmed or changed, with reasons | days |
| game-theoretic pass | section 9 written out with proofs or counterexamples | days |
| simulation | section 10 charts and exploit log | days |
| adversarial review of both | blind reviews, as for the PRs | one round |
| Kleros conversation | answers to section 11 | their clock |
| module prototype and Curate V2 integration, tests, invariants | code | weeks |
| Permanent GTCR integration | code | days |
| Kleros review and audit | | their clock |

## 13. Glossary

**Claim** the request under challenge. **Court loss** what a party pays if it loses in court. **Court gain** what a party receives if it wins. **Band** the price range in which both sides prefer a settlement to court. **Cross** a bid at or above an ask. **Round** one sealed, simultaneous pricing step. **Restart** the return of a claim to a full review period after a withdrawn challenge.
