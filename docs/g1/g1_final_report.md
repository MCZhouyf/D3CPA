# G1 final report

Status: **PASS**.  The author-approved substitution matrix contains 12 successful core slots across six tasks. Actual execution seeds and raw evidence hashes remain in the run matrix; they are not relabelled as physical 11001/11002 executions.

Eligible action rows: 638.  Trace-audit sample: 30 rows.  Token source: unavailable.

## Throughput

Completed-episode wall time (sum of controller attempts): 9407.661 s; mean 783.972 s; p90 1437.925 s.  See `runs/g1/throughput_report.json` for the complete measured distribution.

## Limits

This smoke verifies observability, deterministic labels, and the selected task paths. It does not estimate G6 performance, fit a calibrator, or enable evidence availability masks.

Git finalization: working tree clean = `False`. This status reports verified G1 artifacts; it does not erase or silently commit pre-existing working-tree changes.
