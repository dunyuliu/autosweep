# src/ — copy your MATLAB code here BEFORE running

This directory is empty in the released package. Before launching anything,
copy your project's MATLAB simulation code into here:

```bash
cp -r /path/to/your/matlab_project/* src/
```

`run.permafrost.py` does `shutil.copytree(src, simulations/Case_<N>/)`
for every case and then runs MATLAB inside that copy.

## Required files in src/

- **`Initialization.m`** — must contain `key = value;` assignments for every
  parameter column in `input.dat`. The scheduler overwrites these per case
  via regex (see `run.permafrost.py::modify_initialization`). Example for
  the original Permafrost project's columns:
  ```matlab
  lambda_s = 1.5;
  qt = 0.05;
  e_fold = 2000;
  Swr_freeze = 0.25;
  water_depth_simul = 50;
  ```
  Use whatever column names match your `input.dat`.

- **`Main_loop_2D.m`** — the entry point. The runner wraps this in
  try/catch + exit. If your entry-point has a different name, edit
  `run.permafrost.py::write_runner` (one line).

- **Everything `Main_loop_2D` needs to run** — solvers, mesh code, helper
  functions, lookup tables, etc.

## Output contract

Each case should produce `t<X>kyr.mat` files in its working directory as it
progresses (e.g. `t0kyr.mat`, `t10kyr.mat`, ..., `t401.02kyr.mat`).
A case is considered done when the latest such file has `X >= threshold_kyr`
(default 400, configurable via `--threshold_kyr`).

If your project uses a different output filename scheme, override
`--output_pattern` everywhere it appears (`monitor_loop.py`,
`status_report.py`, `find_unfinished.py`). The pattern is a Python regex
whose first capture group is the time value used to compare against
threshold.

## Reference

The Arctic permafrost project (sibling of this package, at
`../Arctic_Permafrost_Salinity_Change/src/`) is the reference
implementation. Use it to see what a working `src/` looks like.
