# Audit of settlement-design-v0.1

Review date: 2026-09-02. Reviewed document: [`settlement-design-v0.1.md`](settlement-design-v0.1.md).

## Bottom line

The core idea is worthwhile, but the full two-sided module should not advance to a prototype from v0.1. Several claimed invariants do not hold, including passivity safety, anti-griefing, and resistance to self-challenge.

## Findings

### 1. Blocker — budget balance makes Sybil self-challenges effectively free

R2, R6, and R8 cannot all hold against colluding parties. A requester can challenge through another address, have B withdraw by transferring `F + D_c` back to A, restart the review period, and repeat. Because both addresses share an owner, the supposed penalty is an internal transfer; the economic cost is only gas and temporary lockup.

This can continually block honest challengers, especially if the self-challenger withdraws just before `executeChallenge` becomes callable. The attack catalogue's claims of no residual for self-challenge and collusion are therefore backwards. Preventing this requires a non-party cost, concurrent or takeover challenges, or removing O_B—not merely transfers between A and B.

More generally, R6 and R8 are incompatible against Sybils in this construction: a budget-balanced transfer between two identities controlled by one actor cannot provide a nonrefundable deterrent.

### 2. Blocker — O_B is not a settlement outcome

O_A is terminal; O_B restarts the challenge period. Its value therefore includes delay, future challengers, future fees, and the possibility that the same B immediately challenges again. Consequently, B paying `F + D_c` does not necessarily make A whole, and an A-to-B payment cannot purchase any enforceable abstention from B.

The claim that such a withdrawal is equivalent to a challenger who never challenged holds only for procedural opportunity, not utility or security. This invalidates the alleged dominant unilateral exit in A7. Paid O_B should be omitted from v1, or cancellation should require explicit mutual consent plus a nonrefundable anti-grief charge.

The challenger-market argument is also too strong. Today one active challenger guarantees court; under this design, that one challenger can be bought. The regression affects every thin challenger market, not only completely dormant lists.

### 3. High — the central bargaining math is inconsistent with the stated model

In section 4, the O_A width should be:

```text
p(s_A - g_B) + (1-p)(s_B - g_A) = F
```

The draft uses `s_B + g_A`, producing the erroneous `F + 2(1-p)D_c`. With a common probability, the deposit cancels and the width is `F` for every `D_c`, not merely when `D_c = 0`.

More importantly, the document defines privately estimated probabilities and later introduces `p_A` and `p_B`. Under heterogeneous beliefs, the money-only width is:

```text
F + (p_A - p_B)(D + F + D_c)
```

It can be negative or much greater than `F`. The fee remains the only objective resource destroyed, but it is not the width of the parties' subjective settlement band.

The price direction is also inconsistent. The outcome definition says the exiting party pays, the table shows a negative O_A reservation price, the table calls O_B closed when its feasible prices are negative, and sections 5/A8 later contemplate A paying B for O_B. The mechanism must explicitly choose signed prices or fixed payment directions and use that choice consistently.

### 4. High — actual Curate court outcomes are not binary

Both Classic and Curate V2 support ruling `0`, “Refuse to Arbitrate.” Curate V2 then restores the challenger-side status while splitting the remaining deposit between the parties, producing payoffs different from either row in the draft's binary model. See the official [Curate V2 ruling implementation](https://github.com/kleros/curate-v2/blob/master/contracts/src/CurateV2.sol#L509-L557).

The model needs a refusal probability and third payoff vector, or must explicitly exclude arbitrators that can return zero. Until then, the court-loss prices and “dominant fallback” proof do not describe the first intended integration.

### 5. High — the final round cannot reliably execute on the proposed schedule

The design opens round three at 48 hours and also permits court escalation at 48 hours. Shutter releases a key only after the trigger; a client or keeper must then retrieve it, decrypt the ciphertext, and submit the plaintext or on-chain action. The [official Shutter flow](https://docs.shutter.network/docs/protocol/api/how_it_works) describes those post-trigger steps, and Kleros itself uses an [off-chain keeper to decrypt and submit Shutter votes](https://github.com/kleros/kleros-v2/blob/dev/contracts/scripts/keeperBotShutter.ts#L192-L318).

An executor can therefore race or front-run the final settlement with `executeChallenge`. There must be distinct commit, decrypt/reveal, settlement, and court deadlines, with deterministic precedence and a grace period.

### 6. High — “withholding is impossible” overstates Shutter's guarantees

A4 ignores threshold-Keyper failure and keeper/execution liveness. Shutter's own documentation warns that the API is early-stage and the Keyper network is not yet fully decentralized. A keyper leak also does not “fall back to hash-commit behavior”; it gives insiders early information while other parties remain committed.

The design needs explicit behavior for early decryption, delayed or missing key release, failed decryption, and missing execution, including how each condition affects defaults and the court deadline.

### 7. High — passivity is not safe when court is forcibly delayed

R3 promises “never worse,” yet the selected mechanism adds 48 hours to every genuine dispute, forbids early escalation, and calls that “same, one window later.” With the draft's own discount factors `delta_A` and `delta_B`, later is strictly worse. A malicious challenger also buys the extra delay for no incremental cost over today's challenge.

Either party needs a baseline escape to immediate court, or R1–R3 must be weakened. Allowing either party to escalate early may reduce the settlement rate, but it restores the voluntary status-quo option that those requirements promise.

### 8. High — the selected concession default directly contradicts R6

Defaulting concession to `D` explicitly reduces a junk claimant's loss from `D + F` to `D` whenever B remains at the default. A simulation can quantify the resulting behavior but cannot make the deterministic requirement “junk stays as expensive as today” true.

The design must either default to `D + F`, impose a nonrefundable settlement charge, or explicitly relax R6 and explain the accepted reduction in deterrence.

### 9. High — fee-change handling has no liveness guarantee

A11 assumes an arbitrary caller will donate an arbitration-fee shortfall. Without reimbursement or a funded fallback, escalation can remain stuck forever. Fee changes also invalidate the fixed `s/g` payoffs: A's request fee, B's challenge-time fee, and the escalation-time arbitration cost may all differ.

The case must specify who owes a top-up, a top-up deadline, what happens on nonpayment, how the top-up provider is reimbursed, and how fee decreases are distributed. All other mutable parameters—arbitrator, extra data, deposits, defaults, window, token, and encryption configuration—should be snapshotted per case.

### 10. Incomplete — the executable state machine and cryptographic transcript are unspecified

Before implementation, the design must define:

- The bid and ask values each party submits for both mutually exclusive outcomes.
- Signed-price funding and escrow rules.
- Double-cross tie resolution, midpoint rounding, cancellation, and transaction-order precedence.
- The interaction between defaults, sealed rounds, unilateral exits, and already-posted ciphertexts.
- Commitment domain separation by chain, module, arbitrable, case, party, outcome, and round.
- Replay prevention, expiry, callback authentication, and one-time finalization.
- Behavior for failed transfers, failed callbacks, missing keys, and missing fee top-ups.

Without this state machine, R4, R9, R10, and the midpoint-strategy analysis cannot yet be evaluated.

### 11. External reward programs create an additional Sybil-farming risk

If a settled concession counts as a successful challenge for an external incentive program, one actor can submit through A, self-challenge through B, concede, recover all bilateral transfers internally, and collect the external reward. This becomes especially cheap because no fee reaches jurors.

Settled concessions should not automatically earn an external success reward unless that program has an independent anti-Sybil rule or the settlement includes a sufficiently large nonrefundable cost.

### 12. Simulation cannot establish the security claims

Agent-based simulation is useful for comparing settlement rates, delay, surplus division, and behavior under assumed distributions. It cannot prove that no profitable strategy exists or that no configuration makes a party worse off. Best-response search only searches the strategies and horizons encoded in the model.

The roadmap should put a formal state machine, balance conservation proof, liveness analysis, and adversarial traces before simulation. Simulation should then support parameter selection rather than serve as evidence for universal safety claims.

## Recommended direction

For a credible v1:

1. Narrow the mechanism to terminal requester concession only.
2. Decide explicitly whether preserving the `D + F` deterrent outranks sharing the saved fee.
3. Ensure settled concessions cannot generate external reward-farming opportunities.
4. Correct the payoff model for `p_A`, `p_B`, private values, discounting, refusal-to-arbitrate, and dynamic fees.
5. Specify the complete state machine and escrow accounting, including every timeout and failure path.
6. Add adversarial traces for self-challenge, collusion, sparse challenger markets, fee increases, key failure, MEV ordering, and repeated participation.
7. Only then select sealing and pricing mechanisms and run the simulation.

The strongest parts worth keeping are the explicit requirements, recognition that the list is an unrepresented third party, public settlement events, and the attempt to state defaults rather than leaving silence ambiguous. The full O_B bargaining system, however, currently creates more security problems than it solves.
