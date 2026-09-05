# IntendmentArbitrator: state machine and accounting

Specification 0.5, 2026-09-05. Normative for stage 1 of `../docs/intendment-design-v0.9.md`: the arbitrator-level wrapper over an ERC-792 arbitrator (Kleros V1), delivering concession on registration requests and forwarding everything else. Stage 1a deploys it with offers disabled (one price: concede or court); stage 1b enables asks and bids. Supersedes 0.4 after the GPT review of design v0.8 (`../docs/intendment-design-v0.8-review-gpt.md`); section 18 lists what changed. An executable model of stage 1a lives in `../sim/` and runs the traces of section 14 in CI. The transition, reserve-operation and invariant tables in section 5 are generated from `intendment-arbitrator-state-machine.yaml` by `render.py`; `render.py validate` checks the data and `render.py check` fails when the tables drift, both in CI. The YAML is structured specification data, not yet an executable model. Adversarial traces and reviews run against this document; it is written to be attacked. Differences for `IArbitratorV2` are in section 15.

## 1. Actors and roles

| actor | how the wrapper knows it |
|---|---|
| **host** | one arbitrable per wrapper, fixed at deployment (`HOST`); the only address that may call `createDispute` or `appeal` |
| **requester A**, **challenger B** | resolved through the host profile after binding (section 4) |
| **real arbitrator K** | fixed at deployment (for the Gnosis pilot: xKlerosLiquid) |
| **wrapper governor** | registers quote epochs while active, retires the wrapper, and after retirement withdraws principal or migrates surplus under the locks of section 3; can do nothing to an open case; for the pilot, the list's own governor |
| **funder** | anyone who stores money for one case during its funding period and later claims the unused part |
| **party of record** | the wallet the host recorded as requester or challenger, which is the wallet that called it; a contract that calls the host on a user's behalf becomes the party itself, so the wrapper never looks through it |
| **anyone** | may bind, forward, escalate after the deadline, fund, lapse, forward-or-lapse, or claim its own credits |

The wrapper holds, per case, the challenger's fee `q` from `createDispute` until the case ends, plus an earmark from the reserve and any case funding; the reserve itself is not case money. It never holds deposits and never reads them: its prices are shares of the held fee, which is what makes a concession expressible as a ruling plus a fee split and keeps every deposit rule of the host out of the wrapper's accounting.

One wrapper serves one host. A factory deploys a plain, non-upgradeable wrapper per list with the list's governor as wrapper governor, so that adopting the wrapper creates no new trusted party, no reserve is shared between lists, and no code path changes behavior after deployment except registered epochs and retirement (I16). A multi-host variant with an explicit allowlist is possible later and must isolate reserves per host.

## 2. Quote epochs and the envelope

A list's `arbitratorExtraData` is an envelope, `abi.encode(uint8 version, uint32 epochId, bytes realExtraData)`. The wrapper decodes it in `arbitrationCost`, `createDispute`, `appealCost` and `appeal`; it requires `version == 1`, a registered epoch, and `realExtraData` equal to the epoch's registered value. It forwards the epoch's registered real extra data to K, never the envelope. Nothing depends on K ignoring trailing bytes.

An epoch is registered once by the governor (G1) and never changed: `quote = kCostAtRegistration × (10000 + marginBps) / 10000`, with `kCostAtRegistration = K.arbitrationCost(realExtraData)` at registration, `marginBps ≤ MAX_MARGIN_BPS`, a declared `maxCost ≥ quote` (the highest K cost the epoch insures), and `premiumBps ≤ MAX_PREMIUM_BPS`, from which the capacity premium `π = quote × premiumBps / 10000` follows. To change any of them the governor registers a new epoch and the list's governor points the list at the new envelope. A retired wrapper registers no epochs.

`arbitrationCost(extraData)` returns the quote and reverts for an unknown epoch or version. That revert is the one liveness power the wrapper governor holds over the host: a list pointed at an unregistered envelope cannot accept requests until the epoch exists. With the list governor as wrapper governor it is self-inflicted and visible at the first request, never at a challenge.

Hosts store the extra data with each request and use it for both the request-time and the challenge-time fee (verified for Light GTCR and Curate V2), so F_A = F_B = `q` for every case the wrapper receives. A request created before a list switched its arbitrator keeps its old arbitrator and never reaches the wrapper; a request created under this wrapper reaches it even after the list has moved on, for as long as the request is challengeable, which is what the retirement lock is for.

## 3. The reserve

The reserve is the wrapper's balance beyond escrowed fees, unclaimed case funding and claimable credits. It exists because the quote is a fixed price: the challenger's economic fee on a forwarded case is `q` whatever K charges at forwarding, and the reserve absorbs the difference in either direction (I11). It has two accounts.

| account | in | out |
|---|---|---|
| **principal** | the governor's deposits (G2) | to the governor only after retirement, the retirement lock and the timelock, with no case open (G4 to G6) |
| **surplus** | `q − c` on every forwarded case where K cost less than the quote; the premium `π` on every settled case; anyone's gifts (G2 from a non-governor) | insurance draws, first; a successor wrapper of the same factory after retirement (G7); never a party, never revenue |

`reserve = principal + surplus`; `free = reserve − Σ earmarks`.

| rule | statement |
|---|---|
| earmark | at T1 the case is assigned `earmark = min(maxCost − q, free)`. A case whose earmark is the full `maxCost − q` is **insured**: it is covered for every K cost up to `maxCost`. A short earmark is disclosed by `UnderInsured` in the same transaction, so the challenger learns it as they challenge. Earmarks are released to free when the case ends. |
| never a refusal | T1 does not depend on the reserve. A thin reserve produces under-insured cases, never a failed challenge (I10). |
| draw order | at forwarding K's cost is paid from the fee, then the reserve draw, `min(c − q, earmark + free)`, then case funding. Free is a shared second tier; when it is thin, forwarding order decides who uses it, which is exactly the under-reserved condition the governor is meant to prevent. |
| loss waterfall | a reserve draw reduces surplus first and principal second (I19). Principal is capital at risk, not a nominal claim: what the governor can later withdraw is what is left, never what was deposited. |
| refund liability | when a case ends, `refundableAmount = totalFunding − fundingUsed` is stored, and each funder may claim `floor(contribution × refundableAmount / totalFunding)`. The unclaimed remainder, rounding included, is a liability for as long as the wrapper exists; it is never spendable (I18). A case with no funding stores zero. |
| health | `reserve ≥ Σ (maxCost − q) over open cases + floor`, equivalently `free ≥ the uncovered liability of open cases + floor`. Spare capacity for cases not yet opened is a separate number, not part of solvency. Requests already submitted under the wrapper but not yet challenged are a latent liability the wrapper cannot see; the governor monitors it off-chain from the host's events and sizes the floor for it. |
| capacity occupation | an open case occupies `maxCost − q` of capacity for its whole window, and a settlement between two wallets of one owner returns every coin, so capacity is free to occupy at `π = 0`. The premium prices it: a self-challenger pays `π` per case-window. The damage of occupation is bounded by the earmark size, which the governor sets through `maxCost`, and it bites only during a K fee increase. The pilot runs at `π = 0` as a disclosed subsidy with an over-funded reserve and measures earmark-hours; any reserve that is not the list governor's own money should carry a premium. |
| cap and excess | `marginBps` and `premiumBps` are capped in code; the design asks the governor to lower them, down to zero, when surplus exceeds the health target. Surplus is never withdrawn as revenue (I15). |
| retirement | three facts are kept apart. **Declared**: G3 marks the wrapper retired and stops new epochs. **Admission stopped**: the host no longer assigns the wrapper's epochs to new requests, which only the host's governor can do, by pointing the list elsewhere before G3. **Exposure exhausted**: no request submitted under the wrapper can still open a case, which the wrapper cannot observe, because a host's challenge period is a live setting its governor may raise and old requests would become challengeable again. Only the third fact justifies moving capital, so the pilot's procedure is: point the list elsewhere; retire; wait `RETIREMENT_LOCK`, a floor at least the host's challenge period at retirement plus a margin; confirm off-chain from the host's events that every request submitted under the wrapper has executed or resolved; and only then announce (G4), cancel if needed (G5), and execute after `RESERVE_TIMELOCK` (G6) or migrate surplus (G7). The lock is a floor, not the guarantee; the guarantee is the procedure plus the host-governance assumption of section 13. Switching a list from a stage-1a to a stage-1b wrapper is exactly this. |

## 4. Case data and the host profile

| field | set at | meaning |
|---|---|---|
| `epochId`, `choices` | create | from the envelope and the host's call |
| `fee` | create | `msg.value`, equal to the quote `q` |
| `createdAt`, `deadline = createdAt + W`, `fundingEnd = deadline + G` | create | the window and the funding period |
| `earmark` | create | section 3 |
| `kind` | bind | `Registration` or `Removal` |
| `requester`, `challenger` | bind | resolved addresses |
| `ask`, `askSet` | offers | B's concession price as a fee share; starts at 0, may be raised once to at most `q − π`, then only lowered (stage 1b) |
| `bid`, `bidValidUntil` | offers | A's live bid, a fee share, and its expiry (stage 1b) |
| `totalFunding`, `contribution[funder]` | funding | money stored for this case by T10 |
| `fundingUsed`, `refundableAmount`, `claimedFunding` | end | what forwarding consumed, what funders may claim back in total (T15), and what they have claimed |
| `firstForwardFailure` | forwarding | the first time K rejected a correctly funded, properly gassed forwarding attempt for this case, including a reverting quote, or 0 |
| `state` | `Unbound` | one of `Unbound`, `Open`, `Forwardable`, `Forwarded`, `Conceded`, `Lapsed` |
| `kDisputeID` | forward | K's dispute id |

The **host profile** is the code, fixed at deployment, that answers from the host's public getters: the item behind a local dispute id, the request's kind, its requester and challenger, which ruling value means "the challenger wins", and the host's challenge period for the retirement lock. It is read only after the host has stored its dispute mapping, which happens after `createDispute` returns; that is why T2 is a separate step. A wrong profile authorizes the wrong address; it is immutable per deployment. The profile needs no deposit, and the wrapper asks for none (I7). Section 16 lists the supported profiles.

## 5. Transitions

Notation: `q` the escrow, `π` the premium, `c` K's cost at forwarding, `x` a fee share, `W` the window, `G` the funding period, `V` the minimum validity of a bid; `covered(id)` is `quotable(id) and c ≤ fee + earmark + free + unused funding`, evaluated when a transition runs; `graceElapsed(id)` is `firstForwardFailure ≠ 0 and now ≥ firstForwardFailure + RESOLVER_GRACE`; a **qualifying failure** is a revert of K's quote or dispute creation in a call made with at least `MIN_FORWARD_GAS` available. A `?` after an event marks it conditional.

<!-- generated:begin -->
| id | from | move | who | precondition | money | to | events | stage |
|---|---|---|---|---|---|---|---|---|
| T1 | — | `createDispute(choices, extraData) payable` | the host, fixed at deployment | msg.sender == HOST; the envelope decodes to a registered epoch and msg.value == its quote; never conditioned on the reserve | escrow fee = msg.value; earmark = min(maxCost - q, free) | `Unbound` | CaseOpened, UnderInsured? | 1a |
| T2 | `Unbound` | `bind(id)` | anyone; implied by the first party move | the host has stored its dispute mapping for id | — | `Open`, `Forwardable` | CaseBound | 1a |
| T3 | `Forwardable` | `forward(id)` | anyone; the removal requester's interest; a second transaction after the challenge | covered(id) | c to K from fee, then the reserve draw, then funding; fundingUsed and refundableAmount recorded; fee - c, if positive, to surplus; unused earmark to free; on a qualifying failure nothing moves, firstForwardFailure is recorded if unset, and the case stays where it was | `Forwarded` | Escalated, ForwardFailed? | 1a |
| T4 | `Open` | `setAsk(id, x)` | challenger | now < deadline; first call 0 <= x <= q - pi; later calls x < ask | none; if a live bid >= x exists, executes T7 at the bid | `Open`, `Conceded` | AskSet, Settled? | 1b |
| T5 | `Open` | `concede(id, maxShare)` | requester | ask <= maxShare | claimable A += q - pi - ask; claimable B += ask; surplus += pi; earmark to free; refundableAmount = totalFunding; then host.rule(id, CHALLENGER_WINS) | `Conceded` | Settled | 1a |
| T6 | `Open` | `bid(id, x, validUntil)` | requester | now < deadline; x > highest bid so far; x <= q - pi; validUntil >= now + V; validUntil <= deadline; if a bid is live, validUntil >= its validUntil, so a replacement never shortens the offer | none; if x >= ask, executes T5 at the ask | `Open`, `Conceded` | BidPosted, Settled? | 1b |
| T7 | `Open` | `acceptBid(id, minShare)` | challenger | bid live; bid >= minShare | claimable A += q - pi - bid; claimable B += bid; surplus += pi; earmark to free; refundableAmount = totalFunding; then host.rule(id, CHALLENGER_WINS) | `Conceded` | Settled | 1b |
| T8 | `Open` | `escalate(id)` | requester | now < deadline; no live bid; covered(id) | as T3 | `Forwarded` | Escalated, ForwardFailed? | 1a |
| T9 | `Open` | `escalate(id)` | anyone, the challenger included | now >= deadline, so no offer is live; covered(id) | as T3 | `Forwarded` | Escalated, ForwardFailed? | 1a |
| T10 | `Open`, `Forwardable` | `fund(id) payable` | anyone | now < fundingEnd | totalFunding += msg.value; contribution[msg.sender] += msg.value | `Open`, `Forwardable` | Funded | 1a |
| T11 | `Open`, `Forwardable` | `lapse(id)` | anyone | now >= fundingEnd; not covered(id), and not merely unquotable | claimable B += q; refundableAmount = totalFunding; earmark to free; then host.rule(id, REFUSE) | `Lapsed` | Lapsed | 1a |
| T12 | `Forwarded` | `rule(kDisputeID, ruling)` | K only | at most once per K ruling | none held; host.rule(id, ruling) | `Forwarded` | RulingRelayed | 1a |
| T13 | `Forwarded` | `appeal(id, extraData) payable` | the host only, from its own appeal crowdfunding | msg.sender == HOST; K's appeal period open | msg.value to K.appeal(kDisputeID, epoch real extra data) in the same transaction | `Forwarded` | — | 1a |
| T14 | `Unbound`, `Open`, `Forwardable`, `Forwarded`, `Conceded`, `Lapsed` | `claim(to)` | any creditor, for its own claimable balance | claimable[msg.sender] > 0 | claimable[msg.sender] to `to`; the only value transfer to a party in the contract | `Unbound`, `Open`, `Forwardable`, `Forwarded`, `Conceded`, `Lapsed` | Claimed | 1a |
| T15 | `Forwarded`, `Conceded`, `Lapsed` | `claimFunding(id)` | a funder of the case, once | contribution[msg.sender] > 0 and not yet claimed | claimable[msg.sender] += floor(contribution * refundableAmount / totalFunding); the unclaimed remainder stays a liability | `Forwarded`, `Conceded`, `Lapsed` | FundingClaimed | 1a |
| T16 | `Open`, `Forwardable` | `forwardOrLapse(id)` | anyone | now >= fundingEnd; covered(id) or unquotable, and graceElapsed(id); at least MIN_FORWARD_GAS available for the attempt | a fresh forwarding attempt first, with T3's money on success; on a qualifying failure in this same transaction, T11's money and host.rule(id, REFUSE) | `Forwarded`, `Lapsed` | Escalated, ForwardFailed?, Lapsed? | 1a |

| id | move | who | precondition | effect | events |
|---|---|---|---|---|---|
| G1 | `registerEpoch(realExtraData, marginBps, premiumBps, maxCost)` | governor, while not retired | marginBps <= MAX_MARGIN_BPS; premiumBps <= MAX_PREMIUM_BPS; maxCost >= quote | quote = K.arbitrationCost(realExtraData) * (10000 + marginBps) / 10000, fixed forever; pi = quote * premiumBps / 10000; emits the epoch's MetaEvidence pair | EpochRegistered, MetaEvidence |
| G2 | `fundReserve() payable` | anyone | — | from the governor, principal += msg.value; from anyone else, surplus += msg.value, a gift | ReserveFunded |
| G3 | `deactivate()` | governor | not retired | retired = true; retiredAt = now; no epoch can be registered afterwards | Deactivated |
| G4 | `announceWithdrawal(amount, to)` | governor | retired; amount <= principal | pending = {amount, to, announcedAt = now} | WithdrawalAnnounced |
| G5 | `cancelWithdrawal()` | governor | a pending announcement exists | pending cleared | WithdrawalCancelled |
| G6 | `executeWithdrawal()` | governor | pending; now >= announcedAt + RESERVE_TIMELOCK; now >= retiredAt + RETIREMENT_LOCK, where RETIREMENT_LOCK >= the host's challenge period plus a margin; no case in Unbound, Open or Forwardable; amount <= principal and amount <= free at execution | pending cleared; principal -= amount; free -= amount; paid to `to` | PrincipalWithdrawn |
| G7 | `migrateSurplus(successor)` | governor | retired; now >= retiredAt + RETIREMENT_LOCK; no case in Unbound, Open or Forwardable; successor was deployed by the same factory for the same host | the whole surplus moves to the successor as its surplus | SurplusMigrated |

| id | invariant | statement |
|---|---|---|
| I1 | conservation | balance == sum of open fees + sum of unclaimed funding + sum of claimable + reserve, and reserve == principal + surplus, and free == reserve - sum of earmarks, after every transition |
| I2 | one-time finalization | exactly one of T3, T5, T7, T8, T9, T11 executes per case; T12 at most once per K ruling; T15 at most once per funder per case |
| I3 | quote stability | F_A == F_B == q for every case of an epoch; a quote and its premium never change after registration |
| I4 | no holdup | the requester can always execute T5 at the current ask before forwarding; the ask is set at most once upward, to at most q - pi, and then only falls |
| I5 | case-level offer binding | a live bid blocks T8; no offer is live at or after the deadline; T8 exists only before the deadline and T9 only from it, so they are disjoint |
| I6 | passivity, by mode | for an insured case a silent challenger is conceded to at x = 0, a silent requester reaches court at the deadline through T9, and a silent removal is forwarded by anyone; for an under-insured case court depends on free reserve or funding and T11 is possible after the funding period |
| I7 | deposit neutrality | the wrapper never reads, holds or moves a deposit; its prices are fee shares |
| I8 | emergency isolation | T11 is unreachable while covered(id) holds; a covered case reaches Lapsed only through T16, in a transaction in which K rejected a properly funded, properly gassed dispute; an insured case is covered for every c <= maxCost |
| I9 | failure-safe payouts | no transition other than T14 transfers value to a party; a reverting receiver cannot block any transition |
| I10 | no refusal of challenges | T1 reverts only for a wrong sender, an unregistered epoch or a wrong value, never for the state of the reserve |
| I11 | fixed price | the challenger's economic fee on every forwarded case is q; the reserve absorbs q - c in either direction |
| I12 | exclusivity at fundingEnd | for now >= fundingEnd, escalation needs covered(id), T11 needs its negation, and T16 forwards before it lapses, so no instant offers both a forwarding and a refusal of a case K would accept |
| I13 | constant cost | no transition iterates over funders, cases or epochs; funder refunds are computed lazily per funder from one stored fraction |
| I14 | host-only appeal | K.appeal is reached only through T13, and T13 only from the host, so the host's appeal crowdfunding is never bypassed |
| I15 | principal and surplus | surplus leaves the wrapper only to a successor of the same factory after retirement; principal leaves only after retirement, the retirement lock and the timelock, with no case open |
| I16 | non-upgradeable | the wrapper is a plain contract, no proxy and no admin; nothing changes its behavior after deployment except registered epochs and retirement |
| I17 | forward first | a stale forwarding failure never authorizes a refusal by itself; every path to Lapsed for a covered case attempts forwarding in the same transaction |
| I18 | refund liability | refundableAmount minus what funders have claimed is a liability, never spendable by insurance or withdrawal; rounding leaves it unclaimable, not spent |
| I19 | loss waterfall | a reserve draw reduces surplus first and principal second; principal is capital at risk, not a nominal claim |
<!-- generated:end -->

**Ordering inside a transition.** State is written before any external call. T5 and T7 write `Conceded`, credit, release the earmark, then call the host's `rule` with the profile's "challenger wins" value. T11 writes `Lapsed`, credits, then calls `rule` with 0. T3, T8, T9 and T16 read K's quote and call K's `createDispute` inside a try, after checking that at least `MIN_FORWARD_GAS` remains so that the caller cannot starve the call: on success they write `Forwarded`, store `kDisputeID` and emit the ERC-1497 `Dispute` event (section 10); on a qualifying failure they move no money, record `firstForwardFailure` if unset, emit `ForwardFailed`, and leave the case where it was for anyone to retry, except T16, which then lapses in the same transaction. No transition other than T14 sends value to a party. A host `rule` that reverts reverts the transition; that is a host failure the profile assumes away (section 13).

**Offer lifecycle (stage 1b).** An offer is a fee share posted before the deadline. An **ask** is B's price: the default 0 is not an offer and binds nobody; B may raise it once, to at most `q − π`, then only lower it; a set ask persists as an executable price until the case ends and never rises (I4). After the deadline it is an executable quote, not an offer: it binds nobody's escalation and stays executable until forwarding. A **bid** is A's price with a validity of at least `V` that ends no later than the deadline; it is live while `now < validUntil`, so none is live at the deadline instant; while it is live, B may execute it and A cannot escalate (I5); at expiry it is gone. A replacement posted while a bid is live must raise the price and may not end earlier than the bid it replaces, so an offer's two components, its amount and the time it can be taken, both only improve for B. Neither can be posted at or after the deadline, so no offer is live once T9 opens, and the permissionless path needs no offer check: binding is a property of the case, not of a sender address. T8 exists only before the deadline and T9 only from it, so the two are disjoint. Crossing is deterministic: an ask set at or below the live bid executes as an acceptance at the bid; a bid at or above the ask executes as a concession at the ask. Executions carry a limit (`maxShare`, `minShare`) rather than an exact price: since asks only fall and bids only rise, a price moving in the counterparty's favor should not fail the transaction.

**Funding period.** From creation until `fundingEnd`, anyone may store money for a case (T10); the wrapper records the total and each funder's contribution and never iterates over funders (I13). Escalation is never payable; a shortfall is funded first, then escalated by anyone whose transition is otherwise valid. When a case ends the wrapper stores one `refundableFraction`, and each funder claims its share by T15 at its own gas. From `fundingEnd` on, `escalate` and `lapse` test opposite values of `covered(id)`, so exactly one of them is available at any instant (I12): a funded escalation cannot be front-run by a lapse. Case funding closes at `fundingEnd`, but the reserve does not: a gift to the reserve (G2) after the deadline can make an uncovered case covered, after which escalation is the only path. That is a rescue path, kept on purpose and described as such. K's cost can still move after `fundingEnd`; the predicates follow it.

**Resolver failure.** A covered case whose quote or `createDispute` K keeps rejecting would otherwise have no terminal path. After `RESOLVER_GRACE` from the first recorded qualifying failure, and after `fundingEnd`, T16 becomes available: it makes a fresh, properly funded and properly gassed forwarding attempt in the same transaction, forwards if K accepts, and lapses only if K rejects again. A stale failure therefore never authorizes a refusal by itself (I17): an old outage cannot bypass a court that accepts the case now. A case whose quote reverts is unquotable, which is a qualifying failure like any other; T11 is not available for it, only T16 after the grace, so "every case terminates" does not rest on an undefined predicate.

**Removals.** A removal challenge opens no settlement; the wrapper forwards it as soon as anyone asks. The party with the interest is the removal requester, since a challenger's win keeps the item registered, and on Light hosts an unforwarded removal leaves the item registered and its request pending. Forwarding is a second transaction after the challenge, sent by the requester or anyone; stage 1 makes no same-transaction claim, because a contract that bundled the challenge would itself become the challenger of record on stock hosts. A wallet that is a contract may bundle its own calls, since it is the party. An under-insured removal that nobody forwards and nobody funds ends in a refusal after the funding period, which is disclosed in section 7.

## 6. Net payouts

Prices are fee shares `x ∈ [0, q − π]`; the requester's net loss on a concession is `D + π + x`, the design's `Y`. On a concession at `x` the host, on the challenger ruling, pays its pot `P = D + q + D_c` to B. The wrapper then credits:

| to | amount |
|---|---|
| A | `q − π − x` |
| B | `x` |
| surplus | `π` |

Sum `q`, the escrow. Net results: A `−(D + π + x)`, B `+(D + x)`. At the default `x = 0` A recovers the fee less the premium and B receives the pot, A's court loss less the fee. At the ceiling `x = q − π` A's result equals a lost court case. The wrapper needs no deposit to compute any of it.

Court outcomes on a forwarded case, with the challenger's fee fixed at `q` (I11): A loses `s_A = D + q` or gains `g_A = D_c`; B loses `s_B = q + D_c` or gains `g_B = D`. On a refusal ruling Light GTCR and Curate V2 halve the pot: A nets `−(D + q − D_c)/2`, B nets `(D − q − D_c)/2`; Classic distributes the pot by recorded contributions. In every court outcome the parties jointly lose exactly `q`, whatever the distribution rule, because the whole pot returns to them and K's fee is the only leak; the reserve, not a party, carries `q − c`. Case funding, when used, is the funders' loss; `refundableAmount` is what they may claim back, pro rata, each at their own gas (T15).

On emergency lapse the wrapper credits B with `q`, makes the whole funding refundable, and the host applies its refusal distribution. On Light with `D_c = 0` this pays B half of `D + q` without a merits ruling and costs A the same; that is why T11 is reachable only above `maxCost` for an insured case and only after the funding period, why T16 forwards before it lapses, and why both are disclosed as failures.

## 7. Modes

A case is in one of two modes from creation, and the wrapper's promises differ by mode.

| mode | when | passivity | lapse |
|---|---|---|---|
| **insured** | `earmark = maxCost − q` | a silent challenger is conceded to at `x = 0`; a silent requester's case is eligible for court from the deadline; a silent removal is eligible from binding. Eligibility is the wrapper's promise; the transaction is the interested party's or anyone's, and insurance pays for it but does not send it | unreachable for any K cost up to `maxCost` while K accepts disputes; T16 forwards first otherwise |
| **under-insured** | `earmark < maxCost − q`, disclosed at creation | the same, but court depends on free reserve at forwarding time, on case funding, or on a reserve gift | possible after the funding period if K's cost exceeds what the case can pay |

Three properties cannot all be unconditional: never refusing a challenge for lack of reserve, guaranteeing passive escalation to court, and running a finite reserve under arbitrary concurrent demand and fee increases. The wrapper keeps the first and the third unconditional and makes the second conditional on the mode, which is disclosed the moment it is decided.

## 8. Views

| view | `Unbound` | `Open` / `Forwardable` | `Forwarded` | `Conceded` / `Lapsed` |
|---|---|---|---|---|
| `arbitrationCost(extraData)` | the quote | the quote | the quote | the quote |
| `disputeStatus(id)` | `Waiting` | `Waiting` | K's status | `Solved` |
| `currentRuling(id)` | 0 | 0 | K's ruling | the delivered ruling |
| `appealCost`, `appealPeriod` | revert | revert | K's values | revert |
| `caseOf(id)`, `modeOf(id)` | the case record of section 4 and its mode | same | same | same |
| `claimable(addr)`, `fundingClaimable(id, addr)`, `refundLiability()`, `reserve()`, `free()`, `principal()`, `surplus()`, `epoch(epochId)`, `retired()` | the accounting of sections 3 and 4 | same | same | same |

## 9. Events

One event per transition, so that list UIs, wallets, indexers and keepers integrate once: `EpochRegistered(epochId, quote, premium, maxCost, realExtraData)`, `CaseOpened(id, epochId, fee, deadline, fundingEnd, earmark)`, `UnderInsured(id, shortfall)`, `CaseBound(id, kind, requester, challenger)`, `AskSet(id, share)`, `BidPosted(id, share, validUntil)`, `Settled(id, share, requesterCredit, challengerCredit, premium)`, `Escalated(id, kDisputeID, kCost, fundingUsed, by)`, `ForwardFailed(id, reason)`, `Funded(id, funder, amount)`, `FundingClaimed(id, funder, amount)`, `Lapsed(id)`, `RulingRelayed(id, kDisputeID, ruling)`, `Claimed(creditor, to, amount)`, `ReserveFunded(from, amount, principal)`, `Deactivated(at)`, `WithdrawalAnnounced(amount, to, at)`, `WithdrawalCancelled()`, `PrincipalWithdrawn(to, amount)`, `SurplusMigrated(successor, amount)`, plus the ERC-792 `Dispute` and ERC-1497 events toward K.

## 10. Meta-evidence and evidence

Toward K the wrapper is the arbitrable. At T3, T8 and T9 it emits `Dispute(K, kDisputeID, metaEvidenceID, evidenceGroupID)`; the meta-evidence, one per epoch and request kind, is emitted at G1 and carries an evidence display interface that resolves the wrapper-to-host mapping from `kDisputeID` and renders the host's original request evidence, challenge evidence and later submissions from the host's own events. No party has to resubmit anything; a silent party's evidence reaches jurors. The display is part of the deployment and is tested with a silent party before the pilot (design S9). The wrapper offers no evidence relay function.

## 11. Invariants

The invariant table is generated with the transitions in section 5 (I1 to I19).

## 12. The first-block race, stated (stage 1b)

`ask` starts at 0 and B may raise it once. A requester who concedes before B's `setAsk` lands pays the deposit plus the premium. This favors the requester in the first moments after a challenge; a challenger whose wallet is a contract may bundle the challenge and `setAsk` itself, since it is the party of record either way. Accepted and documented; stage 1a has no asks and no race; the arbitrable-side module carries the ask in the challenge.

## 13. Environmental assumptions

| supplied by | what the rest of this document takes as given |
|---|---|
| **the wrapper** (enforced) | everything in sections 5 to 9 and the invariants: fixed price, earmarks, case-level binding, exclusivity, claimable credits, host-only appeal, constant cost, principal and surplus separation, non-upgradeability |
| **the host** (assumed) | it stores the request's arbitration parameters and reuses them at challenge time; its `rule` does not revert for a valid ruling value; its public getters answer as the profile expects; it pays its own pot as it does today, by `send`, which a contract party must be able to receive or the host keeps the money; the party of record is the wallet that called it |
| **the host's governor** (assumed) | it does not raise the challenge period while requests submitted under a retired wrapper are still pending, and it points the list elsewhere before retiring a wrapper; for the pilot the host's governor and the wrapper's are the same Safe, so this is a self-commitment, disclosed |
| **K** (assumed) | `arbitrationCost` and `createDispute` accept a correctly funded, correctly encoded, properly gassed dispute; K's cost changes only through its governance, announced ahead; a K that rejects the case again after a whole grace period is the disclosed emergency of section 5, and a K that has recovered is simply used |
| **the reserve governor** (supplied) | principal at or above the health target, the floor sized for latent exposure, epochs registered before the list points at them, retirement before withdrawal |
| **the evidence UI** (supplied) | a display that renders the host's evidence for K's jurors from the dispute mapping, tested with a silent party |

## 14. Adversarial traces to write

A removal challenged after adoption and never forwarded, insured and under-insured; a request whose challenge arrives after a new epoch is registered; an announced K fee increase within the margin, beyond it within `maxCost`, and beyond `maxCost` with and without funders; `lapse` against a funded case at `fundingEnd`; a bid crossing a lowered ask in one block; an escalation racing an execution; K rejecting a correctly funded dispute before and after the grace period; the host's `rule` reverting on T5 or T11; a profile returning the zero address; a party that is a contract rejecting a transfer; reentry from the host's `rule` into T5, T14 or T15; a second wallet of an offer's owner calling T9; two wrappers over one list; a list switching arbitrators with cases `Open`; self-challenged registrations occupying every earmark until just before the deadline, then conceding at `π = 0` and at `π > 0`; many requests submitted under one epoch and challenged in one block; the old wrapper's principal withdrawn after migration but before old requests' challenge periods expire; ten thousand one-wei funders on one case; two funders partially consumed, claiming in either order, with rounding dust; an EOA calling `appeal` without the host's `fundAppeal`; twenty insured cases crossing one fee increase; a withdrawal announced, then cases opened and closed before execution; a governor gift versus a governor deposit in the two accounts; a temporary K rejection followed by recovery, then T16 forwarding instead of lapsing; a K whose quote reverts; a replacement bid with an earlier expiry, refused; a contract challenger whose receive fails at the host; a reserve gift after `fundingEnd` covering a case; the loss waterfall across surplus and principal in integer units. The executable model in `../sim/` runs those that stage 1a can express.

## 15. Differences for `IArbitratorV2`

The ERC-20 `createDispute` variant is refused; ruling delivery is the same callback; `DisputeRequest` with a template id replaces the V1 `Dispute` event, and the profile supplies the template id; appeals live in dispute kits and are funded through K directly, so T13 is absent; the wrapper needs whitelisting by KlerosCore's governor before it can create disputes.

## 16. Host profiles

| profile | item and request | kind | parties | challenger wins | refusal | pot | challenge period |
|---|---|---|---|---|---|---|---|
| Light GTCR (the Scout lists) | `arbitratorDisputeIDToItemID(wrapper, id)`, then `getItemInfo` for the request count and `getRequestInfo(item, count − 1)` | `getItemInfo(item).status`: `RegistrationRequested` or `ClearingRequested` | `parties[1]`, `parties[2]` of `getRequestInfo` | ruling 2 | ruling 0: the pot halved, the item returns to its prior status | `sumDeposit = D + q + D_c`, paid by `send` | `challengePeriodDuration()` |
| Classic GTCR | `arbitratorDisputeIDToItem`, `getRequestInfo` | the item status at bind | `parties[1]`, `parties[2]` | ruling 2 | ruling 0: the pot by recorded contributions | round 0 `feeRewards`, withdrawn by the parties | `challengePeriodDuration()` |
| Curate V2 (later, section 15) | as Light | as Light | as Light | ruling 2 | ruling 0: halved | `sumDeposit`, paid by `send` | `challengePeriodDuration()` |

A profile states what the wrapper relies on and nothing more: no deposit amounts, no fee history, no evidence. Hosts that push payouts with `send` swallow a failed transfer on their own side; that is the host's behavior today and not the wrapper's concern.

## 17. Release identity

A specification version is released with the design version that cites it; the release head is the commit that adds the design document, which also contains this specification, and `../RELEASES.md` names it.

## 18. What changed from 0.4

| from | to | reason |
|---|---|---|
| lapse available to a covered case once a grace period had passed since any recorded failure | T16 `forwardOrLapse`: a fresh, properly funded, properly gassed attempt first; lapse only on a qualifying failure in the same transaction; a reverting quote counts as a failure; I17 | GPT review of v0.8, finding 1 |
| a retirement lock derived from the host's challenge period and called a guarantee | three facts kept apart; the lock as a floor; the procedure plus a host-governance assumption as the guarantee | finding 2 |
| a router bundling the challenge with the wrapper's next move | no router: the party of record is the wallet that called the host; forwarding and asks are second transactions | finding 3 |
| losses "from the earmark, then free"; a stored fraction; G6 silent on its announcement | a loss waterfall, surplus then principal (I19); `refundableAmount` with floor arithmetic and a permanent liability (I18); G6 clears its announcement and rechecks principal | finding 4 |
| a replacement bid free to end earlier than the bid it replaced | a replacement never shortens a live bid | finding 5 |
| diagram edges invented for state-preserving operations | `preserving` transitions drawn as self-loops and validated | the review's tooling defect |
| passivity worded as court happening; funding-period prose denying rescue by reserve gifts | eligibility for forwarding, with the transaction assumption stated; reserve gifts after `fundingEnd` described as the rescue path they are | the review's wording corrections |
| no executable model | `../sim/`, a stage-1a model with integer accounting and the section 14 traces, run in CI | the review's next step |
