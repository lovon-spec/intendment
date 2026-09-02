# Intendment

Out-of-court settlement for optimistic dispute systems.

**Status: design phase. Nothing is deployed.**

In systems like Kleros Curate, a challenge creates the dispute in the same transaction, so every challenge pays arbitrators, including the ones one side would have conceded on the spot. Intendment is a settlement layer between "a challenge exists" and "a dispute is created": the two parties can end the case by paying each other, priced against what court would have cost them, with the arbitrator as the backstop for cases that still disagree at a deadline.

First target: Kleros Curate. Intended deployment: an arbitrator-level wrapper, `IntendmentArbitrator`, that any ERC-792 or `IArbitratorV2` arbitrable can adopt by pointing its arbitrator at it, without changing the arbitrable; plus an arbitrable-side extension for challenge withdrawal, which cannot be expressed through rulings alone.

## Layout

- `docs/` design documents. Every version is kept, and independent reviews are kept alongside the version they reviewed.
- `spec/` the state machine and accounting, to come.
- `contracts/`, `sim/` to come.

## Related

- kleros/curate-v2 [#110](https://github.com/kleros/curate-v2/pull/110): a hash chain over item status transitions, so a client can verify a list's contents from one storage proof.
- kleros/curate-v2 [#111](https://github.com/kleros/curate-v2/issues/111): the concession window, the seed of this design.

## License

Code: MIT (see `LICENSE`). Documents under `docs/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
