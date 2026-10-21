# Pilot: the Agent Skills Registry on an Intendment wrapper

The registry's arbitrator moves from Kleros (court 19, three jurors) to an Intendment wrapper in
front of that same court. Submitters and challengers pay exactly what they pay today. When a
submission is challenged, the submitter has one day to admit it: then no court case is opened, the
challenger gets the same payout as a court win, and the submitter gets the 21.6 xDAI court fee back.
If nobody answers within the day, anyone sends the case on to Kleros.

Registry `0x67DB…68f9`, timelock `0xc8Ba…3ADa` (7-day delay; our Safe `0x5570…619F` proposes and
cancels; anyone may execute). Wrapper settings: window, funding period, resolver grace and retirement
margin 1 day each, reserve timelock 7 days; one epoch on the registry's current extra data with no
margin or premium and maxCost 32.4 xDAI; a 21.6 xDAI reserve, booked as principal because the
timelock sends it.

Gas below is from a Gnosis fork at block 48,859,000. Even at 1 gwei the whole sequence costs under
0.01 xDAI, and the base fee is far lower today.

## Steps

1. **Deploy the factory** from any funded address (4.33M gas), e.g.
   `forge create contracts/src/IntendmentFactory.sol:IntendmentFactory --rpc-url https://rpc.gnosischain.com --account <deployer> --broadcast`,
   and verify the source. Nobody should deploy through it before step 4: the batch expects the
   factory's first wrapper to be ours.
2. **Propose the Safe transaction.** Pin the juror page first and pass its MetaEvidence:
   `FACTORY=0x… REGISTRATION_META_EVIDENCE=/ipfs/… CLEARING_META_EVIDENCE=/ipfs/… forge script contracts/script/AgentSkillsPilot.s.sol`.
   It prints the Safe transaction (to the timelock, value 0, data `scheduleBatch(…)`), its
   safeTxHash, the operation id, and the later execute and cancel calls. It refuses a missing
   factory and warns on placeholder MetaEvidence. Executing it costs 0.14M gas.
3. **Wait 7 days.** The batch is public in the timelock's `CallScheduled` events; review it there.
4. **Execute.** Check `cast nonce <factory>` still returns 1, fund the Safe with 21.6 xDAI, then send
   the printed `executeBatch` from the Safe with value 21.6 xDAI (4.18M gas). One transaction deploys
   the wrapper, registers the epoch, switches the arbitrator and deposits the reserve. Anyone may
   execute, but only by attaching the 21.6 xDAI. Ship the `intend` profile that pins the wrapper and
   its 192-byte extra data at the same time: the CLI fails closed on a changed arbitrator.
5. **Run the escalation bot.** Watch the wrapper's `CaseOpened` events. Once a case's `deadline` has
   passed with no answer, call `escalate(id)`; call `forward(id)` on removal cases right away, since
   they have no window. Anyone can do this and it only costs gas (0.64M per case); the court fee
   comes from the case. The wrapper checks it has enough gas for the Kleros call, so send with a
   2.2M gas limit or it reverts with `InsufficientCallGas`.

## Cancelling

Until the batch executes, the Safe can cancel it: a Safe transaction to the timelock, value 0, data
`cancel(<operation id>)` as printed in step 2 (0.06M gas). Fix the problem and propose again.
If someone deploys through the factory during the wait, the batch reverts on execution; it cannot
switch the arbitrator to someone else's wrapper. Cancel and propose again with a fresh plan.
