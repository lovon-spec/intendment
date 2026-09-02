# Intendment: out-of-court settlement for optimistic dispute systems

Design document v0.4, 2026-09-02. Status: draft to be argued with. Supersedes `settlement-design-v0.3.md`; section 17 lists what changed and why. The earlier versions and the independent audit of v0.1 are kept in this directory.

## 0. Purpose, ambition, non-goals

**Problem.** In optimistic systems, someone asserts something with a bond, anyone may challenge it with a bond, and a resolver decides who was right. In Kleros Curate the challenge creates the arbitration dispute in the same transaction, so every challenge pays jurors, including those the requester would concede on the spot and those the challenger would take back after reading the evidence. There is no way to concede, no way to take a challenge back, and no way to settle. Other optimistic systems share the shape and the gap.

**Ambition.** A settlement layer between "a challenge exists" and "a dispute is created": the two parties can end the case by paying each other, priced against what the resolver would have cost them, with the resolver as the backstop for cases that still disagree at a deadline. Built as a standard with a reference implementation, usable across resolvers: Kleros arbitrables first, optimistic-oracle systems next.

**What is universal and what is not.** The bargaining structure carries across systems: exits priced at the court loss, monotone posted prices, defaults that never settle against a silent party, and the Sybil principle of section 5. What does not carry is what the second outcome does to the world. "The claim is withdrawn" means the same everywhere and is terminal. "The challenge is withdrawn" restarts a review in a registry and would resolve everyone's money in a prediction market. So the concession half is the universal core and the withdrawal half is per system, and the deployment plan in section 7 follows that line exactly.

**Non-goals.** Settling after a dispute exists (resolvers cannot cancel), appeals, more than two parties, changing any resolver, deposits or challenge periods.

**Precedents.** Kleros Escrow resolves without jurors when one party fails to pay its fee share in time: a settlement layer with one fixed, silent outcome. Kleros's ArbitrableProxy contracts sit between an arbitrable and an arbitrator and forward disputes, which is the deployment shape of section 7. UMA's Optimistic Oracle V3 exposes an escalation-manager hook for custom dispute policy. Polymarket's oracle adapter resets a question once on its first dispute, a crude one-retry version of what this design does with prices.

## 1. Setting and notation

**A** made a claim (in Curate, the requester of a registration or removal; in an oracle, the proposer). **B** contests it (the challenger or disputer). Absent a settlement, a resolver decides.

| symbol | meaning | Scout lists on Gnosis |
|---|---|---|
| D | A's base deposit | 30 xDAI |
| F | arbitration fee, fronted by B, consumed by the resolver in court | 21.6 xDAI |
| D_c | B's challenge deposit | 0 |
| s_A = D + F | A's loss if A loses in court | 51.6 |
| g_A = D_c | A's gain if A wins in court | 0 |
| s_B = F + D_c | B's loss if B loses in court | 21.6 |
| g_B = D | B's gain if B wins in court | 30 |
| p_A, p_B | each side's private estimate of B's chance in court | private |
| r | probability the resolver refuses to rule | small, nonzero |
| v_A, v_B | A's private value of the claim standing; B's private value of it falling | private |

Outcomes. Prices are non-negative and each outcome has a fixed direction; the reverse direction is a separate, named case.

- **O_A, concession.** A withdraws the claim and pays Y to B, 0 ≤ Y ≤ s_A. In Curate a registration request leaves the item Absent, a removal request leaves it Registered. Terminal. Universal.
- **O_B, withdrawal paid by B.** B withdraws the challenge and pays X to A, 0 ≤ X ≤ s_B. The claim continues and its review period restarts in full. Registry-specific.
- **O_B', withdrawal paid by A.** B withdraws and A pays Z to B, 0 ≤ Z ≤ s_A. Same effect on the claim. Registry-specific; section 5 says why it is allowed there.
- **Request withdrawal.** While no challenge stands, A may withdraw the claim and take the deposit back. Not a settlement, but the option A needs after a withdrawn challenge, so that a continued review is a choice rather than an automatic consequence.

Neither settlement outcome consumes the fee.

## 2. Requirements

| id | requirement | why |
|---|---|---|
| R1 | Voluntary: participation never leaves a party worse off than court in money; in time, at most the window | otherwise nobody adopts it; the delay is the one accepted cost |
| R2 | No free griefing: delay or forced court costs its cause at least what it costs the victim | the parties are each other's only enforcers |
| R3 | Passivity-safe: silence yields today's outcome | most failures will be absence |
| R4 | No party can profit from a price the other has revealed | a revealed reservation is otherwise a free option |
| R5 | Prices can respond to evidence during the window | beliefs move |
| R6 | The list's chosen deterrent, the deposit, is never reduced by a settlement; the fee is not a deterrent by design | deposits are the tunable stick; the fee is a cost of court |
| R7 | No settlement registers anything without a full unchallenged review | the list is an unrepresented third party |
| R8 | Budget balance between the parties, with one stated exception if governance wants a resolver share | the saved fee is the only surplus |
| R9 | Front-running resistant | prices and acceptances are on-chain |
| R10 | No lever held by one side only | R2 depends on it |
| R11 | One page of rules | reviewers audit what they can explain |
| R12 | Reusable across arbitrables and resolvers | otherwise a Curate patch |
| R13 | Sybil-neutral: two addresses owned by one actor gain nothing over one | transfers cannot deter a Sybil; the design must remove the benefit |
| R14 | Live: every state has a path to termination without relying on a volunteer | fee changes must not strand a case |
| R15 | Third-party protection is per-system policy: each system decides which outcomes are settleable | the parties at the table never represent the people affected by the outcome |

## 3. What no design can have

Bilateral trade under private information: Myerson and Satterthwaite (1983) rule out a mechanism that is at once budget-balanced, voluntary, manipulation-proof, and always trades when a gain exists. Some cases that should settle will not. Each choice below names the inefficiency it accepts. Simulation compares rule sets and picks parameters; it cannot prove safety, so the roadmap puts the state machine, accounting, liveness and adversarial traces before it.

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

**Ceilings.** The unilateral concession price is s_A, A's court loss, which exceeds B's best court outcome, so B always accepts it. The unilateral withdrawal price paid by B is s_B for the same reason. Ceilings make the unilateral exits credible and prevent holdup.

**Private values and the third party.** v_A includes any external reward for a successful listing; on Scout lists that reward goes to submitters only, so submitters have strong reasons to keep claims alive and challengers are deposit-hunters whose court value on a bad claim is exactly D. The list itself has no negotiator. Two rules stand in for it, both already the security assumption of optimistic curation: any withdrawn challenge returns the claim to a full review (R7), and the community can challenge again. A requester who pays a challenger to withdraw has bought nothing but that fresh review, under the same assumption every unchallenged registration relies on today.

## 5. The Sybil principle and the two floods

**The principle.** A settlement between two addresses owned by one actor is free: every transfer is internal. Therefore any state a settlement can keep a claim in becomes free to occupy. No rule about transfers between A and B can change that; only rules about what the two together can do. This is the general form of the audit's Sybil finding, and it applies to concession alone: submit, self-challenge in the same transaction, sit in the window, concede to yourself at its end, resubmit. Concession is a free "cancel and resubmit" button unless something else stops it.

**What it threatens.** Not the list's contents: a claim held in any loop never sees a full unchallenged review, so nothing registers and nothing is removed faster. What it threatens is the pending page, the workspace of every reviewer, which today always clears within a review period because pending claims either register or get challenged and lose. Two floods:

- **Valid claims, recycled.** Thirty real items looped forever for locked capital and gas. Today a valid item is pending for one review period and is then spent.
- **Junk claims, shielded.** Fresh junk is free; today it costs deposit plus fee because an honest challenger reaches it. Under settlement the attacker's own challenge takes the slot first, and a concession pays that challenger, who is the attacker.

**The rules.** Two, one per flood, plus the deterrent they rely on.

1. **Per-item resubmission cooldown.** After a concession or a request withdrawal, that item ID cannot be resubmitted for several review periods. A corrected resubmission has a different ID and is untouched. Keeping thirty valid items pending then needs on the order of a thousand distinct valid items, which is today's constraint: floods of valid things are limited by the supply of valid things.
2. **Non-exclusive challenges.** Any number of challengers may escrow the fee against the same claim. The earliest standing is the challenger of record and is the party in court. A concession pays every standing challenger their ask, so a self-concession with an honest backstop standing costs the attacker a deposit per honest challenger, today's price. Standing challengers share the court outcome: if the challenger side loses, each loses their fee; if it wins, the challenger of record takes the deposit and the others get their fee back. Piling onto a valid claim therefore costs money, only junk attracts a pile, and a backstop's real incentive is that it becomes of record the moment the one in front withdraws, which is exactly when the one in front is suspected to be a Sybil.

Two alternatives were tried and rejected. A cap on withdrawals per claim blocks honest sequential challengers, whose whole point is that one honest one suffices. A bound on a claim's lifetime is defeated by replacing the claim, since self-concession is free. Time and count caps bound the wrong object; the two rules above bound the item and the slot.

**The non-party cost, stated as a parameter.** Every resolver has a cost that leaves the two parties: Kleros pays jurors, UMA's oracle splits the loser's bond between the winner and UMA's own store. That cost is what makes self-dealing expensive today, and settlement removes it, which is the whole benefit and the whole risk. A system adopting this layer should decide consciously what fraction of that cost survives a settlement: zero gives the floods, one gives no benefit. The two structural rules are how the fraction can safely be near zero for registries. Where they cannot be applied, a non-refundable settlement fee to the resolver is the fallback; it makes floods costly but never as costly as today, and it doubles as the governance sweetener of section 13.

## 6. The mechanism in one page

After a challenge the fee is escrowed and a window opens. The window is a timer. Inside it the only actions are prices and exits; nobody can create the dispute early. When it ends, anyone creates the dispute.

| move | who | when | effect |
|---|---|---|---|
| concede at the ceiling | A | any time | A pays s_A across the standing challengers' asks; claim withdrawn; fees returned |
| post a concession ask | each challenger | any time; only ever lowered; starts at the default | the price A may concede at |
| concede at the asks | A | any time | A pays each standing ask; acceptance carries the expected total |
| post a concession bid | A | any time; only ever raised | a public floor; a challenger may lower to it |
| withdraw at the ceiling | a challenger | any time | pays s_B to A; if none remain, claim continues and review restarts |
| post a withdrawal ask | A | any time; only ever lowered; starts at s_B | the price a challenger may withdraw at |
| withdraw at the ask | a challenger | any time | pays the current ask to A |
| post a buy-out bid | A | any time; only ever raised | what A will pay a challenger to withdraw; that challenger may accept |
| withdraw the request | A | while no challenge stands | deposit returned; claim closed; cooldown starts |
| join as a challenger | anyone | any time in the window | escrows the fee; becomes a standing challenger |
| `executeChallenge` | anyone | at the deadline | dispute created with the challenger of record |

**Why no escalation.** Creating the dispute early ends bargaining now instead of at the deadline. A party expecting to win in court gains hours against a case that runs for weeks; fee movements are handled by the snapshot rule; nothing expires. The only use of an early-escalation right is denying the other side its exit, and a move with no legitimate use and one abusive use should not exist. Removing it also removes every question about who may hold it: nothing to make symmetric, nothing to price, no guaranteed period to size. The one parameter left is the window's length, per system: longer gives absent parties more chance to settle, shorter delays genuine disputes less; a day covers every time zone against resolutions measured in weeks. That delay is the mechanism's one cost to a party who wanted court, and R1 says so.

**Why no sealing.** Every posted price moves in one direction only: asks fall, bids rise. A price that can only move against its owner gives the other side nothing to exploit, so R4 is met by monotonicity instead of secrecy, and commit-reveal machinery with keeper liveness and key failure modes stays out. Sealed rounds remain a possible refinement once real usage shows whether posted prices leave surplus on the table.

**Defaults.** A challenger's concession ask starts at D, the challenger's court win: a silent challenger is conceded to at the deposit, the fee returns to A, and R6 holds because the deposit is untouched. A challenger who wants part of the fee raises nothing; they set the ask in the challenge transaction and can only lower it from there. A's withdrawal ask starts at s_B: a silent A is paid the challenger's full court loss, so a spam challenge is never cheaper than today.

**What the mechanism accepts.** Deals where a challenger would take less but never lowers the ask; deals where A would pay more but nobody acts; the delay of the window on disputes that were always going to court; and concessions that become unaffordable when several honest challengers stand, which then resolve in court as today.

## 7. Deployment: the arbitrator-level wrapper

A binding settlement must sit where the dispute is created, because Curate's `challengeRequest` spends the fee in the same transaction; a wrapper at the user level can only be a convention. But there is a level where a wrapper binds: the arbitrator interface.

**`IntendmentArbitrator`** implements the arbitrator interface toward the arbitrable and acts as an arbitrable toward the real arbitrator, the pattern of Kleros's ArbitrableProxy. The arbitrable calls `createDispute` on it exactly as today, paying the fee; the wrapper opens the window and escrows the fee; at the deadline it forwards the case to the real arbitrator with the same extra data, re-emits the evidence events so jurors see the case properly, maps dispute IDs, and forwards appeals. If A concedes, the wrapper delivers a ruling for the challenger and splits the escrowed fee.

**Concession is exactly expressible.** In Curate a ruling for the challenger pays the pot, D + F, to the challenger, who had paid F to the wrapper. For a concession at price Y between D and D + F, the wrapper refunds D + F − Y to A and pays Y − D to the challenger; the two refunds sum to F, the escrow. At Y = D the whole fee returns to A; at Y = D + F the challenger keeps it all. No change to Curate.

**Withdrawal is not expressible.** A ruling for the requester registers the item outright, with no fresh review, which violates R7 and reopens the buying of listings. So "withdraw and restart" needs the arbitrable's cooperation: section 8. This is why concession is the universal half and why it ships first.

**What the wrapper needs from the arbitrable.** Party identities. The arbitrator interface carries none, so the wrapper uses a small per-arbitrable resolver: for Curate, the dispute-to-item mapping and the request's parties are public getters. One resolver per arbitrable type, a few lines each.

**Adoption.** An existing Curate list adopts by switching its arbitrator through its governor. A new list adopts at deployment, since the factory takes an arbitrator address. That is how a registry built on an unmodified official contract can adopt the layer without forking anything; the wrapper holds fees for a day and must therefore be tiny and audited.

## 8. Arbitrable-side extension: `IntendmentModule`

For the withdrawal half, the arbitrable delegates its challenge handling to a module that holds both stakes, the standing asks and bids, the set of standing challengers, the cooldown records, and the deadlines; pays out on settlements; and at the deadline calls the arbitrable back with either the settled outcome or an instruction to create the dispute with the challenger of record. The arbitrable defines what the two outcomes mean, the restart, request withdrawal, and the fee top-up hook. Curate V2 and Permanent GTCR are the first integrations. Escrow's fee timeout maps onto a module with withdrawal disabled and a silent default.

Before any code: the state machine with every transition, its authorization, deadline and failure path; escrow accounting with a balance-conservation argument; domain-separated identifiers per chain, module, arbitrable, case, party, outcome; replay and re-entry protection; one-time finalization; callback authentication; failed-transfer handling.

## 9. Liveness: fees and volunteers

All parameters are snapshotted per case at challenge time: arbitrator, extra data, deposits, window, defaults. If the arbitration cost has risen by the deadline, whoever creates the dispute supplies the difference and is repaid first from the losing side's stake; if it has fallen, the surplus returns to the challenger of record. If nobody creates the dispute within a grace period, a second deadline lapses the challenge: the challengers' escrows go to A, the claim continues, the review restarts. A lapse is a failure path, not a negotiable outcome.

## 10. Attack catalogue

| attack | what happens |
|---|---|
| spam challenge on a good claim | B pays F at the deadline, or pays A at least s_B to withdraw; delay bounded by the window |
| extortion, "pay me to withdraw" | A refuses; B's better move is to withdraw paying A; otherwise court at the deadline |
| self-challenge loop on a registration | holds nothing but the actor's own listing; honest backstops can join |
| self-challenge loop on a removal | an honest backstop forces court, where the actor loses deposit and fee |
| valid-item flood by recycling | cooldown: each item is pending a fraction of the time; supply-limited as today |
| junk flood behind a self-challenge | a concession pays every standing challenger; honest backstops make it cost a deposit each |
| buying the challenger | possible, into a full fresh review, at every standing challenger's price |
| squeezing a revealed price | asks only fall, bids only rise; nothing to squeeze |
| forcing court out of spite | impossible before the deadline; at the deadline it is simply the outside option |
| front-running an acceptance | acceptance carries the expected total |
| pile-on for concession money | pilers share court liability; only junk is worth piling on, which is deserved |
| Sybil on both sides | every transfer is internal; cooldown and non-exclusive challenges remove the benefit |

## 11. Passivity and timing

| who acts | outcome | versus today |
|---|---|---|
| nobody | court at the deadline | same result, later by the window |
| A with a wrong claim concedes, challengers silent | A pays D per challenger in a day; fee back to A | cheaper for A by the fee, same for the challenger, no jurors |
| a challenger lowers the ask, A concedes | A pays between D and the ask | better for both |
| a wrong challenger withdraws, A silent | pays s_B to A; item back in review | A is paid instead of winning nothing |
| A with a good claim, challenger silent | court at the deadline | later by the window |

## 12. Beyond Kleros: optimistic oracles and prediction markets

The same shape appears in UMA's Optimistic Oracle: a proposer posts a price with a bond, a disputer posts a bond within a liveness period, and UMA's voters resolve. Polymarket resolves its markets through an adapter to Optimistic Oracle V2; disputes are raised on the oracle itself, the adapter learns of them through a callback and resets the question once, and a second dispute goes to the vote. UMA's V3 oracle exposes an escalation-manager hook that can validate disputers and even arbitrate in place of the vote.

**What transfers.** Proposer concession: a proposer who realizes they were wrong retracts, pays the disputer what a lost vote would have paid them, and the resolver's own share of the bond is preserved as the non-party cost of section 5. The economics are identical to losing; only the days of voting are saved, and for a market that is the whole prize: a new proposal can be made at once.

**What does not transfer.** Disputer withdrawal. The people whose money rides on a market outcome are not the two at the table, so a disputer paid to stand down is the third-party problem at its most acute, and R15 says that outcome is off by default there.

**Where it sits.** Disputes happen on the oracle, so a settlement stage needs either the oracle's cooperation, which V3's escalation manager makes possible in principle, or an oracle-compatible front that the adapter talks to and that forwards unsettled disputes to the real oracle. The second needs only the market venue's consent. Which of the two is realistic is a question for the venue, and the exact insertion point is a one-page study still to be written.

## 13. Governance and adoption

The court's value is its shadow; real systems settle most cases. From the resolver's side the argument is that removing pointless cases raises the quality of the cases that remain and lowers the cost of using the system, which grows use. Kleros already accepts disputes not happening, in Escrow. Kleros token holders as a class earn nothing from dispute volume; only active jurors are paid per case, so "fewer pointless cases" costs no visible constituency. UMA's token holders are paid by volume through the bond split, so the same feature reads as revenue loss there, which is why the market-venue route matters. A settlement fee to the resolver, the R8 exception, is the lever that can turn either constituency, and it is left to each system to set.

## 14. Roadmap

| step | output |
|---|---|
| this document argued to v1.0 | positions confirmed or changed, with reasons |
| `IntendmentArbitrator` state machine and accounting | concession only; every transition, deadline, money movement, failure path; balance conservation and liveness argued |
| adversarial traces | Sybil floods, collusion, thin markets, fee increases, ordering, repeated play, as concrete sequences against the state machine |
| blind reviews | as for the earlier PRs |
| pilot | a registry that adopts the wrapper at deployment, measured: settled cases, fees saved, delay added |
| simulation for parameters | window length, cooldown, ask behavior; never as a safety claim |
| `IntendmentModule` state machine, Curate V2 and Permanent GTCR integrations | the withdrawal half |
| oracle insertion study | one page against Polymarket's adapter and UMA V3's hook |
| standard | written only after two systems run it |

## 15. Open questions

For Kleros: whether the concession default at the deposit is acceptable list policy or a per-list parameter; whether a settlement fee to the court should exist; confirmation that the refusal split matches every integration target; multiple removal requests per item in the TCR, an orthogonal improvement this design would benefit from; whether Escrow should migrate onto the module; settlements as first-class objects in the subgraph and the app.

For a market venue: whether an oracle-compatible front that forwards to UMA is acceptable to its users; the window length against a two-hour liveness; who may propose after a concession.

## 16. Module boundary, restated for the wrapper

`IntendmentArbitrator` holds one case: the escrowed fee, the snapshotted parameters, the party resolver's answers, the standing asks and bids for concession, the deadline, and the mapping to the real arbitrator's dispute once forwarded. It implements the arbitrator interface fully, including cost queries and appeals, and the arbitrable interface toward the real arbitrator, including the ruling callback and evidence events. It never holds the parties' deposits; those stay in the arbitrable, which is what makes the concession expressible as a ruling plus a fee split.

## 17. What changed from v0.3, and why

| from | to | reason |
|---|---|---|
| "settlement layer" | Intendment, a standard with a reference implementation | the design became universal in scope |
| one withdrawal per claim | per-item cooldown plus non-exclusive challenges with pay-all-asks and shared court liability | the cap blocked honest sequential challengers; a lifetime bound is defeated by free resubmission; the floods needed item-level and slot-level rules (owner) |
| a guaranteed period then symmetric early escalation | no escalation; the window is a timer | early escalation has no legitimate use and one abusive one (owner) |
| deployment as a Curate change | arbitrator-level wrapper for concession, arbitrable-side module for withdrawal | a ruling plus a fee split expresses concession exactly and binds without changing the arbitrable; withdrawal cannot be expressed by rulings |
| no oracle section | section 12 | the design was found to transfer to optimistic oracles, with disputer withdrawal excluded |
| "UMA burns half the bond" (said in discussion, never in a version) | UMA's store receives it; it is resolver revenue | correction (owner) |
| R1 "never worse than today" | never worse in money; in time at most the window | the audit's delay objection, accepted as the stated cost |
| new R15 | third-party protection is per-system policy | markets and registries differ in who bears the outcome |

## 18. Glossary

**Claim** the assertion under challenge. **Court loss, court gain** what a party pays or receives per resolver outcome. **Ceiling** the unilateral exit price, equal to the exiting party's court loss. **Ask, bid** standing prices; asks only fall, bids only rise. **Challenger of record** the earliest standing challenger, the party in court. **Backstop** any other standing challenger. **Restart** the return of a claim to a full review period. **Cooldown** the period after a concession or request withdrawal during which the same item cannot be resubmitted. **Lapse** the failure path when nobody creates the dispute after the deadline. **Non-party cost** the part of a court outcome that leaves both parties: jurors' fees, an oracle's share.
