# Intendment: out-of-court settlement for optimistic dispute systems

Design document v0.5, 2026-09-02. Status: the full mechanism, sequenced. Supersedes v0.4 after its independent audit (`intendment-design-v0.4-review.md`) and the maintainer's review; section 12 lists what changed and why.

**How to read this document.** Section 1 is the spine: the constraints that adversarial review established, each with the finding that established it. They are not up for re-argument in later sections; a later section that conflicts with the spine is wrong. Section 3 is the full mechanism, every transition, whether or not it is implemented yet. Section 5 is the sequence in which the transitions are delivered, with the gate each stage opens. Section 6 names the open problems of every later transition; section 7 records the rules that were tried and rejected, and why, so that they are not proposed again.

## 0. Purpose

In optimistic systems someone asserts something with a bond, anyone may challenge it with a bond, and a resolver decides who was right. In Kleros Curate the challenge creates the arbitration dispute in the same transaction, so every challenge pays jurors, including those the requester would concede on the spot and those the challenger would take back after reading the evidence. Intendment is a settlement layer between "a challenge exists" and "a dispute is created": the two parties may end the case by paying each other, priced against what the resolver would have cost them, with the resolver as the backstop for cases that still disagree at a deadline. It is built as a standard with a reference implementation: Kleros arbitrables first, optimistic-oracle systems next.

Concession is the first implemented transition, delivered as an arbitrator-level wrapper for registration requests on Kleros V1 lists, because it is the only part deployable without a Kleros merge and because it produces the adoption data that opens the gate for the rest. Everything else in section 3 is the same mechanism, delivered later.

**Precedents.** Kleros Escrow V1 resolves without jurors when a party fails to pay its fee share in time. Kleros Escrow V2 ships a native settlement window: either party proposes an amount, the other accepts or counter-proposes, the last proposer cannot raise the dispute until the settlement timeout has passed, and the receiver may raise it at any time. Kleros's cross-chain proxies and V2 gateways forward disputes behind the arbitrator interface, which is the wrapper's shape. Polymarket's oracle adapter resets a question once on its first dispute.

## 1. The spine

| id | constraint | established by |
|---|---|---|
| S1 | Silence escalates, never concedes. An absent party reaches court exactly as today, one window later at most. | design discussion; a default-concede lets challengers farm absent requesters |
| S2 | Escalation is never free for the escalator. The challenge assigns the waiting obligation: the requester may create the dispute at any time, the challenger not before the window, anyone at the deadline. Prices never transfer that obligation. | derived from R2 (section 4): the challenger's early escalation would cost only time while the requester loses the fee; the requester's costs at least what the challenger loses. Escrow V2's rule, with the challenge as the opening proposal |
| S3 | Any withdrawn challenge restarts the review period in full. | the self-challenge shield: without a restart, a challenge-and-withdraw pair would burn the review period unchallengeable |
| S4 | Free settlement makes pending states free to occupy. A settlement between two wallets of one owner is an internal transfer, so any state a settlement can hold becomes free to hold for gas; no rule keyed on item, request, address, or count changes that, because all are reissued for free. | audit of v0.1 (Sybil), the flood discussion, and the failure of every structural rule tried against it (section 7) |
| S5 | No rule may be keyed on an item ID. Item IDs are hashes of submitted bytes and are the submitter's choice up to salting. | maintainer's review of the v0.4 audit |
| S6 | The deposit is the list's deterrent and is never reduced by a settlement; the arbitration fee is a cost of court, not a deterrent. | maintainer's decision; the fee was never designed as a stick |
| S7 | Third-party protection is per-system policy. Settlement never lets its parties monopolize the only public path for acting against something already in effect. In Curate, settlement on removal requests stays off until independent removal prosecution exists. | audit of v0.4; the removal slot is exclusive and a removal target's ID cannot be salted |
| S8 | Three fees, accounted separately: the fee quoted into the requester's deposit at request time, the fee the challenger pays at challenge time, and the resolver's fee at escalation. Any split is defined on the fee actually held; quotes are frozen per epoch; a shortfall has a named source or the case lapses to a refusal ruling. | audit of v0.4 |
| S9 | Evidence routing is a precondition of any wrapper deployment: the wrapper cannot read the list's logs, so evidence reaches the resolver through a relay or through resolver-side support for the dispute mapping. | audit of v0.4 |
| S10 | Every timeout has a named, incentivized caller and an implementable terminal outcome. | audit of v0.4; R14 |
| S11 | Budget balance between the parties. A resolver share of the saved fee exists only if a system's governance adds it. | R8 |
| S12 | The pending queue is protected by status separation, not by the mechanism: a looped item is always challenged, and both Curate apps list challenged requests apart from unchallenged ones. | verified in `kleros/gtcr` filters and the V2 app's status selector |

## 2. Setting, notation, payoffs

**A** made a claim (the requester); **B** contests it (the challenger). Absent a settlement, a resolver decides.

| symbol | meaning | Scout lists on Gnosis |
|---|---|---|
| D | A's base deposit | 30 xDAI |
| F_A | arbitration fee quoted into A's deposit at request time | 21.6 xDAI |
| F_B | arbitration fee B pays at challenge time, held by the settlement layer | 21.6 xDAI |
| F_E | the resolver's fee at escalation | 21.6 xDAI unless changed |
| D_c | B's challenge deposit | 0 |
| s_A = D + F_A | A's court loss | 51.6 |
| g_A = D_c | A's court gain | 0 |
| s_B = F_B + D_c | B's court loss | 21.6 |
| g_B = D | B's court gain | 30 |
| p_A, p_B | each side's private estimate of B's chance in court | private |
| r | probability the resolver refuses to rule | small, nonzero |
| v_A, v_B | A's private value of the claim standing; B's of it falling | private |

Court has three outcomes: B wins with probability p, A wins with 1−p−r, and refusal with r, which in Curate V2 returns the item to the challenger's side and splits the remaining pot in half.

Money-only bands, each side with its own belief: A concedes at Y ≤ p_A·s_A − (1−p_A)·g_A; B accepts a concession at Y ≥ p_B·g_B − (1−p_B)·s_B; width F + (p_A − p_B)(D + F + D_c) with F the common fee, so F under common beliefs for any D_c. The withdrawal bands mirror these with the roles exchanged. The surplus any settlement can distribute is the fee that court would have consumed, and nothing else.

**Ceilings.** The unilateral concession price is A's court loss; the unilateral withdrawal price is B's. Each exceeds the counterparty's best court outcome, so a counterparty always accepts it, which is what makes the exits credible and prevents holdup.

**Values and the third party.** On Scout lists an external reward goes to submitters only, so submitters have strong reasons to keep claims alive and challengers are deposit-hunters whose court value on a bad claim is exactly D. The list itself has no negotiator; S3 and the challenger market stand in for it, and both are the existing assumption of optimistic curation.

## 3. The full mechanism

After a challenge the fee F_B is escrowed and a window of length W opens. The moves below are the whole mechanism. "Implemented in" names the stage of section 5 that delivers each; "later" moves are specified here so that the first stage is built to their shape.

### 3.1 Prices

Each side may hold one standing ask and one standing bid per outcome. Asks only fall, bids only rise. Acceptance carries the price it expects. Because every price moves against its owner, nothing revealed can be exploited (R4), and no sealing is needed; sealed rounds remain a refinement if usage shows surplus left on the table. Prices never transfer the escalation obligation of S2.

Defaults: B's concession ask starts at D, B's court win, so a silent B is conceded to at the deposit and the fee returns to A (S6). A's withdrawal ask starts at s_B, so a silent A is paid B's full court loss and no spam challenge is cheaper than today.

### 3.2 Transitions

| id | move | who | when | money | effect | implemented in |
|---|---|---|---|---|---|---|
| C1 | concede at the ceiling | A | any time in the window | A pays s_A to B | claim withdrawn; terminal | stage 1 |
| C2 | set the concession ask | B | once up from the default, then only down | none | the price A may concede at | stage 1 |
| C3 | concede at the ask | A | any time | A pays the ask to B; the rest of F returns to A | claim withdrawn; terminal | stage 1 |
| C4 | post a concession bid | A | only up | none | a floor B may lower to | stage 1 |
| W1 | withdraw at the ceiling | B | any time | B pays s_B to A | claim continues; review restarts (S3) | stage 2 |
| W2 | set the withdrawal ask | A | only down from s_B | none | the price B may withdraw at | stage 2 |
| W3 | withdraw at the ask | B | any time | B pays the ask to A | as W1 | stage 2 |
| W4 | withdraw the request | A | while no challenge stands | deposit returned | claim closed | stage 2 (host-side) |
| B1 | post a buy-out bid, bound to one named challenger and a nonce | A | only up | none | what A will pay that challenger to withdraw | stage 3 |
| B2 | accept the buy-out | the named challenger | any time | A pays the bid to B | as W1 | stage 3 |
| E1 | create the dispute | A | any time | F_E paid to the resolver from escrow, shortfall per S8 | court | stage 1 |
| E2 | create the dispute | B | after W | same | court | stage 1 |
| E3 | create the dispute | anyone | after W plus grace | same | court | stage 1 |
| E4 | lapse | anyone | after a second deadline if E1–E3 cannot fund F_E | F_B refunded to B | refusal ruling; the host restores the pre-request status and splits its pot | stage 1 |

### 3.3 Requirements the transitions satisfy

| id | requirement |
|---|---|
| R1 | Voluntary: no party ends worse off than court in money; in time, at most one window per settlement case |
| R2 | No free griefing: delay or forced court costs its cause at least what it costs the victim |
| R3 | Passivity-safe: silence yields today's outcome, delayed at most by the window, except the lapse path of S8, which is a stated failure rule |
| R4 | No party can profit from a price the other has revealed |
| R5 | Prices can respond to evidence during the window |
| R6 | The deposit is never reduced by a settlement (S6) |
| R7 | No settlement registers anything without a full unchallenged review (S3) |
| R8 | Budget balance between the parties (S11) |
| R9 | Front-running resistant: acceptances carry the expected price; buy-outs are recipient-bound |
| R10 | No side holds a lever that is free for it and costly for the other (S2) |
| R11 | One page of rules per transition |
| R12 | Reusable across arbitrables and resolvers |
| R13 | Sybil-neutral: two wallets of one owner gain nothing over one (S4) |
| R14 | Live: every state terminates without a volunteer (S10) |
| R15 | Third-party protection is per-system policy (S7) |

## 4. Why the escalation rule is what it is

Early escalation ends bargaining now instead of at the deadline. Its only legitimate use is a party who wants the ruling sooner; its abusive use is denying the other side its exit. R2 decides who may hold it by asking what it costs each side.

The requester escalating early forgoes the payment the challenger would have made to withdraw, at least the challenger's court loss, which is exactly what the challenger loses when taken to court: priced, with equality. In the concession-only stage there is no withdrawal to forgo, and there is also no victim beyond the challenger's time: a requester with a good claim legitimately wants a ruling, and a requester with a bad one concedes rather than escalates.

The challenger escalating before the requester has had the window costs the challenger only the wait: the deposit later with some risk instead of at least the deposit now. The requester loses the fee, the concession's whole saving. That is free griefing.

So the requester may escalate at any time, the challenger not before the window, anyone at the deadline. This is Escrow V2's rule with the challenge read as the challenger's opening proposal. One refinement Escrow does not need: in-window prices only ever move against their owner, so they are gifts, not proposals, and must not transfer the obligation; otherwise a requester who bid would hand the challenger the right to deny the concession the bid was about. Rights differ by role because costs differ by role; symmetric rights over asymmetric costs would produce asymmetric outcomes. The pure timer, no escalation at all, is equally clean and charges a requester with a good claim the whole window for nothing; the rule above is preferred for that reason and because Kleros has reviewed and shipped it.

## 5. Sequencing and gates

| stage | delivers | deployment | who decides | what it unlocks |
|---|---|---|---|---|
| 1 | C1–C4, E1–E4; registration requests only | `IntendmentArbitrator`, an arbitrator-level wrapper over Kleros V1; concession expressed as a ruling for the challenger plus a split of F_B; adopted by a list's governor switching its arbitrator, or by a new list at deployment | a list's governor. Our own list first; then the Scout lists' governor, a 2-of-4 Safe that re-pointed all three lists' arbitrator in one batch after the KIP-87 Snapshot vote in July 2026, the exact precedent | adoption data: settled cases, fees saved, delay added; the evidence-routing and fee-epoch mechanics proven in production |
| 2 | W1–W4; removal requests, once independent removal prosecution exists | `IntendmentModule`, arbitrable-side, in Curate V2 and Permanent GTCR, whose arbitrator is immutable and cannot take the wrapper | Kleros maintainers; new lists only, since lists are clones | the withdrawal half and the restart; custody of both stakes, which the wrapper never has |
| 3 | B1–B2, negotiated prices beyond monotone posting | module extension | Kleros maintainers | buy-outs with recipient binding; a study of thin challenger markets before enabling |
| 4 | proposer concession on optimistic oracles | an oracle-compatible front adopted by a market venue's adapter, or V3's escalation manager | the market venue; UMA for the V3 route | settlement outside Kleros; the standard |

The court-core route, settle before jurors are drawn inside KlerosCore, is deferred: no cancel or refund path exists in V1 or V2, it needs a new terminal state, fee refunds, a ruling callback, a dispute-kit hook and UI, and V2's governor is currently an externally owned account rather than a DAO contract. Dispute kits cannot host it: they hold no fees and cannot end disputes.

## 6. Open problems of the later transitions, named

| transition | problem | what would resolve it |
|---|---|---|
| W1–W3 | custody: the wrapper holds only F_B and cannot redirect the host's pot; a withdrawal with restart is not expressible as a ruling | the arbitrable-side module holds both stakes and defines the restart |
| W1–W3 on removals | the removal slot is exclusive and its target's ID cannot be salted, so a self-challenged removal blocks honest removers | independent removal prosecution in the host: several removal requests per item, or a join/fork-to-court mechanism |
| B1–B2 | a case-wide buy-out offer can be taken by a fresh wallet that joins and accepts atomically | offers bound to a named challenger and a nonce, as specified |
| B1–B2 | whether buying the only challenger of a thin list is a regression against today, where one challenger guarantees court | measured on stage-1 data; the restart returns the claim to the whole market, and a per-list switch is one parameter if needed |
| C2 | the challenger cannot set an ask inside the challenge transaction through an unmodified host, so the first block after a challenge is a race the requester can win at the default | accepted and documented in stage 1; a challenge router, a signed precommit, or the module in stage 2 removes it |
| S8 | a shortfall at escalation has no reimbursement source in the wrapper | a funded reserve, or the lapse rule; the module can repay from the losing stake |
| S9 | evidence filed on the list must reach jurors | a relay through the wrapper, or resolver-side support for the dispute mapping; the state machine chooses the relay |
| S11 | whether a resolver share of the saved fee is wanted | each resolver's governance; for Kleros, only coherent jurors are paid today and no treasury share exists in code |
| multiparty | more than one standing challenger | rejected for now (section 7); revisit only with an explicit multiparty model |
| oracles | disputer withdrawal on markets | off by default under S7; proposer concession only |

## 7. Rules tried and rejected

| rule | why it fell |
|---|---|
| per-item resubmission cooldown | inert: item IDs are salted for free (S5); also unimplementable in a wrapper, which never sees submissions |
| at most one withdrawal per request | blocks honest sequential challengers, whose whole point is that one honest one suffices |
| a bound on a request's lifetime with a final mode | defeated by replacing the request, since self-concession is free (S4) |
| non-exclusive challengers with pay-all-asks and shared liability | one backstop makes conceding cost two deposits against a court loss of 51.6 on Scout numbers, so junk attracts pile-ons and goes to court; the wrapper cannot pay a backstop anyway; an unanalyzed multiparty mechanism |
| sealed rounds in the first version | keeper liveness and key-failure modes for no gain while prices are monotone |
| symmetric early escalation | the challenger's early escalation is free griefing (section 4) |
| no escalation at all | clean, but taxes a requester with a good claim by the whole window for nothing |
| a guaranteed period followed by symmetric escalation | a construction protecting a lever that had no legitimate use; replaced by section 4 |

## 8. Attack catalogue

| attack | outcome |
|---|---|
| spam challenge on a good claim | the requester escalates at once or waits; the challenger pays the fee in court, or in stage 2 pays the requester at least s_B to withdraw |
| extortion, "pay me to withdraw" | the requester escalates; nothing is purchasable |
| self-challenge loop on a registration | holds only the actor's own listing; sits in the challenged view, never in the review queue (S12) |
| self-challenge loop on a removal | removals are out of scope until independent removal prosecution exists (S7) |
| pending-page flood by self-concession and resubmission | free for gas by S4; confined to the challenged view by S12; canonical-content grouping in the indexer is a further presentation defense |
| squeezing a revealed price | asks only fall, bids only rise |
| forcing court out of spite | never free (S2, section 4) |
| front-running an acceptance | acceptance carries the expected price; buy-outs are recipient-bound |
| first-block concession before the ask is set | accepted; documented in section 6 |
| Sybil on both sides | every transfer internal; the outcome is what one honest actor gets; nothing pending is protected beyond S12 |

## 9. Passivity

| who acts | outcome | versus today |
|---|---|---|
| nobody | court at the deadline | same, one window later |
| A with a wrong claim concedes, B silent | A pays D, the fee returns to A | cheaper for A by the fee, same for B, no jurors |
| B lowers the ask, A concedes | A pays between D and the ask | better for both |
| A with a good claim escalates | court now | identical to today |
| B with a wrong challenge, stage 2 | pays A and leaves; the claim re-enters review | A paid instead of winning nothing |

## 10. Governance and adoption

Kleros governance executes on Ethereum through the Governor's optimistic list; the Gnosis court and the Scout lists are governed by Safes; Kleros V2's core is governed by an externally owned account today. Arbitration fees in both versions go only to coherent jurors, so "only jurors lose" holds in code and no treasury constituency is affected. From the court's side, removing pointless cases raises the quality of the remainder and lowers the cost of using the system. UMA's oracle splits a loser's bond between the winner and UMA's store, so its tokenholders are paid by volume and a market venue is the right counterparty there, with concession preserving the store's share.

## 11. Roadmap

The state machine for stage 1 exists (`spec/intendment-arbitrator-state-machine.md`); next are the adversarial traces against it, blind reviews, the pilot on our own list, a KIP asking the Scout lists' governor to re-point the lists, and, in parallel, the arbitrable-side module for stage 2 together with independent removal prosecution in the host. A standard is written after two systems run it.

## 12. What changed from v0.4, and why

| from | to | reason |
|---|---|---|
| a scope-reduced concession-only version | the full mechanism with a spine, sequenced | maintainer: sequencing, not scope |
| per-item cooldown and non-exclusive challengers | removed; recorded in section 7 | v0.4 audit and the maintainer's salting observation |
| no escalation | requester any time, challenger after the window, anyone at the deadline | derived from R2; Escrow V2 precedent |
| one fee F | three fees, split defined on the fee held | v0.4 audit |
| evidence "re-emitted by the wrapper" | evidence routing as a precondition, relay or resolver-side mapping | v0.4 audit |
| removals in scope | removals out until independent removal prosecution | v0.4 audit; maintainer |
| flood handled by rules | flood confined by status separation, verified in both apps | maintainer |
| ArbitrableProxy as precedent | cross-chain proxies and V2 gateways | integration research |
| requirements stated absolutely | R1, R3, R14 restated with their exceptions | v0.4 audit |

## Glossary

**Claim** the assertion under challenge. **Court loss, court gain** what a party pays or receives per resolver outcome. **Ceiling** the unilateral exit price, the exiting party's court loss. **Ask, bid** standing prices; asks only fall, bids only rise. **Window** the period after a challenge before the challenger may create the dispute. **Restart** the return of a claim to a full review period. **Lapse** the failure path when the resolver's fee cannot be funded. **Independent removal prosecution** a host-layer mechanism by which an honest remover can act while another removal request stands.
