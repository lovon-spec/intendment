"""Find the first block at/after given UTC timestamps (bracketed binary search on block timestamps).
Note: Polygon PoS block time is no longer ~2.0 s, so the bracket is derived from measured rates."""
import json, sys, datetime as dt
import rpc

def ts_of(n):
    for _ in range(6):
        b = rpc.get_block(n)
        if b:
            return int(b["timestamp"], 16)
    raise RuntimeError(f"block {n} unavailable")

def first_block_at_or_after(t, lo, hi):
    assert ts_of(lo) < t <= ts_of(hi), (lo, hi)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if ts_of(mid) < t: lo = mid
        else: hi = mid
    return hi

if __name__ == "__main__":
    head = rpc.block_number() - 100
    head_ts = ts_of(head)
    out = {"head": head, "head_ts": head_ts, "head_utc": dt.datetime.fromtimestamp(head_ts, dt.timezone.utc).isoformat()}
    for label in sys.argv[1:]:
        t = int(dt.datetime.fromisoformat(label).replace(tzinfo=dt.timezone.utc).timestamp())
        # bracket: walk back in steps of 500k blocks until the timestamp is below t
        hi = head
        lo = head - 500000
        while ts_of(lo) >= t:
            hi = lo; lo -= 500000
        b = first_block_at_or_after(t, lo, hi)
        out[label] = {"block": b, "ts": ts_of(b), "prev_ts": ts_of(b - 1)}
    print(json.dumps(out, indent=1))
