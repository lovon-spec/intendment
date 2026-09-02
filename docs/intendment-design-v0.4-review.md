# Audit of Intendment design v0.4

Review date: 2026-09-02. Reviewed document: [`intendment-design-v0.4.md`](intendment-design-v0.4.md), commit `16629fc984580e09f3d8470f86887fbb976b0f30`.

## Bottom line

v0.4 is substantially clearer than v0.3. In particular, the distinction between universal concession and system-specific challenge withdrawal is correct; R13 states the Sybil problem directly; R15 recognizes the unrepresented third party; and the roadmap appropriately puts the state machine and adversarial traces before simulation.

It should still not advance to implementation as written. The per-item cooldown is both unavailable to the proposed arbitrator-only wrapper and, in an integrated module, a free targeted-denial primitive. The wrapper also assumes one arbitration fee where Curate can expose three different fees, and it cannot enforce the proposed top-up reimbursement or replay evidence from the unmodified Curate contract. Finally, non-exclusive challengers do not repair the removal-request bottleneck at the right abstraction and substantially change the economics from the two-party model analyzed by the document.

## Findings

### 1. Blocker — the per-item cooldown is a free censorship primitive

Section 5 makes a cooldown start after either concession or request withdrawal. Section 6 permits A to withdraw an unchallenged request and recover the deposit. Together, those rules permit this trace:

1. An attacker submits a request for target item X.
2. Before a challenge stands, the attacker withdraws the request.
3. The deposit is returned.
4. X cannot be resubmitted for several review periods.
5. The attacker repeats at expiry.

No second wallet, settlement, or resolver fee is needed. If the rule applies to removal requests, an item owner can similarly create and withdraw a removal request to prevent an honest remover from acting. If request withdrawal is restricted to a post-challenge state, the same actor can self-challenge and settle before any third-party transaction can interleave.

Curate makes submission and removal permissionless. Registration item IDs are hashes of the submitted data, so a global cooldown affects every prospective requester of that exact item, not merely the actor that created the withdrawn request. See the official [Curate V2 request functions](https://github.com/kleros/curate-v2/blob/1d1d0311b3bbced6445edf669ce7cfae6c5fc866/contracts/src/CurateV2.sol#L349-L417).

There is a second incompatibility: an arbitrator-level wrapper cannot enforce “this item ID cannot be resubmitted.” Curate does not identify an item to the arbitrator when `addItem` or `removeItem` is called. The wrapper first receives a state-changing call when Curate later calls `createDispute` during a challenge. Rejecting that challenge because the item is cooling down would make the resubmission unchallengeable, which is worse.

Recommendation: remove the global cooldown. Repeated valid pending registrations are principally a presentation/indexing problem; the UI can collapse repeated requests for one item. If an economic throttle is required, it must impose a non-party cost and must not grant the withdrawing requester an exclusive lock over the item. A wrapper-local “settlement unavailable on the next case” flag is implementable, but it is not the item-submission cooldown specified here and needs separate analysis.

### 2. Blocker — the wrapper accounting assumes one fee, while Curate can expose three

The payoff model and section 7 use one value F. For an unmodified Curate integration there can instead be:

- `F_A`, included in A's deposit when the request is submitted;
- `F_B`, paid by B and transferred to the wrapper when the request is challenged; and
- `F_E`, charged by the real arbitrator when the wrapper escalates after the settlement window.

Curate queries `arbitrationCost` separately at request and challenge time. After the challenge, its item pot is `D + F_A + D_c`, while the wrapper holds `F_B`. On a challenger ruling Curate pays that pot directly to the stored challenger. See [submission and challenge accounting](https://github.com/kleros/curate-v2/blob/1d1d0311b3bbced6445edf669ce7cfae6c5fc866/contracts/src/CurateV2.sol#L349-L457) and [ruling payouts](https://github.com/kleros/curate-v2/blob/1d1d0311b3bbced6445edf669ce7cfae6c5fc866/contracts/src/CurateV2.sol#L509-L555).

The claimed concession split works only when `F_A == F_B`. To give A a net loss Y, the wrapper must refund `D + F_A - Y` to A. At the default `Y = D`, that refund is `F_A`; if `F_A > F_B`, the wrapper does not hold enough and cannot claw the difference back from Curate's direct payment to B.

The escalation rule has the same custody problem. If `F_E > F_B`, a third-party executor can supply the difference, but the wrapper cannot enforce repayment “first from the losing side's stake”: that stake remains in Curate and is sent directly to A or B. If nobody supplies the difference, the proposed lapse-and-restart outcome is not expressible by an arbitrator-only wrapper—section 7 correctly explains that a ruling for A executes the request rather than restarting its review.

Recommendation: model `F_A`, `F_B`, and `F_E` separately. For an arbitrator-only wrapper, make fee quotes immutable for an extra-data/version epoch and provide a funded reserve or another explicit source for an escalation shortfall. Do not promise reimbursement from deposits the wrapper does not custody. If custody is required, the design needs a challenge-forwarder or an arbitrable-side integration, which is a different deployment claim.

### 3. High — the removal defense operates on the wrong side of the dispute

For a removal request, A argues “remove the item” and B argues “keep the item.” An honest remover is therefore another A-type actor. Section 10's claim that an honest backstop forces court is mechanically possible only by making that remover join the B side, post a challenger fee, refuse to withdraw, and deliberately lose in court to obtain the outcome they support.

That is not covered by the document's A/B utility model: the supposed backstop has A's substantive preference but B's stake and payout. When the requester wins and the item is correctly removed, this “challenger” loses its fee. An independent honest removal requester would instead post the requester deposit and recover it on a correct ruling.

Non-exclusive challenges can deter the self-settlement loop after the honest party successfully joins: concession must pay that party, or the case reaches court. But they do not remove the exclusive requester lane, and they require public enforcers to take the semantically wrong position.

Recommendation: promote “multiple removal requests per item” from an open question to an integration prerequisite, stated more generally as independent removal prosecution. Literal parallel requests are one implementation; a co-requester, join, or fork-to-court mechanism may avoid N redundant disputes. Until such a path exists, settlement should be disabled for removal requests.

### 4. High — the backstop rule eliminates the central concession case

Each standing challenger's default concession ask is D. With the Scout parameters in the document:

```text
one challenger:                 30
one challenger + one backstop: 60
A's maximum court loss:         51.6
```

One backstop therefore makes default concession more expensive than losing in court. This is not merely an edge case: on an obviously bad claim, a backstop receives D if A concedes and receives its fee back if the challenger side wins. Its principal downside arises only if the claim was actually good. Clear junk thus attracts rational pile-ons until concession is uneconomic, sending precisely the strongest settlement candidates to court.

The document acknowledges that only junk attracts a pile and calls that deserved, but it conflicts with the mechanism's purpose. The chosen safety mechanism and the claimed settlement savings cannot both be assumed. This tradeoff should be explicit and measured before describing concession as the universal core.

### 5. High — evidence cannot be automatically re-emitted by the wrapper

Section 7 says the wrapper re-emits evidence when it creates the real dispute. Curate does not pass evidence to `createDispute`: it passes only the number of choices and arbitrator extra data, then emits `RequestChallenged` with the evidence string after `createDispute` returns. Earlier request evidence likewise exists in Curate's logs. See the official [challenge sequence](https://github.com/kleros/curate-v2/blob/1d1d0311b3bbced6445edf669ce7cfae6c5fc866/contracts/src/CurateV2.sol#L419-L468).

A contract cannot read historical event logs, so the wrapper does not possess those strings to replay under the real dispute ID. Without an additional mechanism, an inactive party's already-submitted evidence may not reach the resolver, violating passivity safety.

The design must choose one of:

- a Curate/module call that carries and stores the evidence;
- a permissionless evidence relay with an authenticated proof of the original event; or
- explicit juror UI and indexer support for following the pseudo-dispute-to-real-dispute mapping back to Curate's original events.

The latter can preserve an unmodified Curate contract but no longer means that the wrapper itself “re-emits” the evidence.

### 6. High — non-exclusive challenges turn the selected mechanism into an unanalyzed multiparty mechanism

The non-goals exclude more than two parties, while section 5 permits any number of challengers with separate asks, liabilities, joining times, and record priority. This is not one aggregate B: concession pays each challenger separately, only one receives the item deposit, and the others have different court payoffs.

Consequences not covered by the two-party bands include:

- no aggregate concession ceiling equal to A's court loss;
- the refusal-to-arbitrate allocation for backstop escrows;
- record withdrawal and successor payout;
- last-minute entry after prices have been revealed;
- unbounded iteration unless all finalization and payouts use aggregate accounting plus pull withdrawals; and
- inconsistent rulings or moot escrows if an integration uses parallel proceedings.

Curate also stores the original `request.challenger` before calling the wrapper and later pays that address directly. An arbitrator-only wrapper cannot make a backstop the recipient of Curate's item pot merely by changing its internal “challenger of record.” That handoff requires an arbitrable-side module or a forwarding challenger that itself is recorded in Curate.

Recommendation: either model the B side explicitly as a multiparty pool and prove its aggregate accounting, or remove non-exclusive challengers from the universal wrapper. The current bilateral analysis does not establish the properties of the selected mechanism.

### 7. High — the posted-price interface contains contradictory or farmable cases

The document defines concession prices as `0 <= Y <= s_A`, starts a challenger ask at D, and permits asks only to fall. Section 7, however, says the wrapper can express only `D <= Y <= D + F`, and R6 says the deposit deterrent is never reduced. A hard lower bound of D (or the integration's exact challenger court gain) is therefore required; otherwise an ask may fall below the claimed deterrent and may require a refund the wrapper cannot fund.

The original challenger also cannot set a non-default ask “in the challenge transaction” through unmodified Curate. Its call to the wrapper contains no price and has `msg.sender == Curate`, not B. Supporting an initial ask above D requires a signed precommit, a challenge router, or a separate transaction in which A can race to concede at the default.

Finally, every A-paid buy-out bid must be bound to an exact challenger and nonce. If it is a case-wide standing offer that “a challenger may accept,” a new address can join and atomically accept the bid, recover its challenge fee, collect A's payment, and leave the original challenger standing. The same actor can repeat through Sybils. Monotonicity does not prevent this; recipient binding does.

### 8. Medium — several passivity and liveness claims remain too strong

R1 says the time cost is at most one window, but sequential challengers may withdraw one after another, restarting a full review each time. Transfers price the delay but do not bound its cumulative duration. The statement is true per settlement case, not per claim.

R3 says silence yields today's outcome. A fee increase followed by no top-up instead lapses the challenge and transfers challenger escrows to A; today Curate creates the dispute immediately at challenge time and has no analogous later top-up failure. This may be an intentionally selected failure rule, but it is not the status quo under silence.

R14 says termination does not rely on a volunteer. Every EVM timeout still requires a transaction, and the wrapper-only lapse cannot express the desired restart. The state machine needs a named, incentivized caller and an implementable terminal outcome for every fee branch.

## What v0.4 improves

The following changes should be retained:

- Concession is separated from challenge withdrawal, and only the former is called universal.
- R13 correctly states that transfers between Sybil identities are not deterrents.
- R15 makes third-party protection an integration policy rather than assuming all systems resemble Curate.
- Optimistic-market challenge withdrawal is disabled by default.
- The delay cost is acknowledged instead of being called literally equivalent to today.
- Formal state machine, accounting, and adversarial traces precede simulation and implementation.

## Recommended direction for v0.5

1. Keep an arbitrator-level, concession-only wrapper as the first implementation target.
2. Enable it only for request classes where concession cannot monopolize action against an already-effective object. In Curate, disable removal concessions until independent removal prosecution exists.
3. Remove the global item cooldown and non-exclusive challengers from the core design. Treat harmless repeated pending registrations as a UI/indexing concern unless evidence shows a protocol-level harm.
4. Specify a wrapper-compatible fee model with distinct request, challenge, and execution fees, an immutable quote rule, and an actual source for shortfalls.
5. Specify how original evidence and metadata reach the real dispute without trusting a volunteer.
6. Define exact recipient-bound price messages, funding, expiry, and nonces before claiming front-running resistance.
7. State this adapter invariant explicitly:

   > Settlement must never let its parties monopolize the only public path for acting against an already-effective object.

The core idea remains worthwhile. The safest path is a deliberately narrow concession wrapper with exact integration preconditions, followed by system-specific withdrawal only after the host's concurrency and third-party rights are solved at the host layer.
