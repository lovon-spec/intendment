# Intendment: out-of-court settlement for optimistic dispute systems

Design document v0.8, 2026-09-04. Status: the full mechanism, sequenced; stage 1 specified to the transaction, with validated structured specification data and CI. Supersedes v0.7 after its independent review (`intendment-design-v0.7-review-gpt.md`); section 12 lists what changed and why. The stage-1 state machine is `../spec/intendment-arbitrator-state-machine.md` 0.4, committed with this version, and is the normative source for states, deadlines, money movements and failure paths; its tables are generated from `../spec/intendment-arbitrator-state-machine.yaml`.

**How to read this document.** Section 1 is the spine: constraints established by adversarial review, each with the finding that established it; a later section that conflicts with the spine is wrong. Section 3 is the full mechanism, every transition, implemented or not. Section 5 is the delivery sequence with the gate each stage opens. Section 6 names the open problems of the later transitions; section 7 records rules tried and rejected so that they are not proposed again.

## 0. Purpose

In optimistic systems someone asserts something with a bond, anyone may challenge it with a bond, and a resolver decides. In Kleros Curate the challenge creates the arbitration dispute in the same transaction, so every challenge pays jurors, including those the requester would concede on the spot and those the challenger would take back. Intendment is a settlement layer between "a challenge exists" and "a dispute is created": the parties may end the case by paying each other, priced against what the resolver would have cost them, with the resolver as the backstop at a deadline. The deadweight it removes is the resolver's fee, its latency, or both: in Kleros mostly the fee, on a prediction market mostly the days of voting. It is a standard with a reference implementation: Kleros arbitrables first, optimistic-oracle systems next.

Concession is the first implemented transition, delivered as an arbitrator-level wrapper adopted by Kleros V1 lists, because it is the only part deployable without a Kleros merge and because it produces the adoption data that opens the gate for the rest. Its first deployment, stage 1a, is the smallest version that tests the hypothesis: one displayed price, a concede button, a court button, court after the deadline. Asks and bids follow in stage 1b once the one-button version shows demand. A V1 list has one arbitrator setting for both request types, so the wrapper receives removal challenges too; it passes those straight to the real arbitrator (section 3.2, P1) and opens settlement only on registrations.

**Precedents.** Kleros Escrow V1 resolves without jurors when a party fails to pay its fee share. Kleros Escrow V2 ships a native settlement window: either party proposes an amount, the other accepts or counter-proposes, the last proposer cannot raise the dispute until the settlement timeout has passed, the receiver may raise it at any time. Kleros's cross-chain proxies and V2 gateways forward disputes behind the arbitrator interface, the wrapper's shape. Polymarket's oracle adapter resets a question once on its first dispute.

## 1. The spine

| id | constraint | established by |
|---|---|---|
| S1 | Silence escalates, never concedes. For an insured case an absent party reaches court as today, one window later at most; for an under-insured case, disclosed at creation, court depends on free reserve or funding, and the emergency lapse is possible. | a default-concede lets challengers farm absent requesters; v0.7 review finding 5 on the trilemma |
| S2 | Escalation is never free for the escalator. The challenge is the challenger's opening offer, so the challenger cannot create the dispute before the window ends. A party cannot create the dispute while an offer of its own is live; a party may always create it to reject the other side's offer. Offers end at the deadline; from then on anyone may create the dispute, and not before: binding is a property of the case, never of a sender address. | R2, section 4; Escrow V2's rule; v0.5 audit finding 5 on revocable offers; v0.6 review finding 2 on the second-wallet bypass |
| S3 | Any withdrawn challenge restarts the review period in full. | the self-challenge shield |
| S4 | Free settlement makes pending states free to occupy: a settlement between two wallets of one owner is an internal transfer, so any state a settlement can hold becomes free to hold for gas; no rule keyed on item, request, address or count changes that. Once a case occupies insurance capacity, the same holds for capacity, and only a price on the state itself changes it. | audit of v0.1; every structural rule tried against it (section 7); v0.7 review finding 1 |
| S5 | No anti-recycling rule may be keyed on a submitter-chosen item ID: registration IDs are hashes of submitted bytes and are re-salted for free. A removal target's ID is fixed, which is why S7 can act on removals at the host layer. | maintainer's review of the v0.4 audit; v0.5 audit finding 7 |
| S6 | The deposit is the list's deterrent and is never reduced by a settlement; the arbitration fee is a cost of court. | maintainer's decision |
| S7 | Third-party protection is per-system policy. Settlement never lets its parties monopolize the only public path for acting against something already in effect. In Curate, settlement on removal requests is off until independent removal prosecution exists, and the stage-1 wrapper enforces it by forwarding removals without opening settlement. | audit of v0.4; v0.5 audit finding 2 |
| S8 | Fees are accounted as three: F_A quoted into the requester's deposit at request time, F_B paid by the challenger at challenge time and held by the layer, F_E charged by the resolver at escalation. The layer's quote is a pure function of the request's arbitration extra data, so F_A = F_B = q by construction on hosts that store the extra data with the request. The quote is a fixed price: the challenger's economic fee on a forwarded case is q whatever the resolver charges, and a disclosed reserve absorbs the difference in either direction. | v0.5 audit findings 3 and 4; v0.6 review finding 1 |
| S9 | Evidence reaches the resolver without a volunteer transaction: the resolver's evidence display follows the authenticated wrapper-to-host dispute mapping and renders the host's original evidence events. A relay through the wrapper is not passivity-safe and is not the route. | v0.5 audit finding 6 |
| S10 | Every timeout has a named, incentivized caller and an implementable terminal outcome. Creating the dispute after the window is the challenger's interest on a registration and the requester's on a removal; anyone else may. | v0.5 audit finding 7; v0.7 review finding 5 on the removal incentive |
| S11 | Budget balance between the parties on every settlement, net of a disclosed capacity premium that the pool keeps. On court cases the difference between the fixed price and the resolver's cost flows to or from the pool. The pool has two accounts: principal, which returns to its provider only after retirement and two locks, and surplus, which is nobody's revenue: it pays insurance, lowers future margins and premiums, or moves to a successor. A resolver share exists only if a system's governance adds it. | R8; v0.6 review finding 1; v0.7 review findings 1 and 7 |
| S12 | The pending queue is protected by status separation: a looped item is always challenged, and both Curate apps list challenged requests apart from unchallenged ones. | verified in `kleros/gtcr` filters and the V2 app's status selector |
| S13 | Lapse is an emergency, not a solvency mechanism. A refusal ruling moves real value on every host, and on Light hosts the requester prefers it to conceding, so it must be unreachable in normal operation: every case is insured up to a declared maximum cost at creation, a funding period precedes any lapse, escalation and lapse are exclusive by construction, and a resolver that keeps rejecting a correctly funded dispute opens the lapse only after a grace period. | v0.5 audit finding 4; v0.6 review finding 3; v0.7 review finding 6 |
| S14 | The layer never refuses a challenge. Its dispute creation reverts only on a host bug, never on the state of its reserve; a thin reserve produces disclosed under-insured cases, not failed challenges. | maintainer's addition on the v0.6 review: a reservation that reverts censors the host's challenge path |
| S15 | No transition depends on a party accepting a transfer: every payout is a claimable credit, and no transition's cost grows with the number of parties, funders or cases. | v0.6 review finding 5; v0.7 review finding 3 on the funder loop |
| S16 | The layer prices in shares of the held fee and never reads a deposit: the requester's net loss on a concession is the deposit, the premium and the share, so the host's deposit rules stay in the host and a changed deposit cannot mis-price a case. | v0.6 review finding 4, resolved by removing the dependency |
| S17 | One layer instance per host, with the host's governor as the layer's governor; the instance is a plain, non-upgradeable contract. A reserve shared across hosts needs an allowlist and per-host isolation. | v0.6 review finding 4; v0.7 review's cleanups |
| S18 | The layer never widens a party's rights against the host: an appeal reaches the resolver only through the host's own appeal path, so the host's appeal crowdfunding, multipliers and round accounting are never bypassed. | v0.7 review finding 4 |
| S19 | A layer instance retires before its reserve moves: requests submitted under it stay challengeable for the host's challenge period after the list has moved on, so principal withdrawal and surplus migration wait for retirement, a lock at least that long, and every case to end. | v0.7 review finding 2 |

## 2. Setting, notation, payoffs

**A** made a claim (the requester); **B** contests it (the challenger). Absent a settlement, a resolver decides.

| symbol | meaning | Scout lists on Gnosis |
|---|---|---|
| D | A's base deposit | 30 xDAI |
| q | the epoch quote: F_A, quoted into A's deposit at request time, and F_B, paid by B at challenge time and held by the layer (S8) | 21.6 xDAI at m = 0 |
| c | the resolver's cost at escalation, F_E; borne by the reserve beyond q, never by a party | 21.6 xDAI today |
| m | the margin the quote carries over the resolver's cost at epoch creation, capped in code | a deployment parameter |
| π | the capacity premium the pool keeps on every settled case, a fraction of q fixed per epoch and capped in code | zero in the pilot |
| x | a fee share, the layer's price unit: 0 ≤ x ≤ q − π | |
| Y = D + π + x | A's net loss on a concession at share x | |
| D_c | B's challenge deposit | 0 |
| s_A = D + q | A's court loss | 51.6 |
| g_A = D_c | A's court gain | 0 |
| s_B = q + D_c | B's court loss: the fixed price plus B's deposit | 21.6 |
| g_B = D | B's court gain: the pot's fee share reimburses exactly what B paid | 30 |
| ρ_A, ρ_B | A's loss and B's result on a refusal ruling; on Light and Curate V2, which halve the pot: ρ_A = (D + q − D_c)/2, ρ_B = (D − q − D_c)/2 | 25.8, 4.2 |
| p_A, p_B | each side's private estimate of B's chance in court | private |
| r | probability the resolver refuses to rule | small, nonzero |

Court has three outcomes: B wins with probability p, A wins with 1−p−r, refusal with r. The refusal distribution is host-specific: Light GTCR and Curate V2 return the item to the pre-request status and halve the pot; Classic distributes the pot in proportion to the parties' recorded contributions. The Scout lists are Light GTCR clones.

Money-only concession band, each side with its own belief: A concedes at Y ≤ p_A·s_A + r·ρ_A − (1−p_A−r)·g_A; B accepts at Y − π ≥ p_B·g_B − (1−p_B−r)·s_B + r·ρ_B, since B receives Y less the premium. Under common beliefs the width is exactly q − π, whatever r and whatever the refusal rule: in every court outcome the whole pot returns to the parties and the resolver's fee is the only leak, so the surplus any settlement distributes is the fee court would have consumed, less the premium the pool keeps. With differing beliefs the width is q − π + (p_A − p_B)(D + q + D_c).

**Ceilings.** The unilateral concession price is s_A, share x = q − π; the unilateral withdrawal price is s_B. Each exceeds the counterparty's best court outcome, so the counterparty always accepts, which makes the exits credible and prevents holdup. The default concession share is 0: A recovers the fee less the premium and B receives the pot, which is B's court win.

**Values and the third party.** On Scout lists an external reward goes to submitters only; challengers are deposit-hunters whose court value on a bad claim is exactly D. The list has no negotiator; S3 and the challenger market stand in for it.

## 3. The full mechanism

After a challenge the fee q is escrowed and a window of length W opens; the deadline is its end, and a funding period of length G follows it. Moves marked 1a are the first deployment, 1b adds offers; later moves are specified here so that stage 1 is built to their shape.

### 3.1 Offers

An offer is a standing, binding fee share posted before the deadline. An **ask** is B's concession price: the default 0 is not an offer and binds nobody, which is why a silent B can be conceded to; B may raise it once, to at most q − π, and then only lower it; once set it persists as an executable price until the case ends and never rises, so a revealed ask never costs A more than B posted; after the deadline it is an executable quote, no longer an offer, and binds nobody's escalation. A **bid** is A's concession price with a validity of at least V that ends no later than the deadline; while it is live B may execute it and A cannot create the dispute; at expiry it is gone. Bids only rise within a case. A concession needs no new funds at any share: it is paid out of A's deposit and the held fee.

No offer can be posted at or after the deadline, so none is live when the permissionless escalation opens; binding is therefore a property of the case (S2). Crossing is deterministic: an ask set at or below the live bid executes as an acceptance at the bid, a bid at or above the ask executes as a concession at the ask. Executions carry a limit, not an exact price: a price that moved in the executor's favor should not fail the transaction.

Defaults: B's ask starts at 0, so a silent B is conceded to at the deposit plus the premium and the rest of the fee returns to A (S6). A's withdrawal ask, when withdrawal exists, starts at s_B, so a silent A is paid B's full court loss and no spam challenge is cheaper than today.

### 3.2 Transitions

| id | move | who | when | money | effect | stage |
|---|---|---|---|---|---|---|
| B0 | bind | anyone; done implicitly by the first party move | after the host has stored the dispute mapping | none | reads the request type through the host profile: registration → settlement open; removal → forwardable | 1a |
| P1 | forward a removal | anyone; the removal requester's interest; a router bundles it with the challenge | after B0 on a removal, while covered | the resolver's cost from the escrow, the earmark, the free reserve, then case funding; q − c to surplus | court, as today; no settlement | 1a |
| C1 | concede at the ask | A | any time while open | A nets −(D + π + x); B nets +(D + x); the pool keeps π; credits, not transfers | claim withdrawn; terminal | 1a, at x = 0 only |
| C2 | set the ask | B | before the deadline; once up to at most q − π, then only down | none; crossing a live bid executes C4 at the bid | the share A may concede at | 1b |
| C3 | post a bid | A | before the deadline; only up; validity ≥ V, ending by the deadline | none until accepted; crossing the ask executes C1 at the ask | an offer B may execute | 1b |
| C4 | accept the bid | B | while the bid is live | A nets −(D + π + bid); B nets +(D + bid) | claim withdrawn; terminal | 1b |
| E1 | create the dispute | A | before the deadline, unless a bid of A's is live; while covered | as P1 | court | 1a |
| E2 | create the dispute | anyone, B included | from the deadline; while covered | as P1 | court | 1a |
| F1 | fund the case | anyone | until the end of the funding period | stored for this case; the unused part claimable later by each funder | makes an uncovered case coverable | 1a |
| F2 | claim unused funding | a funder, once per case | after the case ends | the funder's share of what forwarding did not use | | 1a |
| E3 | emergency lapse | anyone | after the funding period, if the case is not covered or the resolver has rejected it for a grace period | q credited to B; funding fully claimable | refusal ruling; host-specific distribution (section 2); a failure, disclosed | 1a |
| K1 | claim credits | any creditor | any time | the creditor's balance to an address of its choice | the only value transfer to a party | 1a |
| W1 | withdraw at the ceiling | B | any time while open | B pays s_B to A | claim continues; review restarts (S3) | 2 |
| W2 | set the withdrawal ask | A | only down from s_B; validity ≥ V | none | the price B may withdraw at | 2 |
| W3 | withdraw at the ask | B | while the ask is live | B pays the ask to A | as W1 | 2 |
| W4 | withdraw the request | A | while no challenge stands | deposit returned | claim closed | 2, host-side |
| X1 | post a buy-out bid, bound to one named challenger and a nonce | A | only up; validity ≥ V | none until accepted | an offer that challenger may execute | 3 |
| X2 | accept the buy-out | the named challenger | while live | A pays the bid to B | as W1 | 3 |

**Net payouts for a concession at share x on a Light or Classic V1 host, stage 1.** The host pays its pot, D + q + D_c, to B on a challenger ruling. The wrapper holds q. It credits q − π − x to A, x to B, and keeps π in surplus. A nets −(D + π + x), B nets +(D + x); the expressible interval is [D + π, s_A] in Y, and the wrapper computes it without knowing D. The state machine carries the table for every ruling, including refusal, and the funders' accounting.

### 3.3 Requirements the transitions satisfy

| id | requirement |
|---|---|
| R1 | Voluntary: no party ends worse off than court in money; in time, at most one window per settlement case |
| R2 | No free griefing: delay or forced court costs its cause at least what it costs the victim |
| R3 | Passivity-safe by mode: for an insured case silence yields today's outcome, delayed at most by the window; for an under-insured case, disclosed at creation, court depends on reserve or funding and the emergency lapse is a stated failure, not a passive outcome |
| R4 | No party can profit from a price the other has revealed |
| R5 | Prices can respond to evidence during the window |
| R6 | The deposit is never reduced by a settlement (S6) |
| R7 | No settlement registers anything without a full unchallenged review (S3) |
| R8 | Budget balance between the parties net of the disclosed premium (S11) |
| R9 | Front-running resistant: executions carry a limit price; offers bind their owner and end at the deadline; buy-outs are recipient-bound |
| R10 | No side holds a lever that is free for it and costly for the other (S2) |
| R11 | One page of rules per transition |
| R12 | Reusable across arbitrables and resolvers |
| R13 | Sybil-neutral: two wallets of one owner gain nothing over one (S4) |
| R14 | Live: every state terminates with a named caller (S10) |
| R15 | Third-party protection is per-system policy (S7) |
| R16 | Failure-safe: no transition depends on a party accepting a transfer, and none grows with the number of funders or cases (S15) |
| R17 | Never refuses a challenge (S14) |
| R18 | Never widens a party's rights against the host (S18) |
| R19 | Retires before its reserve moves (S19) |

## 4. Why the escalation rule is what it is

Early escalation ends bargaining now instead of at the deadline. Its legitimate use is a party who wants the ruling sooner; its abusive use is denying the other side its exit. R2 decides who may hold it by what it costs each side.

The challenge is the challenger's opening offer: "concede or court." The challenger escalating before the requester has had the window would cost the challenger only the wait, the deposit later with some risk instead of at least the deposit now, while the requester loses the fee. Free griefing; so the challenger waits W. The requester escalating early rejects that offer, which is any receiver's right, and costs the requester what the challenger would have paid to withdraw where withdrawal exists, at least the challenger's court loss; priced with equality.

Offers generalize the same rule. A party who posts an offer is the last mover for that offer's validity and cannot escalate until it lapses or is executed; the receiver may execute it or reject it by escalating at any time. This is Escrow V2's rule, and it repairs v0.5's mistake of treating posted prices as revocable gifts: a price that its owner could revoke by escalating gave the owner a free option and the receiver nothing.

Binding must be a property of the case because S4 forbids keying anything on addresses: an owner with two wallets is one owner, and v0.6's per-sender check let the second wallet take the permissionless path around the first wallet's live offer. Offers therefore end at the deadline and the permissionless path opens only then. This costs nothing. The challenger cannot escalate before the deadline anyway, so an ask's lock never binds and asks can simply persist as prices; a bid's lock binds the requester for exactly its validity, which is the only lock that ever mattered.

The pure timer, no escalation at all, remains an equally clean alternative that charges a requester with a good claim the whole window for nothing; the rule above is preferred for that reason and because Kleros has reviewed and shipped it.

## 5. Sequencing and gates

| stage | delivers | deployment | who decides | gate it opens |
|---|---|---|---|---|
| 1a | B0, P1, C1 at the default, E1–E3, F1, F2, K1 | `IntendmentArbitrator` with offers disabled and the premium at zero: a plain, non-upgradeable arbitrator-level wrapper over Kleros V1, one per list from a factory, the list's governor as its governor; epoch-keyed fixed-price quotes behind an explicit envelope; earmarked reserve with principal and surplus; request-type dispatch; concession as a ruling plus a fee split; removals forwarded, bundled with the challenge by the list's router; claimable credits; host-only appeals; retirement locks; evidence through the resolver's display | a list's governor. Our own list first; then the Scout lists' governor, a 2-of-4 Safe that re-pointed all three lists' arbitrator in one batch after the KIP-87 Snapshot vote in July 2026 | the hypothesis itself: do clearly losing requesters concede before court when they can recover the unused fee? Measured by the pilot metrics below; the epoch, dispatch, credit, funding and evidence mechanics proven with a silent party |
| 1b | C2–C4, and a nonzero premium where the reserve is not the governor's own money | the same contract with offers enabled, redeployed; the old instance retired under S19 | the same governor | negotiated versus default settlements; whether a challenger market forms; capacity occupation under a premium |
| 2 | W1–W4 on registrations; removals once independent removal prosecution exists | `IntendmentModule`, arbitrable-side, in Curate V2 and Permanent GTCR; V2's arbitrator is governor-changeable but withdrawal needs custody the wrapper lacks; Permanent GTCR's arbitrator is immutable and can only take the module | Kleros maintainers; new lists only, since lists are clones | the withdrawal half and the restart; custody of both stakes |
| 3 | X1–X2 | module extension | Kleros maintainers | buy-outs with recipient binding; a thin-challenger-market study on stage-1 data before enabling |
| 4 | proposer concession on optimistic oracles, bounded per question | an oracle-compatible front adopted by a market venue's adapter, or V3's escalation manager | the market venue; UMA for the V3 route | settlement outside Kleros; the standard |

**Pilot metrics, fixed before the pilot so that "successful" is not decided afterwards:** court-avoidance rate; median delay added to cases that still reach court; fees saved net of the added gas; reserve utilization, maximum drawdown, and earmark-hours occupied per settled case, which is what capacity occupation costs and drawdown cannot see; the share of parties who act versus stay silent; default-price versus negotiated settlements once 1b is on; cases needing a keeper or funder; under-insured cases opened; resolver rejections.

Court-core settlement inside KlerosCore is deferred: no cancel or refund path exists in V1 or V2; it needs a new terminal state, refunds, a ruling callback, a dispute-kit hook and UI, and V2's governor is an externally owned account today. Dispute kits cannot host it.

## 6. Open problems of the later transitions, named

| transition | problem | what would resolve it |
|---|---|---|
| W1–W3 | custody: the wrapper holds only the fee and cannot redirect the host's pot; a withdrawal with restart is not expressible as a ruling | the arbitrable-side module |
| removals | the removal slot is exclusive and its target's ID is fixed | independent removal prosecution in the host: several removal requests per item, or a join or fork-to-court mechanism |
| X1–X2 | whether buying the only challenger of a thin list regresses today's guarantee | measured on stage-1 data; a per-list switch is one parameter |
| C2 | the challenger cannot set an ask inside the challenge transaction through an unmodified host, so the first block after a challenge is a race the requester can win at the default | absent in 1a; accepted and documented in 1b; a challenge router removes it; the module carries the ask in the challenge |
| S11 | sizing: the insured maximum per epoch, the floor for latent exposure, the margin and the premium that keep the pool at target without accumulating | set for the pilot from Kleros's fee history and measured earmark-hours; the excess rule is a governance norm, not code |
| S19 | the wrapper cannot see requests submitted under it but not yet challenged, so its retirement lock is a bound, not a count | off-chain monitoring of the host's events; a host hook in the module |
| S10 | "anyone may" is a liveness argument, not an incentive, for forwarding removals and escalating after the deadline; the interested party carries it today | a keeper bounty from the margin, refunded to the party who acts on time; later |
| S9 | the resolver's evidence display must exist for each resolver UI | built and tested with a silent party before the pilot |
| S11 | whether a resolver share of the saved fee is wanted | each resolver's governance; Kleros pays only coherent jurors today |
| offers | posting an offer costs a transaction; monotone curves and signed offers would remove that | EIP-712 offers submitted by anyone; time curves matched permissionlessly; after 1b |
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
| pass-through fee with the surplus refunded to the challenger | a one-way hedge at zero price: the challenger keeps falling fees, the reserve absorbs rising ones, and the reserve can never be replenished from margins it refunds (v0.6 review) |
| pure pass-through with no reserve | economically clean, but a shortfall then needs a volunteer, which is not passivity-safe with an unmodified host (v0.6 review) |
| offer binding checked on the sender address | a second wallet takes the permissionless path around its owner's live offer; violates S4 (v0.6 review) |
| offers posted after the deadline | reintroduces the revocable price: anyone may escalate at any moment, so a posted price is a signal, not an offer |
| a single expiry rule for asks and bids | an ask that expires would have to rise or fall back; either breaks no-holdup or punishes the challenger for posting; asks persist, bids expire |
| payouts pushed inside transitions | a reverting receiver blocks concession and forwarding both: a free court-blocking lever (v0.6 review) |
| reserve capacity enforced by refusing `createDispute` | censors the host's challenge path; on a registry that is the worst failure there is |
| deposit-aware pricing in the wrapper | a deposit changed between request and challenge mis-prices the case; pricing in fee shares needs no deposit at all |
| deleting lapse from the pilot | every state needs a terminal (R14); lapse stays and is made unreachable by parameter instead |
| insurance capacity free to occupy | a self-challenge occupies an earmark for the whole window and recovers every coin (v0.7 review); the premium prices the state itself, which S4 says is the only thing that works |
| refunding funders inside finalization | a loop over funders lets dust contributions push forwarding or lapse past the block gas limit (v0.7 review); one stored fraction, claimed lazily |
| `appeal` callable by anyone | bypasses the host's appeal game: multipliers, contributions, round count (v0.7 review) |
| withdrawing the reserve when no case is open | requests already submitted under the wrapper are still challengeable (v0.7 review); retirement and a lock first |
| unconditional passivity with a finite reserve | never refusing a challenge, guaranteeing court to the silent, and a finite reserve cannot all hold (v0.7 review); passivity is by mode |
| a covered case with a rejecting resolver left to wait | no terminal path (v0.7 review); a grace period, then lapse |
| charging capacity by earmark-time | the right price in principle; too much machinery for stage 1 (v0.7 review) |

## 8. Attack catalogue

| attack | outcome |
|---|---|
| spam challenge on a good claim | the requester escalates at once or waits; the challenger pays q in court |
| extortion, "pay me to withdraw" | the requester escalates; nothing is purchasable |
| self-challenge loop on a registration | holds only the actor's own listing; sits in the challenged view (S12) |
| self-challenge to occupy insurance capacity | free at π = 0 and bounded by the earmark size; priced by the premium per case-window; measured as earmark-hours in the pilot; bites only during a resolver fee increase |
| self-challenge on a removal | forwarded to court at once by the router or anyone (P1); the actor loses deposit and fee |
| pending-page flood by self-concession | free for gas by S4; confined to the challenged view by S12 |
| challenge before an announced fee increase, then withhold | within the margin the fee covers it; up to the insured maximum the earmark does; beyond it the funding period, then the disclosed emergency |
| lower an ask, then front-run its acceptance by escalating | impossible: the challenger cannot escalate before the deadline, and asks persist |
| post a bid to extract a lower ask, then walk away | impossible: bids are executable by the counterparty for their validity, which the owner cannot cut short |
| escalate around one's own offer from a second wallet | impossible: no offer is live when the permissionless path opens (S2) |
| squeezing a revealed price | asks only fall, bids only rise |
| forcing court out of spite | never free (S2, section 4) |
| front-running an execution | executions carry a limit price; crossing executes deterministically; buy-outs are recipient-bound |
| a hostile or reverting receiver | nothing to block: payouts are credits, claimed by the creditor (S15) |
| dust funding from thousands of addresses | nothing to jam: no transition iterates over funders; each funder claims its own refund (S15) |
| appealing through the wrapper without the host's crowdfunding | impossible: only the host may appeal (S18) |
| waiting for a lapse instead of conceding | unreachable while the case is insured and the resolver accepts disputes (S13); an under-insured case is disclosed at creation |
| starving a case of coverage to force a lapse | anyone may fund it during the funding period; the party who prefers court funds it |
| a resolver that rejects a correctly funded dispute | retried by anyone; after the grace period the disclosed emergency, so no case is stranded |
| draining a shared reserve from another host | no shared reserve: one wrapper per host (S17) |
| withdrawing the reserve while old requests can still be challenged | impossible: retirement, a lock at least the host's challenge period, and no open case first (S19) |
| turning surplus into revenue | impossible: surplus leaves only to a successor of the same factory (S11) |
| a host pointed at an unregistered epoch | requests fail at the first attempt, never at a challenge; self-inflicted when the list governor is the wrapper governor |
| first-block concession before the ask is set | absent in 1a; accepted in 1b; section 6 |
| Sybil on both sides | every transfer internal; nothing pending is protected beyond S12, and capacity only by the premium |

## 9. Passivity

| who acts | mode | outcome | versus today |
|---|---|---|---|
| nobody | insured | court after the window, created by the interested party or anyone | same, one window later |
| nobody | under-insured | court if free reserve or funding covers the resolver at forwarding; otherwise refusal after the funding period, disclosed at creation | the wrapper's governance failure; the reserve exists to make it unreachable |
| A with a wrong claim concedes, B silent | any | A nets −(D + π); the fee less the premium returns to A | cheaper for A by the fee less the premium, same for B, no jurors |
| B lowers the ask, A concedes (1b) | any | A nets between −(D + π) and −(D + π + ask) | better for both |
| A with a good claim escalates | insured | court now | identical to today |
| a removal is challenged | any | forwarded to court in the challenge transaction by the router, else by anyone | identical to today with a router; one extra transaction without |
| the resolver rejects a funded dispute | any | retried by anyone; refusal only after the grace period | today the challenge transaction itself would have failed |

## 10. Governance and adoption

Kleros governance executes on Ethereum through the Governor's optimistic list; the Gnosis court and the Scout lists are governed by Safes; Kleros V2's core is governed by an externally owned account today. Arbitration fees in both versions go only to coherent jurors, so no treasury constituency is affected. From the court's side, removing pointless cases raises the quality of the remainder and lowers the cost of using the system. UMA's oracle splits a loser's bond between the winner and UMA's store, so its tokenholders are paid by volume and a market venue is the right counterparty there, with concession preserving the store's share.

Adopting the wrapper is one transaction by a list's governor: point the list at a wrapper deployed for it, with an envelope naming a registered epoch. The wrapper's governor is that same governor, so the list's users gain no new trusted party, and the wrapper is a plain contract that nobody can upgrade. What that governor newly holds is disclosed: the power to register epochs, without which the list cannot accept requests; the duty to keep the reserve at target, without which cases open under-insured; and after retirement, and only then, the return of its own principal under two locks. It holds nothing over an open case and never takes the surplus.

## 11. Roadmap

The stage-1 state machine, its validated structured data and CI are committed with this version. Next: a reference model executed from the fixtures, and the adversarial traces of the specification's section 14 run against it, at minimum the removal never forwarded in both modes, the request crossing epochs, the announced fee increase at each level, lapse against a funded case at the end of the funding period, a bid crossing a lowered ask, an escalation racing an execution, a resolver rejecting before and after the grace period, resolver reverts, a reverting receiver, a second wallet around a live offer, capacity occupation by self-challenge at zero and nonzero premium, dust funders and partial funder refunds, an outside appeal, twenty insured cases crossing one fee increase, a withdrawal announced across case activity, and each supported refusal branch; then the contract skeleton; blind reviews of both documents; the resolver evidence display, tested with a silent party; the stage-1a pilot on our own list with the metrics of section 5 and a reserve funded beyond the number of cases it can hold; a KIP asking the Scout lists' governor to re-point the lists; in parallel, the arbitrable-side module and independent removal prosecution in the host. A standard is written after two systems run it.

## 12. What changed from v0.7, and why

| from | to | reason |
|---|---|---|
| insurance capacity free to occupy; reserve health counting earmarks twice; surplus withdrawable | a capacity premium per epoch, zero in the pilot (S4, S11); health as total reserve against liability; principal and surplus as separate accounts, surplus never revenue; earmark-hours as a pilot metric | v0.7 review findings 1 and 7 |
| the reserve withdrawable with no open case | retirement before any reserve movement, a lock at least the host's challenge period, announce, cancel, execute (S19) | finding 2 |
| funder refunds paid one by one at finalization | one stored fraction, claimed lazily; no transition grows with funders or cases (S15) | finding 3 |
| an appeal path open to anyone | host-only appeals (S18) | finding 4 |
| passivity promised unconditionally | passivity by mode, insured or under-insured, disclosed at creation (S1, R3); removals as the requester's interest, bundled with the challenge by a router | finding 5 |
| a covered case with a rejecting resolver stranded | a recorded failure, a grace period, then the emergency (S13); the environmental assumptions named | finding 6 |
| a false exclusivity invariant; events missing on crossings; a hand-checked renderer | requester escalation before the deadline only; conditional events; `validate`, `diagram`, full fixtures, CI | finding 8 |
| unbounded repeated concessions on an oracle front; a reentrancy left implicit; an empirical claim | per-question bounds; the callback chain stated; the claim removed | finding 9 |
| a wrapper assumed non-upgradeable; an ask after the deadline called an offer; one license for code and text | non-upgradeability stated (S17); an executable quote; MIT for code, CC BY for documents | the review's cleanups |

## Glossary

**Claim** the assertion under challenge. **Court loss, court gain** what a party pays or receives per resolver outcome. **Ceiling** the unilateral exit price, the exiting party's court loss. **Fee share** the layer's price unit, the part of the held fee that goes to the challenger on a concession. **Premium** the part of the held fee the pool keeps on a settled case, the price of occupying insurance capacity. **Offer** a binding standing fee share posted before the deadline: an ask persists, a bid expires. **Executable quote** a set ask after the deadline: still executable, no longer binding anyone's escalation. **Window** the period after a challenge before the deadline. **Deadline** the end of the window, when offers have ended and anyone may create the dispute. **Funding period** the period after the deadline during which anyone may store money for a case. **Epoch** a registered quote with its real extra data, premium and insured maximum. **Envelope** the list's extra data: version, epoch, real extra data. **Margin** the amount by which a quote exceeds the resolver's cost at epoch creation. **Earmark** the part of the reserve set aside for one case at creation. **Mode** insured or under-insured, decided at creation by whether the earmark is full. **Principal** the governor's reserve deposits, returnable after retirement and the locks. **Surplus** everything else in the reserve, never revenue. **Retirement** the governor's declaration that the instance takes no new epochs, starting the lock before principal or surplus can move. **Router** a contract that bundles a host challenge with the wrapper's next move. **Credit** money a party or funder may claim from the layer. **Restart** the return of a claim to a full review period. **Emergency lapse** the disclosed failure path when a cost beyond the insured maximum goes unfunded, or a resolver rejects a funded dispute for a grace period.
