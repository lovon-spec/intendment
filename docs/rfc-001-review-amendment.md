# Proposed RFC 001 amendment: severity access and reimbursement

**Status:** implementation-review amendment to revision 5, not an accepted release.
**Context:** [PR #10 review](https://github.com/lovon-spec/intendment/pull/10#pullrequestreview-5126534507).
The maintainer is editing the next RFC revision separately. This note supplies the
exact rules used by the amended reference model without overwriting that work.

## A. Missing-ticket requests cannot choose their own severity price

For a request with a qualifying ticket at submission, retain the ordinary default:
the admission applies unless the claimant funds severity adjudication. For a
request without such a ticket, the claimant's explicit current claim applies
unless the requester funds adjudication to contest it. Negotiated agreement still
ends either mode without a case. This exception applies only after final rejection;
it cannot change registry validity or turn a default into a juror verdict.

Ticket qualification is determined from the actual submitted request, not the time
at which the wrapper observes it. Late binding of a timely ticket preserves normal
mode. Wrong-owner, cancelled, same-block, expired-at-submission or wrong-policy
tickets do not qualify. Later top-ups cannot buy a different default.

The opening transition freezes both offers and amounts, policy, evidence, default
side, opening party, initial fee payer and reimbursement cap. Raw refusal preserves
that frozen default. Raw refusal still gets pro-rata appeal-refund accounting;
a one-sided appeal-funding outcome instead names an explicit effective winner.

For an unticketed request the requester bears its initial contest fee even if it
wins: there is no reciprocal claimant bond. No unsecured fee reimbursement is
created. Award debt remains distinct from cash and can still go unpaid.

## B. A fee increase reduces coverage, not the right to adjudicate

The normal-mode claimant may open at a fee above the available cost backing:

```text
initialFee       = actual resolver quote paid by the opener
reimbursementCap = min(initialFee, available cost backing)
```

The requester may top up voluntarily but cannot block adjudication by withholding
that top-up. The claimant bears any excess even on winning. The caller supplies
`max_fee` and may supply `min_reimbursement`; opening reverts atomically if either
limit fails. The cap is frozen, allocated once at finality, and never grows through
appeals. Unused backing returns at release. Permanent resolver outages remain a
separate unresolved integration concern, not solved by this fee-shortfall rule.

## C. Claims must be explicit

Remove the implicit maximum rung from the reference model's challenge API. A real
stock-host integration must preserve the original challenge path and separately
specify authenticated declaration timing/defaults if it cannot carry the rung in
the host's challenge transaction. No missing declaration implies maximum severity.

## Optional allowance remains deferred

The earlier `q_s + lambda` option and capped unsecured litigation allowance remain
possible later policies, not implemented here. They need eligible-expense, cap,
payer, recovery and no-double-payment rules. This amendment adds no new pool,
uncapped liability, gas reimbursement or appeal reimbursement.
