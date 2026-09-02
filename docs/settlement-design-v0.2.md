# Pre-dispute settlement for Kleros arbitrables

Design document v0.2, 2026-09-02. Status: draft to be argued with. Supersedes v0.1 after the Codex audit (`settlement-design-v0.1-review.md`); section 14 lists what changed and why.

## 0. Purpose, ambition, non-goals

**Problem.** In Curate a challenge creates the dispute in the same transaction, so every challenge pays jurors, including those the requester would concede on the spot. Today there is no way to concede, no way to take a challenge back, and no way to settle.

**Ambition.** A settlement layer between "a challenge exists" and `createDispute`, in which the two parties can end the case by paying each other instead of paying jurors, reaching court only when they still disagree. Built as a reusable module for two-party, two-outcome arbitrables: Curate V2, Permanent GTCR, Escrow, Proof of Humanity.

**Staging, which is the main change from v0.1.** The two-sided design of v0.1 contained a Sybil hole and a regression for thin challenger markets. So:

- **v1: terminal concession only.** The requester can concede, at a price negotiated below a fixed ceiling. Nothing else changes. No sealing, no rounds, no new attack surface.
- **v2: challenge withdrawal**, only together with non-exclusive challenges, which is what closes the Sybil hole.
- **Later, if ever:** a requester paying a challenger to withdraw. Excluded until a list can opt into it explicitly, because it lets a single active challenger be bought, which today is impossible.

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

Outcomes, with fixed payment directions and non-negative prices (v0.1's signed prices were inconsistent and are dropped):

- **O_A, concession.** A withdraws the claim and pays Y to B, 0 ≤ Y ≤ s_A. A registration request leaves the item Absent, a removal request leaves it Registered. Terminal.
- **O_B, challenge withdrawal (v2).** B withdraws and pays X to A, 0 ≤ X ≤ s_B. The claim continues and its review period restarts in full. Not terminal, and priced accordingly (section 5).

Neither outcome consumes the fee.

## 2. Requirements

| id | requirement | why |
|---|---|---|
| R1 | Voluntary: participation never leaves a party worse off than court, delay included | otherwise nobody adopts it |
| R2 | No free griefing: delay or forced court costs its cause at least what it costs the victim | the parties are each other's only enforcers |
| R3 | Passivity-safe: silence yields today's outcome, with today's timing available | most failures will be absence |
| R4 | No party can profit from a price the other has revealed | a revealed reservation is otherwise a free option |
| R5 | Prices can respond to evidence during the window | beliefs move |
| R6 | Junk claims and junk challenges cost exactly what they cost today | the deterrents belong to the list |
| R7 | No settlement registers anything without a full unchallenged review | the list is an unrepresented third party |
| R8 | Budget balance, with one stated exception if governance wants a court share | the saved fee is the only surplus |
| R9 | Front-running resistant | prices and acceptances are on-chain |
| R10 | Levers are symmetric or priced | R2 depends on it |
| R11 | One page of rules | Kleros audits what it can explain |
| R12 | Reusable across arbitrables | otherwise a Curate patch |
| R13 | Sybil-neutral: two addresses owned by one actor gain nothing over one | budget-balanced transfers cannot deter a Sybil, so the design must remove the benefit instead |
| R14 | Live: every state has a path to termination without relying on a volunteer | fee changes and missing keys must not strand a case |

R6 is kept strictly in v0.2; v0.1 quietly relaxed it through a default.

## 3. What no design can have

Bilateral trade under private information: Myerson and Satterthwaite (1983) rule out a mechanism that is at once budget-balanced, voluntary, manipulation-proof, and always trades when a gain exists. Some cases that should settle will not. Each choice below names the inefficiency it accepts. Simulation can compare rule sets and pick parameters; it cannot prove safety, which is why the roadmap (section 12) puts the state machine, accounting proofs, liveness and adversarial traces before it.

## 4. Payoff structure

Court has three outcomes. The refusal case follows Curate V2's `rule()`: status returns to the challenger's side and the remaining pot, D + F + D_c, is split in half.

| court outcome | probability | A | B |
|---|---|---|---|
| B wins | p | −s_A | +g_B |
| A wins | 1−p−r | +g_A | −s_B |
| refusal | r | −s_A + (D+F+D_c)/2 | −s_B + (D+F+D_c)/2 |

Money-only bands, with each side using its own belief and ignoring r for readability (the refusal row shrinks both sides' expectations symmetrically and is carried in the model, section 10):

- A concedes at Y ≤ p_A·s_A − (1−p_A)·g_A.
- B accepts a concession at Y ≥ p_B·g_B − (1−p_B)·s_B.
- Band width = F + (p_A − p_B)(D + F + D_c). With common beliefs the width is F for any D_c. With a more confident challenger than requester it shrinks and can close; with the reverse it can exceed F. v0.1's width formula was wrong and is withdrawn.

Reading for Scout numbers: a clearly bad claim (both near p = 1) has a band from 30 to 51.6; a coin flip from about 4 to 26; a clearly good claim has no concession band and, in v2, a withdrawal band from 0 to 21.6.

**Ceilings.** The unilateral concession price is s_A = D + F, A's court loss, and it exceeds B's best court outcome, so B always accepts it. In v2 the unilateral withdrawal price is s_B = F + D_c for the same reason. The ceilings are what make the unilateral exits credible and what prevent holdup.

## 5. The two things the parties cannot see, and the one that is not at the table

**Private values.** v_A is the value of the listing to A, including any external reward for a successful listing. On Scout lists that reward exists and goes to submitters only; challengers earn nothing beyond the deposit. Two consequences: submitters have strong reasons to keep claims alive and to resubmit corrected items, and challengers are pure deposit-hunters whose court value on a bad claim is exactly D, so they rationally accept any concession at or above D. Junk pressure on Scout lists comes from the submitter side, which is why R6 is kept strict.

**The list.** No negotiator represents it. Two structural rules stand in for it: the restart after any withdrawal (R7), and a challenger market that can act again. v0.1 claimed a paid withdrawal was equivalent to a challenger who never challenged. That is true of procedure and false of utility: it costs A the delay and the exposure to the next challenger, and it lets A buy the only challenger a thin list has. Hence paid-by-A withdrawal is out, and B-paid withdrawal (v2) is priced as a non-terminal outcome: B's ceiling compensates A for the fee and deposit, and the delay is what A accepts in exchange for being paid rather than winning nothing in court.

**Refusal to arbitrate.** Real and nonzero. It lowers both sides' expected court value, which widens the settlement band slightly, and it is why "court loss" is defined by the losing row, the worst case, not by an expectation.

## 6. v1 in one page: terminal concession

After a challenge, the fee is escrowed and a window opens.

| move | who | when | effect |
|---|---|---|---|
| concede at the ceiling | A | any time in the window | A pays s_A to B; claim withdrawn; fees returned |
| post a concession ask | B | any time; only ever lowered | sets the price A may concede at; starts at the ceiling |
| concede at the ask | A | any time | A pays the current ask; acceptance carries the expected price |
| post a concession bid | A | any time; only ever raised | a public floor A is willing to pay; B may lower the ask to it |
| escalate | A | any time | dispute created now; today's timing preserved |
| escalate | B | after the guaranteed concession period | dispute created; B cannot deny A the chance to concede |
| `executeChallenge` | anyone | at the deadline | dispute created |

**Why no sealing in v1.** The only price that matters is B's ask, and it can only fall. A price that can only fall gives the other side nothing to exploit: A learns B's ceiling shrinking, B learns A's floor rising, and neither can re-price against the other. R4 is met by monotonicity instead of secrecy, and the whole commit-reveal apparatus, with its keeper liveness and Shutter failure modes, stays out of v1.

**Why A may escalate at any time.** Codex's finding 7 is correct: forbidding it makes every genuine dispute later than today, which is worse under any discounting, and lets a challenger add a free delay. A keeps today's option. The lever is priced by what A forgoes: a challenger who would have paid or discounted.

**Why B waits.** The guaranteed concession period, say 24 hours, is the mechanism's purpose: A must be able to concede. After it, B may escalate, at the price of forgoing a faster and larger payment than court would give.

**Default.** B's ask starts at the ceiling s_A. Silent B, junk A: A concedes at D + F, exactly today's loss, to B instead of to jurors, in a day instead of weeks. R6 holds by construction; a lower default was v0.1's mistake. Sharing the saved fee is B's active choice, and a challenger who wants the case closed has every reason to make it.

**What v1 accepts.** Cases where B would take less but never lowers the ask, and cases where A would pay more than B asks but nobody acts. Both resolve as today.

## 7. v2: challenge withdrawal, with non-exclusive challenges

**The Sybil hole in v0.1.** With one challenge slot and a budget-balanced withdrawal, one actor holding both A and B could challenge its own claim, withdraw paying itself, restart, and challenge again in the same block, holding the slot forever for the price of gas. On a removal request that suspends someone else's item indefinitely. No transfer between A and B can price this, because the transfer is internal (R13).

**The fix is structural, not monetary.** Challenges become non-exclusive during the window: any number of challengers may escrow the fee against the same request. The challenger of record is the earliest one still standing; withdrawal removes only the withdrawing challenger; if any challenger stands at the deadline, the dispute is created with the challenger of record as party, and the others are refunded. A self-challenge then cannot block anyone: an honest challenger joins and the case goes to court, where the Sybil's own claim loses its deposit and fee. The benefit of the attack is removed rather than priced, which is the only thing that works against a Sybil.

**Moves added in v2.** B posts a withdrawal ask? No: the asker for O_B is A, who sets the price B may pay to leave, starting at the ceiling s_B and only ever lowered; B may withdraw at the ask or at the ceiling; B may post a public bid that only rises. Same monotone structure, mirrored. Paid-by-A withdrawal does not exist.

**What the restart costs A.** A is paid at least the fee and deposit B would have lost, and gives up the certainty of a ruling against that B. A who prefers the ruling escalates instead; the ask exists only for A who prefers the money.

## 8. Liveness: fees, keys, volunteers

**Fee changes.** All parameters are snapshotted per case at challenge time: arbitrator, extra data, deposits, window, defaults. If the arbitration cost has risen by escalation time, the escalating party supplies the difference, and it is repaid first from the losing side's stake at the end of the case; if the cost has fallen, the surplus returns to B. If B is the party escalating and does not supply the difference by the deadline plus a grace period, anyone may, with the same first-claim reimbursement. If nobody does by a second deadline, the challenge lapses: B's escrow goes to A, the claim continues, the review period restarts. A lapse is a failure path, not a negotiable outcome, and it exists in v1 too.

**Keys and keepers.** v1 has no sealed values, so no key material and no keeper. Should a later version adopt sealed rounds, the schedule must separate commit, key release, reveal, settlement and court deadlines with grace periods, define behavior for early decryption, delayed or missing keys and failed reveals, and never place a reveal and `executeChallenge` at the same block. Codex's findings 5 and 6 are accepted in full and deferred with the feature.

## 9. Attack catalogue, v1 and v2

| attack | v1 | v2 |
|---|---|---|
| spam challenge on a good claim | B pays F at court; A may escalate at once, so no added delay | same, or B withdraws paying A |
| extortion, "pay me to withdraw" | not purchasable; A escalates | same; withdrawal is B paying A, never the reverse |
| self-challenge as a shield | one slot, but no withdrawal exists, so the Sybil's challenge goes to court and loses | non-exclusive challenges; an honest challenger forces court |
| serial delay by withdrawal | no withdrawal | each cycle pays A at least s_B, and cannot block others |
| buying the only challenger | impossible; no payment from A for a withdrawal | impossible; same |
| squeezing a revealed price | asks only fall, bids only rise; nothing to squeeze | same |
| forcing court out of spite | B forgoes a payment above court; A forgoes a payment or discount | same |
| front-running an acceptance | acceptance carries the expected price | same |
| external reward farming through settlement | Scout rewards listings, not challenges; a concession is not a listing | same |
| Sybil on both sides | every transfer is internal and the outcome is what a single honest actor gets | same, plus non-exclusivity |

## 10. Passivity and timing, v1

| who acts | outcome | versus today |
|---|---|---|
| nobody | court at the deadline | same result, later by the window |
| A escalates at once | court now | identical |
| A with a wrong claim concedes, B silent | A pays D + F to B in a day | same money, faster, no jurors |
| B lowers the ask, A concedes | A pays less than today, B gets paid now | better for both |
| A with a good claim, B silent | escalate or wait; court | identical or later by A's choice |

The "later by the window" row is the accepted cost, and it is optional: A can always choose today's timing. Nobody is ever worse off than today without having chosen it.

## 11. Module boundary

`SettlementModule` holds one case: both stakes, the four court-loss and court-gain prices, the snapshotted parameters, the standing ask and bid per outcome, the challengers in v2, the deadlines. It pays out on a settlement and, on escalation or at the deadline, calls the arbitrable back with either the settled outcome or an instruction to create the dispute with the challenger of record. The arbitrable defines the meaning of O_A and O_B, the restart, and the fee top-up hook. Curate V2 and Permanent GTCR are the first integrations. Escrow's fee timeout maps onto a module with O_B disabled and a silent default.

Before any code, the state machine must be written out: states, every transition with its authorization, its deadline and its failure path; escrow accounting with a balance-conservation argument; domain-separated identifiers per chain, module, arbitrable, case, party, outcome; replay and re-entry protection; one-time finalization; callback authentication; failed-transfer handling. Codex's finding 10 is the checklist.

## 12. Roadmap, reordered

| step | output |
|---|---|
| this document argued to v1.0 | positions confirmed or changed, with reasons |
| formal state machine and accounting | section 11's checklist written out; balance conservation and liveness argued |
| adversarial traces | self-challenge, collusion, thin markets, fee increases, ordering, repeated play, written as concrete sequences against the state machine |
| blind reviews | as for the PRs |
| simulation for parameters | window length, guaranteed period, ask behavior; settlement rate, delay, surplus split; never as a safety claim |
| Kleros conversation | section 13 |
| v1 prototype: Curate V2 integration, tests, invariants | code |
| v2 prototype: non-exclusive challenges and withdrawal | code |
| Kleros review and audit | their clock |

## 13. Open questions for Kleros

1. Is preserving the D + F deterrent (v0.2's choice) preferred over sharing the saved fee by default (v0.1's)? v0.2 keeps R6 strict; a per-list default would be one parameter.
2. A settlement fee to the court: none, or a fraction of the saved fee. The one place R8 would bend, and it also serves as a non-party cost if governance ever wants one.
3. Non-exclusive challenges change the Curate data model and UI. Is that acceptable for v2, or should withdrawal wait?
4. Refusal to arbitrate: confirm the modelled split matches every integration target.
5. Escrow: migrate onto the module or leave as is.
6. Should settlements, their outcomes and prices, be first-class in the subgraph and the app? v0.2 assumes yes.

## 14. What changed from v0.1, and why

| v0.1 | v0.2 | reason |
|---|---|---|
| two-sided sealed rounds in v1 | v1 is concession only, posted monotone prices, no sealing | Sybil hole (audit 1), non-terminal O_B (audit 2), keeper timing and Shutter guarantees (audit 5, 6), and v1 needs none of it |
| paid withdrawal in either direction | B-paid withdrawal in v2 with non-exclusive challenges; A-paid withdrawal excluded | one challenger could be bought (audit 2); Sybil shield (audit 1) |
| nobody escalates early | A any time, B after a guaranteed period | free delay against A (audit 7); A's concession right must survive |
| concession default at the deposit | default at the court loss D + F | R6 must hold by construction (audit 8) |
| band width F + 2(1−p)D_c | F + (p_A − p_B)(D + F + D_c) | sign error and heterogeneous beliefs (audit 3) |
| binary court | three outcomes including refusal | Curate V2's `rule()` (audit 4) |
| signed prices, implicit directions | fixed directions, non-negative prices | inconsistency (audit 3) |
| fee top-up by a volunteer | snapshot, obligated party, reimbursement, lapse | liveness (audit 9, R14) |
| simulation as evidence | state machine, accounting and traces first; simulation for parameters | audit 12 |
| Scout counts settled concessions? | moot: Scout rewards listings only, and that shapes v_A and the junk pressure | owner's correction |

## 15. Glossary

**Claim** the request under challenge. **Court loss, court gain** what a party pays or receives per court outcome. **Ceiling** the unilateral exit price, equal to the exiting party's court loss. **Ask, bid** the standing prices, asks only fall, bids only rise. **Challenger of record** the earliest standing challenger in v2. **Restart** the return of a claim to a full review period. **Lapse** the failure path when a required fee top-up never arrives.
