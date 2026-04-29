# CLAUDE.md — autosweep operating manual

`autosweep` runs **N serial simulations** in parallel from a parameter
sweep file and collects their results. The campaign typically takes days
to weeks because each simulation runs hours, can stall on numerical
non-convergence, and the MATLAB process tree is annoying to kill cleanly.

This document tells Claude (or any agent) how to drive a campaign to completion
**without supervision**. Read this entire file before taking action.

---

## 1. The two success conditions

Every case has to clear **two gates**:

1. **`sim_done`** — `simulations/Case_<N>/` contains a `t<X>kyr.mat` file
   with `X >= threshold_kyr` (default 400). The MATLAB simulation finished.
2. **`collected`** — `output/full_results/Time_Evolution_Case<N>.mat` exists.
   The post-processing collection produced the ML training file.

Both must be true → that case is `both_done`. Goal: **all N cases `both_done`**
(minus a small `accepted_failed` set documented below).

---

## 2. Where to look

Always start with `status_report.py` (idempotent, fast):

```bash
python3 status_report.py
```

It refreshes two files:

- **`status_state.json`** — machine-readable. Source of truth for what to do next.
  Contains lists for `sim_done`, `collected`, `both_done`, `need_collect`,
  `need_rerun`, `accepted_failed`, plus a timestamp.
- **`status_log.md`** — human-readable.

Two other state files matter:

- **`failed_cases.json`** — `{"failed": [ids], "reasons": {id: text}}`. Cases
  here are skipped by the monitor and counted as `accepted_failed`.
- **`monitor_state.json`** — retry counts per case. Used by the autopilot.

---

## 3. Files in this package

| File | Purpose |
|---|---|
| `scheduler.py` | Initial run of a contiguous case range across N cores. |
| `rerun_cases.py` | Rerun a *non-contiguous* list of case ids. |
| `run.permafrost.py` | Per-case wrapper: copies `src/` to `Case_<N>/`, edits `Initialization.m`, runs MATLAB. |
| `find_unfinished.py` | Lists cases below `threshold_kyr` (no dir, missing-output dir, or partial output). |
| `status_report.py` | Writes `status_state.json` + `status_log.md`. The dashboard. |
| `monitor_loop.py` | **Autopilot.** Polls status, kills stuck jobs, relaunches reruns + collection until done. |
| `kill_all.sh` | Safe teardown of monitor + schedulers + MATLAB runners + collection. |
| `run.sh` | First-time launch: scheduler over the full range. |
| `run_rerun.sh` | One-shot rerun of all cases under threshold. |
| `run_collection.sh` | One-shot MATLAB collection over a case range. |
| `collect_ML_data_all.m` | MATLAB collection script. **Project-specific** body — replace `collect_one_case()` for a different project. |
| `input.txt` | Sample of the tab-separated parameter file. Rename to `input.dat`. |

---

## 4. Standard workflow

```bash
# 0. (One-time) place src/ MATLAB code, input.dat, and this directory together.
#    src/Initialization.m must contain the parameter assignments (e.g.
#    `lambda_s = 1.5;`) that scheduler will overwrite per case.

# 1. Initial launch.
bash run.sh

# 2. Start the autopilot. Background it. It survives MATLAB crashes/hangs.
nohup python3 monitor_loop.py \
    --num_cores 40 \
    --threshold_kyr 400 \
    --max_retries 3 \
    --stuck_minutes 30 \
    --tick_seconds 1800 \
    > monitor.out 2>&1 &

# 3. Walk away. Check status_log.md or monitor.log occasionally.

# 4. When monitor.log says "ALL DONE", you're done.
```

---

## 5. How the autopilot decides

Every `tick_seconds` (default 30 min):

1. Refresh `status_state.json`.
2. If `need_rerun == 0` and `need_collect == 0` → exit with `ALL DONE`.
3. **Detect stuck cases** in `need_rerun`:
   - Log untouched for `stuck_minutes` (default 30), OR
   - Log tail (last 8 KB) contains `"Timestep size is less than the minimum"` ≥ 2 times
     (the Newton-Raphson divergence loop — see §7).
4. If stuck cases exist *and* a rerun is currently active → kill all runners
   (`pkill -9 -f "matlab.*-r runner"` etc.). They'll be relaunched cleanly next tick.
5. If no rerun is active and there are `need_rerun` cases:
   - Cases retried `>= max_retries` → moved into `failed_cases.json`.
   - Remaining cases → fed to `rerun_cases.py`.
6. If no rerun is active *and* no collection is active *and* `need_collect > 0`:
   - Launch `matlab -batch collect_ML_data_all`.
7. Otherwise: idle until next tick.

---

## 6. Manual driving (when you don't want the autopilot)

```bash
# What's still needed?
python3 status_report.py
cat status_log.md

# Just rerun the unfinished ones (one shot):
bash run_rerun.sh

# Collect what's collectable (one shot):
bash run_collection.sh                # all 1..1000
bash run_collection.sh 825 1000       # subset, e.g. resume after a crash

# Tear everything down:
bash kill_all.sh
```

---

## 7. Failure modes — recognize them, don't keep retrying forever

### 7a. Newton–Raphson non-convergence (a.k.a. "the timestep loop")

Symptom in `simulations/Case_<N>/simulation.log`:
```
We cut timestep size to: dt = 246375
Timestep size is less than the minimum
we have gone back to previous saved timestep
We cut timestep size to: dt = 31536000   ← starts over, infinite loop
```
The solver halves `dt` seven times, hits the minimum, reverts to the last
saved timestep, restarts at full dt, and the same divergence happens again.
Each cycle takes ~30 sec, so logs grow ~800 B/min — looks "alive" in `top`
but progress in time has stopped.

**It will never finish without a model-side fix** (regularization, alternate
friction, parameter rejection). The autopilot's `--max_retries` and stuck
detection eventually mark these as `accepted_failed`. **Do not crank
`--max_retries` higher to "give them another chance" — same wall every time.**

In our 1000-case Permafrost run, all 8 unrecoverable cases shared the
**lowest `Swr_freeze` (0.10 or 0.12)**. If you see a similar parameter
clustering in `failed_cases.json`, the input sampling probably hit a
non-physical region.

### 7b. Silent process detachment

`run.permafrost.py` launches MATLAB with `start_new_session=True`, so killing
the parent shell does NOT kill MATLAB. Worse: the visible MATLAB process is
actually a child (`MathWorksServiceHost client-v1`) of a parent
(`MATLAB ... -r runner`). Killing only the child causes MATLAB to spawn a new
child seconds later. **Always kill `MATLAB ... -r runner` first**, then the
clients. `kill_all.sh` does this in the right order.

### 7c. NFS lock files block deletion

If a directory holds open files on another NFS client, `rm -rf Case_<N>`
fails with `Directory not empty` (it's actually the `.nfs<hex>` lock). Kill
the process holding the file (often a MATLAB on another machine) and retry.

### 7d. Multi-machine racing

If you start the campaign on multiple hosts that share the NFS-mounted
`simulations/`, two hosts can both delete and re-create the same
`Case_<N>/` mid-run, corrupting it. Use `start_case`/`end_case` ranges to
partition work across hosts (e.g. machine A: 1–500, machine B: 501–1000).

### 7e. "Done" cases that aren't done — collection-side errors

A simulation can finish all `t*.mat` files but still throw at the end if
`collect_ML_data` (called by `Main_loop_2D` post-processing) has hardcoded
output paths that don't exist. Symptoms: the simulation.log ends with
`Error using save / Cannot create '/path/...': directory does not exist`.
Files are present; the project-level error is benign — `status_report.py`
will treat the case as `sim_done` and collection will pick it up later.

If you're customizing `collect_ML_data_all.m`, **always use `PERMAFROST_ROOT`**
(env var) or `pwd` — never hardcode an absolute path.

---

## 8. Decision rules (when to ask the user vs proceed)

**Proceed without asking:**
- Status check, refreshing logs, listing cases.
- Launching `run_rerun.sh` or `run_collection.sh` if status shows work to do
  and nothing else is running.
- Killing stuck MATLAB runners that match the §7a pattern.
- Adding a case to `failed_cases.json` after `max_retries` is exceeded.

**Ask the user:**
- Increasing `max_retries` (it will not help non-convergent cases).
- Modifying `src/` MATLAB source.
- Deleting `Case_<N>/` directories that may contain useful partial data.
- Running on multiple hosts (need range partitioning).
- Force-pushing or otherwise destructive git operations.

**Never:**
- Restart the whole campaign (`run.sh`) when a partial state exists. That
  re-runs already-done cases and wipes their dirs (`run.permafrost.py` does
  `shutil.rmtree` on the case dir). Use `run_rerun.sh` instead.
- Edit `Initialization.m` directly in `src/`. Parameters come from
  `input.dat` via `--param`.

---

## 9. Customizing for a different MATLAB project

1. Replace `src/` with the new project's MATLAB code.
2. Edit `src/Initialization.m` so each `--param` key (column name in
   `input.dat`) maps to a `key = value;` assignment that the regex in
   `run.permafrost.py` can find.
3. Update `input.dat` columns to match the parameters being swept.
4. Replace `collect_one_case()` body in `collect_ML_data_all.m` with the new
   project's post-processing.
5. Adjust `--threshold_kyr` and `--output_pattern` in `monitor_loop.py` if
   the success-marker filename differs.

---

## 10. Sanity prompts before any "rerun everything" action

Before launching a big rerun, confirm:
- [ ] No `MATLAB`, `MathWorks`, `scheduler.py`, `rerun_cases.py`, or
      `monitor_loop.py` is currently running (check with `ps aux | grep`).
- [ ] `failed_cases.json` exists if you have known-bad cases — otherwise
      they'll be retried again.
- [ ] You're targeting the right directory. Check `pwd` and that `input.dat`
      and `src/` are present.
- [ ] If running on a shared filesystem, no other host is also touching this
      `simulations/` tree.
