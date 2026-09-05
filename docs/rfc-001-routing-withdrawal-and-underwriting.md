# RFC 001: Neutral resolver routing, challenge withdrawal, and deposit underwriting

- **Status:** Draft for discussion. Not accepted, implemented, audited, or authorized for deployment.
- **Date:** 2026-09-05.
- **Baseline:** [design v0.9](intendment-design-v0.9.md) and [stage-1 state machine 0.5](../spec/intendment-arbitrator-state-machine.md); see [the release manifest](../RELEASES.md).
- **Scope:** Three independently reviewable extensions and their possible product/business model. This RFC does not amend the baseline, change its release head, or gate its concession-only pilot on implementing these extensions.
- **Origin:** The maintainer's proposals for unanimous resolver choice, scalar-priced challenge withdrawal, and reputation-backed deposit financing. The safeguards and experiments below are proposed for review, not represented as decisions already made by the maintainer.

## Abstract

Intendment could become a neutral settlement and capital layer above optimistic systems: parties can concede **or withdraw**, negotiate the permitted financial consequences, jointly select an eligible resolver when adjudication remains necessary, and obtain financing for deposits that otherwise limit useful participation.

This RFC explores three mechanisms:

1. **Consensual resolver routing:** after a challenge but normally before a backend dispute is created, all required rights-holders may agree to use a different, pre-authorized resolver. Absent agreement, the original backstop remains available on the original schedule.
2. **Scalar-priced challenge withdrawal:** a withdrawing challenger and the submitter negotiate a number in `[0, 1]` that allocates a specified pool of unused arbitration fees. A separately funded scalar adjudication is an optional, policy-approved fallback, not a recursive dispute ladder.
3. **Reputation-backed deposit financing:** an underwriter supplies part of a participant's required deposit, absorbs defined losses, and records an obligation to repay. A lower upfront contribution is distinguished from reducing the host's security deposit. Fully funded credit is distinguished from a contingent guarantee and from fractional reserving.

The potential moat is an adopted, neutral coordination layer plus reliable capital and operations, not exclusive access to Solidity. That is a business hypothesis, not an established network effect. Each mechanism must justify its integration cost, capital risk, and effect on third parties independently.

## 1. Motivation and non-goals

### 1.1 The problem worth testing

The maintainer reports, from observing Scout registries, that submission throughput is often constrained by capital locked in deposits. This is the demand hypothesis motivating deposit financing; this RFC does not present it as an independently measured dataset. Challenge-side financing may be less valuable where challengers already face relatively small capital requirements.

Settlement addresses another constraint: a participant may recognize a mistake or resolve a disagreement, yet still face an expensive adjudication path. Concession alone does not cover an honest challenger who wants to withdraw. Nor should a disagreement over compensation necessarily keep the underlying application blocked.

Resolver choice creates a third possibility: the parties still disagree, but agree that another eligible venue offers more suitable costs, timing, or expertise. A neutral intermediary may be better placed than an individual court to present competing venues. Courts could nevertheless implement routing themselves or support the same interface; neutrality is a positioning advantage, not a technical barrier to entry.

### 1.2 Proposed vision

> Intendment lets optimistic applications retain their public verification rules while participants negotiate exits, finance participation, and route remaining disagreements to an agreed backstop.

The three jobs are separate: deciding whether a claim remains active; allocating private financial liabilities; and determining which resolver has authority. An agreement about one must not silently decide the others.

### 1.3 Non-goals

This RFC does not propose a token, a public lending launch, an unrestricted resolver marketplace, automatic reputation scores from raw wallet history, or a claim that capital guarantees resolver availability. It does not assume that Kleros and UMA share interchangeable dispute semantics, or that moving between chains is a simple address change.

Named products and networks are candidate integrations from the discussion, not a verified deployment or compatibility matrix. The document does not rely on unfinished external research.

## 2. Relationship to the existing design

The baseline already specifies withdrawals as later host-side transitions, separates settlement from fee underwriting, fixes the wrapper's resolver, and restricts reserve surplus to non-revenue uses. It also records failed anti-recycling mechanisms. Those constraints are the starting point, not obstacles silently removed by this RFC. See design v0.9 sections 1, 3, 6, and 7.

| Baseline rule | Consequence for this proposal |
|---|---|
| S3: withdrawn challenges restart review in full | A withdrawal cannot approve the underlying claim or shorten public review. |
| S4/S5: self-settlement is an internal transfer; chosen item IDs are cheaply replaced | No reputation or subsidy scheme may treat distinct addresses, item IDs, or settlement counts as proof of independent activity. |
| S6: the host's deterrent deposit is not reduced | The first financing variant supplies the missing deposit, rather than asking the host to accept less. Private deterrence still changes and needs separate analysis. |
| S7: third-party protection is system-specific | Bilateral agreement is insufficient where it removes an outsider's remedy or determines public payouts. |
| S10/S13/S14: explicit execution assumptions and constrained emergency outcomes | Routing and lending must not manufacture new court-blocking or refusal options. |
| S11/S17/S20: isolated reserve, non-revenue surplus, separate settlement and underwriting guarantees | Participant credit needs separate capital, accounting, and commercial terms. Existing surplus is not available to appropriate. |
| S18/S21: host appeals and party-of-record identity are preserved | A routing or financing account cannot accidentally bypass appeals or impersonate the recorded party. |

The scalar withdrawal proposal may conflict with the baseline's no-free-griefing requirement: a nearly complete refund can make delaying a valid request cheaper. That conflict must be resolved or explicitly accepted by a new host policy; it is not eliminated by calling a challenge well intended.

Likewise, resolver selection is a new mechanism, not a setting that can be turned on in the fixed-resolver stage-1 wrapper. New deployments and, for some effects, host changes are required.

## 3. Proposal A: consensual resolver routing

### 3.1 Define what “mid-dispute” means

Distinguish three points in the lifecycle:

- **Challenged, not forwarded:** the case exists in Intendment, but no backend court has accepted it. This is the initial routing target.
- **Accepted by a backend, not finally ruled:** switching requires an explicit cancellation, refund, and authority-transfer protocol. This RFC does not assume that current backends provide one.
- **Ruled or in appeal:** changing venue risks bypassing existing appeal rights or shopping after an unfavorable result. Excluded from the first implementation.

Thus the initial feature is “agree on the forum for an open challenge,” not “abandon an active court whenever its trajectory becomes inconvenient.” Sunk fees do not become refundable merely because the parties agree to move.

### 3.2 Who may agree, and to what?

At claim creation, the host policy commits to a default resolver `R0` and an eligible resolver policy. The first experiment uses a fixed, versioned menu. Candidates discussed include Kleros deployments on different chains and UMA; listing a candidate here does not establish that it is technically or economically substitutable.

The requester and challenger must both authorize a route change. Additional economic rights must be covered by explicit consent or a narrowly defined mandate granted before financing or participation. For example, a lender could approve a specific venue menu and fee cap when making a loan, rather than acquiring a new veto during the dispute.

Public interests are handled by the host's ex-ante policy, not by pretending every trader or registry consumer is a signatory. The menu must preserve the rights and remedies the host promised. If that cannot be demonstrated, rerouting is unavailable even with both visible parties' signatures.

Unanimity is among required rights-holders, not all observers. Identifying those rights-holders is part of integration review.

### 3.3 A routing agreement binds the entire adjudication package

A signed agreement should identify at least:

```text
host, sourceChain, caseId, requestId, caseNonce
policyHash, evidenceReference, evidenceCutoff
resolverAdapter, destinationChain, destinationResolver, configurationHash
questionEncoding, outcomeMapping, refusalMapping
feeCurrency, maximumInitialFee, payerAndRefundRules
appealPolicy, appealFundingResponsibility
executionDeadline, agreementExpiry, fallbackRules
```

The schema is conceptual, not a proposed ABI. It must be domain-separated and support the actual recorded account types. Two signatures over a venue name alone are insufficient: the parties may otherwise be agreeing to different questions, appeal costs, or ruling mappings.

The default resolver's authority is not removed by a partial signature, stale quote, unfunded proposal, or failed routing attempt. Routing negotiations do not restart the settlement deadline. The first implementation permits at most one accepted alternative selection; a broader system still needs a fixed overall deadline.

### 3.4 Execution and failure

For a same-chain route, validation, funding, backend acceptance, and the transition of authority should be atomic where the backend permits it. On failure, there must be no recorded successful transfer of authority or loss of the original execution path. Escalation racing a route change must select exactly one backend.

Cross-chain routing requires a different state machine: authenticated messages, finality assumptions, replay protection, source/destination identity, fee conversion, and an acknowledgment protocol. A timeout alone cannot safely authorize a second court if the first may already have accepted the case. Recovery must resolve uncertain acceptance rather than allow two independently final rulings.

Cross-chain routing is therefore a later, separately reviewed extension. Capital can cover fees; it cannot prove message delivery or make a halted court operate. A cheaper destination is not cheaper after bridging, messaging, evidence transport, appeal funding, and recovery costs unless those costs are included.

### 3.5 What would demonstrate value?

Start with two compatible same-chain test backends and a funded, original default. Exercise consent, quoting, evidence identity, outcome mapping, and every routing race. A subsequent live pilot needs actual cases in which both parties prefer the alternative after all costs, not merely different prices displayed in a frontend.

The hypothesis fails commercially if parties almost never agree, or technically if maintaining equivalent rights costs more than routing saves. Resolver outcome disagreement and reversal rates may inform review but are not simple truth scores.

## 4. Proposal B: scalar-priced challenge withdrawal

### 4.1 Preserve the original idea

The proposed scalar `s` lies in `[0, 1]` and represents a policy-defined assessment of the challenge's justification or good faith. A high score lets an honest mistaken challenger recover more unused fees; a low score allocates more to the submitter. The parties first negotiate or trade over that number. Only an unresolved scalar question goes to its configured resolver.

The intended benefit is an exit for a challenger who corrects a mistake without being treated identically to a deliberately obstructive challenger. Withdrawal remains a first-class goal, not a concession feature with a different label.

### 4.2 Specify the money before specifying a market

Let `F_w` be the **actual escrow available for allocation on withdrawal**, after separately identified irreversible costs and any disclosed nonrefundable charge. It is not the sum of two UI fee quotes, a refund of money already paid to jurors, or the submitter's base deposit.

Using integer scale `S`, with `0 <= s <= S`:

```text
refundToChallenger = floor(F_w * s / S)
compensationToSubmitter = F_w - refundToChallenger
```

For an illustrative pool of 20 units, `s = 0.9` allocates 18 to the challenger and 2 to the submitter; `s = 0.1` allocates 2 and 18. No outside subsidy is implied.

Every host integration must specify a complete ledger: the origin of `F_w`, the treatment of each party's deposit and other fees, which amounts remain locked for renewed review, and the terminal credits. The equation allocates only `F_w`; it is not a complete replacement for the host's withdrawal accounting. No actor's total debit or credit may be counted twice.

The stock wrapper does not control the host's pot or implement a withdrawal with restart. This mechanism requires the host-side custody and lifecycle capabilities already identified for stage 2.

### 4.3 Adjudicate an observable question, not a private mental state

“Good intent” is the motivation, but a resolver cannot directly observe a participant's thoughts. Candidate rubrics include the reasonableness of the objection under the published rules and evidence available when it was raised, the materiality of the identified uncertainty, and whether later evidence explains the withdrawal.

A host must publish a rubric, evidence cutoff, and score anchors before a challenge. Outcome accuracy, probability of winning the original case, reasonableness, and usefulness of review are different quantities. They must not be collapsed into one undefined score.

An agreed score is an economic settlement. It is not independent proof of honesty, an admission that the submission is valid, or a safe training label for the credit system.

### 4.4 Two tracks to compare

**Track W0: negotiated allocation, existing fallback.** The parties agree to the withdrawal and fee split together. Until an agreement executes, the original challenge and its existing escalation schedule remain in force. The existing costly unilateral withdrawal path, where supported, is not silently replaced by a cheap exit. This track tests demand with the least new mechanism.

**Track W1: committed withdrawal, separate scalar case.** Under a policy selected before the challenge, the challenger makes an irreversible withdrawal commitment. The host restarts public review immediately, while the fee-allocation escrow remains unresolved. The parties negotiate `s`; if they fail, a funded scalar resolver decides only that allocation.

W1 separates registry progress from the compensation dispute. It must not let the challenger reinstate the old challenge after seeing a low score. New independent challenges remain possible under the host's normal rules. A scalar ruling neither registers an item nor rules on the merits of a withdrawn challenge.

For W1, publish a terminal rule for silence, resolver refusal or outage, and failure to fund scalar adjudication. One candidate is a conservative fixed allocation accepted in the ex-ante policy; another is requiring the entire scalar fee to be escrowed before entering W1. Which allocation is acceptable remains open. There is no new permissionless right to impose an unfunded second case on the other party.

### 4.5 Avoid an infinite regress and a larger fee than the one saved

Scalar adjudication needs its own quoted cost, payer, deadlines, and bounded appeal policy. If adjudication spends part of `F_w`, the split must use the remaining pool; if it is funded separately, that debit must appear in the ledger. The same fee cannot both pay the resolver and be refunded.

There is no settlement dispute about the settlement of the scalar dispute. A finite adjudication/appeal path ends it. If the expected cost of this path exceeds the money or delay saved, W0 or a simple fixed withdrawal schedule is the better design.

“Only deciding a number” does not establish lower adjudication cost: assessing reasonableness may require essentially the original evidence plus an additional policy judgment.

### 4.6 What makes it a prediction market?

A bilateral agreement over `s` is bargaining. It becomes a market only when positions have defined collateral, payoff, trading, and settlement rules. An experimental scalar claim could pay `s` per fully collateralized unit, with a complementary claim paying `1-s`; its settlement authority must be explicit.

The first prototype should use bilateral, collateral-bounded quotes without external open interest. If outsiders trade positions that settle on `s`, the original two parties cannot privately choose a number that changes those outsiders' entitlements. Such a public market needs a separate design, including how its outcome is determined when the original parties settle. Resolving that by another unbounded market simply moves the problem.

The connection to futarchy is an inspiration about prices and incentives, not proof that this mechanism implements futarchy or discovers objective intent. Thin liquidity and endogenous settlement can make a displayed price uninformative.

### 4.7 Deterrence and abuse are the central open issue

A high refund can reward correction, but it can also let a challenger repeatedly delay good requests cheaply. Parties may own both wallets. A zero-sum transfer between them does not pay for outsiders' review effort, reserve occupancy, or growing registry history.

Candidate mitigations include a nonrefundable challenge/withdrawal cost, a separately charged capacity cost, a meaningful minimum compensation, or restricting W1 to an explicitly governed pilot. None is a solved policy. Per-wallet or freely chosen item-ID limits are not Sybil resistance.

The experiment must measure useful challenges and harm to valid requests, not maximize withdrawal rate. The design must also retain the baseline's restrictions on removals and oracle disputes where withdrawal would remove an outsider's only remedy.

## 5. Proposal C: reputation-backed deposit financing

### 5.1 This is different from the current reserve

The existing reserve covers movement between a fixed arbitration quote and the resolver's eventual fee. Participant financing covers a different risk: a submitter loses a deposit or does not repay a loan.

These exposures need separate underwriting, balance sheets, consent, and loss limits. No loan, default, or commercial distribution in this RFC may consume the baseline's earmarks, claimable credits, funder refunds, or non-revenue surplus.

### 5.2 First variant: fully fund the host deposit

Let `D` be the host's required base deposit, `u` the participant's upfront contribution, and `l` the amount supplied by a credit pool:

```text
D = u + l
```

The host still receives the whole deposit. The participant experiences a lower upfront requirement, not a reduction in the funds protecting the registry. Fees, gas, interest, and any challenge-side deposit are accounted separately.

For an illustrative `D = 30`, `u = 6`, `l = 24`, a submitter with 600 units could contribute to 100 simultaneous deposits rather than 20, ignoring every other cost and eligibility constraint. The pool must actually supply 2,400 units. The total 3,000 locked in the host has not disappeared; capital has been supplied by someone else. Fivefold borrower capacity in this example is not a system-wide fivefold creation of capital.

This is the first variant to test because a funding failure can stop **a new financed submission**, without stopping a challenge to an already admitted claim.

### 5.3 Identity, custody, and control of repayments

Funding must happen atomically with the intended submission, or through an account that prevents borrowing against one action and spending the advance elsewhere. The financing agreement binds the host, exact request, policy, principal, own contribution, permitted settlements, resolver menu, and fee caps.

A generic router becomes the host's party of record; the baseline explicitly warns against assuming otherwise. A user-owned constrained account, an explicit custody structure, or a host extension may be necessary. Each option changes implementation or trust assumptions. The actual account must receive host payouts safely and route repayments without relying on a later voluntary transfer by an anonymous borrower.

An enforceable claim on returned deposits or identified rewards is different from a promise to repay. Assignability and collectible amounts must be checked for each integration.

### 5.4 Cashflows and loss allocation

A minimal proposed waterfall is:

1. The borrower supplies `u` and the pool supplies `l`; the host holds `D`.
2. When returnable collateral is released, the pool is repaid principal before residual borrower equity. Separately disclosed financing fees follow their own agreed priority.
3. If a deposit is slashed or settlement consumes collateral, the borrower bears its own contribution at risk and the pool recognizes any unrecovered principal.
4. A borrower repayment obligation for that shortfall is recorded under the credit agreement. Voluntary future repayment may restore eligibility gradually; it does not undo the host outcome.

Ignoring fees, if `R` units of the financed deposit are actually recovered:

```text
poolRecovery = min(l, R)
borrowerResidual = max(R - l, 0)
poolShortfall = max(l - R, 0)
```

Thus borrower equity absorbs the first reduction in returned collateral under this waterfall. Full deposit loss in the example costs the borrower 6 and the pool 24, before any later collection.

The exact treatment of concession, withdrawal, refusal, partial return, and appealed rulings must be specified. A negotiated exit is not automatically a win. Final slashing is an underwriting loss; refusal or inability to pay an amount due is a credit default. They are related, not identical events.

Unpaid debt is not counted at face value as liquid reserve. Recovery, accounting impairment, suspension of new advances, and charge-off rules are explicit. Losing borrowers cannot restore trust merely by cycling another subsidized account through a repayment.

### 5.5 Keep legitimate exits usable without letting borrowers give away the pool

A financed borrower must not be able to concede pool-funded collateral to a collaborator and leave the debt behind. Conversely, an improvised lender veto can trap parties in unnecessary litigation.

The proposed solution is an ex-ante settlement mandate: the loan defines which losses, exits, resolver choices, and claim assignments it authorizes. It cannot authorize changes to third-party rights. A first pilot may require an underwriter-approved case-specific settlement or a narrow preapproved schedule.

That adds friction and may reduce the product's value; measure it. The mandate must not give a lender the power to block the host's challenge path or extend public deadlines. Funding a participant does not confer authority to decide the underlying registry policy.

### 5.6 Reputation is an input, not collateral by itself

Potential signals should retain their provenance:

| Signal | Possible value | Limitation |
|---|---|---|
| Unchallenged acceptance | Evidence of sustained participation under a particular policy | May reflect no inspection, low reviewer capacity, or easy submissions. |
| Court win | Independently adjudicated outcome for a particular question | Depends on venue, policy, appeal finality, and correlated errors. |
| OoC agreement | Evidence that the parties chose an exit and financial allocation | Cheap to manufacture between related wallets; not an independent merits judgment. |
| Successful repayment | Direct evidence about an actual credit obligation | Can be purchased to build a larger exit opportunity; history cost must be compared with attainable exposure. |
| Stable, valuable activity over time | May make account abandonment expensive | Persistence of an address alone establishes neither identity nor recourse. |

Start with a known, opt-in submitter cohort, small limits, meaningful borrower equity, and aggregate exposure limits across correlated accounts where supportable. Keep public challenge access permissionless; credit eligibility is a separate question. Do not claim to have solved permissionless unsecured lending.

An attack model must include cheap history farming followed by one large loss, self-challenges, purchased accounts, borrower/collaborator transfers, several financed positions opened before an adverse event is recorded, and coordinated borrowers defaulting together. Reputation should not mint credit faster than the cost of manufacturing that reputation, absent another credible source of recourse or security.

### 5.7 Preserving the host deposit is not preserving private deterrence

With financing, a borrower may expose only `u` of immediately collectible personal wealth while the registry receives `D`. If repayment is unenforceable and the identity disposable, the remaining private downside is mostly loss of future access. This can encourage worse submissions even though the host is fully funded.

The key question is whether increased useful throughput exceeds the additional invalid submissions, review burden, and lender losses. First-loss contributions, credible collection, reward assignment where feasible, conservative credit growth, and concentration limits are candidate controls, not proof of incentive compatibility.

Challenger financing can follow if measured demand warrants it. It should not be added merely for symmetry.

## 6. Fractional reserving: a distinct, later proposal

Three quantities must not be conflated:

- **Liquidity:** cash available when deposits must be posted or guarantees called.
- **Loss-absorbing capital:** assets available to absorb credit or guarantee losses.
- **Committed exposure:** obligations already promised, including cases not yet challenged or finalized.

Fully funded lending to an unmodified host requires cash for every advanced deposit. Reserving only a fraction of expected credit losses does not supply the rest of that cash. Borrowing wholesale funding could finance it, but creates a separate funding liability and maturity risk.

A true contingent-guarantee variant would let an adapted host accept `u` in cash plus a promise covering `D-u`, rather than holding all of `D`. Aggregate promises could exceed immediately available reserves. That changes the host's security model: an adversary may cause many calls at once, and the promise can fail when most needed. It is not available merely by placing the stage-1 wrapper in front of an unmodified registry.

Candidate reasons losses may be correlated include a shared policy interpretation, one submission batch containing the same defect, common external dependencies, a resolver outage, and coordinated account abandonment. Premium income and expected future repayments are not present cash to honor calls.

A fractional-reserve proposal would require a separate acceptance decision covering maximum leverage, concentration limits, stress scenarios, liquidity and loss waterfalls, provider withdrawal restrictions, committed backup funding, and the host's explicit outcome if payment fails. It must not advertise unconditional payment or court access from a finite, insufficient pool.

For illustration, `expected loss = exposure * probability of loss * loss given default` can inform pricing. It is neither a worst-case bound nor a solvency test, and correlated portfolios cannot be justified by adding independent-case averages. Pilot measurements must distinguish earned premiums, realized losses, unpaid receivables, and fresh capital contributions.

The recommendation is to test fully funded credit first. Whether guarantee leverage is ever desirable remains open. Public capital solicitation, lending, guarantees, and representations about protection require a separate jurisdiction-specific legal and operational review before launch; this RFC supplies no legal conclusion.

## 7. Architecture and possible business model

### 7.1 Reuse without pretending the hard parts are configuration

A shared kernel could cover case identity, consent, signed offers, timers, terminal-state exclusivity, and authenticated routing commitments. Resolver adapters translate evidence, questions, costs, and rulings. Host adapters control withdrawal, review restart, public rights, custody, and final application effects. Credit vaults supply funding and enforce agreed repayment routes.

Some product policy can be declarative. Other differences are genuine state-machine differences: an immutable host, a multi-answer history, a reset callback, cross-chain acceptance, or a nonassignable payout cannot be wished into a configuration field.

The test of a reusable platform is the third integration after two substantially different hosts, not a diagram drawn before either works. The kernel must remain usable without buying financing or a hosted service.

### 7.2 Revenue hypotheses

Possible revenue includes disclosed capital/time charges on financed deposits, premiums for explicitly bounded guarantees, paid integration and operations, and transparent routing fees where users receive measurable net value. Funding costs, bad debt, audit and operational costs, and capital lockup must be subtracted before calling any of this profit.

Fees should be committed before the relevant action, not extracted opportunistically from parties already locked in a case. Existing baseline surplus stays non-revenue. A commercial credit vault needs new, explicit terms and no cross-subsidy from settlement liabilities.

Routing neutrality also requires disclosure of commissions and ranking methodology. A router that secretly favors its own vault or highest-paying court is not the neutral product proposed here. Settlement should not be discouraged because adjudication earns more revenue.

### 7.3 Moat hypotheses and falsifiers

Open code can be copied. Possible durable advantages are accepted integrations, audited compatibility, an operating record, repeat-user distribution, reliable committed capital, and underwriting information that demonstrably improves decisions. Public on-chain data alone is not exclusive. Courts can offer competing routes; a standard can create ecosystem value without providing its maintainer revenue.

The company hypothesis weakens if credit demand is small, losses consume its margin, every integration remains bespoke, routing is rarely used, or users do not pay for reliable operations. In that outcome, Intendment may still be valuable as an open standard or component of Intendancy rather than a standalone business.

## 8. Required adversarial traces

New models must exercise interactions, not only each feature in isolation. At minimum:

| Area | Trace and required property |
|---|---|
| Consent | Missing, expired, replayed, or domain-mismatched signatures never authorize routing or withdrawal. |
| Routing race | Default forwarding races alternative selection; at most one resolver gains effective authority. |
| Quote failure | Alternative fees rise or acceptance fails; no partial debit or loss of the valid default path. |
| Cross-chain uncertainty | A delayed acknowledgment cannot create two final backends through an unsafe timeout fallback. |
| Rights | The two visible parties cannot route around third-party remedies, host appeals, or a pre-existing financing mandate. |
| Withdrawal | Review restarts in full; the scalar case cannot register the item or revive the withdrawn challenge. |
| Scalar accounting | At `s=0`, `s=1`, and rounding boundaries, payments plus funded costs conserve escrow. |
| Scalar failure | Silence, refusal, an unaffordable fee, and outage have finite, pre-agreed outcomes without recursive cases. |
| Griefing | Repeated high-refund withdrawals quantify delay and review costs imposed on valid submissions. |
| Fake reputation | Related wallets generate OoC wins and scalar scores; these do not automatically create additional unsecured credit. |
| Financed self-challenge | A borrower concedes to a collaborator; pool-funded value is not treated as a successful borrower outcome. |
| Portfolio loss | Several requests lose together before limits update; liquidity and capital shortfalls are visible rather than hidden as receivables. |
| Repayment | Partial return, impairment, later repayment, and account abandonment cannot double-count assets or restore limits mechanically. |
| Shared boundaries | Credit losses cannot consume settlement credits, earmarks, or refund liabilities; lender failure cannot block existing challenges. |
| Retirement | Outstanding funded requests, guarantees, unclaimed credits, and disputed repayment obligations survive migration correctly. |

The existing stage-1 model does not validate these extensions. Any new tests must be identified as new models, not credited to the baseline's current CI coverage.

## 9. Experiments and decisions before implementation

### Experiment 1: measure and shadow-price deposit financing

Use an opt-in, known submitter cohort. Record actual amounts and duration of locked deposits, deferred useful submissions, review capacity, challenge outcomes, and available collectible repayments. Run a shadow credit book before putting pool capital at risk. Separate capital constraints from limits in demand, preparation effort, or reviewing capacity.

**Advance when:** there is meaningful demand for financing at a price that plausibly covers funding, losses, and operations, without unacceptable growth in invalid submissions. A small fully funded pilot follows separate review.

### Experiment 2: model withdrawal before opening a market

Implement W0 and W1 as separate experimental ledger/state models. Compare a negotiated split, a simple fixed withdrawal price, and the scalar backstop. Include passive parties, scarce reviewer attention, self-challenges, and financing-aware settlement permissions.

**Advance when:** the scalar mechanism adds value beyond a simpler withdrawal rule and does not buy small fee savings with larger adjudication costs or cheap harassment. Public secondary trading remains a separate proposal.

### Experiment 3: prove a portable route between two backends

Use two same-chain, compatible test backends. Prove evidence/question identity, consent, funding, appeal compatibility, exclusivity, and fallback behavior. Then identify a real host with a legitimate alternative-venue demand.

**Advance when:** the route is safer or cheaper after total costs and does not weaken the host's public guarantees. Cross-chain routing and switching already accepted court cases are not part of this first gate.

These experiments are independently rejectable. None is a prerequisite for finishing the stage-1a implementation. A successful credit experiment does not validate scalar markets; a successful routing experiment does not validate fractional guarantees.

## 10. Open decisions

1. What observable rubric should the scalar measure, and how much refund is compatible with deterrence?
2. Should the host offer W0, W1, both, or neither; what precisely happens when scalar adjudication is unavailable?
3. Which rights-holders must consent to a route, and which protections cannot be waived bilaterally?
4. Can two actual resolver configurations preserve equivalent question, evidence, refusal, and appeal semantics?
5. How are financed accounts and repayment claims implemented without breaking the host's party-of-record and payout behavior?
6. Which borrower contribution, exposure limits, and settlement mandate keep default and self-dealing risks acceptable?
7. Does additional borrower throughput improve useful registry growth, or merely move a bottleneck to reviewers?
8. Is there a justified case for contingent guarantees after fully funded lending, and who knowingly bears their shortfall risk?
9. Which paid service has independent demand, and what remains valuable if the protocol is copied or adopted natively by courts?

## References and evidence boundaries

- [Design v0.9](intendment-design-v0.9.md): current constraints, payoffs, withdrawals, sequencing, third-party protections, and rejected mechanisms.
- [State machine 0.5](../spec/intendment-arbitrator-state-machine.md): fixed-resolver stage-1 accounting, party identity, reserve separation, and retirement assumptions.
- [Executable model README](../sim/README.md): the implemented model's scope and exclusions.
- [v0.8 independent review](intendment-design-v0.8-review-gpt.md): settlement versus underwriting, reputation-relevant outcome distinctions, and host-account integration concerns.
- [Oracle insertion study](oracle-insertion-polymarket.md): an existing integration hypothesis, not proof that every oracle-facing host supports the same transitions.

Demand observations and new mechanism ideas in this RFC originate in the maintainer discussion. Numerical examples are illustrative arithmetic, not measured returns, deployment parameters, or guarantees. Adoption requires new normative specifications, executable models, integration verification, and review; committing this RFC authorizes none of those outcomes by itself.
