# Intendment: out-of-court settlement for optimistic dispute systems

Design document v0.6, 2026-09-04. Status: the full mechanism, sequenced; stage 1 specified to the transaction. Supersedes v0.5 after its independent audit (`intendment-design-v0.5-review.md`); section 12 lists what changed and why. The stage-1 state machine is `../spec/intendment-arbitrator-state-machine.md`, committed with this version, and is the normative source for states, deadlines, money movements and failure paths.

**How to read this document.** Section 1 is the spine: constraints established by adversarial review, each with the finding that established it; a later section that conflicts with the spine is wrong. Section 3 is the full mechanism, every transition, implemented or not. Section 5 is the delivery sequence with the gate each stage opens. Section 6 names the open problems of the later transitions; section 7 records rules tried and rejected so that they are not proposed again.

## 0. Purpose

In optimistic systems someone asserts something with a bond, anyone may challenge it with a bond, and a resolver decides. In Kleros Curate the challenge creates the arbitration dispute in the same transaction, so every challenge pays jurors, including those the requester would concede on the spot and those the challenger would take back. Intendment is a settlement layer between "a challenge exists" and "a dispute is created": the parties may end the case by paying each other, priced against what the resolver would have cost them, with the resolver as the backstop at a deadline. It is a standard with a reference implementation: Kleros arbitrables first, optimistic-oracle systems next.

Concession is the first implemented transition, delivered as an arbitrator-level wrapper adopted by Kleros V1 lists, because it is the only part deployable without a Kleros merge and because it produces the adoption data that opens the gate for the rest. A V1 list has one arbitrator setting for both request types, so the wrapper receives removal challenges too; it passes those straight to the real arbitrator (section 3.2, P1) and opens settlement only on registrations.

**Precedents.** Kleros Escrow V1 resolves without jurors when a party fails to pay its fee share. Kleros Escrow V2 ships a native settlement window: either party proposes an amount, the other accepts or counter-proposes, the last proposer cannot raise the dispute until the settlement timeout has passed, the receiver may raise it at any time. Kleros's cross-chain proxies and V2 gateways forward disputes behind the arbitrator interface, the wrapper's shape. Polymarket's oracle adapter resets a question once on its first dispute.

## 1. The spine

| id | constraint | established by |
|---|---|---|
| S1 | Silence escalates, never concedes. An absent party reaches court as today, one window later at most. | a default-concede lets challengers farm absent requesters |
| S2 | Escalation is never free for the escalator. The challenge is the challenger's opening offer, so the challenger cannot create the dispute before the window ends. A party cannot create the dispute while an offer of its own is live; a party may always create it to reject the other side's offer. Anyone may create it once the window has ended. | R2, section 4; Escrow V2's rule; v0.5 audit finding 5 on revocable offers |
| S3 | Any withdrawn challenge restarts the review period in full. | the self-challenge shield |
| S4 | Free settlement makes pending states free to occupy: a settlement between two wallets of one owner is an internal transfer, so any state a settlement can hold becomes free to hold for gas; no rule keyed on item, request, address or count changes that. | audit of v0.1; every structural rule tried against it (section 7) |
| S5 | No anti-recycling rule may be keyed on a submitter-chosen item ID: registration IDs are hashes of submitted bytes and are re-salted for free. A removal target's ID is fixed, which is why S7 can act on removals at the host layer. | maintainer's review of the v0.4 audit; v0.5 audit finding 7 |
| S6 | The deposit is the list's deterrent and is never reduced by a settlement; the arbitration fee is a cost of court. | maintainer's decision |
| S7 | Third-party protection is per-system policy. Settlement never lets its parties monopolize the only public path for acting against something already in effect. In Curate, settlement on removal requests is off until independent removal prosecution exists, and the stage-1 wrapper enforces it by forwarding removals without opening settlement. | audit of v0.4; v0.5 audit finding 2 |
| S8 | Fees are accounted as three: F_A quoted into the requester's deposit at request time, F_B paid by the challenger at challenge time and held by the layer, F_E charged by the resolver at escalation. The layer's quote is a pure function of the request's arbitration extra data, so F_A = F_B by construction on hosts that store the extra data with the request; the quote carries a margin over the resolver's cost so that escalation is collateralized when the challenge is accepted; who bears every wei of F_E is named. | v0.5 audit findings 3 and 4 |
| S9 | Evidence reaches the resolver without a volunteer transaction: the resolver's evidence display follows the authenticated wrapper-to-host dispute mapping and renders the host's original evidence events. A relay through the wrapper is not passivity-safe and is not the route. | v0.5 audit finding 6 |
| S10 | Every timeout has a named, incentivized caller and an implementable terminal outcome. Creating the dispute after the window is the challenger's interest; anyone else may. | v0.5 audit finding 7 |
| S11 | Budget balance between the parties; a resolver share exists only if a system's governance adds it; the collateral margin is not a subsidy, it returns to whoever paid it. | R8 |
| S12 | The pending queue is protected by status separation: a looped item is always challenged, and both Curate apps list challenged requests apart from unchallenged ones. | verified in `kleros/gtcr` filters and the V2 app's status selector |
| S13 | Lapse is an emergency, not a solvency mechanism. A refusal ruling moves real value on every host, so it is never the routine answer to fee movement; it exists only for a shortfall beyond the margin that nobody funds, with its host-specific distribution disclosed. | v0.5 audit finding 4 |

## 2. Setting, notation, payoffs

**A** made a claim (the requester); **B** contests it (the challenger). Absent a settlement, a resolver decides.

| symbol | meaning | Scout lists on Gnosis |
|---|---|---|
| D | A's base deposit | 30 xDAI |
| F_A | fee quoted into A's deposit at request time | the epoch quote |
| F_B | fee B pays at challenge time, held by the layer | the same quote (S8) |
| F_E | the resolver's fee at escalation | 21.6 xDAI today |
| m | the margin the quote carries over the resolver's cost at epoch creation | a deployment parameter |
| D_c | B's challenge deposit | 0 |
| s_A = D + F_A | A's court loss | 51.6 at m = 0 |
| g_A = D_c | A's court gain | 0 |
| s_B = F_E + D_c | B's court loss, since B bears the resolver's fee | 21.6 |
| g_B = D + F_A − F_E | B's court gain: the pot's fee share reimburses what B paid | 30 at F_A = F_E |
| p_A, p_B | each side's private estimate of B's chance in court | private |
| r | probability the resolver refuses to rule | small, nonzero |

Court has three outcomes: B wins with probability p, A wins with 1−p−r, refusal with r. The refusal distribution is host-specific: Light GTCR and Curate V2 return the item to the pre-request status and split the pot in half; Classic distributes the pot in proportion to the parties' recorded contributions. The Scout lists are Light GTCR clones.

Money-only concession band, each side with its own belief: A concedes at Y ≤ p_A·s_A − (1−p_A)·g_A; B accepts at Y ≥ p_B·g_B − (1−p_B)·s_B. With F_A = F_B = F_E = F the width is F + (p_A − p_B)(D + F + D_c), F under common beliefs. The surplus any settlement distributes is the fee court would have consumed.

**Ceilings.** The unilateral concession price is s_A; the unilateral withdrawal price is s_B. Each exceeds the counterparty's best court outcome, so the counterparty always accepts, which makes the exits credible and prevents holdup.

**Values and the third party.** On Scout lists an external reward goes to submitters only; challengers are deposit-hunters whose court value on a bad claim is exactly D. The list has no negotiator; S3 and the challenger market stand in for it.

## 3. The full mechanism

After a challenge the fee F_B is escrowed and a window of length W opens. Moves marked stage 1 are delivered by the wrapper; later moves are specified here so that stage 1 is built to their shape.

### 3.1 Offers

An offer is a standing, binding price with a validity period of at least V, set by its owner; it cannot be withdrawn before its validity ends, and its owner cannot create the dispute while it is live (S2). The counterparty may execute it at any time while live, carrying the price it expects. Asks only fall and bids only rise within a window, so a revealed price never gives the counterparty more than its owner offered. A concession bid needs no new funds: any price up to s_A is paid out of A's existing deposit and the held fee.

Defaults: B's concession ask starts at D, B's court win, so a silent B is conceded to at the deposit and F_A returns to A (S6). A's withdrawal ask, when withdrawal exists, starts at s_B, so a silent A is paid B's full court loss and no spam challenge is cheaper than today.

### 3.2 Transitions

| id | move | who | when | money | effect | stage |
|---|---|---|---|---|---|---|
| B0 | bind | anyone; done implicitly by the first party move | after the host has stored the dispute mapping | none | reads the request type through the party resolver: registration → settlement open; removal → forwardable | 1 |
| P1 | forward a removal | anyone; the challenger's interest | after B0 on a removal | F_E to the resolver from escrow; surplus of the quote returns to B | court, as today; no settlement | 1 |
| C1 | concede at the ceiling | A | any time while open | A's net loss s_A: the host pays its pot to B, the held fee's remainder is split so that A nets −s_A | claim withdrawn; terminal | 1 |
| C2 | set the concession ask | B | once up from the default, then only down; each setting is an offer of validity ≥ V | none | the price A may concede at | 1 |
| C3 | concede at the ask | A | any time while open | A nets −ask; B nets +ask | claim withdrawn; terminal | 1 |
| C4 | post a concession bid | A | only up; validity ≥ V | none until accepted | an offer B may execute | 1 |
| C5 | accept the bid | B | while the bid is live | A nets −bid; B nets +bid | claim withdrawn; terminal | 1 |
| E1 | create the dispute | A | any time, unless an offer of A's is live | F_E from escrow per S8 | court | 1 |
| E2 | create the dispute | B | after W, unless an offer of B's is live | same | court | 1 |
| E3 | create the dispute | anyone | after W | same | court | 1 |
| E4 | emergency lapse | anyone | after W plus grace, only if F_E exceeds the quote and neither the reserve nor a funder has covered it | F_B refunded to B | refusal ruling; host-specific distribution (section 2); a governance failure, disclosed | 1 |
| W1 | withdraw at the ceiling | B | any time while open | B pays s_B to A | claim continues; review restarts (S3) | 2 |
| W2 | set the withdrawal ask | A | only down from s_B; validity ≥ V | none | the price B may withdraw at | 2 |
| W3 | withdraw at the ask | B | while the ask is live | B pays the ask to A | as W1 | 2 |
| W4 | withdraw the request | A | while no challenge stands | deposit returned | claim closed | 2, host-side |
| X1 | post a buy-out bid, bound to one named challenger and a nonce | A | only up; validity ≥ V | none until accepted | an offer that challenger may execute | 3 |
| X2 | accept the buy-out | the named challenger | while live | A pays the bid to B | as W1 | 3 |

**Net payouts for a concession at price Y on a Light or Classic V1 host, stage 1.** The host pays its pot, D + F_A + D_c, to B on a challenger ruling. The wrapper holds F_B = F_A. It refunds D + F_A − Y to A and F_B − (D + F_A − Y) to B. The expressible interval is D + F_A − F_B ≤ Y ≤ D + F_A, which with F_A = F_B is exactly [D, s_A]. At the default Y = D, all of F_A returns to A. The state machine carries the table for every ruling.

### 3.3 Requirements the transitions satisfy

| id | requirement |
|---|---|
| R1 | Voluntary: no party ends worse off than court in money; in time, at most one window per settlement case |
| R2 | No free griefing: delay or forced court costs its cause at least what it costs the victim |
| R3 | Passivity-safe: silence yields today's outcome, delayed at most by the window; the emergency lapse is a stated governance failure, not a passive outcome |
| R4 | No party can profit from a price the other has revealed |
| R5 | Prices can respond to evidence during the window |
| R6 | The deposit is never reduced by a settlement (S6) |
| R7 | No settlement registers anything without a full unchallenged review (S3) |
| R8 | Budget balance between the parties (S11) |
| R9 | Front-running resistant: executions carry the expected price; offers bind their owner; buy-outs are recipient-bound |
| R10 | No side holds a lever that is free for it and costly for the other (S2) |
| R11 | One page of rules per transition |
| R12 | Reusable across arbitrables and resolvers |
| R13 | Sybil-neutral: two wallets of one owner gain nothing over one (S4) |
| R14 | Live: every state terminates with a named caller (S10) |
| R15 | Third-party protection is per-system policy (S7) |

## 4. Why the escalation rule is what it is

Early escalation ends bargaining now instead of at the deadline. Its legitimate use is a party who wants the ruling sooner; its abusive use is denying the other side its exit. R2 decides who may hold it by what it costs each side.

The challenge is the challenger's opening offer: "concede or court." The challenger escalating before the requester has had the window would cost the challenger only the wait, the deposit later with some risk instead of at least the deposit now, while the requester loses the fee. Free griefing; so the challenger waits W. The requester escalating early rejects that offer, which is any receiver's right, and costs the requester what the challenger would have paid to withdraw where withdrawal exists, at least the challenger's court loss; priced with equality.

Offers generalize the same rule. A party who posts an offer is the last mover for that offer's validity and cannot escalate until it lapses or is executed; the receiver may execute it or reject it by escalating at any time. This is Escrow V2's rule, and it repairs v0.5's mistake of treating posted prices as revocable gifts: a price that its owner could revoke by escalating gave the owner a free option and the receiver nothing, and the earlier "prices never transfer the obligation" was right only for prices nobody could execute.

The pure timer, no escalation at all, remains an equally clean alternative that charges a requester with a good claim the whole window for nothing; the rule above is preferred for that reason and because Kleros has reviewed and shipped it.

## 5. Sequencing and gates

| stage | delivers | deployment | who decides | gate it opens |
|---|---|---|---|---|
| 1 | B0, P1, C1–C5, E1–E4 | `IntendmentArbitrator`, an arbitrator-level wrapper over Kleros V1: epoch-keyed quotes with a margin, request-type dispatch, concession as a ruling plus a fee split, removals forwarded, evidence through the resolver's display; adopted by a list's governor switching its arbitrator, or by a new list at deployment | a list's governor. Our own list first; then the Scout lists' governor, a 2-of-4 Safe that re-pointed all three lists' arbitrator in one batch after the KIP-87 Snapshot vote in July 2026 | adoption data: settled cases, fees saved, delay added; the fee-epoch, dispatch and evidence mechanics proven with a silent party |
| 2 | W1–W4 on registrations; removals once independent removal prosecution exists | `IntendmentModule`, arbitrable-side, in Curate V2 and Permanent GTCR; V2's arbitrator is governor-changeable but withdrawal needs custody the wrapper lacks; Permanent GTCR's arbitrator is immutable and can only take the module | Kleros maintainers; new lists only, since lists are clones | the withdrawal half and the restart; custody of both stakes |
| 3 | X1–X2 | module extension | Kleros maintainers | buy-outs with recipient binding; a thin-challenger-market study on stage-1 data before enabling |
| 4 | proposer concession on optimistic oracles | an oracle-compatible front adopted by a market venue's adapter, or V3's escalation manager | the market venue; UMA for the V3 route | settlement outside Kleros; the standard |

Court-core settlement inside KlerosCore is deferred: no cancel or refund path exists in V1 or V2; it needs a new terminal state, refunds, a ruling callback, a dispute-kit hook and UI, and V2's governor is an externally owned account today. Dispute kits cannot host it.

## 6. Open problems of the later transitions, named

| transition | problem | what would resolve it |
|---|---|---|
| W1–W3 | custody: the wrapper holds only F_B and cannot redirect the host's pot; a withdrawal with restart is not expressible as a ruling | the arbitrable-side module |
| removals | the removal slot is exclusive and its target's ID is fixed | independent removal prosecution in the host: several removal requests per item, or a join or fork-to-court mechanism |
| X1–X2 | whether buying the only challenger of a thin list regresses today's guarantee | measured on stage-1 data; a per-list switch is one parameter |
| C2 | the challenger cannot set an ask inside the challenge transaction through an unmodified host, so the first block after a challenge is a race the requester can win at the default | accepted and documented; a challenge router removes it; the module carries the ask in the challenge |
| S8 | the reserve that covers a fee increase beyond the margin is external capital | funded and owned by the wrapper's governor, replenished from quote margins, and disclosed; the emergency lapse is the disclosed failure when it is empty |
| S9 | the resolver's evidence display must exist for each resolver UI | built and tested with a silent party before the pilot |
| S11 | whether a resolver share of the saved fee is wanted | each resolver's governance; Kleros pays only coherent jurors today |
| multiparty | more than one standing challenger | rejected (section 7); revisit only with an explicit multiparty model |
| oracles | disputer withdrawal on markets | off under S7; proposer concession only |

## 7. Rules tried and rejected

| rule | why it fell |
|---|---|
| per-item resubmission cooldown | inert: registration IDs are re-salted for free (S5); unimplementable in a wrapper |
| at most one withdrawal per request | blocks honest sequential challengers |
| a bound on a request's lifetime | defeated by replacing the request (S4) |
| non-exclusive challengers with pay-all-asks and shared liability | one backstop makes conceding cost two deposits against a 51.6 court loss; junk attracts pile-ons; the wrapper cannot pay a backstop |
| sealed rounds in the first version | keeper liveness and key failures for no gain while offers bind |
| symmetric early escalation | the challenger's early escalation is free griefing |
| no escalation at all | taxes a requester with a good claim by the whole window |
| a guaranteed period then symmetric escalation | protected a lever with no legitimate use |
| revocable posted prices | a price its owner can revoke by escalating is a free option (v0.5 audit) |
| lapse as the routine answer to fee movement | a refusal ruling pays the challenger half the pot without a merits ruling; an announced fee increase becomes an extraction tool (v0.5 audit) |
| a live resolver fee as the quote | lets a request and its challenge straddle a fee change, breaking the concession split (v0.5 audit) |

## 8. Attack catalogue

| attack | outcome |
|---|---|
| spam challenge on a good claim | the requester escalates at once or waits; the challenger pays F_E in court |
| extortion, "pay me to withdraw" | the requester escalates; nothing is purchasable |
| self-challenge loop on a registration | holds only the actor's own listing; sits in the challenged view (S12) |
| self-challenge on a removal | forwarded to court at once by the wrapper (P1); the actor loses deposit and fee |
| pending-page flood by self-concession | free for gas by S4; confined to the challenged view by S12 |
| challenge before an announced fee increase, then withhold | the quote's margin funds the increase; the reserve beyond it; only an empty reserve reaches the disclosed emergency |
| lower an ask, then front-run its acceptance by escalating | impossible: the owner of a live offer cannot escalate |
| post a bid to extract a lower ask, then walk away | impossible: bids are executable by the counterparty for their validity |
| squeezing a revealed price | asks only fall, bids only rise |
| forcing court out of spite | never free (S2, section 4) |
| front-running an execution | executions carry the expected price; buy-outs are recipient-bound |
| first-block concession before the ask is set | accepted; section 6 |
| Sybil on both sides | every transfer internal; nothing pending is protected beyond S12 |

## 9. Passivity

| who acts | outcome | versus today |
|---|---|---|
| nobody | court after the window, created by the challenger or anyone | same, one window later |
| A with a wrong claim concedes, B silent | A nets −D; F_A returns to A | cheaper for A by the fee, same for B, no jurors |
| B lowers the ask, A concedes | A nets between −D and −ask | better for both |
| A with a good claim escalates | court now | identical to today |
| a removal is challenged | forwarded to court on binding | identical to today, plus one binding transaction |

## 10. Governance and adoption

Kleros governance executes on Ethereum through the Governor's optimistic list; the Gnosis court and the Scout lists are governed by Safes; Kleros V2's core is governed by an externally owned account today. Arbitration fees in both versions go only to coherent jurors, so no treasury constituency is affected. From the court's side, removing pointless cases raises the quality of the remainder and lowers the cost of using the system. UMA's oracle splits a loser's bond between the winner and UMA's store, so its tokenholders are paid by volume and a market venue is the right counterparty there, with concession preserving the store's share.

## 11. Roadmap

The stage-1 state machine is committed with this version. Next: adversarial traces against it, at minimum a removal challenged after adoption, a request crossing quote epochs, an announced fee increase, simultaneous escalation and lapse, a bid crossing a lowered ask, an escalation racing an execution, resolver reverts, failed receivers, and each supported refusal branch; blind reviews of both documents; the resolver evidence display, tested with a silent party; the pilot on our own list; a KIP asking the Scout lists' governor to re-point the lists; in parallel, the arbitrable-side module and independent removal prosecution in the host. A standard is written after two systems run it.

## 12. What changed from v0.5, and why

| from | to | reason |
|---|---|---|
| stage 1 "registration requests only" | request-type dispatch after binding; removals forwarded without settlement | a V1 list has one arbitrator for both request types (v0.5 audit 2) |
| a state machine referenced but uncommitted and v0.4-based | reconciled and committed with this version | v0.5 audit 1 |
| three fee names, one-fee bands | epoch-keyed pure-function quotes so F_A = F_B; margin collateralization; F_E's payer named; net payouts stated | v0.5 audit 3 |
| lapse as the routine shortfall path | emergency only, with the host-specific distribution disclosed (S13) | v0.5 audit 4 |
| revocable posted prices, non-executable bids | binding offers with validity; owner cannot escalate while live; C5 accept | v0.5 audit 5 |
| evidence route undecided | resolver-side display over the dispute mapping (S9) | v0.5 audit 6 |
| "V1" as one payout model; Curate V2 called immutable; S5 stated too broadly; two deadline timelines; "anyone" as an incentive | host models named; only Permanent GTCR immutable; S5 narrowed; one timeline; the challenger named as the incentivized caller | v0.5 audit 7 |

## Glossary

**Claim** the assertion under challenge. **Court loss, court gain** what a party pays or receives per resolver outcome. **Ceiling** the unilateral exit price, the exiting party's court loss. **Offer** a binding standing price with a validity period. **Window** the period after a challenge before the challenger may create the dispute. **Epoch** a value of the arbitration extra data with a fixed quote. **Margin** the amount by which a quote exceeds the resolver's cost at epoch creation. **Restart** the return of a claim to a full review period. **Emergency lapse** the disclosed failure path when a fee increase beyond the margin goes unfunded.
