# Executable model, stage 1a

`intendment/model.py` is an executable model of the IntendmentArbitrator as specified in `../spec/intendment-arbitrator-state-machine.md` 0.5: integer accounting, a Light-GTCR-like host that records whoever calls it as the party of record and pays by `send`, a resolver whose cost, availability and quote availability the test controls, and an invariant check after every transition (conservation, the two reserve accounts, no iteration over funders). Stage 1b offers are behind a flag.

`tests/test_stage1a.py` runs the specification's traces and the v0.8 review's acceptance areas: forward-first resolver failure, quote failure, gas-starved attempts, retirement and withdrawal precision, the party of record, the loss waterfall, pro-rata refunds with dust, ten thousand dust funders, host-only appeals, bid lifetime, capacity occupation under a premium, under-insured removals, reserve gifts after the funding period, and a randomized sequence that must keep every invariant. One test asserts that the transition ids in the YAML source and the model's methods are the same set.

```bash
pip install pyyaml pytest
pytest sim -q
```

It is a model of the specification, not of a contract: gas, reentrancy and ABI details are out of scope, except that "properly gassed" is a boolean the caller controls, as the specification's `MIN_FORWARD_GAS` floor makes it on chain.

## Experiment 3: the credited model

`intendment/credited.py` is RFC 001 revision 2 on top of the stage-1a model, which it subclasses without changing: a cheap first instance with a programmed route and the host's appeal funding rule, credited deposits (prepayment, promise, bond, standing), severity tiers, the cost-shifting and batch concessions, and the bonding rule as an evidence display over an immutable policy. `tests/test_credited.py` runs one test per row of the RFC's section 8 trace table; every transition and every test asserts system-wide conservation. `RESULTS-credited.md` re-derives the payoff table with the award split and lists where the RFC's rules conflict with the spine or with each other. It is not part of the baseline and credits nothing to it.
