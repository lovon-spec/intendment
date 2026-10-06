# Polymarket dispute backtest

The numbers behind sections 0, 1 and 6 of the [oracle design](../docs/intendment-oracle-design-v0.5.md): every UMA dispute on Polymarket's requests in the 90 days to 2026-10-01 (Polygon blocks 89,554,537 to 94,738,439), and what the design's settlement would have changed.

- [`report/scenarios.md`](report/scenarios.md): the design's dispute numbers and its three settlement scenarios, from `scenarios.py`.
- [`report/stats.md`](report/stats.md): the full on-chain picture (volume, fees, rewards, timing, locked stake, disputes), from `scripts/write_report.py`.

## Check the numbers

The two dispute files the backtest reads are in `data/`, so this takes seconds:

```sh
python3 scenarios.py data
```

## Rebuild from the chain

Python 3.13 with `eth-abi` 6.0.0b1, `eth-utils` 6.0.0, `requests` and `numpy` 2.4.6. Public, keyless RPCs only. About an hour, and 400 MB of logs.

```sh
export SSL_CERT_FILE=$(python3 -m certifi)
cd scripts

# 1. contracts and the window's block numbers
python3 probe_contracts.py
python3 find_blocks.py 2026-06-26T00:00:00 2026-07-03T00:00:00 2026-09-01T00:00:00 2026-10-01T00:00:00 \
    > ../data/block_anchors.json 2> ../data/block_anchors.err

# 2. raw logs of UMA's managed and legacy oracles, resumable
python3 fetch_logs.py --oo MOOV2 --from 89000000 --to 94792499 --chunk 2500 --workers 4 > ../data/fetch_MOOV2.log 2>&1
python3 fetch_logs.py --oo OOv2  --from 89000000 --to 94792499 --chunk 5000 --workers 2 > ../data/fetch_OOv2.log 2>&1
python3 moov2_history.py

# 3. one row per Polymarket request, enriched for requests made before the fetched range
python3 build_requests.py > ../data/build_requests.log 2>&1
python3 enrich_requests.py 6 > ../data/enrich.log 2>&1

# 4. statistics, the two dispute files, Polymarket market metadata
python3 columns.py > ../data/columns.log 2>&1
python3 stats_np.py
python3 gamma_disputes.py
python3 gamma_summary.py

# 5. the checks the report cites
python3 store_check.py
python3 crosscheck.py > ../data/crosscheck.log 2>&1
python3 crosscheck2.py
(cd ../data && python3 ../scripts/crosscheck_merge.py)   # only if crosscheck.py stopped on a rate limit

# 6. the report
python3 write_report.py && mv ../stats.md ../report/stats.md
cd .. && python3 scenarios.py data > report/scenarios.md
```

Chain data for the fixed window reproduces exactly. Polymarket's market metadata (titles, lifetime volumes, open interest) is read live; the files here are as fetched on 2026-10-06, so volumes of markets still trading will have moved.

## Corrections to design v0.4

- Honest self-corrections are 57, not 52, and paid UMA 25,000, not 22,875 (14,250 would stay with the proposers, 10,750 go to the venue). v0.4 left out all of one proposer's self-disputes, but only 86 of them sit on requests with a liveness of a billion seconds, the configuration accident; its other 5 are ordinary.
- "Too early" on 589 counts every such settlement in the window, including disputes raised before it. Of the window's own 1,097 resolved disputes, 567 came back too early.
- The 84% of settled disputes on 500-bond markets since MOOV2 launched comes from a separate scan of all MOOV2 disputes and is not rebuilt here. In this window it is 61% (672 of 1,097 resolved disputes).

Design v0.5 carries these.
