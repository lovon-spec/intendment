# Independent review of Intendment design v0.7 and state machine 0.3

Review date: 2026-09-04. Reviewed: `main` at `b74d031`: [`intendment-design-v0.7.md`](intendment-design-v0.7.md), [`../spec/intendment-arbitrator-state-machine.md`](../spec/intendment-arbitrator-state-machine.md) 0.3 with its YAML source and renderer, the README, the release manifest and [`oracle-insertion-polymarket.md`](oracle-insertion-polymarket.md). Produced by GPT at the maintainer's request and reproduced verbatim; the maintainer's assessment and the changes it produced are recorded in the next design version.

---

I reviewed the current `main` branch at `b74d031`, including design v0.7, state-machine spec 0.3, the YAML source, renderer, README, release manifest, and the revised Polymarket insertion note. I also checked the relevant Light GTCR and Kleros appeal paths against their source contracts. There are still no contracts or simulations, so this remains a mechanism-and-specification review rather than a Solidity audit.

## Overall take

This is a **substantial improvement**.

You folded essentially every meaningful point from the v0.6 review:

* The one-way fee hedge is gone.
* The fixed-price model is now economically coherent.
* The reserve has explicit earmarks and a declared insured maximum.
* Offers are bound at case level rather than sender level.
* Funding exists as stored case credit rather than an attempted top-up inside escalation.
* Deposits are no longer part of wrapper pricing.
* Payouts are claimable credits.
* One host gets one wrapper.
* Stage 1a is now the genuinely minimal experiment.
* The refusal outcome is included in the bargaining math.
* The Polymarket callback story is no longer internally contradictory.
* The specification has a machine-readable companion and release manifest.

The fee-share change is especially elegant. Pricing only the allocation of `q`, without asking the wrapper to understand the host deposit, is cleaner than trying to build an increasingly clever host adapter. Stage 1a—one known price, concede or court—is still exactly the right first product.

My verdict would be:

> **Design v0.7 is strong and much more internally coherent. Spec 0.3 still needs changes before implementation, mainly around finite insurance capacity, funder accounting, and the appeal boundary.**

Those are not signs that the core idea is shaky. They are the next layer of problems that becomes visible now that the simpler contradictions have been removed.

---

## 1. The reserve now has a capacity problem, not an accounting problem

The fixed-price model repairs the prior economic inconsistency. The important new question is: **who pays for temporarily occupying insurance capacity?**

At case creation, the wrapper earmarks up to `maxCost − q`. On a settlement, the whole fee goes back to the two parties and the earmark is released.

That enables this trace:

1. One owner submits a request as A.
2. The same owner challenges it as B. Light GTCR does not prohibit the requester from also being the challenger.
3. The case receives an earmark.
4. The owner leaves the case open for almost the whole window.
5. Just before permissionless escalation opens, A concedes at `x = 0`.
6. The host pot goes to B and the wrapper fee goes back to A.

With the Scout figures, the owner locks `D + 2q + D_c = 73.2 xDAI`, but recovers the entire amount on concession. The economic cost is gas and temporary capital lock, while the case has occupied `maxCost − q` of shared reserve capacity for most of the window. The host's challenge path records the challenger but contains no requester-versus-challenger inequality check, and the v0.7 settlement accounting makes the same-owner round trip balance to zero.

This is important because S4 already recognizes that self-settled states are effectively free to occupy. In v0.6 that mostly affected the pending-items view. In v0.7, an open case also occupies a **scarce shared financial resource**.

I would add a trace along the lines of:

> N self-challenged registrations consume every available earmark for W; an honest challenge then opens underinsured.

I would also add **earmark-hours** or **reserve-capacity-hours** to the pilot metrics. Maximum drawdown does not capture this attack because no money needs to leave the reserve.

### Possible resolutions

The cleanest economic answer is a small capacity premium, retained by the insurance pool on every challenged case—even one that settles. For example, split the held fee into:

* A small non-refundable insurance premium `π`.
* A distributable settlement amount `q − π`.

At the default settlement, A would lose `D + π` instead of exactly `D`; B would still receive its court-win amount `D`; and a self-challenger would pay something to occupy the reserve.

That revises S11 slightly, but it turns the reserve into actual insurance: coverage has a premium whether or not a claim is ultimately made.

A more experimental version would charge by earmark-time, making immediate concessions nearly free while making full-window reserve occupation costly. That is conceptually attractive, although probably too much machinery for stage 1a.

The alternative is to call the reserve an explicitly governor-funded public subsidy, overfund it for the pilot, and accept that capacity occupation is not economically priced. That can be reasonable for an experiment, but it should be presented as a conscious policy choice.

---

## 2. Unchallenged requests are latent reserve liabilities

The wrapper allocates an earmark only when `createDispute` is called, which happens at challenge time. But the host fixes the request's arbitration parameters when the request is submitted and uses those same parameters if the request is challenged later.

Consequently, the wrapper can have:

* No currently open cases.
* Plenty of old, still-challengeable requests pointing to it.
* A governor withdrawal under G3.
* A burst of challenges afterwards, all using the old quote and now opening underinsured.

The current withdrawal rule checks only that no case is `Unbound`, `Open`, or `Forwardable`. It does not account for requests that have not yet become wrapper cases.

This matters immediately for the proposed 1a-to-1b redeployment. Switching the list to a new wrapper does not retire the old wrapper: requests created with the old arbitration parameters can still reach it during their remaining challenge periods.

I would specify a reserve retirement procedure:

1. Stop assigning the wrapper to new requests.
2. Wait until every request created under it is no longer challengeable.
3. Resolve all cases already opened.
4. Only then migrate or withdraw the reserve.

For the pilot, the simplest rule may be: **reserve capital is not withdrawable while the wrapper is active; after deactivation, it remains locked for at least one full maximum challenge period plus a safety margin.**

This also means the reserve-health target should ideally consider both:

* Open-case liabilities.
* Latent exposure from still-challengeable requests.

The wrapper cannot observe the second category generically without a host hook, so stage 1 may have to use conservative off-chain monitoring. That limitation is worth stating directly.

---

## 3. Funder refunds must be lazy and constant-cost

This is the clearest implementation blocker in spec 0.3.

T10 permits any number of funders. T3 says unused credit is returned to its funders, and T11 says every funder's credit becomes claimable. The source also records credit per funder.

As written, finalizing the case seems to require iterating through the funder set. An attacker can send tiny contributions from many addresses and make `forward` or `lapse` exceed the block gas limit.

There is also an unresolved allocation question when only some case credit is consumed:

> Funder 1 contributes 10, funder 2 contributes 10, and only 5 is needed. Whose 5 was used?

The state machine needs a no-loop rule. A reasonable construction is:

* Record `totalFunding`.
* Record each address's contribution.
* At forwarding, calculate `fundingUsed`.
* Store one case-level refund ratio.
* Each funder independently claims its proportional refund later.

Conceptually:

```text
refundableFraction = (totalFunding - fundingUsed) / totalFunding
funderRefund = contribution[funder] × refundableFraction
```

Rounding dust can go to the reserve or the last claimant. On lapse, the refundable fraction is one.

This keeps T3 and T11 constant-cost regardless of how many funders exist. I would add traces for:

* Ten thousand one-wei funders.
* Two funders with partially used credit.
* A funder claiming before and after another funder.
* Rounding dust.
* Reentrant funding-refund claims.

---

## 4. `appeal` should only be callable by the host

Spec 0.3 currently gives T13 to "anyone."

That is unsafe for the target hosts.

Light GTCR's `fundAppeal` implements the appeal game: it records contributions, applies winner/loser multipliers, tracks funded sides, advances `roundCount`, subtracts the appeal cost, and only then calls its configured arbitrator's `appeal`.

The real Kleros arbitrator requires its arbitrable contract to call `appeal`. In the wrapped arrangement, that arbitrable contract is the wrapper.

Therefore, if an arbitrary EOA can call:

```text
wrapper.appeal(...)
```

the wrapper calls K, and K sees a valid call from its arbitrable. But the GTCR host never ran `fundAppeal`, so:

* The appeal multipliers were bypassed.
* The host's contribution records were not updated.
* `roundCount` was not advanced.
* An attacker may be able to force an appeal for only the bare appeal cost.
* Later fee-and-reward accounting can become inconsistent.

The fix is pleasantly small:

```text
T13 caller: HOST only
```

Anyone who wants to fund an appeal should use the host's existing `fundAppeal` function. The wrapper's appeal views remain public.

I would treat this as a must-fix before writing the contract.

---

## 5. Passivity is conditional on insurance, but some invariants remain unconditional

The document now contains a useful solvency trade-off, but the "spine" occasionally talks as though the trade-off does not exist.

S1 says a silent party reaches court after one window. I6 says a silent requester reaches court at the deadline and a silent removal is forwarded. But T3 and T9 both require `covered(id)`. An underinsured case with no funder does not reach court; it reaches refusal after the additional funding period.

There is a simple trilemma here:

1. Never reject a challenge for lack of reserve.
2. Guarantee passive escalation to court.
3. Use a finite reserve under arbitrary concurrent demand and fee increases.

You cannot make all three unconditional. v0.7 chooses the first and third, with underinsurance and lapse as the exceptional result. That is defensible; the wording should reflect it.

I would introduce two explicit operating modes:

* **Fully insured:** passive court guarantee through `maxCost`.
* **Underinsured:** challenge accepted, but court depends on available free reserve or case funding; lapse is possible.

Then qualify S1, R3, I6, and the passivity table accordingly. That is clearer than calling underinsurance disclosed while retaining unconditional liveness language elsewhere.

### Removals deserve stronger wording

The same issue is particularly sensitive for removals. An underinsured removal can remain unforwarded and ultimately receive a refusal ruling, leaving the item registered on Light GTCR. That is materially weaker than "removals are passed straight to court."

Also, the named incentive in T3/P1 is backwards: on a clearing request, the **requester** wants removal, while the challenger's winning ruling keeps the item registered. Light GTCR's ruling logic confirms that challenger victory on a clearing request returns the item to `Registered`.

So the transition should say:

> anyone; primarily the removal requester's interest

For the pilot, I would require a much stronger reserve condition for removal cases—or a dedicated keeper—because the stage-1 wrapper should not accidentally turn removal challenges into a new holding pattern.

---

## 6. A correctly funded but reverting resolver can strand a case

The state machine says that if K's call reverts, the transition reverts and the case remains where it was. But lapse is available only when the case is **not covered**.

That leaves a gap:

* `covered(id) == true`
* `K.arbitrationCost(...)` works
* `K.createDispute(...)` nevertheless reverts
* Escalation cannot complete
* Lapse cannot execute because the case is covered

The case has no terminal path.

This does not necessarily require a complicated fallback arbitrator. Two reasonable choices are:

**State the assumption plainly:** liveness is conditional on K accepting a correctly funded, correctly encoded dispute.

Or introduce a small failure state:

```text
ForwardAttemptFailed
```

A caught K revert records the failure without finalizing. Anyone can retry. After a separate resolver-failure grace period, governance or a predefined emergency route becomes available.

The same general point applies to a permanently reverting host `rule`, although trusting the host profile and host contract is a more natural hard assumption.

I would add a short "environmental assumptions" section distinguishing:

* Properties enforced by the wrapper.
* Properties assumed of the host.
* Properties assumed of K.
* Properties supplied by the reserve governor.
* Properties supplied by the evidence UI.

That will make the security story easier to understand than treating every dependency failure as another attack-table row.

---

## 7. Reserve accounting and governance need a few sharper definitions

### The stated target appears to double-count earmarks

The spec defines `free` as reserve balance excluding earmarks. It then gives the target:

```text
free ≥ Σ(maxCost − q) over open cases + floor
```

But a fully insured open case has already moved `maxCost − q` out of `free` and into its earmark.

For one case with liability 10:

* A total reserve of 10 can earmark the complete liability.
* Afterwards, `earmark = 10` and `free = 0`.
* The case is fully insured.
* Yet the stated target says `free ≥ 10`.

That target effectively requires twenty units for a ten-unit liability.

The likely intended health condition is one of:

```text
totalReserve ≥ totalLiability + floor
```

where:

```text
totalReserve = free + Σ earmarks
```

or:

```text
free ≥ totalUncoveredLiability + floor
```

Extra spare capacity for future cases is sensible, but it should be separately named rather than hidden in the solvency equation.

### "Nobody's revenue" is not yet enforced

Positive `q − c` flows into `free`. G3 then permits the governor to withdraw `free` to an arbitrary address after a timelock and while no case is open. The accounting does not distinguish:

* Capital originally contributed by the governor.
* Donations from other reserve funders.
* Underwriting surplus earned from court cases.

So the pool can, in fact, become governor revenue.

A cleaner model would separately track:

* **Reserve principal**, returnable to its provider only after safe decommission.
* **Underwriting surplus**, which either lowers future quotes or migrates to a successor reserve.

Alternatively, state candidly that the existing host governor controls reserve surplus. Since it already governs the list, that may be an acceptable trust choice, but it is different from saying the pool is nobody's revenue.

### The timelock announcement is missing from the state machine

G3 requires a withdrawal to have been announced earlier, but no operation creates that announcement. There should be something like:

```text
announceReserveWithdrawal(amount, to, nonce)
cancelReserveWithdrawal(nonce)
executeReserveWithdrawal(nonce)
```

The announcement must bind both `amount` and `to`; a generic "withdrawal was announced at time T" is not sufficient.

---

## 8. The machine-readable source is useful, but not executable yet

Adding the YAML and drift checker is a very good move. It improves the repository immediately.

A few things should be tightened before calling it the source for executable fixtures.

### I12 is literally false

At or after `fundingEnd`, for a covered `Open` case, both T8 and T9 are satisfiable for the requester:

* T8 permits the requester.
* T9 permits anyone, including the requester.

Both lead to the same outcome, so this is not an exploit, but the invariant says exactly one transition is satisfiable.

A simple correction is to make T8 explicitly the **early** path:

```text
T8: requester, now < deadline, no live bid
T9: anyone, now >= deadline
```

Then the transitions are disjoint and the invariant becomes true.

### The event model has small mismatches

Examples:

* T1's YAML event list contains `CaseOpened` but omits the conditional `UnderInsured`.
* T4 and T6 can cross and settle, but their event lists do not represent the resulting `Settled`.
* T12 names `Ruling` in YAML, while the prose event catalogue does not clearly list a wrapper `Ruling` event.

### The renderer checks formatting, not semantics

It currently verifies that one Markdown block matches the YAML. It does not check:

* Duplicate transition IDs.
* Unknown state IDs.
* Missing conditional events.
* References to nonexistent transitions.
* Terminal-state reachability.
* Mutually exclusive guards.
* Symbolic balance conservation.
* Reserve operations, which are omitted from the JSON fixture output.

That is completely fine for a first renderer, but I would describe the YAML as **structured specification data**, not yet an executable state machine.

Some high-value next steps:

* Add a schema validator.
* Include reserve operations in `fixtures`.
* Generate a Mermaid or Graphviz state diagram.
* Generate symbolic balance deltas rather than English money strings.
* Add a tiny Python reference model.
* Run `render.py check` and schema validation in GitHub Actions.

At present there is no repository CI directory, so drift protection still depends on someone remembering to execute the script.

---

## 9. The Polymarket note is much better, with one new boundary to add

The revised callback timeline is coherent:

```text
front dispute
→ settlement window
→ either concession without adapter callback
→ or forwarding followed by callback
```

That fixes the previous contradiction.

Two later-stage points remain.

### Repeated concessions need an absolute bound

As written, after a concession the front permits a new proposal without consuming the adapter's one reset. Nothing in the note caps how many times this can repeat.

I therefore infer that a sufficiently motivated actor could repeatedly:

1. Propose.
2. Dispute.
3. Concede.
4. Start a fresh liveness period.

The Store fee makes this non-free, which is good, but market-manipulation value can greatly exceed protocol fees. I would add either:

* `MAX_CONCESSIONS_PER_QUESTION`, or
* An absolute question-level deadline after which the next dispute must forward.

That preserves the useful "wrong proposals do not consume Polymarket's reset" property without permitting unbounded resolution delay.

### The callback is intentionally reentrant

When the front eventually calls `priceDisputed`, the adapter's callback immediately resets the question by calling `requestPrice`, `setEventBased`, `setCallbacks`, and possibly `setBond` and `setCustomLiveness` on its configured oracle—which is the front.

So forwarding will look roughly like:

```text
front → adapter.priceDisputed()
      → front.requestPrice()
      → front.setEventBased()
      → front.setCallbacks()
      → ...
```

The front must be deliberately reentrancy-compatible for this callback sequence. It cannot simply put one global `nonReentrant` guard around forwarding and request creation. This deserves one explicit trace in the insertion note.

I would also soften or source the statement that wrong early bot proposals are "the common case." The architectural argument works without that empirical claim.

---

## Smaller cleanups

A set ask persists after the deadline and remains executable until forwarding, while the text also says no offer is live at or after the deadline. Mechanically, I understand the distinction: after the deadline the ask is an executable quote but no longer blocks escalation. Naming it that way would remove the semantic contradiction.

The release manifest points readers to specification section 13 for Curate V2 support, while the host-profile table is section 14. More generally, I would pin one **release-head commit or tag** containing both artifacts. At the pinned spec commit `c9338de`, the spec already refers to design v0.7, but that design is added only in its child commit `c78064b`. A single release head avoids partially self-referential component commits.

The README says all of `spec/` is CC BY, but `spec/render.py` is code and the root license says code is MIT. Giving `render.py` an SPDX header and adding a dedicated CC BY notice for the Markdown/YAML would remove ambiguity.

The claim that the governor can do nothing to an open case should be accompanied by "the wrapper is non-upgradeable." An upgradeable factory/proxy would invalidate that claim even if all ordinary parameters are immutable.

## Extra traces I would add now

Alongside the traces already in the roadmap:

1. Self-challenged cases occupy all earmarks until just before the deadline.
2. Many requests are submitted under an old epoch and challenged simultaneously.
3. The old wrapper's reserve is withdrawn after migration but before old requests' challenge periods expire.
4. Ten thousand dust funders contribute to one case.
5. Multiple funders are partially consumed.
6. An EOA calls the wrapper's `appeal` without using `host.fundAppeal`.
7. `K.arbitrationCost` succeeds but `K.createDispute` reverts.
8. A removal opens underinsured and its challenger refuses to forward.
9. A reserve withdrawal is announced, then cases open and close before execution.
10. Repeated Polymarket concessions reach the proposed absolute question limit.

## Bottom line

Net-net: **I like v0.7 a lot more than v0.6.** It now feels like one coherent mechanism rather than several good ideas held together by unresolved fee accounting.

The main conceptual frontier is the reserve. Once settlement cases receive real earmarked insurance, "free self-settlement" stops being only a UI nuisance and becomes a capacity question. That is probably the most interesting new design problem here.

The funder-loop and appeal issues are concrete and easy to classify: they should simply be fixed before Solidity. The reserve-capacity and latent-liability issues require a more explicit policy choice, but they do not require abandoning the architecture.

I would keep stage 1a exactly as small as it now is. Fix host-only appeals, make funding refunds lazy, add the resolver-failure assumption or state, clarify insured versus underinsured behavior, and write a safe reserve-retirement procedure. After that, I'd feel pretty good about moving from prose into a reference model and contract skeleton.

This is getting quite real now—in a good way.
