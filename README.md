# Intendment

Out-of-court settlement for optimistic dispute systems.

**Status: design and prototypes. Nothing is deployed.**

In systems like Kleros Curate, a challenge creates the dispute in the same transaction, so every challenge pays arbitrators, including the ones one side would have conceded on the spot. Intendment is a settlement layer between "a challenge exists" and "a dispute is created": the two parties can end the case by paying each other, priced against what court would have cost them, with the arbitrator as the backstop for cases that still disagree at a deadline. What it removes is the resolver's fee, its latency, or both.

## Kleros Curate

Today every challenge on a Curate list goes straight to Kleros, and jurors get paid even when the submitter would have admitted the mistake on the spot. With Intendment:

1. Someone challenges a submission. The Kleros dispute isn't opened yet; the case waits for a short window.
2. The submitter can concede. The challenger gets the deposit as today, and the submitter gets the court fee back instead of it paying jurors.
3. If the submitter disagrees, or does nothing, the case goes to Kleros exactly like today.

A list adopts it by having its governor point the list's arbitrator at a small wrapper contract, `IntendmentArbitrator`. Curate itself doesn't change; it's the same kind of switch the Scout lists made for KIP-87. The first pilot is planned on the Agent Skills Registry on Gnosis.

Where to look:

- [curate-v2 #111](https://github.com/kleros/curate-v2/issues/111): the idea in two minutes.
- [`contracts/`](contracts/README.md): the wrapper, a prototype that is not audited, tested against real Curate lists and Kleros on a Gnosis fork.
- [Design v0.9](docs/intendment-design-v0.9.md): the full mechanism, including the rules that stop people from gaming it, with the stage-1 [state machine](spec/intendment-arbitrator-state-machine.md) and an [executable model](sim/README.md).
- [RFC 001](docs/rfc-001-routing-withdrawal-and-underwriting.md): ideas beyond conceding: a cheap first round with agent jurors, severity tiers so small mistakes cost less than the full deposit, and smaller up-front deposits where the rest is only owed if you lose.

Comments are welcome on #111 or in this repo's issues.

## Polymarket

A prototype plug-in for Polymarket's V2 oracle that skips the UMA vote when a proposer admits a wrong answer. It's in [`oracle/`](oracle/README.md), tested against the deployed contracts on a Polygon fork. The design is [oracle design v0.5](docs/intendment-oracle-design-v0.5.md), and [`backtest/`](backtest/README.md) has the numbers from 90 days of real disputes.

## Layout

- `docs/` design documents. Every version is kept, and independent reviews are kept alongside the version they reviewed, named for the version and, where the reviewer was a model, for the model. RFCs (`docs/rfc-*.md`) are proposals under discussion; nothing in them is part of the baseline until a version folds it in. [`RELEASES.md`](RELEASES.md) lists the release heads.
- `spec/` the stage-1 state machine and accounting: [`intendment-arbitrator-state-machine.md`](spec/intendment-arbitrator-state-machine.md) is normative; its tables are generated from [`intendment-arbitrator-state-machine.yaml`](spec/intendment-arbitrator-state-machine.yaml), structured specification data that [`render.py`](spec/render.py) validates, renders, diagrams and exports as fixtures; CI runs `validate` and `check` on every change. The wrapper is non-upgradeable by design.
- `sim/` an executable model of stage 1a with integer accounting and the specification's traces as tests; CI runs them.
- `contracts/` the stage-1a Curate wrapper, `IntendmentArbitrator`, a prototype that is not audited, with unit tests and Gnosis fork tests against real Curate lists and Kleros; CI runs both.
- `oracle/` the Polymarket V2 oracle module, a prototype that is not audited, with unit tests and Polygon fork tests; CI runs both.
- `backtest/` the Polymarket dispute backtest behind the oracle design's numbers: the scripts that rebuild it from the chain, the dispute dataset and the reports.

## Related

- kleros/curate-v2 [#110](https://github.com/kleros/curate-v2/pull/110): a hash chain over item status transitions, so a client can verify a list's contents from one storage proof.
- kleros/curate-v2 [#111](https://github.com/kleros/curate-v2/issues/111): the concession window, the seed of this design.

## License

Code, which is `spec/render.py`, `sim/`, `contracts/`, `oracle/` and `backtest/`: MIT (see `LICENSE`; source files carry an SPDX header). Documents, which are everything under `docs/` and the Markdown and YAML under `spec/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
