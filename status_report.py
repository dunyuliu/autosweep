"""Categorize all cases by simulation/collection status, with persistent logs.

Outputs:
  - stdout:           summary counts
  - status_log.md:    human-readable report
  - status_state.json: machine-readable state (case lists for each category)

Categories:
  - sim_done:         cases that reached the simulation threshold (>= --threshold_kyr).
                      A SUCCESS for the simulation step.
  - collected:        cases whose collected output file exists. SUCCESS for collection.
  - both_done:        sim_done AND collected. End-state success.
  - need_collect:     sim_done but not yet collected.
  - need_rerun:       neither sim_done nor known-failed (sim missing or partial).
  - accepted_failed:  listed in failed_cases.json — give up and skip.
"""
import argparse
import csv
import json
import re
from pathlib import Path
from datetime import datetime


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input_dat", default="input.dat")
    p.add_argument("--simulations_dir", default="simulations")
    p.add_argument("--output_dir", default="output")
    p.add_argument("--collection_subdir", default="full_results")
    p.add_argument("--collection_pattern", default="Time_Evolution_Case{cid}.mat")
    p.add_argument("--threshold_kyr", type=float, default=400.0)
    p.add_argument("--output_pattern", default=r"^t([\d.]+)kyr\.mat$")
    p.add_argument("--write_md", default="status_log.md")
    p.add_argument("--write_json", default="status_state.json")
    p.add_argument("--known_failed", default="failed_cases.json")
    return p.parse_args()


def latest_kyr(case_dir: Path, pattern: re.Pattern) -> float:
    best = -1.0
    for p in case_dir.glob("t*.mat"):
        m = pattern.match(p.name)
        if m:
            try:
                v = float(m.group(1))
                if v > best:
                    best = v
            except ValueError:
                pass
    return best


def load_failed(path: Path):
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text()).get("failed", []))
    except Exception:
        return set()


def main():
    args = parse_args()
    pattern = re.compile(args.output_pattern)

    with open(args.input_dat) as f:
        total = sum(1 for _ in csv.reader(f, delimiter="\t")) - 1

    sim_root = Path(args.simulations_dir)
    coll_root = Path(args.output_dir) / args.collection_subdir
    failed = load_failed(Path(args.known_failed))

    sim_done, collected = [], []
    both_done, need_collect, need_rerun, accepted_failed = [], [], [], []

    for cid in range(1, total + 1):
        case_dir = sim_root / f"Case_{cid}"
        coll_file = coll_root / args.collection_pattern.format(cid=cid)

        is_sim_done = case_dir.is_dir() and latest_kyr(case_dir, pattern) >= args.threshold_kyr
        is_coll_done = coll_file.is_file()

        if is_sim_done:
            sim_done.append(cid)
        if is_coll_done:
            collected.append(cid)

        if cid in failed:
            accepted_failed.append(cid)
        elif is_sim_done and is_coll_done:
            both_done.append(cid)
        elif is_sim_done and not is_coll_done:
            need_collect.append(cid)
        else:
            need_rerun.append(cid)

    print(f"sim_done:        {len(sim_done)} / {total}")
    print(f"collected:       {len(collected)} / {total}")
    print(f"both_done:       {len(both_done)} / {total}")
    print(f"need_collect:    {len(need_collect)} / {total}")
    print(f"need_rerun:      {len(need_rerun)} / {total}")
    print(f"accepted_failed: {len(accepted_failed)} / {total}")

    state = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "total": total,
        "threshold_kyr": args.threshold_kyr,
        "counts": {
            "sim_done": len(sim_done),
            "collected": len(collected),
            "both_done": len(both_done),
            "need_collect": len(need_collect),
            "need_rerun": len(need_rerun),
            "accepted_failed": len(accepted_failed),
        },
        "sim_done": sim_done,
        "collected": collected,
        "both_done": both_done,
        "need_collect": need_collect,
        "need_rerun": need_rerun,
        "accepted_failed": accepted_failed,
    }

    if args.write_json:
        Path(args.write_json).write_text(json.dumps(state, indent=2))

    if args.write_md:
        def fmt(ids): return " ".join(map(str, ids)) if ids else "(none)"
        md = [
            "# Status Log",
            f"_Updated: {state['timestamp']}_",
            "",
            "## Success counts",
            f"- **sim_done**: {len(sim_done)} / {total}  (simulation reached >= {args.threshold_kyr} kyr)",
            f"- **collected**: {len(collected)} / {total}  (collection output exists)",
            f"- **both_done**: {len(both_done)} / {total}  (end-state success)",
            "",
            "## Outstanding work",
            f"- **need_collect**: {len(need_collect)} / {total}",
            f"- **need_rerun**: {len(need_rerun)} / {total}",
            f"- **accepted_failed**: {len(accepted_failed)} / {total}",
            "",
            "## need_rerun", fmt(need_rerun), "",
            "## need_collect", fmt(need_collect), "",
            "## accepted_failed", fmt(accepted_failed), "",
        ]
        Path(args.write_md).write_text("\n".join(md))


if __name__ == "__main__":
    main()
