# Tests

Two layers:

## 1. `test_python.py` — fast, hermetic, always runs

Builds a 5-case synthetic project layout in `/tmp` (input.dat, src/,
simulations/, output/, failed_cases.json) and exercises every Python
script:

- `status_report.py` — verifies each case lands in the right category
  (both_done, need_collect, need_rerun, accepted_failed, sim_done, collected).
- `find_unfinished.py` — verifies the unfinished case ids and counts.
- `scheduler.py --dry_run` — verifies command construction and core
  bucketing.
- `rerun_cases.py --dry_run` — same for non-contiguous case lists.
- `monitor_loop.case_is_stuck()` — verifies stuck detection from log
  age and from repeated "Timestep size is less than the minimum"
  divergence pattern.

No MATLAB required. Run from anywhere:

```bash
python3 tests/test_python.py
```

Exit 0 = pass. Any FAIL line means a regression.

## 2. `test_collection.sh` — end-to-end, needs MATLAB + a reference project

Symlinks `simulations/`, `src/`, `input.dat` from a completed reference
project (default: `Arctic_Permafrost_Salinity_Change`) into a temp dir,
runs `collect_ML_data_all.m` for a small case range, and verifies the
expected output `.mat` files appear.

```bash
# Defaults: REF_DIR=/home/staff/dliu/6.Kehua/Arctic_Permafrost_Salinity_Change
#           TEST_CASES="1 100 500"
bash tests/test_collection.sh

# Override:
REF_DIR=/path/to/your/finished/project TEST_CASES="42 100 999" bash tests/test_collection.sh
```

Auto-skips with a SKIP message if MATLAB isn't on PATH or the reference
data isn't available — safe to run on any machine.

## Run both

```bash
bash tests/run_tests.sh
```
