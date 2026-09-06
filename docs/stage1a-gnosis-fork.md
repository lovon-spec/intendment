# Stage 1a: pinned Gnosis integration slice

**Status:** review tests, not deployment approval. Results must be read from the
CI run for the exact commit; a successful offline mock suite is not a fork result.
**Parent:** PR #11's event/funding amendment at `85ceabd`.
This slice adds tests and a separate workflow, not production contract behavior.

## Targets and provenance

All eight traces use Gnosis chain 100 at **block 48,112,715**, the block recorded
in RFC 001's route experiment. There is no fallback to latest state.

| Component | Pinned target |
|---|---|
| Real Kleros V1 | `0x9C1dA9A04925bDfDedf0f6421bC7EEa8305F9002` |
| Entry court | Court 19, three jurors; expected initial quote 21.6 xDAI |
| Real Classic GTCR factory | `0x794Cee5a6e1501b633eC13b8c1e327d9860FE039` |
| Existing Light Scout Address Tags list | `0x66260C69d03837016d88c9877e61e08Ef74C59F2` |

Classic instances are created by the real factory on the fork, initially pointing
to Kleros, then adopted by a newly deployed Intendment wrapper. The Light traces
adopt the wrapper on the actual list by impersonating its governor **on the fork**.
Both retain the host's real challenge and appeal code. Classic submits descriptor
bytes; Light submits a URI through the distinct `addItem(string)` selector. Test
metadata and item contents exercise plumbing, not content-policy compliance.

Source references:

- [Intendancy real-factory test](https://github.com/lovon-spec/Intendancy/blob/f22edf0727cd27d0f36348f917d3dbdb12de5785/contracts/test/IntendancyRegistry.t.sol): factory address, deployment ABI and Classic setup pattern. That existing test uses a mock arbitrator; this slice does not claim to reuse an already-published real-juror harness.
- [Kleros deployment addresses](https://github.com/kleros/kleros-docs/blob/c054b208d2147d50301de195e46b68b22d4cd4fb/developer/deployment-addresses.md): Light Address Tags list.
- [GTCR source](https://github.com/kleros/tcr/tree/72e547ea135d839dc5db34e79e9f94f05c6a92bb/contracts): Classic/Light request and crowdfunding ABIs.
- [Gnosis xKlerosLiquid source](https://github.com/kleros/xdai-kleros-liquid/blob/149d6a714c74050f927c9aff453582029449b341/contracts/kleros/xKlerosLiquid.sol): AuRa-compatible RNG access, phase cycling, sortition, commit/reveal, appeal periods and ruling execution. The test exercises deployed fork bytecode, rather than recompiling this source as a substitute.

Each setup checks chain/block identity, nonempty deployed code, and the expected
court quote. It emits host/resolver code hashes for run provenance. This is an
RPC-backed fork, not an independently authenticated chain-state proof.

## What the eight traces check

Run each of the following for both Classic and Light:

1. **Concession:** submit, challenge, bind through real getters, concede, claim the
   fee credit. Check exact requester/challenger payoffs and no Kleros fee payment.
2. **Court ruling:** forward using the production wrapper's gas budgets, draw real
   stakers, cast their committed/revealed votes, finish the real appeal period,
   execute Kleros's ruling, and check host status and monetary outcomes.
3. **Appeal reversal:** initial jury rejects; both sides fund the appeal through
   the real host; seven jurors reverse the ruling; execute the callback and claim
   the real host's first appeal-round rewards. Check payments and both event namespaces.
4. **Unchallenged:** execute after the real challenge period, check full request
   refund and membership, and verify that no wrapper case was invented.

Event checks deliberately require different local and remote dispute IDs.
`DisputeCreation` and `AppealDecision` on the wrapper use local IDs; wrapper-emitted
ERC-1497 `Dispute` and `Ruling` use Kleros IDs. Kleros's `AppealPossible` is checked
at its source and its original window is read through the wrapper. No wrapper
notification synchronizer or new deadline is manufactured.

## Source-confirmed indexer gate

The inspected [gtcr-indexer AppealPossible handler](https://github.com/kleros/gtcr-indexer/blob/df5e900344a59d5a6621090d2747628cba863511/src/mappings/Arbitrator/AppealPossible.ts)
looks up a Registry or LRegistry entity using the event's `_arbitrable` address.
For a forwarded Intendment dispute, Kleros emits that address as the **wrapper**,
not the host. That handler does not implement the additional remote-to-local/host
mapping and would not process the event as a host registry event without adaptation.
The inspected [Curate timeline](https://github.com/kleros/gtcr/blob/70b5bc365bf881b75186f1e3294401385d4abc2f/src/components/request-timelines.tsx)
uses the indexed round's appeal start, ruling and event transaction hash.

These source observations are not a deployed-frontend compatibility test. Before
using that pipeline, implement and test wrapper-aware indexing/notification or an
explicit polling path. Preserve the actual Kleros appeal window and resolve the
exact cached host request, not a later request for the same item. This PR does not
modify either upstream application or synthesize a late `AppealPossible` event.

## Controlled inputs and important limits

These are deterministic **integration** tests, not evidence of economic security:

- Actors receive test-only native balances. Governors and drawn juror addresses
  are impersonated using Foundry, exclusively inside the ephemeral fork.
- Kleros's RNG provider is replaced through its real governor function by a
  deterministic fork-only provider implementing the Gnosis `IRandomAuRa` calls:
  `nextCommitPhaseStartBlock`, `collectRoundLength`, `isCommitPhase`, `currentSeed`.
  The mainnet `requestRN`/`getUncorrelatedRN` interface is not used. The actual
  court's sortition tree, existing stakers, draw, commit/reveal, vote counting,
  periods, appeals and callback code are otherwise exercised. No Kleros/host
  storage is overwritten and no result is injected by directly calling the
  wrapper's `rule` as the resolver.
- External RNG service availability, adversarial juror behavior and live staking
  incentives are **not validated**. Native/token fee redistribution to jurors is
  outside these traces; actual ruling execution and host fund distribution are
  exercised independently.
- Court 19 with three then seven jurors is tested, not the proposed agent court
  or every parent-court jump. Logged forwarding gas is one observed test path,
  not a universal upper bound or calibration of independent cold transactions.
- Official Curate UI, legacy subgraph, notification delivery and silent-party
  evidence display compatibility remain separate gates. Following a remote
  event correctly in a Solidity test does not repair an indexer automatically.
- Stock-host challenge withdrawal/restart and RFC severity/credit are not part
  of this stage-1a slice. The normative specification remains unchanged.

## Running

Requires Foundry v1.3.6, Solidity 0.8.30 and a Gnosis archive-capable RPC.

```bash
RUN_GNOSIS_FORK=true GNOSIS_RPC_URL=https://rpc.gnosischain.com \
  forge test --match-path 'contracts/test/fork/GnosisStage1a.t.sol' -vvv
```

The dedicated `Stage 1a pinned Gnosis fork` workflow sets the opt-in variable and
runs these traces. An unavailable/rate-limited/archive-incomplete RPC makes that
job fail; it never silently substitutes mocks or unpinned state. An ordinary
`forge test` without `RUN_GNOSIS_FORK=true` explicitly skips the eight RPC tests;
its green status alone must not be reported as passing this fork gate.

No command here signs or broadcasts a transaction to Gnosis. There are no wallet
keys, deployment scripts, production parameter changes, merges or issue closures.
