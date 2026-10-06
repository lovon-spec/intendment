"""Minimal read-only JSON-RPC client for Polygon with endpoint fallback and retries.

Only read methods are used (eth_blockNumber, eth_call, eth_getLogs, eth_getBlockByNumber,
eth_getCode). No signing, no wallets, no API keys.
"""
import json
import random
import threading
import time

import requests

ENDPOINTS = [
    "https://polygon-bor-rpc.publicnode.com",
    "https://polygon.drpc.org",
    "https://1rpc.io/matic",
    # Added after the listed ones proved unusable for eth_getLogs at this log density
    # (publicnode: 10-1000 block cap depending on result size; drpc free: ~100 blocks;
    # 1rpc: 50 blocks). Both are public, keyless endpoints.
    "https://polygon.gateway.tenderly.co",
    "https://polygon.api.onfinality.io/public",
    # "https://polygon-rpc.com",  # returned 403 "API key disabled, tenant disabled" on 2026-10-01
]

_lock = threading.Lock()
_penalty = {e: 0.0 for e in ENDPOINTS}  # unix time until which the endpoint is cooled down
_session = threading.local()


class RpcError(Exception):
    def __init__(self, msg, code=None, endpoint=None):
        super().__init__(msg)
        self.code = code
        self.endpoint = endpoint


def _sess():
    s = getattr(_session, "s", None)
    if s is None:
        s = requests.Session()
        _session.s = s
    return s


def _pick(exclude=()):
    now = time.time()
    with _lock:
        live = [e for e in ENDPOINTS if _penalty[e] <= now and e not in exclude]
        if not live:
            live = [e for e in ENDPOINTS if e not in exclude] or list(ENDPOINTS)
            live.sort(key=lambda e: _penalty[e])
            return live[0]
    return random.choice(live)


def _cool(ep, secs):
    with _lock:
        _penalty[ep] = max(_penalty[ep], time.time() + secs)


def call(method, params, endpoint=None, timeout=45, retries=8, fatal_codes=()):
    """Call a JSON-RPC method. Rotates endpoints on transport/overload errors.

    Raises RpcError for JSON-RPC errors that look deterministic (e.g. 'range too large'),
    so callers can adapt (e.g. shrink the block range)."""
    last = None
    tried = []
    for attempt in range(retries):
        ep = endpoint or _pick(exclude=tried[-1:] if tried else ())
        tried.append(ep)
        body = {"jsonrpc": "2.0", "id": random.randint(1, 1 << 30), "method": method, "params": params}
        try:
            r = _sess().post(ep, json=body, timeout=timeout, headers={"content-type": "application/json"})
        except requests.RequestException as e:
            last = RpcError(f"transport {type(e).__name__}: {e}", endpoint=ep)
            _cool(ep, 10)
            time.sleep(min(2 ** attempt, 20) * 0.5)
            continue
        if r.status_code in (429, 500, 502, 503, 504, 520, 521, 522, 524, 529) or r.status_code >= 500:
            last = RpcError(f"HTTP {r.status_code}: {r.text[:200]}", code=r.status_code, endpoint=ep)
            _cool(ep, 15 if r.status_code == 429 else 8)
            time.sleep(min(2 ** attempt, 20) * 0.5)
            continue
        try:
            j = r.json()
        except ValueError:
            last = RpcError(f"bad json HTTP {r.status_code}: {r.text[:200]}", endpoint=ep)
            _cool(ep, 8)
            continue
        if isinstance(j, dict) and j.get("error"):
            err = j["error"]
            if isinstance(err, dict):
                msg = str(err.get("message", err)); code = err.get("code")
            else:
                msg = str(err); code = None
            low = msg.lower()
            # Deterministic-ish errors that the caller should handle by changing the request
            if any(k in low for k in ("range", "too many", "limit", "exceed", "response size", "10000", "query returned more")):
                raise RpcError(msg, code=code, endpoint=ep)
            if code in fatal_codes or "execution reverted" in low:
                raise RpcError(msg, code=code, endpoint=ep)
            last = RpcError(msg, code=code, endpoint=ep)
            _cool(ep, 8)
            time.sleep(min(2 ** attempt, 20) * 0.5)
            continue
        if "result" not in j:
            last = RpcError(f"no result: {str(j)[:200]}", endpoint=ep)
            _cool(ep, 8)
            continue
        return j["result"]
    raise last or RpcError("unknown failure")


def block_number():
    return int(call("eth_blockNumber", []), 16)


def get_block(n, full=False):
    return call("eth_getBlockByNumber", [hex(n), full])


def eth_call(to, data, block="latest"):
    return call("eth_call", [{"to": to, "data": data}, block])


def get_logs(address, topics, from_block, to_block, endpoint=None, timeout=60):
    flt = {"fromBlock": hex(from_block), "toBlock": hex(to_block), "topics": topics}
    if address:
        flt["address"] = address
    return call("eth_getLogs", [flt], endpoint=endpoint, timeout=timeout, retries=6)
