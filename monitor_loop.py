"""Autopilot: drive a simulation campaign to completion without manual intervention.

Loop until status_report.py shows no need_rerun and no need_collect.

Each tick (default every 30 min):
  1. Run status_report.py (refreshes status_state.json + status_log.md)
  2. Read state. If both_done + accepted_failed == total, exit.
  3. Detect stuck cases: log file untouched > stuck_minutes OR
     log ends with repeated "Timestep size is less than the minimum"
     (configurable via --stuck_log_token).
  4. If sims are running but none stuck, do nothing.
  5. If there are need_rerun cases AND no rerun is currently active:
       - Filter out cases that have been retried >= max_retries → add to failed.
       - Launch rerun_cases.py for the rest.
  6. If there are need_collect cases AND no rerun running AND no collection running:
       - Launch matlab -batch collect_ML_data_all.
  7. Append actions to monitor.log.

State files:
  - status_state.json  (refreshed by status_report.py)
  - monitor_state.json (retry counts, last-action timestamps)
  - failed_cases.json  (permanent failures; respected by status_report.py)
  - monitor.log        (action history)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input_dat", default="input.dat")
    p.add_argument("--simulations_dir", default="simulations")
    p.add_argument("--source_dir", default="src")
    p.add_argument("--num_cores", type=int, default=40)
    p.add_argument("--threshold_kyr", type=float, default=400.0)
    p.add_argument("--max_retries", type=int, default=3,
                   help="After this many retries on a case, mark it failed and skip")
    p.add_argument("--stuck_minutes", type=int, default=20,
                   help="Log untouched this long => treat case as stuck")
    p.add_argument("--stuck_log_token", default="Timestep size is less than the minimum",
                   help="String at end of log indicating non-recoverable state")
    p.add_argument("--tick_seconds", type=int, default=1800,
                   help="Seconds between monitor ticks (default 30 min)")
    p.add_argument("--collect_script", default="collect_ML_data_all",
                   help="MATLAB script name for collection")
    p.add_argument("--max_ticks", type=int, default=0,
                   help="Stop after this many ticks (0 = unlimited)")
    return p.parse_args()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(msg: str):
    line = f"[{now()}] {msg}"
    print(line, flush=True)
    Path("monitor.log").open("a").write(line + "\n")


def run(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=False, **kw)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    tmp.replace(path)


def is_process_running(pattern: str) -> bool:
    """Returns True if any process whose argv matches `pattern` exists."""
    out = subprocess.run(
        ["pgrep", "-fa", pattern],
        capture_output=True, text=True
    )
    return bool(out.stdout.strip())


def case_log_path(simulations_dir: str, cid: int) -> Path:
    return Path(simulations_dir) / f"Case_{cid}" / "simulation.log"


def case_is_stuck(cid: int, args) -> bool:
    """A case is 'stuck' if its log hasn't been touched for stuck_minutes
    OR its tail repeatedly contains the stuck_log_token."""
    log_path = case_log_path(args.simulations_dir, cid)
    if not log_path.exists():
        return False  # no log yet — not stuck, just hasn't started
    age_min = (time.time() - log_path.stat().st_mtime) / 60
    if age_min > args.stuck_minutes:
        return True
    # Repeated divergence pattern: token appears in last ~50 lines more than once
    try:
        with log_path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 8192))
            tail = f.read().decode("utf-8", errors="ignore")
        return tail.count(args.stuck_log_token) >= 2
    except Exception:
        return False


def refresh_status(args) -> dict:
    cmd = [
        sys.executable, "status_report.py",
        "--input_dat", args.input_dat,
        "--simulations_dir", args.simulations_dir,
        "--threshold_kyr", str(args.threshold_kyr),
    ]
    run(cmd, capture_output=True)
    return load_json(Path("status_state.json"), {})


def mark_failed(cids: list, reason: str):
    path = Path("failed_cases.json")
    data = load_json(path, {"failed": [], "reasons": {}})
    failed = set(data.get("failed", []))
    reasons = data.get("reasons", {})
    for cid in cids:
        failed.add(cid)
        reasons[str(cid)] = reasons.get(str(cid), reason)
    data["failed"] = sorted(failed)
    data["reasons"] = reasons
    save_json(path, data)


def launch_rerun(case_ids: list, args):
    cases_str = " ".join(map(str, case_ids))
    cmd = [
        sys.executable, "rerun_cases.py",
        "--input_dat", args.input_dat,
        "--source_dir", args.source_dir,
        "--num_cores", str(args.num_cores),
        "--cases", cases_str,
    ]
    log(f"LAUNCH rerun for {len(case_ids)} cases: {cases_str[:200]}{'...' if len(cases_str)>200 else ''}")
    subprocess.Popen(cmd, stdout=open("rerun.log", "a"), stderr=subprocess.STDOUT)


def launch_collection(args):
    log(f"LAUNCH collection (MATLAB: {args.collect_script})")
    subprocess.Popen(
        ["matlab", "-batch", args.collect_script],
        stdout=open("collect.log", "a"),
        stderr=subprocess.STDOUT,
    )


def kill_stuck_matlabs():
    """Kill the MATLAB runner processes — they get respawned only if a parent
    chain is still alive, which we also kill."""
    subprocess.run(["pkill", "-9", "-f", "matlab.* -r runner"], check=False)
    subprocess.run(["pkill", "-9", "-f", "run.permafrost.py"], check=False)
    subprocess.run(["pkill", "-9", "-f", "rerun_cases.py"], check=False)
    time.sleep(3)


def tick(args, monitor_state) -> bool:
    """One monitor iteration. Returns True if work remains, False if all done."""
    state = refresh_status(args)
    if not state:
        log("ERROR: status_report.py produced no state; will retry next tick")
        return True

    counts = state["counts"]
    log(f"STATUS: sim_done={counts['sim_done']} collected={counts['collected']} "
        f"both_done={counts['both_done']} need_collect={counts['need_collect']} "
        f"need_rerun={counts['need_rerun']} accepted_failed={counts['accepted_failed']}")

    # Done?
    if counts["need_rerun"] == 0 and counts["need_collect"] == 0:
        log("ALL DONE.")
        return False

    rerun_running = is_process_running("rerun_cases.py") or is_process_running("scheduler.py")
    collect_running = is_process_running(f"matlab.* -batch {args.collect_script}")

    # Identify stuck cases among need_rerun
    if counts["need_rerun"] > 0:
        stuck = [c for c in state["need_rerun"] if case_is_stuck(c, args)]
        if stuck and rerun_running:
            log(f"STUCK detected: {stuck[:20]}{'...' if len(stuck)>20 else ''} "
                f"({len(stuck)} cases). Killing all runners to clear.")
            kill_stuck_matlabs()
            rerun_running = False

        # If no rerun running, queue need_rerun cases (minus those over retry limit)
        if not rerun_running:
            retries = monitor_state.setdefault("retry_counts", {})
            to_run, to_fail = [], []
            for c in state["need_rerun"]:
                if retries.get(str(c), 0) >= args.max_retries:
                    to_fail.append(c)
                else:
                    to_run.append(c)
            if to_fail:
                log(f"GIVE UP on {len(to_fail)} cases over max_retries: {to_fail}")
                mark_failed(to_fail,
                            f"Exceeded max_retries={args.max_retries}; never reached "
                            f"{args.threshold_kyr} kyr.")
            if to_run:
                for c in to_run:
                    retries[str(c)] = retries.get(str(c), 0) + 1
                save_json(Path("monitor_state.json"), monitor_state)
                launch_rerun(to_run, args)

    # Collection (don't compete with sims for resources unless sims are gone)
    if counts["need_collect"] > 0 and not collect_running and not rerun_running:
        launch_collection(args)
    elif counts["need_collect"] > 0 and rerun_running:
        log(f"DEFER collection: {counts['need_collect']} pending but reruns active")

    return True


def main():
    args = parse_args()
    monitor_state = load_json(Path("monitor_state.json"), {"retry_counts": {}})

    log(f"=== monitor_loop start (tick={args.tick_seconds}s, "
        f"max_retries={args.max_retries}, stuck_min={args.stuck_minutes}) ===")
    ticks = 0
    while True:
        more = tick(args, monitor_state)
        save_json(Path("monitor_state.json"), monitor_state)
        if not more:
            log("=== monitor_loop done ===")
            return
        ticks += 1
        if args.max_ticks and ticks >= args.max_ticks:
            log(f"=== monitor_loop reached max_ticks={args.max_ticks} ===")
            return
        time.sleep(args.tick_seconds)


if __name__ == "__main__":
    main()
