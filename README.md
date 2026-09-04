# Intendment

Out-of-court settlement for optimistic dispute systems.

**Status: design phase. Nothing is deployed.** Current version: design [v0.8](docs/intendment-design-v0.8.md) with the stage-1 [state machine 0.4](spec/intendment-arbitrator-state-machine.md); see [`RELEASES.md`](RELEASES.md) for the release head.

In systems like Kleros Curate, a challenge creates the dispute in the same transaction, so every challenge pays arbitrators, including the ones one side would have conceded on the spot. Intendment is a settlement layer between "a challenge exists" and "a dispute is created": the two parties can end the case by paying each other, priced against what court would have cost them, with the arbitrator as the backstop for cases that still disagree at a deadline. What it removes is the resolver's fee, its latency, or both.

First target: Kleros Curate. Intended deployment: an arbitrator-level wrapper, `IntendmentArbitrator`, one per list, that a list adopts by pointing its arbitrator at it, without changing the list; its first version has one price and two buttons, concede or court. An arbitrable-side extension follows for challenge withdrawal, which cannot be expressed through rulings alone.

## Layout

- `docs/` design documents. Every version is kept, and independent reviews are kept alongside the version they reviewed, named for the version and, where the reviewer was a model, for the model.
- `spec/` the stage-1 state machine and accounting: [`intendment-arbitrator-state-machine.md`](spec/intendment-arbitrator-state-machine.md) is normative; its tables are generated from [`intendment-arbitrator-state-machine.yaml`](spec/intendment-arbitrator-state-machine.yaml), structured specification data that [`render.py`](spec/render.py) validates, renders, diagrams and exports as fixtures; CI runs `validate` and `check` on every change. The wrapper is non-upgradeable by design.
- `contracts/`, `sim/` to come.

## Related

- kleros/curate-v2 [#110](https://github.com/kleros/curate-v2/pull/110): a hash chain over item status transitions, so a client can verify a list's contents from one storage proof.
- kleros/curate-v2 [#111](https://github.com/kleros/curate-v2/issues/111): the concession window, the seed of this design.

## License

Code, which today is `spec/render.py` and later `contracts/` and `sim/`: MIT (see `LICENSE`; source files carry an SPDX header). Documents, which are everything under `docs/` and the Markdown and YAML under `spec/`: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
