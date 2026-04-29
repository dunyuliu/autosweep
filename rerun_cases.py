"""Rerun a non-contiguous list of cases by case number."""
import argparse
import csv
import os
import subprocess
import sys


def parse_arguments():
    p = argparse.ArgumentParser(description="Rerun specific cases")
    p.add_argument("--input_dat", default="input.dat")
    p.add_argument("--output_dir", default="simulations")
    p.add_argument("--source_dir", default="src")
    p.add_argument("--num_cores", type=int, required=True)
    p.add_argument("--cases", required=True,
                   help="Comma- or space-separated case numbers")
    p.add_argument("--dry_run", action="store_true")
    return p.parse_args()


def load_all_jobs(input_dat_path):
    jobs = {}
    with open(input_dat_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        params = reader.fieldnames
        for i, row in enumerate(reader, 1):
            jobs[i] = {p: float(row[p]) for p in params}
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
    case_nums = [int(x) for x in args.cases.replace(",", " ").split()]

    if not case_nums:
        sys.exit("Error: --cases is empty")

    params, all_jobs = load_all_jobs(args.input_dat)

    print(f"Rerunning {len(case_nums)} cases across {args.num_cores} cores")
    print(f"Parameters: {params}")

    buckets = [[] for _ in range(args.num_cores)]
    for i, case_num in enumerate(case_nums):
        if case_num not in all_jobs:
            print(f"Warning: case {case_num} not in input.dat, skipping")
            continue
        cmd = format_command(all_jobs[case_num], case_num,
                             args.output_dir, args.source_dir)
        buckets[i % args.num_cores].append(cmd)

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
