"""Distribute a contiguous range of cases across N CPU cores.

Each row of input.dat is one case. Header row defines parameter names.
Parameters are passed to run.permafrost.py via --param key=value.
"""
import argparse
import csv
import os
import subprocess
import sys


def parse_arguments():
    parser = argparse.ArgumentParser(description="Simulation scheduler")
    parser.add_argument("--input_dat", default="input.dat",
                        help="Tab-separated file with header row + one row per case")
    parser.add_argument("--output_dir", default="simulations",
                        help="Where Case_<N>/ directories are created")
    parser.add_argument("--source_dir", default="src",
                        help="MATLAB source directory to copy into each case")
    parser.add_argument("--num_cores", type=int, required=True)
    parser.add_argument("--start_case", type=int, default=1,
                        help="1-based first case number to run")
    parser.add_argument("--end_case", type=int, default=None,
                        help="1-based last case number; defaults to last row")
    parser.add_argument("--dry_run", action="store_true")
    return parser.parse_args()


def load_jobs(input_dat_path):
    """Returns (parameter_names, list of dicts)."""
    if not os.path.exists(input_dat_path):
        sys.exit(f"Error: input file '{input_dat_path}' not found.")

    jobs = []
    with open(input_dat_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        params = reader.fieldnames
        if not params:
            sys.exit(f"Error: '{input_dat_path}' is missing a header row.")
        for row in reader:
            try:
                jobs.append({p: float(row[p]) for p in params})
            except (TypeError, ValueError) as exc:
                sys.exit(f"Error parsing row {len(jobs)+1}: {exc}")

    if not jobs:
        sys.exit(f"Error: no data rows in {input_dat_path}")
    return params, jobs


def format_command(job, case_number, output_dir, source_dir):
    cmd = [
        sys.executable, "run.permafrost.py",
        "--wait",
        "--output_dir", output_dir,
        "--source_dir", source_dir,
        "--case_number", str(case_number),
    ]
    for k, v in job.items():
        cmd.extend(["--param", f"{k}={v}"])
    return " ".join(cmd)


def main():
    args = parse_arguments()

    if not os.path.exists(args.source_dir):
        sys.exit(f"Error: source dir '{args.source_dir}' not found.")

    params, all_jobs = load_jobs(args.input_dat)
    total = len(all_jobs)
    end_case = args.end_case if args.end_case is not None else total

    if args.start_case < 1 or args.start_case > total:
        sys.exit(f"Error: --start_case {args.start_case} out of range [1..{total}]")
    if end_case < args.start_case or end_case > total:
        sys.exit(f"Error: --end_case {end_case} out of range")

    jobs = all_jobs[args.start_case - 1: end_case]
    print(f"Cases {args.start_case}..{end_case} ({len(jobs)} jobs) on {args.num_cores} cores")
    print(f"Parameters: {params}")

    buckets = [[] for _ in range(args.num_cores)]
    for i, job in enumerate(jobs):
        case_num = args.start_case + i
        buckets[i % args.num_cores].append(
            format_command(job, case_num, args.output_dir, args.source_dir)
        )

    if args.dry_run:
        for i, b in enumerate(buckets):
            for cmd in b:
                print(f"[Core {i+1}] {cmd}")
        return

    procs = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        chained = " ; ".join(bucket)
        print(f"[Core {i+1}] {len(bucket)} jobs queued")
        procs.append(subprocess.Popen(chained, shell=True))

    print(f"\n{len(procs)} worker chains launched. Output: {args.output_dir}/")


if __name__ == "__main__":
    main()
