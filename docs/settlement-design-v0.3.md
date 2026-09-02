# Pre-dispute settlement for Kleros arbitrables

Design document v0.3, 2026-09-02. Status: draft to be argued with. Supersedes v0.2 after the owner's review of the Codex audit; section 14 lists what changed and why, from v0.1 onward.

## 0. Purpose, ambition, non-goals

**Problem.** In Curate a challenge creates the dispute in the same transaction, so every challenge pays jurors, including those the requester would concede on the spot and those the challenger would take back after reading the evidence. Today there is no way to concede, no way to take a challenge back, and no way to settle.

**Ambition.** A settlement layer between "a challenge exists" and `createDispute`, in which the two parties can end the case by paying each other instead of paying jurors, reaching court only when they still disagree. Built as a reusable module for two-party, two-outcome arbitrables: Curate V2, Permanent GTCR, Escrow, Proof of Humanity.

**Scope of v1.** Concession and challenge withdrawal, in both payment directions, with one structural rule, at most one withdrawal per request, that removes the only real abuse found. Posted prices, no sealing, no rounds. Sealed pricing is a possible later refinement, not a v1 dependency.

**Non-goals.** Settling after a dispute exists (the arbitrator cannot cancel), appeals, more than two parties, changing the arbitrator, deposits or challenge periods.

**Precedent.** Kleros Escrow already resolves without jurors when one party fails to pay its fee share in time: a settlement module with one fixed, silent outcome.

## 1. Setting and notation

**A** made a claim (the requester of a registration or removal). **B** contests it (the challenger). Absent a settlement, an arbitrator decides.

| symbol | meaning | Scout lists on Gnosis |
|---|---|---|
| D | A's base deposit | 30 xDAI |
| F | arbitration fee, fronted by B, consumed by jurors in court | 21.6 xDAI |
| D_c | B's challenge deposit | 0 |
| s_A = D + F | A's loss if A loses in court | 51.6 |
| g_A = D_c | A's gain if A wins in court | 0 |
| s_B = F + D_c | B's loss if B loses in court | 21.6 |
| g_B = D | B's gain if B wins in court | 30 |
| p_A, p_B | each side's private estimate of B's chance in court | private |
| r | probability the arbitrator refuses to rule | small, nonzero |
| v_A, v_B | A's private value of the claim standing; B's private value of it falling | private |

Outcomes. Prices are non-negative and each outcome has a fixed direction; the reverse direction is a separate, named case.

- **O_A, concession.** A withdraws the claim and pays Y to B, 0 ≤ Y ≤ s_A. A registration request leaves the item Absent, a removal request leaves it Registered. Terminal.
- **O_B, withdrawal paid by B.** B withdraws the challenge and pays X to A, 0 ≤ X ≤ s_B. The claim continues and its review period restarts in full.
- **O_B', withdrawal paid by A.** B withdraws the challenge and A pays Z to B, 0 ≤ Z ≤ s_A. Same effect on the claim. This is A buying the challenge away; section 5 explains why it is allowed.
- **Request withdrawal.** While no challenge stands, A may withdraw the claim and take the deposit back. Not a settlement, but the option A needs after a withdrawn challenge, so that a continued review is a choice rather than an automatic consequence.

Neither settlement outcome consumes the fee.

## 2. Requirements

| id | requirement | why |
|---|---|---|
| R1 | Voluntary: participation never leaves a party worse off than court | otherwise nobody adopts it |
| R2 | No free griefing: delay or forced court costs its cause at least what it costs the victim | the parties are each other's only enforcers |
| R3 | Passivity-safe: silence yields today's outcome | most failures will be absence |
| R4 | No party can profit from a price the other has revealed | a revealed reservation is otherwise a free option |
| R5 | Prices can respond to evidence during the window | beliefs move |
| R6 | The list's chosen deterrent, the deposit, is never reduced by a settlement; the juror fee is not a deterrent by design | deposits are the tunable stick; the fee is a cost of court |
| R7 | No settlement registers anything without a full unchallenged review | the list is an unrepresented third party |
| R8 | Budget balance, with one stated exception if governance wants a court share | the saved fee is the only surplus |
| R9 | Front-running resistant | prices and acceptances are on-chain |
| R10 | Levers are symmetric | R2 depends on it |
| R11 | One page of rules | Kleros audits what it can explain |
| R12 | Reusable across arbitrables | otherwise a Curate patch |
| R13 | Sybil-neutral: two addresses owned by one actor gain nothing over one | transfers cannot deter a Sybil; the design must remove the benefit |
| R14 | Live: every state has a path to termination without relying on a volunteer | fee changes must not strand a case |

## 3. What no design can have

Bilateral trade under private information: Myerson and Satterthwaite (1983) rule out a mechanism that is at once budget-balanced, voluntary, manipulation-proof, and always trades when a gain exists. Some cases that should settle will not. Each choice below names the inefficiency it accepts. Simulation compares rule sets and picks parameters; it cannot prove safety, so the roadmap (section 12) puts the state machine, accounting, liveness and adversarial traces before it.

## 4. Payoff structure

Court has three outcomes. The refusal case follows Curate V2's `rule()`: status returns to the challenger's side and the remaining pot, D + F + D_c, is split in half.

| court outcome | probability | A | B |
|---|---|---|---|
| B wins | p | −s_A | +g_B |
| A wins | 1−p−r | +g_A | −s_B |
| refusal | r | −s_A + (D+F+D_c)/2 | −s_B + (D+F+D_c)/2 |

Money-only bands, each side using its own belief, refusal carried in the model but omitted here for readability:

- A concedes at Y ≤ p_A·s_A − (1−p_A)·g_A. B accepts a concession at Y ≥ p_B·g_B − (1−p_B)·s_B.
- Band width = F + (p_A − p_B)(D + F + D_c). With common beliefs it is F for any D_c; a more confident challenger than requester narrows it and can close it; the reverse widens it.
- The withdrawal bands mirror these with the roles exchanged.

Scout numbers: a clearly bad claim settles between 30 and 51.6; a coin flip between about 4 and 26; a clearly good claim has no concession band and a withdrawal band from 0 to 21.6.

**Ceilings.** The unilateral concession price is s_A, A's court loss, which exceeds B's best court outcome, so B always accepts it. The unilateral withdrawal price paid by B is s_B for the same reason. Ceilings are what make the unilateral exits credible and what prevent holdup.

## 5. The two things the parties cannot see, and the one that is not at the table

**Private values.** v_A is the value of the listing to A, including any external reward for a successful listing. On Scout lists that reward goes to submitters only; challengers earn nothing beyond the deposit. So submitters have strong reasons to keep claims alive and to resubmit corrected items, and challengers are deposit-hunters whose court value on a bad claim is exactly D: they rationally accept any concession at or above D, and the fee above it is the bargaining space.

**The list.** No negotiator represents it. Two rules stand in for it, and both are the existing security assumption of optimistic curation rather than new ones: any withdrawn challenge returns the claim to a full review period (R7), and the community that watches the list can challenge again. A requester who pays a challenger to withdraw (O_B') has bought nothing but that fresh review, under the same assumption every unchallenged registration already relies on. The one thing that would break this is a cheap way to repeat it, which section 7's rule removes: only the first challenge on a request can ever be withdrawn, so at most one challenger can ever be bought, and the next one goes to court.

**Refusal to arbitrate.** Real and nonzero; it lowers both sides' expected court value, which widens the band slightly, and it is why "court loss" is the losing row, not an expectation.

## 6. v1 in one page

After a challenge, the fee is escrowed and a window opens. The window has a guaranteed part, during which nobody can escalate, and an open part.

| move | who | when | effect |
|---|---|---|---|
| concede at the ceiling | A | any time | A pays s_A to B; claim withdrawn; fees returned |
| post a concession ask | B | any time; only ever lowered | the price A may concede at; starts at the default |
| concede at the ask | A | any time | A pays the current ask; acceptance carries the expected price |
| post a concession bid | A | any time; only ever raised | a public floor; B may lower the ask to it |
| withdraw at the ceiling | B | any time, if the request's one withdrawal is unused | B pays s_B to A; claim continues; review restarts |
| post a withdrawal ask | A | any time; only ever lowered | the price B may withdraw at; starts at s_B |
| withdraw at the ask | B | any time, same condition | B pays the current ask |
| post a buy-out bid | A | any time; only ever raised | what A will pay B to withdraw (O_B'); B may accept |
| accept the buy-out | B | any time, same condition | A pays the bid to B; claim continues; review restarts |
| withdraw the request | A | while no challenge stands | deposit returned; claim closed |
| escalate | A or B | after the guaranteed part | dispute created now |
| `executeChallenge` | anyone | at the deadline | dispute created |

**Why no sealing.** Every posted price moves in one direction only: asks fall, bids rise. A price that can only move against its owner gives the other side nothing to exploit, so R4 is met by monotonicity instead of secrecy, and the commit-reveal machinery with its keeper liveness and key failure modes stays out. Sealed rounds remain a possible refinement once real usage shows whether posted prices leave surplus on the table.

**Why the guaranteed part.** It is the mechanism's purpose: A must be able to concede and B must be able to withdraw before either can be dragged to court. After it, either side may escalate, at the price of forgoing what the other would have paid; the lever is symmetric (R10) and the delay on a genuine dispute is bounded by the guaranteed part.

**Defaults.** B's concession ask starts at D, B's court win: a silent B is conceded to at the deposit, the fee returns to A, and R6 holds because the deposit is untouched. B raises nothing; B can only lower from wherever B set the ask in the challenge transaction, so a B who wants part of the fee says so at challenge time. A's withdrawal ask starts at s_B: a silent A is paid B's full court loss, so a spam challenge is never cheaper than today.

**What v1 accepts.** Deals where B would take less but never lowers the ask; deals where A would pay more but nobody acts; and the delay of the guaranteed part on disputes that were always going to court.

## 7. The one structural rule

**At most one withdrawal per request.** Once a challenge on a request has been withdrawn, by O_B or O_B', every further challenge on that request is final: it ends in concession or in court.

What it does. A challenge-withdraw-rechallenge loop by one actor holding both sides is free of transfers and costs only gas; on a registration request it holds nothing hostage but the actor's own listing, so it is not an attack; on a removal request it would keep someone else's item pending removal indefinitely without ever reaching the court that would cost the actor deposit and fee. The rule ends the loop at its second challenge, at the deadline, in court, where the actor loses from both sides. It also bounds buy-outs: a requester can pay away one challenger, never the next. And it needs no change to how many challengers or requests an item can have.

What it costs. A second, honest challenger on the same request cannot retract; they go to court or accept a concession. A Sybil could spend the request's one withdrawal on itself to deny that option to a later honest challenger; the only effect is that the honest challenger has to be right, which they already have to be.

Orthogonal and worth doing in the TCR itself: allowing several removal requests per item, so an honest remover is never blocked behind someone else's stalled request. Not part of this module.

## 8. Liveness: fees and volunteers

All parameters are snapshotted per case at challenge time: arbitrator, extra data, deposits, window, defaults. If the arbitration cost has risen by escalation time, the escalating party supplies the difference and is repaid first from the losing side's stake; if it has fallen, the surplus returns to B. If the party that must escalate does not, anyone may escalate with the difference after a grace period, with the same first-claim reimbursement. If nobody does by a second deadline, the challenge lapses: B's escrow goes to A, the claim continues, the review restarts. A lapse is a failure path, not a negotiable outcome, and it does not consume the request's withdrawal.

## 9. Attack catalogue

| attack | what happens |
|---|---|
| spam challenge on a good claim | B pays F at court, or pays A at least s_B to withdraw; delay bounded by the guaranteed part |
| extortion, "pay me to withdraw" | A refuses; B's better move is to withdraw paying A; if B waits, court after the window |
| self-challenge loop on a registration | holds nothing but the actor's own listing; not an attack |
| self-challenge loop on a removal | ends at the second challenge in court; actor loses deposit and fee (section 7) |
| serial delay by withdrawal | one withdrawal per request; the next challenge is final |
| buying the challenger | possible once per request, at the challenger's price, into a full fresh review; the next challenger cannot be bought |
| buying the only challenger of a thin list | same as any unchallenged registration on that list today; the assumption is the community, and it is unchanged |
| squeezing a revealed price | asks only fall, bids only rise; nothing to squeeze |
| forcing court out of spite | not during the guaranteed part; after it, the escalating side forgoes what the other would have paid; symmetric |
| front-running an acceptance | acceptance carries the expected price |
| external reward farming | Scout rewards listings, not challenges; a concession is not a listing |
| Sybil on both sides | every transfer is internal; the outcome is what one honest actor gets; one withdrawal per request |

## 10. Passivity and timing

| who acts | outcome | versus today |
|---|---|---|
| nobody | court at the deadline | same result, later by the window |
| A with a wrong claim concedes, B silent | A pays D to B in a day; fee back to A | cheaper for A by the fee, same for B, no jurors |
| B lowers the ask, A concedes | A pays between D and the ask | better for both |
| B with a wrong challenge withdraws, A silent | B pays s_B to A; item back in review | A is paid instead of winning nothing |
| A with a good claim, B silent | wait, then escalate after the guaranteed part | later by at most the guaranteed part |
| both act | bargaining | better whenever a band is open |

## 11. Module boundary

`SettlementModule` holds one case: both stakes, the court-loss and court-gain prices, the snapshotted parameters, the standing asks and bids, the withdrawal-used flag of the request, the deadlines. It pays out on a settlement and, on escalation or at the deadline, calls the arbitrable back with either the settled outcome or an instruction to create the dispute. The arbitrable defines what O_A and O_B mean, the restart, the request-withdrawal, and the fee top-up hook. Curate V2 and Permanent GTCR are the first integrations; Escrow's fee timeout maps onto a module with withdrawal disabled and a silent default.

Before any code: the state machine with every transition, its authorization, deadline and failure path; escrow accounting with a balance-conservation argument; domain-separated identifiers per chain, module, arbitrable, case, party, outcome; replay and re-entry protection; one-time finalization; callback authentication; failed-transfer handling.

## 12. Roadmap

| step | output |
|---|---|
| this document argued to v1.0 | positions confirmed or changed, with reasons |
| formal state machine and accounting | section 11 written out; balance conservation and liveness argued |
| adversarial traces | self-challenge on removals, collusion, thin markets, fee increases, ordering, repeated play, as concrete sequences against the state machine |
| blind reviews | as for the PRs |
| simulation for parameters | window and guaranteed part, ask behavior; settlement rate, delay, surplus split; never as a safety claim |
| Kleros conversation | section 13 |
| prototype: module, Curate V2 integration, tests, invariants | code |
| Permanent GTCR integration | code |
| Kleros review and audit | their clock |

## 13. Open questions for Kleros

1. The concession default at the deposit returns the saved fee to the requester by default. Is that acceptable list policy, or should it be a per-list parameter?
2. A settlement fee to the court: none, or a fraction of the saved fee. The one place R8 would bend.
3. Refusal to arbitrate: confirm the modelled split matches every integration target.
4. Multiple removal requests per item in the TCR: an orthogonal improvement this design would benefit from.
5. Escrow: migrate onto the module or leave as is.
6. Settlements, outcomes and prices as first-class objects in the subgraph and the app.

## 14. What changed, and why

| from | to | reason |
|---|---|---|
| v0.1: two-sided sealed rounds | v0.3: posted monotone prices, no sealing | monotonicity meets R4 without keeper liveness or key failure modes (audit 5, 6) |
| v0.1: band width F + 2(1−p)D_c; binary court; signed prices | corrected width; three court outcomes; fixed directions | audit 3, 4 |
| v0.1: fee top-up by a volunteer | snapshot, obligated party, reimbursement, lapse | audit 9 |
| v0.2: v1 concession-only, withdrawal deferred behind non-exclusive challenges | v0.3: withdrawal in v1 with one withdrawal per request | the registration loop is not an attack; the removal loop is, and the rule closes it without a multi-challenger change (owner) |
| v0.2: A-paid withdrawal excluded | allowed, bounded to once per request | the fresh review is the existing security assumption; the rule bounds buy-outs (owner) |
| v0.2: A escalates any time, B after a period | nobody during the guaranteed part, either side after | symmetry (owner); delay still bounded (audit 7) |
| v0.2: concession default at D + F | default at D; R6 restated as deposit-only | the deposit is the designed deterrent; the fee is not (owner) |
| v0.2: request withdrawal dropped | restored | the requester must be able to choose not to continue (owner) |
| v0.1: Scout counts settled challenges? | moot | Scout rewards listings only (owner) |

## 15. Glossary

**Claim** the request under challenge. **Court loss, court gain** what a party pays or receives per court outcome. **Ceiling** the unilateral exit price, equal to the exiting party's court loss. **Ask, bid** standing prices; asks only fall, bids only rise. **Guaranteed part** the opening part of the window in which nobody can escalate. **Restart** the return of a claim to a full review period. **Lapse** the failure path when a required fee top-up never arrives.
