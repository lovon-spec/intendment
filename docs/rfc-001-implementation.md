# RFC 001 revision 5: executable implementation and review amendment

**Status:** review prototype; no Solidity, deployment, live funds, or security sign-off.
**Source:** RFC 001 revision 5 at `42711615200e5b3be8a19de8d3be0feb550b2bc5`, plus the
[PR #10 review](https://github.com/lovon-spec/intendment/pull/10#pullrequestreview-5126534507)
and the [proposed RFC amendment](rfc-001-review-amendment.md).
**Implementation:** [`sim/intendment/rfc001.py`](../sim/intendment/rfc001.py).
**Tests:** [`sim/tests/test_rfc001.py`](../sim/tests/test_rfc001.py).

This integer-accounting implementation does not replace `model.py`, the normative
stage-1 state machine, the RFC, or the historical `exp/credited-model` experiment.
The review amendment fixes the missing-ticket severity bypass and quote-increase
veto, and makes severity claims explicit. Its changes to defaults are intentional
policy amendments, not claims that revision 5 already specified those defaults.

## 1. Scope and exact boundaries

Implemented: per-request collateral reservations, separately funded severity cost
bonds, late ticket binding, binary merits, concession, monotone negotiation,
frozen final offers, final cost shifting, appeal crowdfunding with lazy claims,
unsecured debt and repayment, prefunded Merkle mandates, and exactly-once release.

The host and resolver are controlled fixtures, not deployed adapters. Juror results
and governance credit limits are explicit scenario inputs, not a voting system or
validated reputation score. Transactions restore money, state, counters and events
on failure; global scans and deep copies are test machinery, not Solidity logic.

Not implemented: stage-1 Solidity; real Classic/Light profiles; the baseline fee
reserve/epoch/lapse mechanism; host-side withdrawal/restart; real juror selection;
Ethereum ABI, EIP-712 or account signatures; storage proofs; gas or reentrancy;
reserve underwriting; optional litigation allowances; behavioral convergence.
Withdrawal remains planned. This model does not substitute concession for it.

## 2. Accounts: debt is never counted as money

| Account | Purpose |
|---|---|
| `wallet` | External actor cash; `mint` is a fixture endowment only. |
| `free` | Submitter cash not committed to a request. |
| `award` | Secured promise for one reservation. |
| `cost` | Separate initial-severity-cost backing for that reservation. |
| `host` | Request prepayment, merits fee, and challenge deposit. |
| `merits-fee` | Challenger fee held until concession or merits forwarding. |
| `credit` | Pull-payment claim with a chosen recipient. |
| `appeal` | One round's funding, rewards, and refund liability. |
| `mandate` | One authorization's remaining prefunding. |
| `jurors` | Irreversible court fees in the fixture. |
| `host-dust` | Odd-unit remainder from a host refusal split. |

Debt is a separate liability per case, aggregated per requester. It cannot create
claimable cash. Repayment transfers existing cash to the creditor and reduces debt
exactly once. Debt blocks new unsecured exposure, not an existing challenge.
All amounts are integers; multiplication/division uses full precision and floors.
The Solidity port must preserve that arithmetic. Policies are immutable/versioned.

## 3. Decisions requiring reviewer attention

### D1. The cost bond is additional to host cash

```text
host request cash = u + meritsFee
wrapper backing   = secured award portion + severityCostCap
```

An unsecured award still requires a cash-backed cost allowance to qualify for the
normal admission default. With `u=6`, merits fee `0.5`, cost cap `0.5`, and zero
award collateral, cash required is `7`, not `6.5`. The host pot is never double-counted.
An admitted award becomes an irrevocable cash credit. Final settlement pays only
the increment above that admission. Purpose-specific cost backing is not consumed
by award debt. Unused backing becomes free after financial finality.

### D2. Reimbursement capacity does not limit access to adjudication

For a qualifying request the claimant fronts the actual quoted severity fee. The
opening transaction checks the caller's `max_fee` and optional `min_reimbursement`:

```text
reimbursement_cap = min(actual initial fee, available request cost backing)
```

A quote above the backing no longer blocks opening. The claimant knowingly bears
the excess even if it wins; that excess is not new requester debt. Optional requester
top-ups before opening can improve reimbursement, but withholding a top-up is not
a veto. Fee, backing and reimbursement cap are frozen on opening. Excess backing
returns at release. `lambda = 0`; no extra gas/keeper allowance is implemented.

The cap is allocated using the final effective outcome, never a provisional vote.
A subsequent fee quote cannot change the frozen reimbursement. Appeals do not add
to it. `min_reimbursement` protects a caller from accepting less backing than intended.

A resolver outage can still prevent opening. The negotiation deadline/default
remains the RFC's behavior, not a proof of liveness through arbitrary outages.
The amendment fixes fee *shortfalls*, not permanent resolver failure. Merits fee
drift still rejects with `baseline adapter required`, rather than inventing a subsidy.

### D3. Default and opening roles depend on backing at submission

| Request had a qualifying ticket at submission | Default without adjudication | Permitted opener and initial fee payer | Reimbursement |
|---|---|---|---|
| Yes | Requester's admission | Claimant | Frozen cap, only if claimant finally wins |
| No | Claimant's explicit, current claim | Requester | None, irrespective of outcome |

A naked request cannot concede low and thereby prevent a higher award being
established. The requester can either negotiate agreement or pay to contest the
claim. In the unticketed mode that fee is its own expense; the claimant has posted
no reciprocal cost bond and acquires no reimbursement debt. This is a deliberate
exception to ordinary cost shifting. The final award can still be unsecured debt,
not guaranteed collection. Registry membership has already been resolved.

Qualification uses actual submission history (`_matches`), including requester,
request identity, policy, pre-submission block, and ticket expiry. `challenge()`
observes/binds that history. Delayed observation of a timely ticket is normal mode;
an invalid, cancelled, wrong-owner or late ticket is not. A higher later fee does
not invalidate a qualifying ticket or reverse the burden. Late donations cannot
retroactively buy a different default.

The frozen record includes default side, opening party, fee payer and reimbursement
cap. Refusal preserves that frozen default: admission in normal mode, claim in
unticketed mode. Raw `REFUSE` remains raw for pro-rata appeal accounting; it is not
silently changed into a jury win. A funding-default winner, in contrast, is an
explicit effective outcome. The two modes use the same immutable offers.

### D4. Appeals and finality

| Funding by deadline | Effective behavior |
|---|---|
| Neither side fully funded | Provisional ruling stands; partial funding refunded. |
| Exactly one side fully funded | That side wins; the unspent round is refunded. |
| Both sides fully funded | Pay the next court fee and open the next round. |
| Final raw refusal | Apply the frozen severity default; appealed rounds refund pro rata. |

The losing side has the first half-window; winner/refusal sides have the full
window. Claims are lazy, funder/round at a time; rounding remains a liability.
The scenario uses a finite configured appeal schedule. A real adapter must match
the resolver's promised appeal rights, not override them with an arbitrary cap.

The initial severity fee is reimbursed only after finality and only within the
frozen cap. Both reversal directions are tested. No appeal fee becomes award debt.
Initial silence is not defeat for a *qualifying* requester; failure to defend a
funded appeal can be. Unticketed requests have the different disclosed default.

### D5. Explicit claims; stock-host admission is not changed

`challenge(..., claim=...)` requires an explicit valid rung. Missing, `None`, boolean
and invalid values do not become maximum claims. Test helpers choose their intended
rung explicitly; production callers must do the same.

`host_submit` still does not require a ticket. Missing backing remains a visible
policy violation, not automatic rejection or a blocked challenge. The reference
model combines a challenge with its declaration; a real stock-host integration
may need a separate wrapper declaration and a bounded declaration window. It must
not censor the stock host's challenge path or invent a top-rung claim if that
declaration never arrives. That ABI/lifecycle decision is outside this slice.

### D6. Reservations and mandates

A ticket binds host, requester, item, expected request index, policy, nonce,
secured maximum and expiry. A timely request remains backed when linked late;
cancellation consults actual host state. A stranger at the anticipated slot cannot
consume the ticket. Release needs both host and financial finality. Mature debt
survives release; retirement does not erase tickets, mandates, credits or debts.

Mandates use direct authorization and domain-separated SHA-256 Merkle fixtures,
not Ethereum ABI/EIP-712. Scope is fixed; a claimant's lower claim reduces payment.
An independently settled case consumes nothing; escalation winning a race rejects
execution without spending; counters and cash roll back with a failed callback.
Expired/exhausted mandates refund once. No case depends on processing another.
The requester/keeper still must execute: no scheduler is modeled.

### D7. Standing and behavior remain inputs

An explicit unsecured limit bounds aggregate exposure, including unused tickets.
No settlement count, age or purportedly independent wallet trains that limit.
Results and limits are scenario inputs. Passing tests establishes state/accounting
properties, not repayment likelihood, juror accuracy or bargaining convergence.

## 4. Validation and review coverage

Run from the repository root:

```bash
python -m unittest discover -s sim/tests -p 'test_rfc001.py' -v
pytest sim -q
```

The amended RFC suite has **111 tests**: the original 87 updated where semantics
changed, plus 24 review regressions. It passes locally under unittest; combined
baseline and Python-version CI results must be reported separately.

New regressions cover unticketed low-concession/default/contest/refusal, repayment,
both directions of appeal reversal, raw refusal pro-rata refunds, late binding,
wrong-owner and same-block tickets, capped fee increases, optional top-ups,
minimum-reimbursement slippage, and explicit claims. Existing tests cover
conservation, immutable offers, mandate races, ticket release, authority, rounding,
rollback and seeded lifecycle scenarios.

## 5. Next slice

Port stage 1a against its existing model and actual host getter boundary in a
separate PR. The RFC financial model is not the stage-1 fee-reserve model. Before
porting this financial layer, pin signatures/ABI, proofs, callbacks, gas, and the
remaining outage and declaration behavior. No deployment or issue closure is
implied by either the model or this amendment.
