# Stage 1a Solidity: first review slice

**Status:** unaudited review prototype, no production deployment authorization.
**Baseline:** design v0.9 and state machine 0.5 at `4271161`.
**Separate work:** PR #10's RFC-001 financial reference model and review amendment.
This slice does not port that financial layer or alter the baseline specifications.

## What is implemented

`IntendmentArbitrator` is a plain, immutable-address ERC-792 wrapper. Registration
cases may concede at share zero or go to the original resolver. Removal cases
cannot concede and are immediately eligible for forwarding. Binding is a separate,
permissionless operation after the host saves its dispute mapping. Party methods
bind implicitly. The recorded host requester/challenger are the only authorities;
no router, tx.origin lookup or custodial identity inference exists.

The port covers quote envelopes/epochs, principal and surplus, earmarks, coverage,
case funding, pro-rata lazy refunds, concession, forwarding, quote/create failures,
forward-first emergency lapse, host-only appeal, ruling relay, pull credits,
retirement, announced principal withdrawal and same-factory surplus migration.
Factory deployment requires the host's current governor and creates an ordinary
contract, not a proxy. Stage-1b offers are not included; `concede(id,maxShare)` keeps
the future-compatible argument but the only share available in stage 1a is zero.

## Review the host boundary first

`HostProfiles` implements the getter ABIs from `kleros/tcr` commit
`72e547ea135d839dc5db34e79e9f94f05c6a92bb`:

- Light: `arbitratorDisputeIDToItemID` and `(status,count,deposit)` item getter.
- Classic: `arbitratorDisputeIDToItem` and `(data,status,count)` item getter.
- Both: the ten-field `getRequestInfo` tuple, including parties, arbitrator,
  extra data and meta-evidence ID.

Binding verifies a pending request, nonzero parties, disputed/unresolved flags,
matching local dispute ID, the wrapper as request arbitrator, and the original
encoded envelope. Deposit and descriptor values are not used in accounting.
The request identity and metadata are cached for evidence/indexer mapping.

The test hosts reproduce these **ABIs and callback ordering**, not complete GTCR
behavior. In particular, the Classic test fixture does not prove Classic refusal
payout accounting or host appeal crowdfunding; those remain the real host's job.
The production validation must exercise actual Classic/Light contracts and Kleros
on a pinned fork. This slice does not claim that validation has happened.

## Money and conservation

```text
accounted = principal + surplus + openFees + refundLiability + totalClaimable
free      = principal + surplus - totalEarmarked
```

Every quantity is updated incrementally. No settlement, migration, withdrawal or
claim enumerates funders, cases or epochs. Refund arithmetic uses a 512-bit product
with floor division; unclaimed rounding remains a permanent liability. Funding is
used only after the held fee and available case reserve. Loss consumes surplus
before principal. A favorable resolver quote accrues to surplus, not a party.

A forced native-currency transfer can make actual balance exceed accounted balance.
That excess is not spendable reserve until `syncSurplus()` explicitly donates it
to surplus. It never becomes principal or a party/funder credit. The corresponding
invariant is actual balance = accounted balance + unaccounted excess at transaction
boundaries, rather than pretending unsolicited transfers cannot occur.

`claim(to)` is the only case-party payment. Credits clear before the external call
and revert on failed delivery. The host still owns and distributes its deposit pot;
its own failed-send semantics are not repaired by wrapper credits.

## Resolver failure and gas: deployment assumptions, not magic guarantees

Quote and create calls have bounded gas budgets (`100,000` and `1,500,000`) and
copy at most one return word. The caller must supply a floor that includes EIP-150
headroom and post-call reserve. Insufficient caller gas reverts without recording a
resolver failure. A reverting quote/create call records failure with no funds moved.
Successful calls with malformed output or reused IDs revert the entire transaction,
including backend acceptance and payment; they never authorize emergency lapse.

The emergency operation first makes a fresh funded forwarding attempt after both
the funding deadline and failure grace. Recovery therefore wins over an old failure.
A quotable uncovered case uses the separately guarded normal lapse path. A reverting
quote cannot use normal lapse as if it were evidence of insufficient money.

**The fixed budgets must be measured against the exact target deployment.** A real
resolver whose correct create path exceeds the configured budget can be misclassified
as unavailable; this is a deployment blocker until validated. The code is a prototype
of the spec's properly-gassed predicate, not a general oracle for service health.
Budget exhaustion by a resolver is distinct from caller starvation. There is no
new claim that capital guarantees a working resolver or submitted transaction.

All state-mutating entrypoints share a reentrancy guard. Supported Kleros callbacks
are asynchronous; a resolver that calls `rule` synchronously from `createDispute`
is not supported by this slice. External host `rule` failure rolls the transition
back, including refunds/credits, so retry is possible after host recovery.

## Explicit API and lifecycle choices

1. `registerEpoch` takes registration/removal MetaEvidence URIs in addition to the
   four economic arguments, so the spec's epoch metadata emission has an actual
   source. Governance must supply the proper immutable policy and display URI.
2. Only canonical envelopes are accepted, and real extra data is capped at 1,024
   bytes. The underlying registered bytes, never the envelope, go to the resolver.
3. The retirement floor snapshots the host's current challenge period at retirement
   plus an immutable positive margin. This does **not** prove latent requests are
   exhausted. The existing governance procedure is still required: stop new host
   assignments, finalize all old requests, then move capital. A later period change
   cannot be made safe by this local clock alone.
4. Principal withdrawals recheck current capital and consume their announcement.
   A rejecting withdrawal recipient rolls back only that withdrawal. Surplus can
   migrate only to a genuine same-factory, same-host instance. No owner extraction
   of earned surplus is implemented.
5. Rulings are relayed once and host failures revert that latch. Appeals originate
   only from the host and require the original epoch. The host retains its own
   crowdfunding, funding-default and reimbursement rules. The wrapper does not
   reimplement the host's financial appeal game.
6. Terminal fee accounting at forwarding does not mean the court case is ruled.
   The host will receive its result later; wrapper reserve money is no longer at
   risk for that case after successful forwarding.

## Tests and what they do not establish

Foundry tests exercise both getter profiles; canonical epochs; requester-only early
escalation; permissionless post-deadline forwarding; removal exclusion; reserve
waterfalls; fee increases/decreases; case funding/dust; stale and persistent resolver
failure; caller starvation; malformed/reused return IDs; callbacks and reentrancy;
credit receivers; appeal authorization; principal locks and migration; forced ETH;
and fuzzed waterfall/refund arithmetic. Test fixtures are intentionally explicit.

Compiler and test outcomes are recorded in the PR/CI, not assumed from source review.
No local Solidity compiler was available in the authoring environment; GitHub CI is
the compilation/test gate. Python model/spec checks run separately in the same
workflow. Passing tests is not an audit or proof of economic safety.

Before deployment: real-host pinned-fork traces, model-vs-contract differential
traces, gas-budget calibration, a working silent-party evidence display, funding
and retirement runbooks, and independent review are still required. Stage-1b bids,
RFC severity/debt/reservations/mandates, challenge withdrawal/restart, V2/ERC-20,
reserve underwriting and a browser UI are not part of this slice.
