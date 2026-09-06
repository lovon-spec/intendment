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
Do not deploy this slice with real funds. No live-fork or security-audit sign-off
is claimed. A functional evidence display and live host/resolver validation are
required before a pilot.
