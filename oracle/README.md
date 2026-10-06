# Oracle module

`IntendmentReporterModule` is a reporter module for Polymarket Protocol V2's OracleAggregator. It runs the optimistic proposal and dispute game itself, puts a settlement window between every dispute and UMA, and forwards only disputes the parties do not settle to UMA's OptimisticOracleV2, which decides them as today. A dispute the parties settle pays UMA nothing. The design is [`docs/intendment-oracle-design-v0.3.md`](../docs/intendment-oracle-design-v0.3.md), section 4.

This is a prototype for review. It is not audited and must not hold real funds.

## Layout

- `src/IntendmentReporterModule.sol`: the module. Non-upgradeable; every parameter is fixed at deployment.
- `src/Interfaces.sol`: the minimal interfaces it calls (UMA's oracle, finder and store, the V2 aggregator). No upstream source is copied.
- `test/IntendmentReporterModule.t.sol`: unit tests against stand-ins in `test/Mocks.sol` that reproduce UMA's money rules. Every test ends by checking that the module's balance equals its four money buckets.

## Run

```sh
cd oracle
forge build --sizes
forge test -vvv
```

Foundry 1.5.1, Solidity 0.8.30, no external libraries.
