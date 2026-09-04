# Releases

A design version and a specification version are one release when they are committed together and cite each other. A release is its signed commits; no tags or timestamp proofs are made (the `v0.4` tag and its OpenTimestamps proof predate that decision and stay as they are). Each release names one **release head**, the commit that adds the design document and therefore contains both artifacts.

## v0.8, 2026-09-04

- release head: 4a4ef27
- design: `docs/intendment-design-v0.8.md` at 4a4ef27
- stage-1 state machine 0.4: `spec/intendment-arbitrator-state-machine.md` at b5797aa, generated from `spec/intendment-arbitrator-state-machine.yaml` at b5797aa by `spec/render.py` (`validate`, `check`, `diagram`, `fixtures`); CI at `.github/workflows/spec.yml`
- supported host profiles: Light GTCR (the Scout lists on Gnosis), Classic GTCR; Curate V2 described, not yet supported (specification section 15)
- review status: v0.7 and 0.3 reviewed by GPT (`docs/intendment-design-v0.7-review-gpt.md`, folded); v0.8 and 0.4 unreviewed

## v0.7, 2026-09-04

- design: `docs/intendment-design-v0.7.md` at c78064b
- stage-1 state machine 0.3: `spec/intendment-arbitrator-state-machine.md` at c9338de, generated from `spec/intendment-arbitrator-state-machine.yaml` at c9338de by `spec/render.py`
- supported host profiles: Light GTCR (the Scout lists on Gnosis), Classic GTCR; Curate V2 described, not yet supported (specification section 13)
- release head: c78064b
- review status: v0.6 reviewed by GPT (`docs/intendment-design-v0.6-review-gpt.md`, folded); v0.7 and 0.3 reviewed by GPT at 0f34622, folded into v0.8

## v0.6, 2026-09-04

- design: `docs/intendment-design-v0.6.md` at 4c16932
- stage-1 state machine 0.2: `spec/intendment-arbitrator-state-machine.md` at d292a3e
- review status: GPT at f2a1b81

## v0.5, 2026-09-02

- design: `docs/intendment-design-v0.5.md` at 7530951
- review status: Codex, `docs/intendment-design-v0.5-review.md` at a486765, request changes; folded into v0.6

## v0.4, 2026-09-02

- design: `docs/intendment-design-v0.4.md` at 16629fc; tag `v0.4` with a GitHub release; OpenTimestamps proof `docs/intendment-design-v0.4.md.ots`, Bitcoin-attested
- review status: Codex, `docs/intendment-design-v0.4-review.md` at b9c4be2; folded into v0.5

## v0.1 to v0.3, 2026-09-02

- `docs/settlement-design-v0.1.md`, `-v0.2.md`, `-v0.3.md`, imported from the maintainer's working notes; v0.1 reviewed by Codex (`docs/settlement-design-v0.1-review.md`)
