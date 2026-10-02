# RFC 002: Parallel-backed Polymarket resolution and cheaper concessions

**Status:** draft 0.1 for discussion. Not part of design v0.9, not an executable specification, and not a deployment proposal.

**Base:** Intendment `main` at `0ac661c018eab0547c7a255998287cc78258e156`.

**Scope:** the full Polymarket mechanism proposed in the design discussion, including the correction that concessions remove a person's backing, never an outcome or another person's backing. The timing completion below is a proposed review default. Funding and reward allocation remain substantive design gates, not minor implementation details.

This RFC proposes replacing the fee-preserving Polymarket approach in the [earlier insertion study](oracle-insertion-polymarket.md). That study is retained for history. The Kleros baseline, RFC 001, release manifest, models and implementations are unchanged. Their tests do not validate this redesign.

## The idea, without the machinery

One market has a small set of possible answers. Many people may independently put money behind the same answer.

Everyone shares a fixed resolution schedule. Someone may concede and withdraw their own position, paying a stated penalty. They cannot withdraw anyone else's position, remove an answer from the available choices, or restart the schedule.

At the deadline, one remaining, sufficiently reviewed answer can resolve optimistically. Conflicting answers require one authoritative UMA decision. No remaining answer is not a vote for NO: it needs a separate fallback. A separately funded request for authoritative adjudication cannot be cancelled by two other parties settling.

The point is to stop a self-challenging pair from owning the only route forward. If they want to stop an honest backer, they must leave a funded conflicting position or fund actual adjudication. Their private concession loop cannot keep resetting everyone else.

**Parallel participation. Independent backing. One shared deadline. One authoritative answer.**

The intended benefit is cheaper correction of mistakes and less time with money tied up. It is not a claim of lower trading fees, free adjudication, or solved oracle governance.

## 1. What changes from the earlier study

The earlier study places a concession window before forwarding a dispute to UMA. It deliberately pays UMA's Store as though the proposer lost a vote, even when no vote happens. It also preserves the adapter's automatic reset after a concession. [1]

This proposal changes both the economics and the source of progress:

| Earlier approach | Proposed direction |
|---|---|
| One proposal/disputer pair controls the current local case. | Anyone may independently back a candidate answer; the first pair does not own the process. |
| Concession reopens a proposal round. | Concession affects only the conceding position, within the same fixed epoch. |
| The normal UMA charge is preserved on concessions. | No automatic UMA payment for a purely local concession. Any retained local charge must be separately justified. |
| Retry limits and an external charge restrict repeated restarts. | The main defence is that private settlements cannot restart public progress. Limits may still protect resources, but cannot censor the independent route. |
| No separate outcome-reward design. | Concession penalties provisionally feed an epoch reward pot rather than an immediate first-challenger bounty. Distribution remains open. |

The core idea is consistent with the baseline's third-party protection principle: settlement must not monopolize the only public path to act. It does not repeal the baseline's observation that transfers between two controlled wallets are not a cost to their owner. It tries to remove the shared bottleneck those transfers previously let the owner occupy. [2]

## 2. The example has to work whichever answer is true

### If NO is correct

Alice backs YES. Another wallet she controls opposes it. Alice concedes and repeats with fresh positions.

Bob independently backs NO. Alice's transactions cannot change Bob's backing or the epoch deadline.

If nobody keeps a conflicting answer backed, Bob's sufficiently reviewed NO can resolve. If Alice keeps YES backed, the disagreement goes to the shared oracle process. Alice cannot withdraw Bob's position or cancel that process with a settlement elsewhere.

### If YES is correct

Alice's concession must not delete YES. Carol can also back YES:

```text
YES
  Alice: conceded
  Carol: active, funded

NO
  Bob: active, funded
```

Carol keeps YES alive. If Bob concedes, a sufficiently reviewed YES can resolve. If Bob stays, UMA decides. Ten extra wallets backing NO do not outvote Carol: this is not a majority poll.

If nobody honestly backs the correct answer, optimistic resolution may be wrong. The claim is conditional on an honest, sufficiently funded participant getting a transaction included in time and keeping their position active. It is not a guarantee that honest participation will exist.

## 3. Objects and authority

### Market and epoch

The market key binds the chain, actual market/condition identity and integrating contract. It is not an arbitrary description or requester-chosen salt. All wrapper positions that affect the same trader payouts must use the same authoritative process.

An **epoch** is one attempt to resolve that market under fixed terms. Its opening record binds:

- the market key, epoch number, question/rules version and evidence interpretation;
- the finite outcome set and the time at which the question is being judged;
- the opening time, proposal cutoff, minimum review period and final deadline;
- backing requirements, concession terms, reward policy and oracle funding policy;
- the oracle route, accepted result mapping and authority to report market payouts.

None of those terms may change underneath live positions. A new request timestamp or adapter callback cannot create an independent reset budget. Future policy changes apply only through an explicit new-epoch or new-market rule.

### Outcomes and backing positions

An outcome is a canonical value, not one wallet's proposal text. For a supported binary market the terminal values might be YES and NO; a split payout is allowed only where that market's rules and contract support it. This draft does not assume all Polymarket market types have the same answer set. [3]

A backing position records its owner, market/epoch, outcome, creation time, escrow and status. Only its owner may concede it. Multiple positions may back the same outcome. Each qualifying position must meet the published funding requirement; an unfunded comment does not acquire a veto.

A supported outcome has at least one active qualifying position. Counts and total stakes do not select the truth. One qualifying honest backer is enough to keep their outcome represented.

Positions are individually identified even when an owner creates more than one. Same-wallet and different-wallet positions must be treated alike for the threat model; address counts are not proof of independent people.

### Challengers and evidence

Backing a conflicting outcome is the economic form of a challenge. Anyone can also submit evidence without creating another outcome or another mandatory dispute.

The first objection receives no exclusive right to escalation or market control. Later participants need not reproduce every prior objection, and every copy of an answer must not require a separately funded defence.

An objection that the event is not yet decidable needs a **nonterminal** route. It must not be forced into a false YES or NO claim. Section 7 distinguishes this from a split payout and ordinary oracle failure.

## 4. The clock: a fixed deadline still needs a full review period

A bare rule saying "the sole answer left at the deadline wins" is unsafe. A new answer could arrive just before that deadline without giving anyone time to respond.

**Proposed review default:** give each epoch an initial proposal period followed by a full review period:

```text
opens                 proposal cutoff A               final deadline D
  |---- proposal period ----|------ full review L ------|
                                               D = A + L
```

The durations are parameters to test, not chosen production values. Opening is permitted only under the market's predeclared eligibility rule. Contract time alone does not prove an external event has happened.

Any qualifying position entered by `A` is eligible to support optimistic resolution at `D`, provided that exact position remains active through the deadline. Conceding and reopening produces a new position and a new qualification time. Another backer's timely position remains unaffected.

A new fully funded conflicting position may still be submitted during review, before `D`. This preserves the last-minute objection path. But a late position cannot become an optimistic winner merely because every timely position concedes. If the only remaining answer lacks timely active backing, the epoch requires oracle adjudication instead.

At `D`, backing and concession changes close whether or not a keeper has called the sealing function. Every mutating entry point checks the deadline; transaction ordering after `D` cannot silently change the snapshot. Settlement does not extend `A`, `L` or `D`.

This is a conservative timing completion, not a free efficiency improvement: the initial proposal period may make a clean market slower than today's simple proposal window. Measure that cost. A future per-outcome-clock design needs a separate finality rule; it must not be silently substituted here.

## 5. Concession and an independent right to adjudication

### Conceding a position

Before `D`, the owner can concede their own backing position under the epoch's fixed terms. The transition:

1. Removes that position from active backing, not the outcome itself.
2. Moves its stated penalty into the epoch's provisional reward pot.
3. Makes any genuinely uncommitted remainder claimable by the owner.
4. Leaves every other position, deadline and committed oracle request unchanged.

Re-entering an outcome requires a new funded position. There is no bounty just for creating and conceding positions, and no transfer to a self-appointed challenger on each cycle.

The penalty cannot spend money already earmarked for the oracle. A position with a committed obligation may lose its active backing status only under a transition that preserves the earmark. After the deadline snapshot, private withdrawals cannot erase the frozen disagreement.

A concession is a financial/procedural action, not a juror finding that a particular allegation was true.

### Separately funded escalation

Before `D`, any participant may irrevocably commit an independently funded request for the epoch's authoritative decision. The required full forwarding escrow is checked; an unfunded flag does not reserve this route. The public question, time and oracle are already fixed by the epoch, not selected by the caller.

For this draft, forwarding becomes eligible at `D`, preserving the common review opportunity. The commitment survives every later concession. A second caller joins the existing request or supplies evidence; they cannot create a competing authority or renew its clock.

Funding this optional route is not a way to seize another user's bond, receive the entire reward pot, or spend a public subsidy automatically. Its maximum cost and refund terms must be published before commitment. Ordinary honest participation should not require using this more expensive option when a timely outcome position suffices.

Once a committed case can be forwarded, anyone may execute that transition using its escrow. The executor does not become the economic winner just by calling a function. A keeper payment, if adopted, pays for useful execution and comes from a separately bounded budget.

## 6. The deadline decision and finality

At `D`, the epoch seals its active outcome set, timely-backing flags, funding commitments and reward entitlements. The seal must operate on a bounded outcome set, not iterate over every backer.

| Snapshot | Next action |
|---|---|
| Exactly one terminal outcome, with timely active backing; no committed adjudication | Resolve optimistically to that outcome. |
| Two or more supported outcomes | Commit one authoritative oracle request. |
| One terminal outcome but only late backing | Oracle adjudication; no shortened optimistic review. |
| No supported terminal outcome | No invented answer. Follow the funded no-answer fallback or remain visibly unresolved. |
| A funded independent adjudication was committed | Use that request, even if a sole answer remains. |
| Only a nonterminal "not yet decidable" position remains | No trader payout and no unilateral reset; use the specified oracle/nonterminal policy. |

Different outcomes count as disagreement regardless of how many wallets or how much money is on either side. Ten YES positions and one NO position still mean one unresolved question.

The implementation shape is:

```text
Open
  -> sealed at the fixed deadline
       -> Resolved, for a safely reviewed sole terminal answer
       -> NeedsOracle
            -> OraclePending, once the exact forwarding call is funded
                 -> Resolved, for a supported terminal oracle result
                 -> AwaitingEvent, for an authenticated nonterminal result
            -> FundingShortfall, if the forwarding quote cannot be met
```

There is at most one authoritative adjudication identity per epoch. It may have oracle-internal rounds, but competing wrapper requests cannot race to set different payouts. Once committed, its question, relevant time and destination are immutable; a recovered oracle is retried under the same authority, not replaced by a new private settlement.

A valid final result reports market payouts once. Unclaimed bonds, reward calculations, stale callbacks and unrelated historical disputes do not reopen the market or block trader redemption. Financial claims use separate pull payments.

## 7. "Too early," no answer and oracle failure are different

A terminal split payout is not the same as "the event has not happened yet." Polymarket and UMA documentation describe special treatment for premature proposals; the concrete identifier and market adapter must support the exact mapping used. [3][4]

An authenticated Too-Early/ignore result can end this epoch without a terminal payout and permit a later epoch. It must not reinterpret earlier backing against a later world state. The new epoch has a new relevant time and a fresh full review schedule.

The conditions for reopening must be fixed in advance: for example an observable eligibility condition and a minimum retry delay, plus a fresh funding requirement. A conceding wallet cannot declare Too Early for everyone. An oracle-approved nonterminal result is not evidence of a self-settlement delay attack, but repeated premature openings still need cost and scheduling analysis.

No backing at the deadline, a depleted fee escrow, a failed callback and an oracle outage are **not** Too Early. None automatically starts another cheap epoch or produces YES, NO or a split.

This draft leaves the exact no-answer payer and reopening predicate open. Without those choices, unconditional eventual resolution is not a demonstrated property.

## 8. Where the money goes

### Fee-saving opportunity

In the classic OOv2 source, each side escrows `B + F`; opening a dispute sends `F + floor(B / 2)` to UMA's Store. The charge occurs at dispute creation, not after the vote. The source explicitly relates the burned bond share to costly delay even when both sides are controlled by the same party. [4]

Using the discussion's illustrative `B = $500`, `F = $250`, and no proposal reward:

| Classic adjudicated case | Amount |
|---|---:|
| Proposer escrow | $750 |
| Disputer escrow | $750 |
| Total escrow | $1,500 |
| UMA Store payment | $500 |
| Winner receives, including returned escrow | $1,000 |
| Winner's net gain | $250 |
| Loser's net loss | $750 |

These are example parameters, not a claim about every current market or collateral token. Actual deployment values must be read and pinned.

Avoiding the real dispute can avoid that $500 charge. A retained local charge and extra execution costs reduce the saving. Paying a penalty into a user reward pot is a redistribution among participants, not payment for UMA adjudication.

The proposal therefore drops automatic UMA payment on local concessions. Whether any smaller local charge is needed remains an economic question. It cannot be justified merely by calling the old charge unavoidable.

### Provisional concession reward pot

The latest proposal puts concession penalties into an **epoch-level reward pot** for successful active backing of the final answer. It avoids immediately paying a self-challenger, but it is not yet a complete incentive solution.

The following rules are fixed requirements for evaluating a distribution:

- One finite pot; no full bounty per challenger and no reward based on address count.
- Eligibility freezes no later than the deadline. After the result becomes known, nobody can join to collect it.
- A conceded position has no entitlement through that position. A genuinely new position is evaluated under its own time and risk commitments.
- A trader's payout does not depend on processing every reward recipient.
- Splitting one eligible economic stake across wallets must not increase its aggregate entitlement, except for explicitly analysed rounding effects.
- No reward for self-created activity from an external subsidy unless the subsidy has a separately demonstrated anti-farming design.

The distribution rule is **open**. "First correct backer" creates an ordering/front-running contest. Stake-proportional rewards favour capital and permit dilution by later large stakes. Time-weighted or locked-share rules add complexity. Backing every outcome and later collecting on the winner must be analysed using total gains and losses across all controlled wallets.

If Alice concedes and later also backs the correct answer, her eventual recovery is not automatically harmless. The required question is whether the entire strategy subsidizes disruption or crowds out useful reviewers. The earlier conversational claim that a market-level pot itself solves bounty capture is withdrawn here.

For no winner, Too Early, or an oracle result nobody backed, the disposition of the pot must be specified before opening the epoch. Do not silently give it to the finalization caller, governance or a new epoch. Until a policy is selected, the pot cannot be advertised as a working challenger compensation mechanism.

### Oracle funding is a separate commitment

Reward money, refundable position principal and money promised to UMA are not interchangeable.

A useful ledger partition is:

```text
contract cash = uncommitted position escrow
              + reserved oracle escrow
              + undistributed reward pots
              + claimable user credits
              + separately funded operating budgets
```

A unit of currency appears in exactly one bucket. Moving it changes the corresponding liabilities atomically. A concession cannot refund or award collateral that still backs an oracle obligation. A funding receipt is not cash until the funds have actually arrived.

The classic forwarding sequence may need **both full bonds**, not just the nonrefundable Store charge. Under the example above, that is $1,500 of available escrow even though the final Store payment is $500. Extra proposal rewards, buffers and execution costs must be accounted for separately. [4]

Two funding directions remain to choose between: earmarked participant collateral, or an explicit prepaid per-epoch sponsor budget. Neither may be silently treated as free insurance. Participant funding needs deterministic allocation when many outcomes/backers exist; sponsor funding needs protection against adversarially forced expenses and repeated epochs. The zero-backer and late-singleton routes must be covered too, not just the easy two-sided case.

An epoch may claim a funded fallback only to the extent its actual reserve covers the declared quote range. Cost increases beyond coverage lead to a disclosed shortfall and a top-up path; they must never authorize an unreviewed answer, seize promised refunds, or reset the review clock. This draft has no solution guaranteeing availability under arbitrary fee increases or permanent oracle failure.

The exact selected funding policy, loss waterfall, surplus return, refusal treatment and allocation of the oracle's returned funds are prerequisites to a normative state machine.

## 9. What the design does and does not prevent

### Conditional progress argument

Assume one honest participant enters qualified backing for the correct terminal answer by the proposal cutoff, keeps it active, transactions are included, required funding is available, and the oracle is available and adjudicates correctly when used.

Other wallets can withdraw only themselves. Therefore the honest position still appears at the deadline. Either it is the only sufficiently reviewed answer, or disagreement causes one authoritative oracle decision. Private concession loops cannot remove that position or extend the epoch.

That is the intended non-blocking property. It is a design argument to test against the implementation, not a completed formal proof or an economic-equilibrium result.

### Remaining risks

An attacker can still leave a wrong position backed and force adjudication, at the configured real economic exposure. Cheap local settlement does not mean genuinely disputed outcomes can be decided without a resolver.

An attacker can occupy storage or flood interfaces with positions. Resolution must iterate over the fixed outcome set, and claims must be individually withdrawable. A per-market limit that lets an attacker fill all slots would recreate exclusion; resource controls cannot close the honest backing or adjudication path.

A one-backer liveness argument is not proof that someone will want to be that backer. Reward capture, all-outcome hedging, griefing against someone else's stake, transaction ordering and proposer willingness to concede remain economic questions.

No mechanism here defeats chain censorship, proves the oracle's independence, or replaces absent honest monitoring. Retaining a small charge is an option to test; retaining the entire old UMA payment is not a requirement assumed by this RFC.

## 10. Integration: not a drop-in concession button

The old study is a useful source of adapter constraints, but this proposal changes more than its callback timing. [1]

The classic OOv2 request records one proposer and one disputer. Parallel backing therefore lives in Intendment. A single canonical request represents the unresolved market question when UMA is needed; multiple backing positions do not become multiple outcome-setting votes. UMA's Internal Optimistic Oracle pattern is precedent for custom local escalation logic, not evidence this design already works. [4][5]

The classic Polymarket adapter stores an immutable oracle address and resets on the first dispute callback. The integration must ensure its authoritative epoch is not replaced by that reset. A new adapter version or explicit market-side module is likely needed; merely pointing the old adapter at another address is not claimed sufficient. Existing markets stay under their original resolution authority. [1][6]

The integration review must settle:

| Boundary | Required property |
|---|---|
| Current deployment | Identify the exact market type, collateral, oracle, permissions and adapter/reporter version. Public source is not proof of deployed configuration. |
| Request identity | One canonical market/epoch question; duplicate wrappers and request timestamps cannot create competing payout authorities. |
| Question and time | Preserve the epoch's rules and relevant time. Classic event-based OOv2 derives its DVM time from proposal timing; recreating a proposal later must not make an originally premature assertion valid. |
| OO proposer/disputer mapping | Specify who supplies both bonds and receives OO proceeds. UMA's binary proposer-versus-disputer payout is not automatically the payout rule for multiple candidate answers. |
| Unbacked oracle answer | A supported authoritative result may differ from every privately backed answer. Market correctness takes priority; reward/funding treatment must already be specified. |
| Callbacks and evidence | Map real backers and original evidence; support expected callback nesting; reject stale-epoch callbacks without blocking unrelated valid settlement. |
| Nonterminal results | Distinguish valid split, Too Early/ignore, malformed response and outage. Never coerce them into one default payout. |
| Finality | Only the selected authority may report payouts, once. Outstanding bond claims cannot delay that report. |

For the source review, the classic OOv2 file had blob SHA `da64e9ac7ba72e8bba27c99593db5c1c8fa40249`; the classic adapter file had blob SHA `da8ebd9d1b23bc644888c149939a92da302f55bf`. A prototype must additionally pin chain, addresses, implementation code hashes and a block. No live deployment compatibility is asserted here.

Approach Polymarket first for product and protocol feedback. Do not promise that all current integration paths can be changed without UMA coordination or permissions review.

## 11. Draft invariants and acceptance traces

The invariants to implement and test are:

1. Only a position's owner can concede it; no concession mutates another owner's backing.
2. Outcomes are fixed canonical values. Address count and stake majority never select the result.
3. Private actions do not extend the epoch schedule.
4. Optimistic finality requires a sole terminal outcome with timely active backing and no committed adjudication.
5. At most one authoritative adjudication identity exists per epoch; funded commitments cannot be cancelled by private settlement.
6. Every cash liability is funded, isolated and allocated at most once; no concession releases a live oracle earmark.
7. Review and finalization do not iterate over an unbounded list of wallets, funders or obsolete positions.
8. Oracle failure, zero backing and Too Early are distinct states; none implies an arbitrary terminal answer.
9. A terminal market result is reported once; financial claims and stale callbacks cannot reopen it.
10. Reward claims are bounded by available funds and cannot be multiplied simply by adding addresses.

These are **tests to write**, not tests run by this PR:

| Trace | Required observation |
|---|---|
| Correct answer NO; other wallets repeatedly concede YES positions | Timely honest NO backing and the shared deadline remain unchanged. |
| Correct answer YES; Alice concedes her YES while Carol keeps YES | Carol's backing remains; YES is neither deleted nor presumed wrong. |
| Ten conflicting wallets versus one honest qualifying backer | One unresolved question, not a majority result or ten mandatory cases. |
| Many duplicate positions and many subsequent concessions | Work to seal remains bounded by the outcome set; the public route stays open. |
| Last timely backer concedes; only a late backer remains | No optimistic finalization without a full review period. |
| Back/concede/seal calls at the exact deadline in different orderings | The timestamp guards yield one immutable deadline state. |
| A funded independent decision request followed by every position conceding | Its funding and authority survive; no payout uses its reserved cash. |
| Concurrent forwarding or duplicate callbacks | At most one accepted authority and one market payout. |
| First challenger refuses to execute an eligible funded request | Another caller can execute; it does not steal the winner's financial rights. |
| Escrow quote rises within and beyond declared coverage | Covered forwarding works; shortfall is explicit and never fabricates a result. |
| No remaining backers; no sponsor; or no winning privately backed outcome | No default-to-NO, double-spending, unbounded debt or silent pot seizure. |
| Oracle returns Too Early versus malformed response versus outage | Only the authenticated nonterminal path can authorize a fresh epoch under policy. |
| Proposal recreated at UMA after a delay | The pinned question and original relevant time are preserved. |
| Split stakes, all-outcome hedging, self-concession and re-entry | Aggregate rewards/costs reveal whether cycling can subsidize disruption. |
| Reverting recipient, lost keeper, stale evidence or adapter reset | Funds remain claimable, failure is visible, and no private action replaces authority. |

## 12. Open decisions and delivery gates

| Decision | What must be chosen or demonstrated |
|---|---|
| Epoch timing | Eligibility, proposal-period length, review duration and late-objection treatment; quantify delay added to clean markets. |
| Funding | Exact reserve provider, collateral obligations, quote bounds, shortfall recovery, zero-backer fallback and returned-fund allocation. |
| Rewards | Concession penalty, discount, pot eligibility/weights, payout on nonterminal or unbacked outcomes, and behaviour under Sybil splitting and hedging. |
| Nonterminal epochs | Precise Too-Early encoding, retry eligibility and funding, with no freely renewable private reset. |
| Integration | Canonical request/time mapping, current adapter/oracle permissions, full cash flow and one-time payout reporting. |
| Operational assumptions | Monitoring, keeper budget, outage handling and disclosed governance powers. |

The next deliverable is a small isolated model of these rules with a chosen funding and reward policy. It should explore all deadline branches and use integer cash accounting. Then compare alternative reward policies and adversarial incentives; passing accounting tests alone does not establish good incentives.

Only after those choices pass review should the project write a normative state machine and a pinned-fork adapter prototype. Nothing in this RFC imports success claims from the Kleros model or authorizes live-fund deployment.

Measure at least actual external fees, collateral tied up over time, market payout time separately from backer refund time, participation capital, successful concessions, forced adjudications, and the cheapest bounded disruption. The shared schedule can save fees yet slow some uncontested cases; report both.

The pitch remains simple: **people should be able to admit a mistaken position without paying for an unnecessary oracle vote, and their private settlement should not control anyone else's route to resolution.** Whether this draft achieves that economically as well as procedurally remains to be demonstrated.

## References

[1] [Earlier Polymarket insertion study](oracle-insertion-polymarket.md), retained as the fee-preserving serial design, not silently rewritten by this RFC.

[2] [Intendment design v0.9](intendment-design-v0.9.md), especially S4, S7, S10, S14, S15 and S20. This RFC proposes a different Polymarket mechanism; it does not amend the normative stage-1 specification.

[3] [Polymarket resolution documentation](https://docs.polymarket.com/concepts/resolution). Background for review periods and outcome handling, not a frozen contract specification or a claim about every market type.

[4] [Classic UMA OptimisticOracleV2 source](https://github.com/UMAprotocol/protocol/blob/master/packages/core/contracts/optimistic-oracle-v2/implementation/OptimisticOracleV2.sol): `proposePriceFor`, `disputePriceFor`, `_settle`, `_computeBurnedBond`, `_getTimestampForDvmRequest`, and `_stampAncillaryData`.

[5] [UMA Internal Optimistic Oracle documentation](https://docs.uma.xyz/developers/optimistic-oracle/internal-optimistic-oracle): architectural precedent for local proposal/escalation logic with an oracle backstop.

[6] [Classic Polymarket UmaCtfAdapter source](https://github.com/Polymarket/uma-ctf-adapter/blob/main/src/UmaCtfAdapter.sol): immutable oracle, dispute callback/reset, and final payout mapping.
