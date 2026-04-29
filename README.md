# autosweep

> **Multi-core parameter sweeps for any serial solver, with autopilot recovery.**

`v0.0.1-rc1`

An orchestration framework for running 100s–1000s of long-running serial
simulations across all the cores you have, with automatic detection and
recovery from stalls, crashes, and partial completions.

Originally built for an Arctic permafrost ML training-data campaign that
ran 1000 cases over ~2 weeks across 3 machines, recovering from solver
non-convergence, stuck processes, NFS lock issues, and partial collection
runs. The lessons from that campaign — the five failure modes documented in
`CLAUDE.md` — are what make this package different from a naive sweep runner.

This package ships **only the orchestration framework** (Python + shell).
You bring your own simulator (MATLAB by default; trivially adaptable to any
black-box command-line solver).

---

## Quick start

### Step 1 — copy in your project files

Before running anything, place your project's files in this package's
working directory (the package root, alongside `monitor_loop.py`, etc.):

```bash
# 1a. MATLAB source — copy your simulation code into src/
cp -r /path/to/your/matlab_project/* src/
# Required inside src/:
#   - Initialization.m   — must contain `key = value;` lines for every
#                          parameter column in input.dat (the scheduler
#                          overwrites these per case via regex)
#   - Main_loop_2D.m     — entry point called by run.permafrost.py
#                          (rename in run.permafrost.py::write_runner if yours
#                          is named differently)
#   - everything Main_loop_2D needs to run

# 1b. Parameter sweep — drop in your input.dat
cp /path/to/your/input.dat ./input.dat
# Tab-separated, header row + one row per case. Column names must match
# the variable names in src/Initialization.m.

# 1c. Collection script — drop in your project-specific MATLAB
#     post-processing script (whatever its name).
cp /path/to/your/collect_<your_project>.m ./
# Then either rename to collect_ML_data_all.m, OR set the env var:
export COLLECT_SCRIPT=collect_<your_project>
```

The collection script is project-specific (it knows the structure of your
state variables), so this package does NOT ship one. See "Collection script
contract" below for the interface it needs to satisfy.

### Step 2 — initial launch

```bash
bash run.sh
```

### Step 3 — start the autopilot

```bash
nohup python3 monitor_loop.py \
    --num_cores 40 \
    --threshold_kyr 400 \
    --max_retries 3 \
    --stuck_minutes 30 \
    --collect_script "${COLLECT_SCRIPT:-collect_ML_data_all}" \
    > monitor.out 2>&1 &
```

### Step 4 — walk away

Status updates land in `status_log.md`. Done when `monitor.log` shows
`ALL DONE`.

---

## What it does

For each case in `input.dat`, the system:

1. Copies `src/` to `simulations/Case_<N>/`
2. Edits `Initialization.m` so the case's parameter values are set
3. Runs MATLAB (`Main_loop_2D` by default)
4. Checks the case reached the simulation threshold (`t<X>kyr.mat` with `X >= --threshold_kyr`)
5. Runs your collection MATLAB script to produce post-processed files in `output/`

When things go wrong, the autopilot:

- Detects stuck cases (log untouched > 30 min, or stuck on Newton-Raphson divergence)
- Kills the relevant MATLAB processes (parent + child, in the right order)
- Relaunches up to `--max_retries` times
- Marks repeatedly-failing cases as `accepted_failed` so they don't block completion

---

## File guide (what's shipped vs. what you supply)

### Shipped by this package

| File | Purpose |
|---|---|
| **`monitor_loop.py`** | Autopilot. Run this, walk away. |
| **`status_report.py`** | Refresh the dashboard (`status_state.json` + `status_log.md`). |
| **`kill_all.sh`** | Safe teardown — handles MATLAB's parent/child respawn trick. |
| `scheduler.py` | Initial run of a contiguous case range. |
| `rerun_cases.py` | Rerun a non-contiguous list of case ids. |
| `find_unfinished.py` | List cases below the simulation threshold. |
| `run.permafrost.py` | Per-case launcher (called by the schedulers). |
| `run.sh`, `run_rerun.sh`, `run_collection.sh` | Entry-point shell wrappers. |
| `input.txt` | Sample 5-row input. Rename to `input.dat`. |
| `src/README.md` | Notes on what goes in `src/`. |
| **`CLAUDE.md`** | Full operating manual for an AI agent driving the campaign. |
| `tests/` | Hermetic Python tests + optional e2e MATLAB test. |

### YOU supply (project-specific)

| File | Where | Purpose |
|---|---|---|
| `src/*.m` | `src/` | Your simulation code. Must include `Initialization.m` and an entry-point `Main_loop_2D.m`. |
| `input.dat` | package root | Tab-separated parameter sweep. |
| `<your_collection_script>.m` | package root | Post-processing MATLAB script. Default name `collect_ML_data_all.m`; override with `COLLECT_SCRIPT` env var. |

---

## Collection script contract

`run_collection.sh` and `monitor_loop.py` invoke MATLAB with:

```bash
START_CASE_ID=N END_CASE_ID=M PERMAFROST_ROOT=$(pwd) \
    matlab -batch "${COLLECT_SCRIPT:-collect_ML_data_all}"
```

Your `${COLLECT_SCRIPT}.m` must:
- Read `START_CASE_ID`, `END_CASE_ID` from `getenv()`.
- For each `case_id` in that range, `cd` into `simulations/Case_<case_id>/` and produce post-processed `.mat` files under `output/<category>/`.
- Honor the `failed_cases.json` skip list (read with `jsondecode(fileread(...))`).
- Tolerate per-case failures (try/catch around each case so one bad case
  doesn't kill the whole batch).

A reference implementation tailored for the Permafrost project lives at
`Arctic_Permafrost_Salinity_Change/collect_ML_data_all.m` (sibling of this
package). Use it as a template and rewrite the body of `collect_one_case`
for your project's state variables.

---

## State files (created at runtime)

| File | Role |
|---|---|
| `status_state.json` | Source of truth: per-category lists of case ids. |
| `status_log.md` | Human-readable status. |
| `monitor_state.json` | Per-case retry counts (autopilot). |
| `monitor.log` | Action history (autopilot). |
| `failed_cases.json` | Permanently-failed case ids. Honored by the autopilot, status reporter, and collection script. |
| `simulations/Case_<N>/simulation.log` | Per-case MATLAB output. |

---

## Tests

```bash
bash tests/run_tests.sh
```

- `tests/test_python.py` — fast hermetic tests of all Python scripts on a
  synthetic 5-case fixture. No MATLAB required.
- `tests/test_collection.sh` — end-to-end MATLAB collection test. Skips if
  MATLAB isn't available or if the reference project (with its `<COLLECT_SCRIPT>.m`)
  isn't found.
- `tests/test_simulation.sh` — end-to-end simulation test (slow, ~2–4 hours).
  Runs a small range of real cases through the full pipeline.

See `tests/README.md` for usage details and overrides.

---

## Read this before driving the system manually

`CLAUDE.md`. Especially §7 (failure modes — the MATLAB process tree
gotcha alone will save you an hour) and §8 (when to ask vs proceed).

---

## Acknowledgments

Initial release scaffolded with [Claude Code](https://claude.com/claude-code).
The hard-won failure modes documented in `CLAUDE.md` are real lessons from
the Arctic permafrost campaign, not dry-run guesses.
