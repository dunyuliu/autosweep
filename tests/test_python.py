"""Smoke tests for the Python scripts in the package.

Builds a tiny synthetic project layout in a temp dir:
  input.dat with 5 rows
  src/ with a dummy Initialization.m
  simulations/Case_1..5/ in various states (done / partial / missing)
  output/full_results/ partially populated
  failed_cases.json marking one case as failed

Then runs each script and asserts the output is what we expect.

No MATLAB required. Run from anywhere:
  python3 tests/test_python.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent


def py(script_name, *args, cwd=None):
    """Run a script in PKG with args, return (returncode, stdout, stderr)."""
    cmd = [sys.executable, str(PKG / script_name), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout, p.stderr


def make_fixture(root: Path):
    """Build a 5-case mock layout under `root`.

    Case  1: dir exists, t401.02kyr.mat present, collection file present  -> both_done
    Case  2: dir exists, t401.02kyr.mat present, no collection file       -> need_collect
    Case  3: dir exists, only t250kyr.mat (partial)                       -> need_rerun
    Case  4: no dir at all                                                 -> need_rerun
    Case  5: dir exists, t401.02kyr.mat present, marked failed             -> accepted_failed
    """
    # input.dat
    (root / "input.dat").write_text(
        "lambda_s\tqt\te_fold\tSwr_freeze\twater_depth_simul\n"
        "1.5\t0.05\t1500\t0.20\t30\n"
        "2.0\t0.06\t1700\t0.22\t40\n"
        "2.5\t0.07\t1900\t0.24\t50\n"
        "3.0\t0.08\t2100\t0.26\t60\n"
        "3.5\t0.09\t2300\t0.28\t70\n"
    )

    # src/ with a dummy Initialization.m
    src = root / "src"
    src.mkdir()
    (src / "Initialization.m").write_text(
        "lambda_s = 1.0;\nqt = 0.05;\ne_fold = 1500;\n"
        "Swr_freeze = 0.20;\nwater_depth_simul = 30;\n"
    )
    (src / "Main_loop_2D.m").write_text("disp('hi'); exit;\n")

    # simulations/Case_*
    sims = root / "simulations"
    sims.mkdir()
    for cid in (1, 2, 3, 5):
        (sims / f"Case_{cid}").mkdir()
    # Case 1: complete
    (sims / "Case_1" / "t0kyr.mat").write_text("x")
    (sims / "Case_1" / "t401.02kyr.mat").write_text("x")
    # Case 2: complete (no collection yet)
    (sims / "Case_2" / "t0kyr.mat").write_text("x")
    (sims / "Case_2" / "t401.02kyr.mat").write_text("x")
    # Case 3: partial
    (sims / "Case_3" / "t0kyr.mat").write_text("x")
    (sims / "Case_3" / "t250kyr.mat").write_text("x")
    # Case 4: no dir
    # Case 5: complete but marked failed
    (sims / "Case_5" / "t0kyr.mat").write_text("x")
    (sims / "Case_5" / "t401.02kyr.mat").write_text("x")

    # collection output for Case 1 only
    coll = root / "output" / "full_results"
    coll.mkdir(parents=True)
    (coll / "Time_Evolution_Case1.mat").write_text("x")

    # failed_cases.json marking Case 5
    (root / "failed_cases.json").write_text(json.dumps({
        "failed": [5],
        "reasons": {"5": "test fixture: marked failed for unit test"},
    }))


def assert_eq(name, got, want):
    if got != want:
        print(f"  FAIL: {name}: got {got!r}, want {want!r}")
        sys.exit(1)
    print(f"  ok: {name}")


def test_status_report(root: Path):
    print("\n[test_status_report]")
    rc, out, err = py("status_report.py", cwd=str(root))
    assert_eq("returncode", rc, 0)
    state = json.loads((root / "status_state.json").read_text())
    counts = state["counts"]
    assert_eq("total", state["total"], 5)
    assert_eq("sim_done", counts["sim_done"], 3)        # cases 1, 2, 5
    assert_eq("collected", counts["collected"], 1)      # case 1
    assert_eq("both_done", counts["both_done"], 1)      # case 1
    assert_eq("need_collect", counts["need_collect"], 1)  # case 2
    assert_eq("need_rerun", counts["need_rerun"], 2)    # cases 3, 4
    assert_eq("accepted_failed", counts["accepted_failed"], 1)  # case 5
    assert_eq("both_done list", state["both_done"], [1])
    assert_eq("need_collect list", state["need_collect"], [2])
    assert_eq("need_rerun list", state["need_rerun"], [3, 4])
    assert_eq("accepted_failed list", state["accepted_failed"], [5])


def test_find_unfinished(root: Path):
    print("\n[test_find_unfinished]")
    rc, out, err = py("find_unfinished.py", cwd=str(root))
    assert_eq("returncode", rc, 0)
    ids = sorted(int(x) for x in out.split())
    # Cases 3 (partial output) and 4 (no dir). Case 5 has t401.02kyr so it's
    # at threshold even though we mark it failed elsewhere.
    assert_eq("ids", ids, [3, 4])
    assert_eq("stderr count", "Total unfinished: 2 / 5" in err, True)


def test_scheduler_dry_run(root: Path):
    print("\n[test_scheduler_dry_run]")
    rc, out, err = py("scheduler.py",
                      "--num_cores", "2", "--start_case", "2", "--end_case", "4",
                      "--dry_run", cwd=str(root))
    assert_eq("returncode", rc, 0)
    # 3 cases over 2 cores: bucket 0 gets cases 2 and 4, bucket 1 gets case 3
    assert_eq("Core 1 has Case 2", "case_number 2" in out, True)
    assert_eq("Core 1 has Case 4", "case_number 4" in out, True)
    assert_eq("Core 2 has Case 3", "case_number 3" in out, True)
    # Parameter passing
    assert_eq("lambda_s passed", "lambda_s=2.0" in out, True)


def test_rerun_cases_dry_run(root: Path):
    print("\n[test_rerun_cases_dry_run]")
    rc, out, err = py("rerun_cases.py",
                      "--num_cores", "2", "--cases", "3 5",
                      "--dry_run", cwd=str(root))
    assert_eq("returncode", rc, 0)
    assert_eq("Case 3 queued", "case_number 3" in out, True)
    assert_eq("Case 5 queued", "case_number 5" in out, True)


def test_monitor_helpers(root: Path):
    """Test stuck-case detection in monitor_loop.py."""
    print("\n[test_monitor_helpers]")
    sys.path.insert(0, str(PKG))
    import importlib
    monitor = importlib.import_module("monitor_loop")

    class A: pass
    args = A()
    args.simulations_dir = str(root / "simulations")
    args.stuck_minutes = 30
    args.stuck_log_token = "Timestep size is less than the minimum"

    # Case_3 has no log -> not stuck (just hasn't started writing yet)
    assert_eq("no log => not stuck", monitor.case_is_stuck(3, args), False)

    # Add a stuck-pattern log to Case_3
    log = root / "simulations" / "Case_3" / "simulation.log"
    log.write_text(
        "We cut timestep size to: dt = 246375\n"
        "Timestep size is less than the minimum\n"
        "we have gone back to previous saved timestep\n"
        "We cut timestep size to: dt = 246375\n"
        "Timestep size is less than the minimum\n"
        "we have gone back to previous saved timestep\n"
    )
    assert_eq("repeated divergence => stuck", monitor.case_is_stuck(3, args), True)

    # Make an old log that's not divergent
    log2 = root / "simulations" / "Case_2" / "simulation.log"
    log2.write_text("normal output\n")
    old = (Path("/tmp").resolve()).stat().st_mtime - 7200  # 2 hours ago
    os.utime(log2, (old, old))
    assert_eq("very old log => stuck", monitor.case_is_stuck(2, args), True)


def main():
    with tempfile.TemporaryDirectory(prefix="pmss_test_") as tmp:
        root = Path(tmp)
        print(f"Test fixture in: {root}")
        make_fixture(root)
        test_status_report(root)
        test_find_unfinished(root)
        test_scheduler_dry_run(root)
        test_rerun_cases_dry_run(root)
        test_monitor_helpers(root)
    print("\nAll Python tests passed.")


if __name__ == "__main__":
    main()
