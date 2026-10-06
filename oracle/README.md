# Oracle module

`IntendmentReporterModule` is a reporter module for Polymarket Protocol V2's OracleAggregator. It runs the optimistic proposal and dispute game itself, puts a settlement window between every dispute and UMA, and forwards only disputes the parties do not settle to UMA's OptimisticOracleV2, which decides them as today. A dispute the parties settle pays UMA nothing. The design is [`docs/intendment-oracle-design-v0.5.md`](../docs/intendment-oracle-design-v0.5.md), section 4.

This is a prototype for review. It is not audited and must not hold real funds.

## Layout

- `src/IntendmentReporterModule.sol`: the module. Non-upgradeable; every parameter is fixed at deployment.
- `src/Interfaces.sol`: the minimal interfaces it calls (UMA's oracle, finder and store, the V2 aggregator). No upstream source is copied.
- `test/IntendmentReporterModule.t.sol`: unit tests against stand-ins in `test/Mocks.sol` that reproduce UMA's money rules. Every test ends by checking that the module's balance equals its four money buckets.
- `test/fork/PolygonFork.t.sol`: the same game on a Polygon fork against the deployed contracts: Polymarket's V2 OracleAggregator and BinaryModule, UMA's legacy OptimisticOracleV2, its bridge tunnel and its proposer whitelist. Nothing is mocked; privileged steps impersonate the live role holders.

## Run

Foundry 1.5.1, Solidity 0.8.30, no external libraries.

```sh
cd oracle
forge build --sizes
forge test -vvv
```

The fork tests skip themselves without a fork. Any Polygon archive RPC works; the block is pinned:

```sh
forge test -vv --match-path 'test/fork/*' --fork-url https://polygon.drpc.org --fork-block-number 95030000
```

They show three things on the real contracts:

- A first dispute the proposer concedes: UMA's Store receives nothing; the disputer gets half the bond and Polymarket the other half.
- A later dispute conceded inside its window: the market reopens without a vote and resolves on the next proposal.
- A dispute nobody settles: UMA takes its fee and half the bond as today, the vote's answer arrives through the bridge, UMA pays the winning disputer directly, and Polymarket's finalizer finalizes the answer on BinaryModule.
