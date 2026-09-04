# Audit of Intendment design v0.5

Review date: 2026-09-02. Reviewed document: [`intendment-design-v0.5.md`](intendment-design-v0.5.md), commit `7530951907aa495fdc217a038da84f179fa010f5`.

## Bottom line

v0.5 makes the right high-level corrections to v0.4. It removes the ineffective item cooldown and the unanalyzed multiparty challenger patch, treats independent removal prosecution as a host-layer prerequisite, distinguishes the three fee observations, and makes evidence routing a deployment gate. The resulting sequence is much more credible. In particular, the decision to fix the exclusive removal-request lane in the host, rather than masking it with parallel challengers, is the right one.

Stage 1 is nevertheless not ready for implementation or adversarial traces as described. The claimed stage-1 state machine is not part of the reviewed commit and the local draft still specifies v0.4. More substantively, a V1 list cannot select the wrapper for registration disputes alone: the same arbitrator hook handles registration and removal challenges, and the wrapper cannot identify which kind it received until after `createDispute` returns. The document therefore needs an explicit removal pass-through path. Its accounting also names `F_A`, `F_B`, and `F_E` but continues to derive prices and payoffs using one common `F`; who funds an escalation shortfall changes both parties' court payoffs. Finally, lapse is neither a neutral nor presently well-defined failure path. On the target V1 contracts it can award part of A's request stake to B without a merits ruling, creating a profitable challenge around a known fee increase.

My recommendation is **request changes**. Keep the sequence and the narrow concession-first target, but do not pilot it until the stage-1 adapter, exact money flows, fully funded escalation, evidence route, and executable state machine agree with one another.

## Findings

### 1. Blocker — the claimed stage-1 state machine is neither committed nor a v0.5 state machine

Section 11 says that [`spec/intendment-arbitrator-state-machine.md`](../spec/intendment-arbitrator-state-machine.md) exists and that adversarial traces are next. At the reviewed commit there is no `spec/` entry in the repository. At review time the file exists only as an untracked working-tree file (`?? spec/`). A reader of the GitHub commit therefore cannot inspect the artifact on which the roadmap relies.

The local draft is also explicitly a companion to v0.4 and materially disagrees with v0.5:

- it says there is no early escalation, while v0.5 adds E1 for A at any time and E2 for B after `W`;
- it proxies the resolver's live fee rather than defining immutable quote epochs;
- it treats a fee shortfall as an executor donation and gives lapse a condition that is not implementable as written;
- it leaves the evidence route undecided;
- it still refers to the removed per-item cooldown; and
- it contains no executable counterpart to C4.

The ask's numeric default is not by itself a contradiction—the old draft represents only B's share of the fee, while v0.5 appears to represent the total settlement price—but that change of representation also needs to be stated and proved in the accounting.

Recommendation: update and commit a versioned v0.5 state machine before writing traces. It should be the normative source for states, roles, deadlines, quote epochs, net payout formulas, request-type dispatch, evidence routing, and every external-call failure. The design document should not say this artifact exists until the linked commit actually contains it.

### 2. Blocker — a V1 arbitrator switch cannot apply to registration requests only

Stage 1 says the wrapper handles “registration requests only” and is adopted by changing a V1 list's arbitrator. That is not a selectable boundary in either V1 host.

Classic `GeneralizedTCR.challengeRequest` accepts both `RegistrationRequested` and `ClearingRequested`, then invokes the one arbitrator stored on the request with only `choices` and `arbitratorExtraData`. The item mapping is written only after `createDispute` returns. See the official [Classic challenge sequence](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/GeneralizedTCR.sol#L283-L325) and its single [governor-controlled arbitrator setting](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/GeneralizedTCR.sol#L563-L570). Light GTCR does the same: both request types use the request's one arbitration-parameter record, and its dispute-to-item mapping is also stored after the external call. See [Light's challenge sequence](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/LightGeneralizedTCR.sol#L390-L447) and [arbitration-parameter update](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/LightGeneralizedTCR.sol#L781-L819).

Consequently:

1. Re-pointing the list sends future challenged removals to the wrapper too.
2. During `createDispute`, the wrapper receives no item ID or request type.
3. The wrapper can resolve the type through the host only after its call has returned and the host has stored the local dispute mapping.
4. Merely making concession functions revert for removals is insufficient: without a separate path, a removal dispute waits in the settlement state or can become stranded.

This does not make the wrapper architecture impossible. It does mean that request-type dispatch is part of stage 1, not a later concern. A safe adapter needs an explicit post-bind fork such as:

```text
Unbound -> RegistrationOpen
        -> RemovalForwardable
```

Settlement functions must require `RegistrationOpen`; a removal must be forwardable to the real arbitrator immediately after binding, with a named caller and failure behavior. If “immediately” must mean the same transaction as the challenge for an EOA user, a router or host change is required. Otherwise the document must disclose the additional transaction and prove its liveness. Until this path exists, S7 is a policy statement that the proposed deployment cannot enforce.

### 3. Blocker — three fee names have not yet become three-fee accounting

Sections 1 and 2 introduce `F_A`, `F_B`, and `F_E`, but the payoff bands in section 2 immediately return to a common `F`, and the table still sets `s_B = F_B + D_c` and `g_B = D`. Those values are correct only under additional equal-fee and funding assumptions that are nowhere made invariant.

For a challenged V1 registration, let the host's pot after challenge be:

```text
P = D + F_A + D_c
```

The wrapper separately holds `F_B`. This follows directly from Light GTCR's [request accounting](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/LightGeneralizedTCR.sol#L297-L335), [challenge accounting](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/LightGeneralizedTCR.sol#L390-L447), and [ruling payout](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/LightGeneralizedTCR.sol#L607-L667); Classic has the same first-round pot shape.

If concession is expressed as a challenger ruling and `Y` means the net transfer from A to B, the wrapper must pay:

```text
refund to A = D + F_A - Y
refund to B = F_B - (D + F_A - Y)
```

The expressible interval is therefore:

```text
D + F_A - F_B <= Y <= D + F_A
```

At the proposed default `Y = D`, the wrapper must return exactly `F_A` to A. It can do that only if `F_B >= F_A`. Exact equality is the simple intended case, but “quotes are frozen per epoch” does not yet establish it. The epoch must be an immutable value selected by the `arbitratorExtraData` captured on the request; a mutable time-based quote allows a request and its later challenge to straddle an epoch.

Escalation depends on `F_E`, not `F_B`. If B bears the full resolver fee—including any shortfall—and excess `F_B` is returned, the money-only court outcomes are:

```text
A loses: s_A = D + F_A
A wins:  g_A = D_c
B loses: s_B = F_E + D_c
B wins:  g_B = D + F_A - F_E
```

If A, a keeper, or a reserve supplies `F_E - F_B`, those payoffs change again. A caller donation is not a detail outside the game: it decides who is worse off, what surplus settlement saves, and whether R1, R2, R8, and S11 hold. A reserve is external funding unless its capital and replenishment are explicitly charged to these cases, so it cannot simply coexist with a claim of budget balance “between the parties.”

Recommendation: specify the exact immutable epoch key, require and test the relationship between `F_A` and `F_B`, name who economically bears every wei of `F_E`, and derive all bands from those values. C1 and C3 should state net payouts, not merely “A pays,” because the actual implementation combines a direct host payout to B with a split of B's wrapper escrow.

### 4. Blocker — lapse is a profitable no-merits outcome, not a neutral liveness fallback

E4 says that, after a second deadline, anyone may lapse a case “if E1–E3 cannot fund `F_E`.” There are two separate problems.

First, inability to attract a voluntary top-up is not an on-chain predicate. If the escalation function is payable, it is always fundable by a sufficiently funded caller. If both escalation-with-top-up and lapse remain callable after the second deadline, ordering decides the outcome. If lapse merely checks `F_B < F_E`, a lapse caller can front-run someone who is ready to provide the difference. The mechanism needs an explicit funding state, stored contributions, a cutoff, and mutually exclusive post-cutoff transitions. It must also say which fee observation is locked if the resolver quote changes during that process.

Second, ruling 0 transfers real value. On Light GTCR a refusal restores the pre-request status and splits `P` equally between requester and challenger. With the Scout figures and `D_c = 0`, lapse does this:

```text
B originally pays F_B:       21.6
wrapper refunds F_B:         21.6
host pays B half of P:       25.8
B's net gain without ruling: 25.8
```

See Light's [refusal branch](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/LightGeneralizedTCR.sol#L645-L655). Classic V1 is different but still gives B value: it distributes the remaining first-round pot proportionally to the parties' recorded contributions. See [Classic's refusal accounting](https://github.com/kleros/tcr/blob/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts/GeneralizedTCR.sol#L399-L429).

This creates a concrete trace around an announced resolver-fee increase:

1. B challenges just before the increase and pays old `F_B`.
2. During the window, the real resolver's price becomes `F_E > F_B`.
3. B withholds the top-up.
4. Unless A or an external reserve pays the difference, B calls lapse, recovers `F_B`, and receives part of A's request stake without a merits ruling.

The wrapper has converted a challenge at the old fully funded price—which today would create court immediately—into an option to extract value after the fee increase. A may be able to buy court by supplying the shortfall, but then B has externalized part of its court cost onto A. This violates the substance of S1 and the stated court outside options even if lapse is labeled an exception to R3.

Recommendation: do not rely on refusal as an ordinary solvency mechanism. Once a challenge is accepted, escalation should already be fully collateralized for that quote epoch, whether through an epoch reserve funded and locked in advance or another explicit construction. If an emergency lapse remains, model it as a loss-bearing governance failure with its exact host-specific distribution and attack surface; do not describe it as equivalent to passive escalation.

### 5. High — the posted-price interface contains nonbinding bids and revocable “gifts”

Section 3.1 says each side may hold a standing ask and bid for each outcome. C4 lets A post a concession bid, but there is no transition by which B accepts it. B can only lower its own ask to the bid, after which A alone decides whether to execute C3 or E1. The result is not a bid: A reveals a nonbinding number and receives a binding lower ask in return. That gives A a free option and directly contradicts the claim that no revealed price can be exploited.

The interaction between W2 and E1 exposes the same missing rule in stage 2. A's withdrawal ask starts at `s_B` and can only move down, so after any reduction the payment A forgoes by escalating is **at most** `s_B`, not “at least the challenger's court loss” as section 4 says. A can lower the ask, observe B's attempted W3 acceptance, and front-run it with E1. Carrying an expected price prevents a price-update sandwich; it does not prevent the offer's owner from terminating the state first.

There are coherent choices, but the document must select one:

- make bids funded, counterparty-executable offers and add the missing accept transitions;
- make a lowered ask irrevocable until an explicit expiry and define whether it temporarily constrains the owner's escalation right; or
- permit revocation by escalation, but stop calling the value a standing bid or a monotone gift and revise R2/R4 accordingly.

The first-block C2 race is candidly accepted and is not this finding. The issue here is that the full mechanism's own transactions do not implement the price rights that its safety argument assumes.

### 6. High — evidence routing is a stated gate, but the proposed gate is still open

S9 correctly promotes evidence routing to a deployment precondition. Section 6 then says “the state machine chooses the relay,” while the only local state-machine draft explicitly leaves two options undecided.

An app prompt to resubmit evidence through the wrapper is not passivity-safe. In V1, challenge evidence is emitted by the list only after the wrapper's `createDispute` call returns—the Classic and Light challenge sequences linked above show that ordering—and earlier requester evidence exists only in the list's events. The wrapper cannot read those historical logs. If A or B becomes inactive after using the existing list UI, the real resolver must still receive the already-filed material.

The stage-1 gate should require one deployed end-to-end route:

- resolver UI/indexer support that follows the authenticated wrapper-to-list dispute mapping and renders the original list evidence; or
- an idempotent permissionless relay that proves the source event and preserves the original party, evidence group, URI, and request type, with a named incentive if liveness relies on a transaction.

A wrapper function that simply lets anyone emit an evidence URI under their own address is not an authenticated replay of the original event. Evidence may be open-submission, but party attribution and complete passive discovery still matter to jurors. The pilot should not begin until a test dispute demonstrates request evidence, challenge evidence, meta-evidence, appeals, and a silent party through the actual resolver interface.

### 7. Medium — several host-specific and spine claims need correction

The remaining issues are smaller individually, but they matter in a document intended to become a reusable standard:

- Section 2 describes Curate V2's half-split refusal while stage 1 targets “Kleros V1.” Light V1 also halves the pot, but Classic V1 distributes it proportionally. The selected Scout host and adapter must be named; “V1” is not one payout model.
- Section 5's phrasing appears to include Curate V2 among hosts “whose arbitrator is immutable.” The official base contract has a governor-only [`changeArbitrationParams`](https://github.com/kleros/curate-v2/blob/1d1d0311b3bbced6445edf669ce7cfae6c5fc866/contracts/src/CurateV2.sol#L305-L315) function. An arbitrable-side module may still be required for custody and restart, but immutability is not the reason for Curate V2; if the sentence means only Permanent GTCR, it should say so.
- S5 says no rule may be keyed on an item ID because item IDs are submitter-salted. That is true for anti-recycling rules on registrations, but S7 correctly observes that a removal target has one fixed ID. Narrow S5 to submitter-chosen registration IDs so it does not contradict the host-layer rule required for removals.
- S2 and section 4 say anyone can escalate “at the deadline,” while E3 says anyone only after `W` plus a grace period. S1, R1, R3, and the passivity table also promise court after one window. Select one timeline and state the extra delay honestly.
- “Anyone” names an authorization class, not an incentivized caller. E3 and E4 need the incentive S10 promises. On the EVM, a timeout changes no state by itself.

## What v0.5 gets right

The following choices should survive the next revision:

- The item cooldown is gone. Registration IDs can be re-salted, and a global cooldown would have granted a cheap lock over other users.
- Non-exclusive challengers are rejected until there is an actual multiparty model.
- Removal settlement is gated on independent removal prosecution. This fixes the exclusive public-action lane at the correct layer instead of asking an honest remover to join the semantically wrong side of somebody else's dispute.
- Registration self-settlement is treated as an actor holding its own claim, with challenged items separated in the UI, rather than as protocol-level censorship.
- The deposit remains the deterrent; settlement distributes only a genuinely avoided court cost.
- Evidence routing, fee variance, liveness, and third-party protection are explicit gates rather than implementation footnotes.
- Sequencing concession before withdrawal is sensible because the wrapper can express only the former with its limited custody.

## Recommended path to v0.6

1. Reconcile and commit the stage-1 state machine. Make it the exact executable interpretation of C1–C4 and E1–E4.
2. Add a V1-host adapter state that distinguishes registration from removal after binding and forwards removals without opening settlement.
3. Define an immutable request epoch that makes the required `F_A`/`F_B` relationship enforceable, then write the net payout table for every ruling using `F_A`, `F_B`, `F_E`, and the identity of the shortfall payer.
4. Fully collateralize escalation before accepting a challenge. Treat refusal as an emergency host-specific loss allocation, not the routine answer to fee movement.
5. Either make C4 and the later bids counterparty-executable or remove them. Specify offer expiry and its precedence relative to E1–E3.
6. Choose and deploy the evidence route before the pilot, then test it with one silent party.
7. Run adversarial traces at minimum for: a removal challenged after wrapper adoption; a request crossing quote epochs; an announced fee increase; simultaneous escalation and lapse; C4 crossing C2; E1 racing W3; resolver reverts; failed ETH receivers; and every Classic-versus-Light refusal branch actually supported.

The core idea remains promising, and v0.5 has discarded the two most distracting detours from v0.4. The remaining work is narrower but more fundamental: make the claimed narrow deployment boundary real, and make every terminal branch conserve the exact economic outside option it says it preserves.
