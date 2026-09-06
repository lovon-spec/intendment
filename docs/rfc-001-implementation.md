# RFC 001 revision 5: first executable implementation

**Status:** review prototype; no Solidity, deployment, live funds, or security sign-off.
**Source:** RFC 001 revision 5 at `42711615200e5b3be8a19de8d3be0feb550b2bc5`.
**Implementation:** [`sim/intendment/rfc001.py`](../sim/intendment/rfc001.py).
**Tests:** [`sim/tests/test_rfc001.py`](../sim/tests/test_rfc001.py).

This is a self-contained, integer-accounting implementation of the revision-5
lifecycle. It does not replace `model.py`, the normative stage-1 state machine,
or the historical `exp/credited-model` experiment. The latter implements older
semantics and must not be cited as coverage of this implementation.

## 1. Scope and exact boundaries

Implemented: per-request collateral reservations, separately funded severity
cost bonds, submission observation and late ticket binding, binary merits,
concession, monotone severity negotiation, frozen binary final offers, final
cost shifting, bounded appeal crowdfunding with lazy claims, unsecured debt and
repayment, prefunded Merkle-scope mandates, retirement without confiscation,
and exactly-once release.

The model includes a simulated registration host and a controlled resolver so
that the complete lifecycle is executable. They are **not deployed adapters**.
Publishing a resolver ruling is a fixture operation authenticated to a named
resolver actor, not a jury-selection or voting implementation. Governance credit
limits are explicit scenario inputs, not a validated reputation-scoring system.

Not implemented in this slice:

- the stage-1 Solidity wrapper, factory, and real Classic/Light host profiles;
- the baseline reserve/fee-epoch insurance and emergency-lapse state machine;
- the host-side challenge-withdrawal/restart extension (withdrawal remains on the
  roadmap; this PR neither rejects it nor silently substitutes concession);
- real juror draws, court-tree fee discovery, proof-of-storage verification,
  EIP-712/account signatures, callback ABI/reentrancy/gas behavior;
- reserve underwriting, fractional reserves, optional litigation allowance;
- a behavioral simulation establishing final-offer convergence.

The implementation is deliberately a reference model before a money-holding
contract port. No test here establishes production gas bounds or live juror
behavior. All public model transitions take an atomic world snapshot, validate
invariants on success, and restore money, host state, resolver state, counters,
and events on failure. Deep-copying and global invariant scans are test machinery,
not operations to translate into Solidity.

## 2. Accounts: debt is never counted as money

Balances are isolated by purpose:

| Account | Owner / purpose |
|---|---|
| `wallet` | External actor cash. `mint` supplies test endowments only. |
| `free` | Submitter cash not committed to a request. |
| `award` | Secured promise for one reservation. |
| `cost` | Separate first-instance severity cost backing for that reservation. |
| `host` | That request's prepayment, merits fee, and challenge deposit. |
| `merits-fee` | Challenger fee held until concession or merits forwarding. |
| `credit` | Pull-payment claim, withdrawable to a chosen recipient. |
| `appeal` | One round's funding/reward/refund liability. |
| `mandate` | One authorization's unspent prefunding. |
| `jurors` | Irreversible court fees in this model. |
| `host-dust` | Explicit odd-unit remainder from a host refusal split. |

Unsecured debt is stored separately per case and aggregated per requester. A
judgment can create debt but cannot mint claimable cash. A payment transfers
existing cash to the creditor and reduces that debt exactly once. Existing
unpaid debt prevents opening *new unsecured* exposure, not challenging an
existing submission or obtaining a ruling.

All amounts are integers. `Policy.amount` uses full-precision multiplication and
floor division by 10,000; the eventual Solidity port must use equivalent checked
full-precision arithmetic. Example test amounts use an arbitrary common base
unit, not measured deployment prices. `Policy` is immutable and versioned;
changing the host's active policy affects later submissions only.

## 3. Implementation choices requiring reviewer attention

### D1. The cost bond is additional to the host's prepayment

For a fully secured promise:

```text
host request cash = u + meritsFee
wrapper backing   = (D - u) + severityCostCap
```

For a credited requester, some of `D - u` can be unsecured, but the severity cost
cap must still be cash-backed by a valid ticket. It is not borrowed from the host
pot and is never counted twice. With u=6, meritsFee=0.5, costCap=0.5, and a fully
unsecured award gap, the initial cash requirement is 7 rather than 6.5.

The admission is an irrevocable minimum payment once rejection is conceded.
It is credited to the claimant from award collateral, requester cash, or mandate
cash. Final settlement pays only the *incremental* award, avoiding double payment.
Unused collateral and cost backing become free after financial finality; fixed
unsecured debt survives that release. A cost bond is not general collateral for
an unpaid award unless a later policy expressly changes that priority.

### D2. Fee drift must not create phantom reimbursement

Severity opening checks the live fixture quote against BOTH the claimant's
`max_fee` and actual cost backing. If either is insufficient, the entire opening
reverts: no fee is spent, snapshot created, or position frozen. The requester may
voluntarily add cost backing before opening. A lower actual fee is reimbursed
only at the amount actually paid; excess backing is returned after finality.

`lambda = 0`: no gas allowance or appeal reimbursement is implemented. A later
`q_s + lambda` option needs its own eligible-expense and cap rules.

A quote increase or resolver outage can prevent opening within the negotiation
window. This model applies the RFC's admission default if no case opens by that
window's end. It **does not claim that outcome is a proved passivity guarantee
under fee shocks**. Review the production shortfall/failure policy before porting.
Merits fee drift explicitly rejects with `baseline adapter required`; the stage-1
reserve mechanism is not accidentally approximated by this financial model.

### D3. Finality, not the first jury result, allocates the cost bond

The severity snapshot freezes the parties, rungs, monetary amounts, policy,
evidence reference, initial fee, cost cap, and resolver configuration. Later
appeals use precisely that record. Period durations and a finite appeal-fee
schedule are fixed in the scenario policy; each actual round's start/end is set
when its provisional ruling is published. Unknown future absolute deadlines
cannot honestly be snapshotted at initial creation.

No cost bond is paid or released on a provisional ruling. The final effective
outcome decides it: claimant => reimburse the original initial fee; requester or
refusal => return cost backing to the requester. Appeal fees do not increase
award debt or the cost-shifting guarantee.

The modeled appeal table is explicit:

| Funding by round deadline | Effective behavior |
|---|---|
| Neither side fully funded | Provisional ruling stands; partial funding refundable. |
| Exactly one side fully funded | That side wins by funding default; that unspent round's funding refundable. |
| Both fully funded | Pay one next-round court fee and open the next round. |
| Final raw refusal | Severity uses the admission; prior appealed-round funds share pro rata. |

The losing side has only the first half of the funding window. Winners and
refusal sides have the full window. Claims are lazy, one funder/round at a time;
rounding dust remains a liability, not operator revenue. At the end of the finite
scenario schedule, no further appeal can be opened. The actual adapter must
match the selected resolver's real appeal availability rather than invent a cap
that overrides rights already promised by that resolver.

**Initial severity silence is not an automatic loss. Failing to defend a funded
appeal can be.** That distinction is intentional in this prototype and must be
visible in the eventual interface/policy.

### D4. Reservation expiry concerns eligibility at submission, not delayed observation

Ticket identity binds host, requester, item, expected request index, policy,
nonce, secured maximum, and expiry. The ticket predates the submission by a block.
A timely submission may be bound after expiry. Cancellation inspects the actual
simulated host record, not just `ticket.state`, so an unobserved but timely request
keeps its backing. A stranger taking the anticipated slot cannot consume it.
Cancelled tickets never revive. Repeated submissions to the same item keep
separate request-index identities, even while earlier severity remains pending.

Release requires a resolved host request and a finished financial case, when
one exists. A matured unsecured debt remains payable but has no unresolved claim
on that ticket's remaining purpose-specific cash. Retirement does not cancel old
reservations, mandate execution, claims, or debt repayment.

### D5. An unmodified host can admit an unbacked request

`host_submit` intentionally does not call or require the wrapper. The simulated
host therefore allows direct submissions lacking a qualifying ticket. Their
challenge and merits paths remain open. Absence of a ticket is exposed in events;
a reviewer can apply the listing policy. The model does not turn that economic
policy violation into automatic adjudication.

A missing cost bond cannot support a guaranteed reimbursable severity case, so
severity opening is rejected rather than inventing backing. The ordinary
negotiation expiry/default still applies. This is an explicit limitation of the
stock-host policy route, **not a claim that all direct submissions are insured**.
A real host-module admission hook could enforce backing atomically. This boundary
needs an explicit integration decision before a production credited-host launch.

### D6. Mandates authorize, they do not schedule execution

The first version models direct authorizations and SHA-256 Merkle commitments.
It does not verify Ethereum signatures. Leaves are domain-separated over the
instance, case ID, exact request, requester and policy; internal nodes use a
different prefix. The Solidity port must pin a concrete ABI/hash/signature
encoding, then regenerate interoperability fixtures instead of assuming these
Python commitments are Ethereum-compatible.

Scope is fixed. A mandate rung is a maximum: a claimant's lower existing claim
reduces the amount paid. Execution debits only this mandate's prefunding, never
another reservation. Case count, cash, and the host transition commit atomically.
An independently conceded/resolved case is a no-op. A merits escalation winning
the race rejects the competing execution without spending budget. Expiry or
exhausted caps release unused prefunding once. Single-case exits stay available.

There is no transaction scheduler in this model. The requester/keeper must call
before relevant deadlines. Protocol state cannot guarantee that an actor acts.

### D7. Standing and strategy are inputs, not a discovered equilibrium

An explicit per-requester unsecured limit bounds aggregate outstanding exposure,
including unused reserved tickets. It is supplied by the scenario governor and
is not inferred from settlement counts, account age, or purported independent
wallets. Existing obligations survive limit changes and retirement.

Juror results are also scenario inputs. Deterministic and seeded tests establish
accounting/state properties under those inputs, not that participants converge,
that the ladder is socially optimal, or that a promise will be collected.

## 4. Test-to-review mapping

| Review topic | Representative tests |
|---|---|
| #1 merits/severity separation | zero-case agreement, severity-only concession, merits accept/refusal, contested merits then severity |
| #3 reservations | two liabilities isolated; double use; stranger submission; late binding; same item/new index; financial finality |
| #4 mandates | prefunding, valid proofs, fixed scope, cap exhaustion, one decision/many executions |
| #5 convergence hypothesis | explicitly outside correctness tests; no fabricated behavioral result |
| #6 frozen offers | immutable snapshots, update/open race orders, later policy update, inherited appeal offers |
| #7 cost shifting | actual lower fee, top-up for higher fee, both appeal reversal directions, only initial fee reimbursed |
| #8 lifecycle | cancellation, expiry, rollback on host failure, replay, callback retry, concurrent execution orders |
| #2/#9 underwriting | no pool added; debt never treated as cash; later research stays separate |
| Cross-cutting | cash conservation, exact host pot, isolated liabilities, lazy appeal rewards/dust, unauthorized calls, integer boundaries, seeded lifecycles |

Run from the repository root:

```bash
python -m unittest discover -s sim/tests -p 'test_rfc001.py' -v
# Existing repository CI also discovers these tests:
pytest sim -q
```

Local verification for this implementation: **87 unittest tests passed**,
including seeded lifecycle scenarios. It also collects and passes under pytest.
Only these new tests were run locally in the implementation environment; the
unchanged stage-1 test suite is left to the repository's existing combined CI.
Do not infer a baseline/full-suite result from the new test count.

## 5. Next implementation slice

Port the already-specified stage-1a wrapper against its existing model and create
the actual host-profile boundary. For RFC 001, first port the reservation and
cost-bond ledger, then the final-offer financial case, then mandates invoking the
same single-case transition. Keep any state-machine deviations explicit and
reviewed. Real callback ordering, gas, signatures, court/host integration,
liability-history reads, and failure handling require Solidity and fork tests.

This document does not change the v0.9 release head, authorize deployment, close
review issues automatically, or mark a model assertion as a contract guarantee.
