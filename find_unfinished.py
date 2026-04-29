"""Find cases that haven't reached the completion threshold.

Reports them as space-separated case numbers on stdout, count on stderr.
"""
import argparse
import csv
import re
import sys
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input_dat", default="input.dat")
    p.add_argument("--simulations_dir", default="simulations")
    p.add_argument("--threshold_kyr", type=float, default=400.0)
    p.add_argument("--output_pattern", default=r"^t([\d.]+)kyr\.mat$",
                   help="Regex matching final-output files; group(1) = time in kyr")
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


def main():
    args = parse_args()
    pattern = re.compile(args.output_pattern)

    with open(args.input_dat) as f:
        total = sum(1 for _ in csv.reader(f, delimiter="\t")) - 1

    sim_root = Path(args.simulations_dir)
    unfinished = []
    for cid in range(1, total + 1):
        case_dir = sim_root / f"Case_{cid}"
        if not case_dir.is_dir():
            unfinished.append(cid)
            continue
        if latest_kyr(case_dir, pattern) < args.threshold_kyr:
            unfinished.append(cid)

    print(" ".join(str(c) for c in unfinished))
    print(f"Total unfinished: {len(unfinished)} / {total}", file=sys.stderr)


if __name__ == "__main__":
    main()
