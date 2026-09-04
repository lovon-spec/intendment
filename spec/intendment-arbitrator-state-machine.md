# IntendmentArbitrator: state machine and accounting

Specification 0.3, 2026-09-04. Normative for stage 1 of `../docs/intendment-design-v0.7.md`: the arbitrator-level wrapper over an ERC-792 arbitrator (Kleros V1), delivering concession on registration requests and forwarding everything else. Stage 1a deploys it with offers disabled (one price: concede or court); stage 1b enables asks and bids. Supersedes 0.2 after the GPT review of design v0.6 (`../docs/intendment-design-v0.6-review-gpt.md`); section 15 lists what changed. The transition, reserve and invariant tables in section 5 are generated from `intendment-arbitrator-state-machine.yaml` by `render.py`; `render.py check` fails when they drift. Adversarial traces and reviews run against this document; it is written to be attacked. Differences for `IArbitratorV2` are in section 13.

## 1. Actors and roles

| actor | how the wrapper knows it |
|---|---|
| **host** | one arbitrable per wrapper, fixed at deployment (`HOST`); the only address that may call `createDispute` |
| **requester A**, **challenger B** | resolved through the host profile after binding (section 4) |
| **real arbitrator K** | fixed at deployment (for the Gnosis pilot: xKlerosLiquid) |
| **wrapper governor** | registers quote epochs and may withdraw free reserve when no case is open; can do nothing to an open case; for the pilot, the list's own governor |
| **funder** | anyone who stores money for one case during its funding period |
| **anyone** | may bind, forward, escalate after the deadline, fund, lapse, or claim its own credits |

The wrapper holds, per case, the challenger's fee `q` from `createDispute` until the case ends, plus an earmark from the reserve; the reserve itself is governor- and margin-funded and is not case money. It never holds deposits and never reads them: its prices are shares of the held fee, which is what makes a concession expressible as a ruling plus a fee split and keeps every deposit rule of the host out of the wrapper's accounting.

One wrapper serves one host. A factory deploys a wrapper per list with the list's governor as wrapper governor, so that adopting the wrapper creates no new trusted party and no reserve is shared between lists. A multi-host variant with an explicit allowlist is possible later and must isolate reserves per host.

## 2. Quote epochs and the envelope

A list's `arbitratorExtraData` is an envelope, `abi.encode(uint8 version, uint32 epochId, bytes realExtraData)`. The wrapper decodes it in `arbitrationCost`, `createDispute`, `appealCost` and `appeal`; it requires `version == 1`, a registered epoch, and `realExtraData` equal to the epoch's registered value. It forwards the epoch's registered real extra data to K, never the envelope. Nothing depends on K ignoring trailing bytes.

An epoch is registered once by the governor (G1) and never changed: `quote = kCostAtRegistration × (10000 + marginBps) / 10000`, with `kCostAtRegistration = K.arbitrationCost(realExtraData)` at registration, `marginBps ≤ MAX_MARGIN_BPS` (a deployment constant), and a declared `maxCost ≥ quote`, the highest K cost the epoch insures. To change the price or the court the governor registers a new epoch and the list's governor points the list at the new envelope.

`arbitrationCost(extraData)` returns the quote and reverts for an unknown epoch or version. That revert is the one liveness power the wrapper governor holds over the host: a list pointed at an unregistered envelope cannot accept requests until the epoch exists. With the list governor as wrapper governor it is self-inflicted and visible at the first request, never at a challenge.

Hosts store the extra data with each request and use it for both the request-time and the challenge-time fee (verified for Light GTCR and Curate V2), so F_A = F_B = `q` for every case the wrapper receives. A request created before a list switched its arbitrator keeps its old arbitrator and never reaches the wrapper.

## 3. The reserve

The reserve is the wrapper's balance beyond escrowed fees, earmarks, case credits and claimable credits: the **free** balance. It exists because the quote is a fixed price: the challenger's economic fee on a forwarded case is `q` whatever K charges at forwarding, and the reserve absorbs the difference in either direction (I11).

| rule | statement |
|---|---|
| earmark | at T1 the case is assigned `earmark = min(maxCost − q, free)`. A case whose earmark is the full `maxCost − q` is **insured**: it is covered for every K cost up to `maxCost`. A short earmark is disclosed by `UnderInsured` in the same transaction, so the challenger learns it as they challenge. Earmarks are released to free when the case ends. |
| never a refusal | T1 does not depend on the reserve. A thin reserve produces under-insured cases, never a failed challenge (I10). |
| draw order | at forwarding K's cost is paid from the fee, then the earmark, then free, then case credit. Free is a shared second tier; when it is thin, forwarding order decides who uses it, which is exactly the under-reserved condition the governor is meant to prevent. |
| inflow | on every forwarded case `q − c`, if positive, goes to free; on every settlement the whole fee goes to the parties and nothing to the reserve. The margin is a premium paid only by cases that reach court. |
| target | `free ≥ Σ (maxCost − q) over open cases + floor`; a wrapper below target opens under-insured cases. The pilot funds the reserve for more open cases than it can have. |
| cap and excess | `marginBps` is capped in code; the design asks the governor to lower the margin, down to zero, when free exceeds target. |
| withdrawal | G3 only when no case is `Unbound`, `Open` or `Forwardable`, after `RESERVE_TIMELOCK` from an announcement, and only from free. No withdrawal ever touches an escrow, an earmark or a credit. |

## 4. Case data and the host profile

| field | set at | meaning |
|---|---|---|
| `epochId`, `choices` | create | from the envelope and the host's call |
| `fee` | create | `msg.value`, equal to the quote `q` |
| `createdAt`, `deadline = createdAt + W`, `fundingEnd = deadline + G` | create | the window and the funding period |
| `earmark` | create | section 3 |
| `kind` | bind | `Registration` or `Removal` |
| `requester`, `challenger` | bind | resolved addresses |
| `ask`, `askSet` | offers | B's concession price as a fee share; starts at 0, may be raised once to at most `q`, then only lowered (stage 1b) |
| `bid`, `bidValidUntil` | offers | A's live bid, a fee share, and its expiry (stage 1b) |
| `credit`, per funder | funding | money stored for this case by T10 |
| `state` | `Unbound` | one of `Unbound`, `Open`, `Forwardable`, `Forwarded`, `Conceded`, `Lapsed` |
| `kDisputeID` | forward | K's dispute id |

The **host profile** is the code, fixed at deployment, that answers from the host's public getters: the item behind a local dispute id, the request's kind, its requester and challenger, and which ruling value means "the challenger wins". It is read only after the host has stored its dispute mapping, which happens after `createDispute` returns; that is why T2 is a separate step. A wrong profile authorizes the wrong address; it is immutable per deployment. The profile needs no deposit, and the wrapper asks for none (I7). Section 14 lists the supported profiles.

## 5. Transitions

Notation: `q` the escrow, `c` K's cost at forwarding, `x` a fee share, `W` the window, `G` the funding period, `V` the minimum validity of a bid; `covered(id)` is `c ≤ fee + earmark + free + credit`, evaluated when a transition runs.

<!-- generated:begin -->
| id | from | move | who | precondition | money | to | stage |
|---|---|---|---|---|---|---|---|
| T1 | — | `createDispute(choices, extraData) payable` | the host, fixed at deployment | msg.sender == HOST; the envelope decodes to a registered epoch and msg.value == its quote; never conditioned on the reserve | escrow fee = msg.value; earmark = min(maxCost - q, free); UnderInsured if short | `Unbound` | 1a |
| T2 | `Unbound` | `bind(id)` | anyone; implied by the first party move | the host has stored its dispute mapping for id | — | `Open`, `Forwardable` | 1a |
| T3 | `Forwardable` | `forward(id)` | anyone; the challenger's interest | covered(id) | c to K from fee, then earmark, then free, then credit; fee - c, if positive, to free; unused earmark to free; unused credit to its funders' claimable | `Forwarded` | 1a |
| T4 | `Open` | `setAsk(id, x)` | challenger | now < deadline; first call 0 <= x <= q; later calls x < ask | none; if a live bid >= x exists, executes T7 at the bid | `Open`, `Conceded` | 1b |
| T5 | `Open` | `concede(id, maxShare)` | requester | ask <= maxShare | claimable A += q - ask; claimable B += ask; earmark to free; then host.rule(id, CHALLENGER_WINS) | `Conceded` | 1a |
| T6 | `Open` | `bid(id, x, validUntil)` | requester | now < deadline; x > highest bid so far; x <= q; validUntil >= now + V; validUntil <= deadline | none; if x >= ask, executes T5 at the ask | `Open`, `Conceded` | 1b |
| T7 | `Open` | `acceptBid(id, minShare)` | challenger | bid live; bid >= minShare | claimable A += q - bid; claimable B += bid; earmark to free; then host.rule(id, CHALLENGER_WINS) | `Conceded` | 1b |
| T8 | `Open` | `escalate(id)` | requester | no live bid; covered(id) | as T3 | `Forwarded` | 1a |
| T9 | `Open` | `escalate(id)` | anyone, the challenger included | now >= deadline, so no offer is live; covered(id) | as T3 | `Forwarded` | 1a |
| T10 | `Open`, `Forwardable` | `fund(id) payable` | anyone | now < fundingEnd | credit += msg.value, recorded per funder | `Open`, `Forwardable` | 1a |
| T11 | `Open`, `Forwardable` | `lapse(id)` | anyone | now >= fundingEnd; not covered(id) | claimable B += q; each funder's claimable += its credit; earmark to free; then host.rule(id, REFUSE) | `Lapsed` | 1a |
| T12 | `Forwarded` | `rule(kDisputeID, ruling)` | K only | at most once per K ruling | none held; host.rule(id, ruling) | `Forwarded` | 1a |
| T13 | `Forwarded` | `appeal(id, extraData) payable` | anyone, as on K; the host's appeal crowdfunding | K's appeal period open | msg.value to K.appeal(kDisputeID, epoch real extra data) in the same transaction | `Forwarded` | 1a |
| T14 | `Unbound`, `Open`, `Forwardable`, `Forwarded`, `Conceded`, `Lapsed` | `claim(to)` | any creditor, for its own claimable balance | claimable[msg.sender] > 0 | claimable[msg.sender] to `to`; the only value transfer to a party in the contract | `Unbound`, `Open`, `Forwardable`, `Forwarded`, `Conceded`, `Lapsed` | 1a |

| id | move | who | precondition | effect |
|---|---|---|---|---|
| G1 | `registerEpoch(realExtraData, marginBps, maxCost)` | governor | marginBps <= MAX_MARGIN_BPS; maxCost >= quote | quote = K.arbitrationCost(realExtraData) * (10000 + marginBps) / 10000, fixed forever; emits the epoch's MetaEvidence pair |
| G2 | `fundReserve() payable` | anyone | — | free += msg.value |
| G3 | `withdrawReserve(amount, to)` | governor | no case in Unbound, Open, Forwardable; announced RESERVE_TIMELOCK earlier; amount <= free | free -= amount; paid to `to` |

| id | invariant | statement |
|---|---|---|
| I1 | conservation | balance == sum of open fees + sum of earmarks + sum of case credits + sum of claimable + free, after every transition |
| I2 | one-time finalization | exactly one of T3, T5, T7, T8, T9, T11 executes per case; T12 at most once per K ruling |
| I3 | quote stability | F_A == F_B == q for every case of an epoch; a quote never changes after registration |
| I4 | no holdup | the requester can always execute T5 at the current ask before forwarding; the ask is set at most once upward and then only falls |
| I5 | case-level offer binding | a live bid blocks T8; no offer is live at or after the deadline; T9 needs no offer check because none can exist |
| I6 | passivity | a silent challenger is conceded to at x = 0; a silent requester reaches court at the deadline through T9; a silent removal is forwarded by anyone |
| I7 | deposit neutrality | the wrapper never reads, holds or moves a deposit; its prices are fee shares |
| I8 | emergency isolation | T11 is unreachable while covered(id); an insured case is covered for every c <= maxCost |
| I9 | failure-safe payouts | no transition other than T14 transfers value to a party; a reverting receiver cannot block any transition |
| I10 | no refusal of challenges | T1 reverts only for a wrong sender, an unregistered epoch or a wrong value, never for the state of the reserve |
| I11 | fixed price | the challenger's economic fee on every forwarded case is q; the reserve absorbs q - c in either direction |
| I12 | exclusivity at fundingEnd | for now >= fundingEnd, exactly one of the escalation transitions (T3, T8, T9) or T11 has a satisfiable precondition at any instant, since they test opposite values of covered(id) |
<!-- generated:end -->

**Ordering inside a transition.** State is written before any external call. T5 and T7 write `Conceded`, credit, release the earmark, then call the host's `rule` with the profile's "challenger wins" value. T11 writes `Lapsed`, credits, then calls `rule` with 0. T3, T8 and T9 write `Forwarded`, call K's `createDispute`, store `kDisputeID`, then emit the ERC-1497 `Dispute` event (section 9). No transition other than T14 sends value to a party; a host or K call that reverts reverts the transition, and the case stays where it was.

**Offer lifecycle (stage 1b).** An offer is a fee share posted before the deadline. An **ask** is B's price: the default 0 is not an offer and binds nobody; B may raise it once, to at most `q`, then only lower it; a set ask persists as an executable price until the case ends and never rises (I4). A **bid** is A's price with a validity of at least `V` that ends no later than the deadline; it is live while `now < validUntil`, so none is live at the deadline instant; while it is live, B may execute it and A cannot escalate (I5); at expiry it is gone. Neither can be posted at or after the deadline, so no offer is live once T9 opens, and the permissionless path needs no offer check: binding is a property of the case, not of a sender address. Crossing is deterministic: an ask set at or below the live bid executes as an acceptance at the bid; a bid at or above the ask executes as a concession at the ask. Executions carry a limit (`maxShare`, `minShare`) rather than an exact price, since asks only fall and bids only rise, a price moving in the counterparty's favor should not fail the transaction.

**Funding period.** From creation until `fundingEnd`, anyone may store money for a case (T10). Escalation is never payable; a shortfall is funded first, then escalated by anyone whose transition is otherwise valid. From `fundingEnd` on, `escalate` and `lapse` test opposite values of `covered(id)`, so exactly one of them is available at any instant (I12): a funded escalation cannot be front-run by a lapse, and a lapse cannot be pre-empted by money arriving in the same transaction. K's cost can still move after `fundingEnd`; the predicates follow it.

## 6. Net payouts

Prices are fee shares `x ∈ [0, q]`; the requester's net loss on a concession is `D + x`, the design's `Y`. On a concession at `x` the host, on the challenger ruling, pays its pot `P = D + q + D_c` to B. The wrapper then credits:

| to | amount |
|---|---|
| A | `q − x` |
| B | `x` |

Sum `q`, the escrow. Net results: A `−(D + x)`, B `+(D + x)`. At the default `x = 0` A recovers the whole fee and B receives the pot, A's court loss less the fee. At the ceiling `x = q` A's result equals a lost court case. The wrapper needs no deposit to compute either.

Court outcomes on a forwarded case, with the challenger's fee fixed at `q` (I11): A loses `s_A = D + q` or gains `g_A = D_c`; B loses `s_B = q + D_c` or gains `g_B = D`. On a refusal ruling Light GTCR and Curate V2 halve the pot: A nets `−(D + q − D_c)/2`, B nets `(D − q − D_c)/2`; Classic distributes the pot by recorded contributions. In every court outcome the parties jointly lose exactly `q`, whatever the distribution rule, because the whole pot returns to them and K's fee is the only leak; the reserve, not a party, carries `q − c`.

On emergency lapse the wrapper credits B with `q` and funders with their credits, and the host applies its refusal distribution. On Light with `D_c = 0` this pays B half of `D + q` without a merits ruling and costs A the same; that is why T11 is reachable only above `maxCost` for an insured case, and only after the funding period, and is disclosed as a governance failure.

## 7. Views

| view | `Unbound` | `Open` / `Forwardable` | `Forwarded` | `Conceded` / `Lapsed` |
|---|---|---|---|---|
| `arbitrationCost(extraData)` | the quote | the quote | the quote | the quote |
| `disputeStatus(id)` | `Waiting` | `Waiting` | K's status | `Solved` |
| `currentRuling(id)` | 0 | 0 | K's ruling | the delivered ruling |
| `appealCost`, `appealPeriod` | revert | revert | K's values | revert |
| `caseOf(id)` | the case record of section 4 | same | same | same |
| `claimable(addr)`, `free()`, `epoch(epochId)` | the accounting of sections 3 and 4 | same | same | same |

## 8. Events

One event per transition, so that list UIs, wallets, indexers and keepers integrate once: `EpochRegistered(epochId, quote, maxCost, realExtraData)`, `CaseOpened(id, epochId, fee, deadline, fundingEnd, earmark)`, `UnderInsured(id, shortfall)`, `CaseBound(id, kind, requester, challenger)`, `AskSet(id, share)`, `BidPosted(id, share, validUntil)`, `Settled(id, share, requesterCredit, challengerCredit)`, `Escalated(id, kDisputeID, kCost, by)`, `Funded(id, funder, amount)`, `Lapsed(id)`, `Claimed(creditor, to, amount)`, `ReserveFunded(from, amount)`, `ReserveWithdrawn(to, amount)`, plus the ERC-792 `Dispute` and ERC-1497 events toward K.

## 9. Meta-evidence and evidence

Toward K the wrapper is the arbitrable. At T3, T8 and T9 it emits `Dispute(K, kDisputeID, metaEvidenceID, evidenceGroupID)`; the meta-evidence, one per epoch and request kind, is emitted at G1 and carries an evidence display interface and dynamic script that resolve the wrapper-to-host mapping from `kDisputeID` and render the host's original request evidence, challenge evidence and later submissions from the host's own events. No party has to resubmit anything; a silent party's evidence reaches jurors. The display is part of the deployment and is tested with a silent party before the pilot (design S9). The wrapper offers no evidence relay function.

## 10. Invariants

The invariant table is generated with the transitions in section 5 (I1–I12).

## 11. The first-block race, stated (stage 1b)

`ask` starts at 0 and B may raise it once. A requester who concedes before B's `setAsk` lands pays only the deposit. This favors the requester in the first moments after a challenge; a challenger who wants a fee share bundles the challenge and `setAsk` through a router. Accepted and documented; stage 1a has no asks and no race; the arbitrable-side module carries the ask in the challenge.

## 12. Adversarial traces to write

A removal challenged after adoption and never forwarded; a request whose challenge arrives after a new epoch is registered; an announced K fee increase within the margin, beyond it within `maxCost`, and beyond `maxCost` with and without funders; `lapse` against a funded case at `fundingEnd`; a bid crossing a lowered ask in one block; an escalation racing an execution; K reverting at forwarding; the host's `rule` reverting on T5 or T11; a profile returning the zero address; a party that is a contract rejecting a transfer; reentry from the host's `rule` into T5 or T14; a second wallet of an offer's owner calling T9; two wrappers over one list; a list switching arbitrators with cases `Open`; a governor withdrawing while a case is `Unbound`; twenty insured cases crossing one fee increase; an under-insured case whose shortfall nobody funds.

## 13. Differences for `IArbitratorV2`

The ERC-20 `createDispute` variant is refused; ruling delivery is the same callback; `DisputeRequest` with a template id replaces the V1 `Dispute` event, and the profile supplies the template id; appeals live in dispute kits and are funded through K directly, so T13 is absent; the wrapper needs whitelisting by KlerosCore's governor before it can create disputes.

## 14. Host profiles

| profile | item and request | kind | parties | challenger wins | refusal | pot |
|---|---|---|---|---|---|---|
| Light GTCR (the Scout lists) | `arbitratorDisputeIDToItemID(wrapper, id)`, then `getItemInfo` for the request count and `getRequestInfo(item, count − 1)` | `getItemInfo(item).status`: `RegistrationRequested` or `ClearingRequested` | `parties[1]`, `parties[2]` of `getRequestInfo` | ruling 2 | ruling 0: the pot halved, the item returns to its prior status | `sumDeposit = D + q + D_c`, paid by `send` |
| Classic GTCR | `arbitratorDisputeIDToItemID`, `getRequestInfo` | the item status at bind | `parties[1]`, `parties[2]` | ruling 2 | ruling 0: the pot by recorded contributions | round 0 `feeRewards`, withdrawn by the parties |
| Curate V2 (later, section 13) | as Light | as Light | as Light | ruling 2 | ruling 0: halved | `sumDeposit`, paid by `send` |

A profile states what the wrapper relies on and nothing more: no deposit amounts, no fee history, no evidence. Hosts that push payouts with `send` swallow a failed transfer on their own side; that is the host's behavior today and not the wrapper's concern.

## 15. What changed from 0.2

| from | to | reason |
|---|---|---|
| surplus of the fee over K's cost returned to B; reserve "replenished from margins" | fixed price: B always bears `q`; `q − c` to or from the reserve; the reserve's target, cap, earmark and withdrawal rules stated | GPT review of v0.6, finding 1 |
| offer binding checked on the sender; T10 open to anyone after `W` regardless | binding as a property of the case: offers end at the deadline, the permissionless path opens only then; limit prices; deterministic crossing; asks persist, bids expire | finding 2 |
| funding only inside `escalate`; lapse racing a funded escalation | T10 `fund` until `fundingEnd`; `escalate` non-payable; `escalate` and `lapse` exclusive by `covered(id)` | finding 3 |
| a shared, permissionless-host reserve; the resolver reading the host's current base deposit; an appended epoch word | one wrapper per host from a factory; prices as fee shares, no deposit read at all; an explicit envelope | finding 4, and the fee-share simplification |
| payouts pushed to the parties inside transitions | claimable credits and T14 `claim` | finding 5 |
| one stage 1 | stage 1a with offers disabled, 1b with offers | finding 6 |
| a prose table maintained by hand | the YAML source and `render.py check` | the machine-readable specification suggestion |
| `createDispute` silent about the reserve | I10: never refused for reserve state; under-insurance disclosed at creation | the maintainer's addition |
