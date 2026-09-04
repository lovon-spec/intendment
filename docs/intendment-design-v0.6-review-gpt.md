# Independent review of Intendment design v0.6

Review date: 2026-09-04. Reviewed: [`intendment-design-v0.6.md`](intendment-design-v0.6.md) at commit `4c16932`, with [`../spec/intendment-arbitrator-state-machine.md`](../spec/intendment-arbitrator-state-machine.md) 0.2 at `d292a3e`. Produced by GPT at the maintainer's request and reproduced verbatim; the maintainer's assessment and the changes it produced are in `intendment-design-v0.7.md`, section 12.

---

What feels especially strong
The "spine" is excellent. Recording the constraints, where they came from, and declaring later conflicting text wrong is unusually good design-document discipline. The rejected-rules section is equally valuable: it prevents future contributors from repeatedly rediscovering attractive-but-broken ideas such as item cooldowns, free early escalation, or casual multiparty challengers.
The sequencing is sensible. Concession first through an arbitrator wrapper; withdrawal only after gaining host-side custody; buy-outs only after observing the challenger market; oracle systems later; and no attempt to declare a standard until it has run in two systems. That is a credible route from mechanism to infrastructure rather than an everything-at-once protocol plan.
The third-party thinking is mature. The decision not to support removal settlement while one party can occupy the sole removal lane is correct. "The two parties agree" is not enough when the affected public is absent from the negotiation.
The court remains real. A good claimant can reject settlement and escalate immediately. Silence does not magically become concession. That distinction protects the mechanism from becoming a disguised default-judgment machine.
What I would change before a pilot
1. Choose one coherent fee-risk model
This is the biggest issue I see.
Let:
q be the fixed epoch quote paid by the challenger.
c be the real arbitrator cost when escalation occurs.
The present state machine refunds the challenger when c < q, but uses the reserve—and then potentially another caller—to cover the difference when c > q. In effect, the challenger receives the benefit of falling fees while some or all of the risk of rising fees is socialized.
That creates three problems:
The challenger does not always economically bear F_E, although the payoff table says it does.
The reserve cannot really be "replenished from quote margins," because positive spreads are returned to the challenger.
The reserve is providing a one-way hedge whose price is currently zero.
The funding order and refund rule are explicit in the state machine, while the design separately says the reserve will be replenished from margins. Those two choices do not currently fit together.
My preferred model would be a fixed-price court ticket:
B always economically pays q.
If q > c, the difference stays in the epoch reserve.
If c > q, the reserve covers the difference.
On a settlement, where no court risk materializes, the escrow can still be fully distributed between the parties.
That gives the epoch quote a clear meaning, makes the default concession price much easier to justify, and allows the reserve to operate like actual insurance rather than a subsidy. It would require revising the strict wording of S11, but a visible and coherent fee-risk pool is better than a hidden cross-case transfer.
The other coherent option is pure pass-through: B must cover the actual c, gets every surplus back, and there is no reserve insurance. That is economically clean but considerably harder to make passivity-safe with an unmodified host.
Whichever model you choose, reserve capacity should be reserved per outstanding case or per epoch. A shared reserve that covers one case in isolation may fail when twenty cases cross the same fee increase. Without reserved capacity, transaction ordering decides which cases receive insurance.
2. Make offer binding a property of the case, not of the sender address
The current state machine blocks A or B from escalating while their own offer is live, but T10 allows anyone to escalate after W. An offer owner can therefore use another wallet to call the permissionless path. Technically the named party did not escalate; economically the same actor did.
That conflicts with offer binding and Sybil neutrality.
A clean rule would be:
Permissionless escalation is unavailable while any binding offer is live.
No offer may remain live beyond the settlement deadline.
Posting an offer requires now + V <= deadline.
At the deadline, all offers have necessarily expired and anyone may escalate.
This avoids both the alternate-wallet bypass and indefinitely extended cases.
I would also tighten the offer API:
Use concede(maxPrice) rather than exact expectedY == ask.
Use acceptBid(minPrice) rather than exact equality.
Clearly specify what happens after an ask expires.
If a falling ask crosses a live bid, allow a permissionless match() with a predetermined price rule.
Because asks only improve for A and bids only improve for B, inequality-based slippage protection is safer and causes fewer needless transaction failures.
There is also a small specification inconsistency here: bids explicitly need to be live when accepted, while concession at an ask does not clearly require the ask to remain live. Offer expiry needs one unambiguous lifecycle.
3. Turn emergency funding into an actual state
T11 permits lapse when no funder has covered the shortfall, but the transition table has no separate fund or topUp move. A caller can provide money only as part of an escalation transaction.
That means a funded escalation can be front-run by lapse after the deadline. The winner is simply whichever transaction lands first—the same issue identified in the v0.5 review, now narrowed but not fully eliminated.
Either:
Add an explicit funding period and stored case credit, after which escalation and lapse become mutually exclusive; or
Under the fixed-price model, fully reserve the case's supported liability when it is opened and leave lapse only for a truly catastrophic cost above a declared maximum.
I would strongly consider leaving emergency lapse out of the first pilot altogether. A tiny pilot with ample, locked collateral is easier to reason about than a pilot containing a value-moving governance-failure branch.
Removal pass-through deserves special treatment too. A challenged removal should not eventually turn into a refusal ruling merely because nobody sent the second forwarding transaction. A bindAndForward route, paired with a small execution bounty, would better match the claim that removals behave as they do today.
4. Make the host trust boundary explicit
The standard is not quite "any ERC-792 arbitrable can point at it." It is "any compatible arbitrable for which there is a trusted adapter."
The wrapper needs host-specific knowledge of:
Request type.
Request-specific deposit—not merely the host's current configured deposit.
Requester and challenger.
Challenger-winning ruling.
Refusal behavior.
Evidence mapping.
Whether the host's payout semantics match the concession formula.
I would make that adapter a first-class object, with a small versioned capability manifest. For the pilot, the simplest safe architecture may be one wrapper per list or an explicit host allowlist. A permissionless host combined with a shared reserve creates an obvious reserve-griefing surface.
I would also change the quote encoding. Instead of appending an epoch word and depending on the real arbitrator ignoring trailing bytes, use an explicit wrapper envelope:
wrapperExtraData = (version, epochId, realArbitratorExtraData)
The wrapper decodes it and forwards only realArbitratorExtraData to K. That is cleaner, easier to version, and much more portable beyond one Kleros encoding assumption.
5. Make every payout failure-safe
No terminal transition should depend on A or B accepting a native-token transfer.
A hostile contract wallet, an accidentally non-payable address, or a reverting receiver should not be able to prevent concession, forwarding, or lapse. The wrapper can finalize the state and create withdrawable credits:
credits[A] += ...
credits[B] += ...
Recipients then claim separately, optionally to another destination. The state machine already lists failed receivers and reentrancy among the adversarial traces; using pull payments removes a large class of those cases at once.
6. Consider an even smaller first experiment
The first hypothesis is not really "will users conduct an on-chain bilateral negotiation?"
It is:
Will clearly losing requesters accept the challenger outcome before court if they can recover the unused arbitration fee?
You can test that with an extremely small mechanism:
One displayed fixed concession price.
One "concede" action.
One "go to court" action.
Court after the deadline.
No custom asks or bids are required initially. That version captures the most obvious avoided cases and makes the UX almost self-explanatory. The bargaining functions can be switched on only after the one-button version demonstrates demand.
For the pilot, I would predefine:
Court-avoidance rate.
Median added delay.
Fees saved after additional gas.
Reserve utilization and maximum drawdown.
Percentage of parties who act versus remain silent.
Default-price versus negotiated settlements, once bargaining is enabled.
Number of cases requiring keeper intervention.
The design already treats adoption data as the gate for later stages; making the measurements explicit now will prevent "successful pilot" from becoming subjective later.
Some cooler directions
Signed offers. EIP-712 plus ERC-1271 offers would let parties create binding asks or bids without first paying for an on-chain update. Anyone could submit the signed offer, enabling relayers and better smart-wallet support.
Monotone offer curves. Since asks are only meant to fall and bids only to rise, a party could publish a simple time curve rather than repeatedly update a price. A permissionless matcher settles when the curves cross. This feels particularly natural for Intendment, although I would keep it out of the first contract.
A keeper bond or execution bounty. A small amount can be refunded to B when B forwards or escalates on time, but paid to a third party when someone else must do it after the deadline. That turns "anyone may call" into an actual liveness incentive.
A minimal discovery interface. A standard read interface and common events for SettlementOpened, OfferPosted, Settled, and Escalated would let wallets, list UIs, indexers, and keeper networks integrate once instead of learning every host adapter.
Settlement profiles. I would frame the future standard as several outcome-preserving profiles:
Claimant concession.
Challenger withdrawal with review restart.
Recipient-bound buy-out.
Oracle proposal retraction.
The Kleros mechanism saves money; the Polymarket direction mainly saves resolution time. That is an interesting expansion of the thesis: the avoided deadweight may be resolver fees, latency, or both.
Machine-readable specification. Put states, preconditions, authorization, deadlines, and balance deltas into a small JSON/YAML source and generate the Markdown table and property-test fixtures from it. That would prevent the design and normative state machine from drifting apart again.
A few small cleanups
The README still says the state machine is "to come," even though it is now committed and normative. It should link directly to v0.6 and the stage-1 spec.
A tiny release manifest would also help because "design v0.6" and "specification 0.2" can look like different releases:
Intendment release v0.6
- design document: <commit>
- stage-1 state machine: <commit>
- supported host profiles: ...
- review status: ...
The bargaining equations introduce a nonzero refusal probability r, but then calculate thresholds as though court had only two outcomes. Either define p conditional on a non-refusal ruling or include the host-specific refusal payoffs.
The Polymarket note should eventually be rebased from v0.4. In particular, "call priceDisputed exactly as today" and "a conceded dispute does not consume the adapter's reset" need one explicit callback timeline; with the current adapter behavior, those claims do not automatically coexist.
Bottom line
Net-net, I'm into it. It feels like serious dispute plumbing rather than financial mechanism theater. The problem is real, the insertion point is credible, and the design has become impressively good at remembering why tempting alternatives failed.
I would call v0.6 ready for executable modeling and another adversarial review, but not quite ready for a value-bearing pilot. The three things I would settle first are the fixed-price-versus-pass-through fee choice, genuinely case-level offer binding, and the reserve/lapse state.
And honestly, the smallest version may be the most persuasive: concede at a known price, or go to court. If that quietly removes a meaningful fraction of pointless disputes, the larger vision becomes much easier to explain—and much harder to dismiss.
