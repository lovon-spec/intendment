# IntendmentArbitrator: state machine and accounting

Specification 0.2, 2026-09-04. Normative for stage 1 of `../docs/intendment-design-v0.6.md`: the arbitrator-level wrapper over an ERC-792 arbitrator (Kleros V1), delivering concession on registration requests and forwarding everything else. Adversarial traces and reviews run against this document; it is written to be attacked. Differences for `IArbitratorV2` are in section 11.

## 1. Actors and roles

| actor | how the wrapper knows it |
|---|---|
| **host** | the arbitrable that called `createDispute`; stored per case |
| **requester A**, **challenger B** | resolved through the host's party resolver after binding (section 3) |
| **real arbitrator K** | fixed at deployment (for the Gnosis pilot: xKlerosLiquid) |
| **wrapper governor** | registers quote epochs and funds the reserve; can do nothing to an open case |
| **anyone** | may bind, forward, create the dispute after the window, or trigger the emergency path |

The wrapper holds one party's money at a time: the challenger's fee F_B, from `createDispute` until concession, forwarding, or emergency lapse, plus a governor-funded reserve that is not case money. It never holds deposits; those stay in the host, which is what makes a concession expressible as a ruling plus a fee split.

## 2. Quote epochs

`arbitrationCost(extraData)` returns `quotes[keccak256(extraData)].price` and reverts for unregistered extra data. A quote is registered once by the governor and never changed: `price = kCostAtRegistration × (1 + m)`, with `kCostAtRegistration = K.arbitrationCost(extraData)` at registration and `m` the margin, a deployment constant. To change the price the governor registers a new extra-data value; Kleros reads only the leading court and juror fields of extra data, so an appended epoch word changes the key without changing the court.

Hosts store the extra data with each request and use it for both the request-time and the challenge-time fee (verified for Light GTCR and Curate V2), so F_A = F_B = `price` for every case the wrapper receives. A request created before a list switched its arbitrator keeps its old arbitrator and never reaches the wrapper.

## 3. Case data and the party resolver

| field | set at | meaning |
|---|---|---|
| `host`, `choices`, `extraData` | create | as passed by the host |
| `fee` | create | `msg.value`, which must equal the quote |
| `createdAt` | create | window start |
| `kind` | bind | `Registration` or `Removal` |
| `requester`, `challenger` | bind | resolved addresses |
| `ask` | bind | B's concession price; starts at `D`, the host's base deposit as reported by the resolver |
| `askSet` | false | whether B has set the ask once |
| `askValidUntil`, `bid`, `bidValidUntil` | offers | live offers and their validity |
| `state` | `Unbound` | one of `Unbound`, `Open`, `Forwardable`, `Conceded`, `Forwarded`, `Lapsed` |
| `kDisputeID` | forward | K's dispute id |

The resolver is a per-host-type contract, fixed at wrapper deployment, that answers from the host's public getters: the item behind a local dispute id, the request's kind, its requester and challenger, the host's base deposit for that request type, and which ruling value means "the challenger wins." It is read only after the host has stored its dispute mapping, which happens after `createDispute` returns. A wrong resolver authorizes the wrong address; it is immutable per deployment.

## 4. Transitions

Notation: `fee` is the escrow, `Y` a concession price, `P = D + F_A + D_c` the host's pot, `W` the window, `V` the minimum offer validity, `G` the grace period.

| id | from | move | who | precondition | money | to |
|---|---|---|---|---|---|---|
| T1 | — | `createDispute(choices, extraData)` payable | host | `msg.value == quote(extraData)` | escrow `fee` | `Unbound` |
| T2 | `Unbound` | `bind(id)` | anyone; implied by T3–T7 | the host has stored the mapping | none | `Open` if registration, `Forwardable` if removal |
| T3 | `Forwardable` | `forward(id)` | anyone; the challenger's interest | — | K's current cost from `fee`, then reserve, then `msg.value`; surplus of `fee` over K's cost returned to B | `Forwarded` |
| T4 | `Open` | `setAsk(id, Y, validity)` | challenger | first call any `D ≤ Y ≤ s_A`; later calls strictly lower; `validity ≥ V` | none | `Open` |
| T5 | `Open` | `concede(id, expectedY)` | requester | `expectedY == ask` (or `== s_A` for the ceiling) | section 5 | `Conceded` |
| T6 | `Open` | `bid(id, Y, validity)` | requester | `Y` strictly higher than the current bid; `Y ≤ ask`; `validity ≥ V` | none | `Open` |
| T7 | `Open` | `acceptBid(id, expectedY)` | challenger | bid live; `expectedY == bid` | section 5 with `Y = bid` | `Conceded` |
| T8 | `Open` | `escalate(id)` | requester | no live bid of A's | as T3 | `Forwarded` |
| T9 | `Open` | `escalate(id)` | challenger | `now ≥ createdAt + W`; no live ask of B's below the ceiling within its validity | as T3 | `Forwarded` |
| T10 | `Open` | `escalate(id)` | anyone | `now ≥ createdAt + W` | as T3 | `Forwarded` |
| T11 | `Open` or `Forwardable` | `lapse(id)` | anyone | `now ≥ createdAt + W + G`; K's current cost exceeds `fee` plus the reserve; no funder has topped up | refund `fee` to B | `Lapsed` |
| T12 | `Forwarded` | `rule(kDisputeID, ruling)` | K only | — | none held | `Forwarded`, ruled |
| T13 | `Forwarded` | `appeal(id, extraData)` payable | anyone, as on K | K's appeal period open | forwarded to K in the same transaction | `Forwarded` |

Ordering inside a transition: state is written before any external call. T5 and T7 write `Conceded`, pay, then call the host's `rule` with the resolver's "challenger wins" value. T11 writes `Lapsed`, refunds, then calls `rule` with 0. T3 and T8–T10 write `Forwarded`, call K's `createDispute`, store `kDisputeID`, then emit the ERC-1497 `Dispute` event (section 7).

**Offers and escalation.** An ask set by B is an offer with validity; while it is live B cannot escalate (T9). A bid posted by A is an offer with validity; while it is live A cannot escalate (T8). Either side may always escalate to reject the other's offer, subject to the window for B. A live offer cannot be withdrawn; it lapses at its validity or is executed. The default ask at `D` is not an offer of B's: it binds nobody's escalation, which is why a silent B can still be conceded to.

**Funding order at escalation.** K's cost at that moment is paid first from `fee`, then from the reserve, then from the caller's `msg.value`; a caller's contribution is repaid from the surplus if K's cost later proves lower, never from the host's pot, and is otherwise a recorded donation. If the reserve is empty and no caller funds it within `G`, T11 is the only remaining transition.

## 5. Net payouts

On a concession at price `Y`, the host, on the challenger ruling, pays its pot `P` to B directly. The wrapper then pays:

| to | amount |
|---|---|
| A | `D + F_A − Y` |
| B | `F_B − (D + F_A − Y)` |

Sum `F_B`, the escrow. Expressible interval `D + F_A − F_B ≤ Y ≤ D + F_A`, which under section 2 is `[D, s_A]`. Net results: A `−Y`, B `+Y` (B paid `F_B` and receives `P` plus the wrapper's part).

For every ruling on a forwarded case the wrapper holds nothing but a possible surplus of `fee` over K's cost, returned to B at forwarding; net court outcomes are the host's, with B bearing K's fee: A loses `s_A = D + F_A` or gains `D_c`; B loses `F_E + D_c` or gains `D + F_A − F_E`.

On emergency lapse the wrapper refunds `F_B` to B and the host applies its refusal distribution: Light GTCR and Curate V2 split `P` in half; Classic distributes `P` by recorded contributions. On Light with `D_c = 0` this pays B `(D + F_A)/2` without a merits ruling; that is why T11 is reachable only after the reserve is exhausted and is disclosed as a governance failure.

## 6. Views

| view | `Unbound` | `Open` / `Forwardable` | `Forwarded` | `Conceded` / `Lapsed` |
|---|---|---|---|---|
| `arbitrationCost(extraData)` | the quote | the quote | the quote | the quote |
| `disputeStatus(id)` | `Waiting` | `Waiting` | K's status | `Solved` |
| `currentRuling(id)` | 0 | 0 | K's ruling | the delivered ruling |
| `appealCost`, `appealPeriod` | revert | revert | K's values | revert |

## 7. Meta-evidence and evidence

Toward K the wrapper is the arbitrable. At T3 and T8–T10 it emits `Dispute(K, kDisputeID, metaEvidenceID, evidenceGroupID)`; the meta-evidence, one per registered extra data and request kind, is emitted at quote registration and carries an evidence display interface and dynamic script that resolve the wrapper-to-host mapping from `kDisputeID` and render the host's original request evidence, challenge evidence and later submissions from the host's own events. No party has to resubmit anything; a silent party's evidence reaches jurors. The display is part of the deployment and is tested with a silent party before the pilot (design S9). The wrapper offers no evidence relay function.

## 8. Invariants

1. **Conservation.** Per case the wrapper's attributable balance is `fee` from T1 until T3, T5, T7, T8–T10 or T11, each of which pays out exactly `fee` plus any recorded caller contribution; appeals pass through.
2. **One-time finalization.** Exactly one of T3, T5, T7, T8–T10, T11 executes per case; T12 at most once per K ruling.
3. **Quote stability.** `F_A = F_B` for every case, by section 2.
4. **No holdup.** A concession at the current ask is always executable by A before forwarding; asks only fall after being set; A's worst case is the ask as set, never higher.
5. **Offer binding.** A live offer cannot be withdrawn and blocks its owner's escalation; the counterparty can execute it or reject it by escalating.
6. **Passivity.** A silent B is conceded to at `D`; a silent A reaches court at `W`; a silent removal is forwarded by anyone.
7. **Deposit neutrality.** The wrapper never touches the host's deposits (design S6).
8. **Emergency isolation.** T11 is unreachable while the reserve covers K's cost.

## 9. The first-block race, stated

`ask` starts at `D` and B may raise it once. A requester who concedes before B's `setAsk` lands pays `D`. This favors the requester in the first moments after a challenge; a challenger who wants a fee share bundles the challenge and `setAsk`. Accepted and documented; a challenge router, or the arbitrable-side module, removes it.

## 10. Adversarial traces to write

A removal challenged after adoption and never forwarded; a request whose challenge arrives after a new quote is registered; an announced K fee increase within the margin, and beyond it with an empty reserve; `lapse` racing a funded `escalate`; a bid crossing a lowered ask in one block; an escalation racing an execution; K reverting at forwarding; the host's `rule` reverting on T5 or T11; a resolver returning the zero address; a party that is a contract rejecting a transfer; reentry from the host's `rule` into T5; two wrappers over one list; a list switching arbitrators with cases `Open`.

## 11. Differences for `IArbitratorV2`

The ERC-20 `createDispute` variant is refused; ruling delivery is the same callback; `DisputeRequest` with a template id replaces the V1 `Dispute` event, and the resolver supplies the template id; appeals live in dispute kits and are funded through K directly; the wrapper needs whitelisting by KlerosCore's governor before it can create disputes.
