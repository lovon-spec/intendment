# Independent review of Intendment design v0.8 and state machine 0.4

Review date: 2026-09-04. Reviewed: the v0.8 release head `4a4ef27` ([`intendment-design-v0.8.md`](intendment-design-v0.8.md), [`../spec/intendment-arbitrator-state-machine.md`](../spec/intendment-arbitrator-state-machine.md) 0.4 with its YAML source and renderer, [`oracle-insertion-polymarket.md`](oracle-insertion-polymarket.md), and the previous review). Produced by GPT at the maintainer's request and reproduced verbatim; the reviewer's own runnable checks lived in its sandbox and are not part of this repository. The maintainer's assessment and the changes it produced are recorded in the next design version.

---

**This is a meaningful improvement, but I would not freeze spec 0.4 unchanged.** The earlier review's main concerns have largely been addressed at the design level. What remains is more specific: a resolver-failure escape hatch that can outlive the failure, an insufficiently constrained retirement boundary, a router identity problem, incomplete financial-accounting rules, and a stage-1b offer-replacement loophole.

My bigger-picture conclusion is positive, with an important qualification:

> **Stage 1a is a worthwhile product experiment. The concession mechanism is now simpler and clearer than the insurance and failure-management machinery surrounding it. That surrounding machinery—not bargaining—is where I would concentrate the next engineering effort.**

I reviewed the paired release at **`4a4ef27`**, its YAML and renderer, the previous review, and the oracle insertion note. The release manifest identifies that commit as the v0.8/0.4 release head. There are still no Solidity contracts or full executable protocol model in the repository, so the findings below concern the specification and integration design, not deployed vulnerabilities. I also ran small, independent reproductions of the relevant predicates and arithmetic; those are linked below.

## What v0.8 actually fixes

The changes are substantive rather than cosmetic:

| Earlier concern | Assessment of v0.8 / 0.4 |
| --- | --- |
| Unrestricted wrapper appeals bypassing the host's crowdfunding | **Resolved in the specification:** T13 is host-only. |
| Finalization potentially looping over funders | **Resolved structurally:** individual lazy claims replace settlement-time iteration. Exact arithmetic still needs definition. |
| Unconditional passivity claims despite finite reserves | **Much improved:** insured and under-insured cases are explicit. Some remaining wording still overstates liveness. |
| Free occupation of reserve capacity | **Recognized and priced in the design:** the premium is a real answer; keeping it zero in the pilot is an expressly accepted subsidy, not a solved economic problem. |
| Withdrawal despite latent, unchallenged requests | **Directionally repaired:** retirement and locks exist. Their relationship to mutable host parameters is not yet sufficient. |
| A funded case stranded by a rejecting resolver | **A path now exists, but its trigger needs revision.** |

These changes appear in the normative transitions and invariants, not just the design's change log. In particular, host-only appeals, separate reserve accounts, and the move away from funder loops are worth preserving.

# Findings to resolve before freezing the specification

## 1. Resolver failure becomes a persistent option to avoid a recovered court

**Priority: high; affects stage 1a.**

The new failure predicate is:

```text
resolverFailed(id) =
    firstForwardFailure != 0
    and now >= firstForwardFailure + RESOLVER_GRACE
```

After the funding deadline, T11 permits lapse when either the case is underfunded **or this predicate holds**. The timestamp records the first failed forwarding attempt; it does not establish that the resolver remained unavailable throughout the grace period, or that it is unavailable now. The prose acknowledges that escalation and lapse may overlap after a failure, but I8 still says lapse is unreachable when the case is covered and K accepts disputes. Those statements are not equivalent.

A counterexample is straightforward:

1. A correctly funded forwarding attempt fails temporarily.
2. K recovers.
3. Nobody successfully forwards this particular case before the grace and funding deadlines.
4. Both ordinary forwarding and lapse are now permitted.
5. A party that prefers the refusal distribution submits—or races to submit—`lapse`.

**A historical infrastructure failure has become a continuing financial option.**

This matters because lapse is not a neutral cancellation. The specification itself explains that on Light GTCR it can transfer value from the requester to the challenger without a merits ruling.

### Recommended change

When a covered case reaches the resolver-failure fallback, **give successful forwarding priority within the same transaction**:

```text
grace elapsed
    → make a fresh, properly funded forwarding attempt
    → success: Forwarded
    → qualifying failure: emergency outcome
```

This would not prove continuous past unavailability. It would establish the more useful property:

> An old failure cannot authorize refusal when court can successfully accept this case now.

Also define what counts as a qualifying failure. A caught revert is not automatically proof of a resolver outage. Test gas-starved calls and distinguish a failure of K's actual dispute-creation logic from caller-induced execution failure.

There is a related uncovered edge: **what happens when `K.arbitrationCost` itself reverts?** Both coverage and the forwarding precondition depend on that quote. Catching only `createDispute` does not provide a terminal route when the quote cannot be obtained. Either explicitly exclude quote-service failure from the liveness guarantee, or specify a separate unavailable-quote path. Do not let "every case terminates" depend on an undefined predicate.

This is the place where I would be most conservative. A fallback that changes the allocation of money should require stronger justification than "a call failed sometime earlier."

## 2. Retirement does not yet establish that latent exposure has ended

**Priority: high for the claimed guarantee; affects stage 1a.**

The new retirement procedure is the right direction. However, `RETIREMENT_LOCK` is described as a deployment-time constant derived from the host's challenge period. That period is not necessarily immutable.

Light GTCR's challenge function compares elapsed time against the **current** `challengePeriodDuration`, and the governor can change that duration. It is not a deadline snapshotted into each request.

Consequently:

```text
wrapper deployed with a seven-day host challenge period
→ retirement lock fixed at eight days
→ request submitted under wrapper
→ host moves to successor; old wrapper retires
→ host challenge period becomes thirty days
→ eight-day retirement lock expires
→ principal withdrawn
→ old request can still be challenged against the old wrapper
```

The current specification does not rule that out.

There is a second issue: `deactivate()` stops **epoch registration**, not the host assigning an existing wrapper epoch to new requests. The design says the host *should* already point elsewhere, but G3 does not require that, and T1 must remain available for legitimate old requests.

### Recommended change

Separate three facts that are currently too close together:

**Retirement declared:** the wrapper has been marked retired.

**Admission stopped:** the host is no longer assigning it to new requests.

**Latent exposure exhausted:** no remaining host request can subsequently open a case against it.

Only the third fact justifies releasing underwriting capital.

For a pilot, a documented governance constraint and monitored retirement procedure can be adequate. But specify the constraint: for example, a maximum challenge horizon that cannot be exceeded while old requests remain pending, together with verified cessation of new assignments and finalization of expired requests.

Simply reading the period at retirement or withdrawal is not a complete solution either: a later increase could revive a still-pending request's challenge eligibility.

This is principally a **missing host-governance assumption**, not an arbitrary outsider's exploit. Nevertheless, the attack catalogue currently calls premature withdrawal "impossible," which is stronger than the mechanism establishes.

## 3. An ordinary challenge router becomes the challenger

**Priority: integration blocker; relevant to stage 1a removals and stage 1b asks.**

The specification relies on a router to bundle:

```text
host.challengeRequest(...)
wrapper.bind(...)
wrapper.forward(...) / wrapper.setAsk(...)
```

That is not a transparent convenience layer on the supported stock host.

Light GTCR explicitly records:

```solidity
request.challenger = msg.sender;
```

Therefore, when a normal router contract calls `challengeRequest`, **the router—not the wallet that called the router—is the challenger**. The host also sends the challenger's award to that recorded address.

The wrapper would then correctly bind the router as B. This affects settlement authority, credits, host payouts, and whose identity appears in the evidence history.

### Recommended change

Choose and specify one actual account model:

* A **user-owned batching account** is the real challenger, with a payout-compatible receiving path.
* A **router explicitly acts as a custodial or accounting intermediary**, with authenticated per-case ownership and withdrawals.
* Stage 1a uses **direct wallet challenges followed by permissionless binding/forwarding**, without claiming same-transaction forwarding.

The third option is the least new machinery for the first pilot. Stage 1a has no ask-setting race to solve.

A generic router must not be presented as though it preserves the caller's identity automatically. Nor should the wrapper "recover" the user through `tx.origin`; the host's recorded party is the authority.

Also retain the distinction between wrapper payout safety and host payout safety. Claimable wrapper credits do not repair a stock host's failed `send` to a router or smart account. The spec already acknowledges that host behavior; the proposed router makes testing it essential rather than incidental.

## 4. The two-account reserve needs explicit loss and refund accounting

**Priority: must specify before implementing fund-holding code.**

Separating principal from surplus is a good repair. But the transitions still say that losses are paid "from the earmark, then free" without specifying how the loss reduces **principal versus surplus**.

An earmark is a restriction on spending capacity. It is not, by itself, an ownership or loss-allocation account.

Consider:

```text
principal = 100
surplus   = 0
fee       = 20
K cost    = 30
```

After forwarding, ten units of reserve have been consumed. What are the new principal and surplus balances? The current transition text does not answer that precisely enough.

I would specify a waterfall, such as:

```text
reserve loss = max(c − q − fundingUsed, 0)

consume surplus first
consume at-risk principal second
```

Another waterfall could be defensible. What matters is that **principal means either remaining at-risk capital or a nominal repayment claim**, and the choice is explicit. Those interpretations create different withdrawal rights.

### Refund arithmetic

The lazy refund ratio is mathematically sensible:

```text
(totalFunding − fundingUsed) / totalFunding
```

But the implementation should not store an integer division result as the "fraction." Specify numerator/denominator storage and a full-precision calculation:

```text
refund_i =
    floor(contribution_i × refundableAmount / totalFunding)
```

Define the zero-funding case, overflow behavior, outstanding refund liability, and when residual dust becomes surplus. Until dust is actually determined, it must not accidentally become spendable reserve while funder claims remain outstanding.

The withdrawal operation needs similar precision. G6 should explicitly consume its pending announcement and recheck the **current** principal balance, not only free reserve. Insurance losses may occur between announcement and execution. As written, clearing the announcement is absent from G6's effects.

These are specification gaps, not evidence of existing fund theft. They are exactly the details an executable ledger model should force you to settle.

## 5. A replacement bid can shorten an existing commitment

**Priority: high for stage 1b; does not block an offers-disabled stage 1a.**

T6 requires a new bid to increase its amount and satisfy:

```text
validUntil >= now + V
validUntil <= deadline
```

It does **not** require the replacement to preserve the expiry of an already-live bid.

For example:

```text
deadline = 100
V = 10
B's ask = 10

t = 10: A bids 5, valid until 90
t = 20: A replaces it with 6, valid until 30
t = 31: A escalates
```

The replacement satisfies T6. It does not cross the ask, so no settlement occurs. At time 31 there is no live bid, making T8 available.

A has shortened a commitment that originally ran until time 90.

### Recommended change

For a replacement while the old bid is live, require:

```text
newValidUntil >= oldValidUntil
```

Alternatively, prohibit replacing a live bid except by increasing its price while retaining its existing expiry.

This preserves both components of B's option: **the offered amount and the time during which it may be accepted**. Monotonic prices alone do not establish binding offers.

# One concrete tooling defect

## The generated diagram invents changes of case state

`render.py` takes the Cartesian product of a transition's `from` and `to` lists. For multi-state identity transitions it then skips the matching pairs.

For T14, whose intent is "claim credits without changing the case state," that produces edges equivalent to:

```text
Conceded --> Open: T14 claim
```

while omitting the corresponding self-loop. T10 similarly appears capable of converting an open registration into a forwardable removal. Those are diagram-generation errors, not protocol behaviors.

The data needs to distinguish:

```text
state-preserving operation
```

from:

```text
operation with alternative target states
```

Successful forwarding and failed forwarding also need explicit branches before this data becomes an executable model.

The repository correctly says the YAML is **structured specification data, not an executable model**. Preserve that distinction. Its current validator checks identifiers, states, events, stages, and limited structural consistency; CI does not yet establish conservation or liveness.

# Bigger-picture assessment

## Stage 1a has a stronger rationale than stage 1b

This is the most important strategic point I would add.

In your money-only model, default concession gives B a net gain of **D**. That is already B's best ordinary monetary court outcome. A receives the unused fee less the premium.

Consequently, stage 1a already implements a particularly attractive concession price:

> Give the challenger what winning would have paid, and let the requester recover the fee that court no longer needs.

There is no need to discover whether B would prefer some smaller monetary amount. At this default, B already receives its court-win amount.

Under that model, **stage 1b does not enlarge the set of requester concessions made affordable by stage 1a**. Raising B's ask makes concession more expensive for A. Asks and bids primarily determine how much of the saved fee B can extract.

That does not make stage 1b useless. Its potential justification is **ex ante challenger supply**: greater possible rewards might induce more people to inspect claims and challenge bad ones. But that is a different hypothesis from "negotiation makes more disputes settle."

I would therefore set the stage-1b gate as:

> Do additional challenger rewards improve useful review coverage enough to offset more expensive concessions, bargaining transactions, and delay?

Using the design's illustrative `D = 30`, `q = 21.6`, zero premium, zero refusal probability, and no non-monetary value, A prefers default concession when:

$$
p_A(D+q)\ge D
\quad\Longrightarrow\quad
p_A\ge\frac{30}{51.6}\approx58.1\%.
$$

A positive ask raises that threshold. This is a useful benchmark for a behavioral model, not a forecast about real users. The example values and underlying payoffs come from the design.

**I would be comfortable leaving the product at stage 1a substantially longer than the current sequencing might suggest.**

## Settlement changes the incentive system, even when deposits remain unchanged

"The deposit is never reduced" is a valid accounting property. It is not the same as "the deterrence against bad requests is unchanged."

Under direct court resolution, a losing requester in your model loses `D + q`. Under default concession it loses `D + π`. That reduction is the product's intended benefit—but it is also a reduction in the cost of submitting something that will lose.

Two competing effects are plausible:

**Beneficial:** obvious mistakes leave cheaply and quickly; challengers recover their capital sooner; fewer uncontested errors consume court resources.

**Adverse:** opportunistic submitters can try more low-quality requests because being caught costs less.

The answer is empirical, not a reason to reject settlement. But it means **court-avoidance rate alone is an inadequate success metric**.

Your new metrics already improve matters by including net gas savings, underinsurance, resolver rejection, and earmark-hours. I would add challenged-invalid submissions per unit of useful accepted content, reviewer effort, removal response performance under registration load, and the full reserve subsidy required per externally meaningful case.

Raw settlement volume is especially easy to manufacture through self-challenges. Evaluate an identifiable pilot cohort separately from permissionless activity; do not treat heuristics about different wallet addresses as proof of independent parties.

## This is now both a settlement protocol and a fixed-price underwriting service

The settlement arithmetic is small. Much of the complexity comes from promising a stable `q` while K charges a potentially different `c`: epochs, earmarks, latent exposure, funding, principal, surplus, retirement, and emergency refusal.

I would make that product boundary explicit:

**Settlement:** who may end the dispute, when, and with which fee allocation.

**Underwriting:** who absorbs fee changes, how much exposure is accepted, and what happens when coverage is insufficient.

This does not require two contracts. It requires separate guarantees, tests, metrics, and operational ownership.

It also sharpens the governance claim. Using the host's existing governor introduces no additional governor address. But it gives that governor an additional operational duty: maintaining an underwriting pool. "No new trusted party" does not mean "no new trust assumption."

Similarly, distinguish private fee refunds from system-wide savings. Report reserve losses, retained margins, premiums, gas, and funded shortfalls separately. Otherwise, a large refund can look like efficiency when part of its counterfactual economics depended on a public subsidy.

## A concession is an outcome, not a factual admission

This distinction matters especially for Intendancy.

A requester can concede because it is wrong, because defending is inconvenient, because the cost is not worthwhile, or because it no longer cares about the listing. Financial agreement does not establish which explanation is true.

The UI and downstream records should distinguish:

```text
conceded
court ruled against requester
emergency refusal
```

All may lead to host status changes, but they are not the same evidentiary event. The specification already emits distinct settlement, lapse, and ruling events; use those distinctions rather than reducing everything to "rejected by arbitration."

For a security-oriented registry, that is not cosmetic. Consumers may want conservative execution behavior without asserting that every disabled package was adjudicated malicious.

## Intendancy remains a useful pilot, but it exposes costs that status-separated views do not solve

Intendancy's Classic design authenticates an append-only enumeration, including absent historical items. Separating challenged items in the UI does not remove their storage, proof, indexing, and snapshot costs.

Your new premium helps price repeated self-settled cases **when enabled**. The stage-1a pilot still sets it to zero. Thus the previous Intendancy-specific concern remains an accepted exposure rather than a closed finding: cheap, rapidly conceded submissions can add permanent history even without occupying reserve capacity for long.

Add **historical rows and proof bytes created per useful accepted artifact** to that pilot's measurements. Earmark-hours will not capture immediate self-concessions.

I still favor the launch order you described: **Intendancy on direct Kleros first, then a separately reviewed Intendment pilot**. That gives you a baseline and avoids simultaneously changing the registry's operating process and its dispute economics.

# Two smaller wording corrections that matter

**"Nobody acts" does not imply court occurs.** The passivity table still describes court after the window when nobody acts, then attributes execution to an interested party or anyone. Those are different conditions. Say that the case becomes eligible for forwarding at the deadline, and separately state the keeper or party-activity assumption. Insurance pays for execution; it does not cause a transaction to be submitted.

**The funding deadline does not freeze coverage.** Although T10 stops case funding at `fundingEnd`, G2 still permits reserve donations. A donation followed by escalation can make an uncovered case covered after that deadline. This does not violate complementary predicates evaluated in a single state, but it contradicts the stronger prose that a lapse cannot be pre-empted by money arriving in the same transaction. Preserve useful rescue paths and describe them accurately.

# What I would do next

I would move from further broad design iteration to a **small executable stage-1a model**, while correcting the specific rules above.

Its acceptance criteria should cover:

| Area | Required evidence |
| --- | --- |
| Resolver failure | Temporary failure followed by recovery cannot leave a stale right to bypass a functioning court; quote failures have an explicit treatment. |
| Retirement | Old request challenges are exercised across migration and host-period changes; the supported governance assumptions are explicit. |
| Account integration | The real challenger identity, host award recipient, wrapper creditor, and authorized caller agree through the chosen wallet/router path. |
| Accounting | Every transition updates escrow, refund liabilities, credits, principal, surplus, and earmarks exactly; partial refunds and losses are tested in integer units. |
| Adversarial operation | Registration floods, under-insured removals, passive parties, and reserve funding around deadlines are exercised together—not only as isolated examples. |

Then build the contract skeleton against that model. Keep offers disabled until the bid-lifetime rule is repaired and there is evidence for stage 1b's challenger-participation thesis.

I ran **seven reviewer-written checks** covering the bid replacement, recovered resolver, retirement horizon, reserve-funding boundary, refund arithmetic, generated-diagram behavior, and the illustrative concession threshold. They are small reproductions, **not** a full protocol simulation or a run of the repository's own test suite: runnable checks and execution results lived in the reviewer's sandbox (`predicate_counterexamples.py`, `test_results.txt`) and are not reproduced here.

## Bottom line

**The core idea is worth building, and v0.8 is stronger than v0.7.** The fee-share abstraction, concession-only first deployment, removal exclusion, and preservation of the host's appeal path form a coherent first product.

I would not describe the remaining work as another architecture rewrite. But neither is it merely implementation polish: the current fallback and lifecycle rules can produce outcomes that contradict the stated guarantees.

The most valuable next step is to make those guarantees executable. **Prove that the small concession mechanism behaves correctly inside its much larger insurance and integration boundary—and let stage 1a establish demand before adding bargaining.**
