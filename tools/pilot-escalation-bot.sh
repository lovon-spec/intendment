#!/usr/bin/env bash
# Escalation bot for the Agent Skills Registry's Intendment wrapper on Gnosis.
#
# The wrapper never sends a case to Kleros by itself: someone has to call it. Every run, this bot
# looks at each case the wrapper holds and sends the one call the contract would accept right now,
# in this order:
#   escalate(id)        a registration challenge nobody answered within the window
#   forward(id)         a removal challenge, which has no window and goes to Kleros at once
#   forwardOrLapse(id)  Kleros kept failing past the grace period: retry, else the emergency lapse
#   lapse(id)           the court fee can't be covered after the funding period: the emergency lapse
# Each call is test-run with eth_call first and only sent if it would succeed (escalate and forward
# only if they would actually reach Kleros). Cases that have ended (forwarded, conceded, lapsed) are
# not looked at again. The bot decides nothing itself and only spends gas: court fees come from the
# case. Run it every few minutes, e.g. from cron under flock.
#
# Files in $BOT_DIR (default ~/.intendment-bot): key (the bot's private key, mode 600), address,
# done (ids of ended cases). Nothing is ever printed from the key file.
set -uo pipefail

CAST=${CAST:-$HOME/.foundry/bin/cast}
BOT_DIR=${BOT_DIR:-$HOME/.intendment-bot}
RPC=${RPC:-https://rpc.gnosischain.com}
WRAPPER=${WRAPPER:-0x00658F534A29DaC9D068F8df258A97F4103b6506}
GAS_LIMIT=${GAS_LIMIT:-2600000} # the wrapper needs about 2.2M gas left for the Kleros call
MIN_BALANCE_WEI=${MIN_BALANCE_WEI:-10000000000000000} # warn below 0.01 xDAI

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"; }
FROM=$(cat "$BOT_DIR/address")
DONE="$BOT_DIR/done"
touch "$DONE"

code=$("$CAST" codesize "$WRAPPER" --rpc-url "$RPC" 2>/dev/null) || { log "rpc error reading the wrapper"; exit 1; }
if [ "$code" = "0" ]; then log "wrapper not live yet"; exit 0; fi

count=$("$CAST" call "$WRAPPER" 'caseCount()(uint256)' --rpc-url "$RPC" 2>/dev/null) || { log "rpc error reading caseCount"; exit 1; }
count=${count%% *}

balance=$("$CAST" balance "$FROM" --rpc-url "$RPC" 2>/dev/null || echo 0)
if [ "$(python3 -c "print(int('$balance') < $MIN_BALANCE_WEI)")" = "True" ]; then
  log "WARNING: bot balance $balance wei is below $MIN_BALANCE_WEI; top up $FROM"
fi

# simulate <signature> <id> -> prints the call's return value, fails if the call would revert
simulate() { "$CAST" call "$WRAPPER" "$1" "$2" --from "$FROM" --gas-limit "$GAS_LIMIT" --rpc-url "$RPC" 2>/dev/null; }

send() { # <function> <id>
  local out hash status
  out=$("$CAST" send "$WRAPPER" "$1(uint256)" "$2" --private-key "$(cat "$BOT_DIR/key")" \
    --gas-limit "$GAS_LIMIT" --rpc-url "$RPC" --json 2>&1) || { log "case $2: $1 failed to send: ${out:0:300}"; return 1; }
  hash=$(echo "$out" | jq -r '.transactionHash')
  status=$(echo "$out" | jq -r '.status')
  log "case $2: sent $1, tx $hash, status $status"
}

open=0
for ((id = 0; id < count; id++)); do
  grep -qx "$id" "$DONE" && continue
  raw=$("$CAST" call "$WRAPPER" 'caseOf(uint256)' "$id" --rpc-url "$RPC" 2>/dev/null) || { log "case $id: rpc error"; continue; }
  state=$((16#${raw:2:64})) # enum State { Unbound, Open, Forwardable, Forwarded, Conceded, Lapsed }
  if [ "$state" -ge 3 ]; then echo "$id" >> "$DONE"; log "case $id: ended (state $state)"; continue; fi
  open=$((open + 1))
  if [ "$(simulate 'escalate(uint256)(bool)' "$id")" = "true" ]; then send escalate "$id"; continue; fi
  if [ "$(simulate 'forward(uint256)(bool)' "$id")" = "true" ]; then send forward "$id"; continue; fi
  if simulate 'forwardOrLapse(uint256)(bool)' "$id" > /dev/null; then send forwardOrLapse "$id"; continue; fi
  if simulate 'lapse(uint256)' "$id" > /dev/null; then send lapse "$id"; continue; fi
done
log "ok: $count cases, $open open"
