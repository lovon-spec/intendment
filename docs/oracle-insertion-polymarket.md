# Insertion study: Intendment between Polymarket and UMA's Optimistic Oracle

Companion to `intendment-design-v0.4.md`, section 12. One page, written against the public contracts on 2026-09-02. Facts carry a source; judgments are marked as such.

## How Polymarket resolves a market today

Source: `Polymarket/uma-ctf-adapter`, `src/UmaCtfAdapter.sol` (default branch, pushed 2025-09-03), `src/interfaces/IOptimisticOracleV2.sol`.

1. **Initialize.** The adapter saves the question and calls `requestPrice` on UMA's Optimistic Oracle V2 with the market's ancillary data, a reward for the proposer, an optional custom bond, and an optional custom liveness (the OO's default liveness is 2 hours). It marks the request event-based and asks for a callback on dispute only.
2. **Propose and dispute happen on the oracle, not on the adapter.** A proposer calls the OO's `proposePrice` and posts the bond; anyone may call the OO's `disputePrice` within the liveness and posts the same bond. The adapter has no function in this path.
3. **First dispute: the adapter resets.** The OO calls the adapter's `priceDisputed`. If the question has not been reset before, the adapter issues a fresh price request with a new timestamp, at most two requests per question. The disputed first request continues on the oracle on its own and is resolved by UMA's vote for the bonds; the adapter simply no longer reads it.
4. **Second dispute: the vote.** A dispute on the reset request goes to UMA's Data Verification Mechanism. The adapter marks the reward for refund and waits.
5. **Resolve.** Anyone calls `resolve`; the adapter calls `settleAndGetPrice`, maps the price to YES, NO or a 50/50 split, and reports payouts to the conditional-tokens contract. An "ignore" price triggers another reset. Admins can pause, flag for manual resolution, and reset as a failsafe.

Two consequences for any settlement layer. The adapter cannot intercept a dispute before the oracle has it, because the dispute is made on the oracle. And the adapter's oracle address is fixed at construction, so a different oracle means a new adapter deployment, which Polymarket has done before across adapter versions; existing markets stay on the adapter they were created with.

## Where a settlement window can sit

| option | what it is | who must agree | verdict |
|---|---|---|---|
| A. oracle-compatible front | a contract that implements the requester-, proposer- and disputer-facing OO V2 interface, holds bonds in escrow, runs the concession window on a dispute, and forwards unsettled disputes to the real OO | Polymarket only: a new adapter version pointed at the front | the realistic path |
| B. UMA V3 escalation manager | V3's `EscalationManagerInterface` lets a manager validate disputers and even arbitrate in place of the vote | UMA, and Polymarket migrating its adapter to V3 | the principled path, not the near one |
| C. change to OO V2 | a window inside UMA's contract | UMA governance | not pursued |

## Option A in detail

**Normal flow, unchanged.** The adapter requests a price from the front exactly as it does from the OO. Proposers propose on the front and post the bond; disputers dispute on the front within the liveness and post the bond. The front calls the adapter's `priceDisputed` callback exactly as the OO would; from the adapter's side nothing differs.

**The window.** A dispute on the front opens the concession window instead of escalating. Only one move exists in it, by design (section 12 of the design, requirement R15): the proposer may **concede**, retracting the proposal and paying the disputer what a lost vote would have paid them. Everything UMA's vote would have taken out of the parties is preserved: the disputer receives the winner's share of the proposer's bond, and the oracle's share is paid to UMA's Store just as a vote would have paid it. The economics of a concession are identical to losing the vote; only the days of voting are saved, and for a market that is the prize. There is no disputer withdrawal and no price to negotiate, because the people whose money rides on the outcome are not at the table.

**After a concession.** The request stays open on the front and a new proposal may be made at once, with a fresh liveness. The adapter is not reset and its one reset is not consumed, so a market can survive more than one wrong proposal before the vote becomes unavoidable. A disputer who knows the right answer is usually the next proposer.

**Unsettled at the deadline.** The front forwards the case to the real OO: it requests a price for the same ancillary data, proposes the disputed price from the proposer's escrowed bond, and disputes it from the disputer's escrowed bond. UMA's vote resolves it exactly as today; the front receives the settlement as requester and pays the real proposer and disputer according to the outcome. Voters see the same ancillary data.

**What Polymarket gains.** Markets with a wrong early proposal, which is the common case when bots race to propose, resolve in hours instead of days. UMA's vote sees only genuine disagreements, which also means fewer of the public resolution fights. Nothing changes for genuine disputes.

**What UMA sees.** Its Store is paid on every concession as it would be on a vote, and the DVM's caseload drops only by the cases nobody wanted to argue. The revenue argument that makes this adversarial for UMA in the abstract is weakened by keeping the oracle's share intact; whether UMA sees it that way is a question for them, but nothing here needs their consent.

**Sybil check.** A proposer who disputes their own proposal and concedes pays the oracle's share of the bond to the Store, so the loop is not free; that is the non-party cost of the design's section 5, supplied here by UMA's own fee split rather than by a rule of ours.

## What is still open

- The window length against a two-hour liveness: an hour is the natural order; to be argued with Polymarket, not decided here.
- The front holds bonds for the length of the window and must forward faithfully; it must be small and audited, and its proposer and disputer roles on the real OO must be checked against OO V2's rules for a requester proposing and disputing its own request.
- UMA's dispute interface will show the front as proposer and disputer; the real parties must be recoverable from the front's events.
- Whether a conceded proposal should still pay the proposer reward to anyone: the design says no reward on a retracted proposal.
- Judgment, not fact: Polymarket is the party to approach first, with the adapter change as a concrete offer rather than a proposal to UMA.
