# Stage-1a Solidity review prototype

Non-upgradeable, native-currency ERC-792 wrapper for the **existing stage-1a
specification 0.5**, not the later RFC credit/severity layer.

```sh
forge build --sizes
forge test -vvv
```

Compiler: Solidity 0.8.30, via IR, optimizer 200, Paris EVM. CI pins Foundry v1.3.6.
No contract-library dependency is needed. Tests use a minimal cheatcode interface
and explicit host/resolver fixtures.

Start review at [the implementation note](../docs/stage1a-solidity-implementation.md).
Status: a pilot deployment. The factory is live on Gnosis at
`0xc2D5c23316C49a45Fb3b6bb48BA631d464113865`, and the Agent Skills Registry's switch to its
wrapper is scheduled through the registry's timelock; see the
[pilot runbook](../docs/pilot-agent-skills-registry.md). The code passed automated security
reviews and fork tests against the real registry, Curate lists and Kleros on Gnosis, and the
juror page that follows cases through the wrapper is in the registry's own repository. It has not
had an external audit.
