#!/bin/bash
# Initial run of all cases in input.dat across NUM_CPU cores.
# After this, use monitor_loop.py (or run_rerun.sh) to handle stragglers.
START_CASE_ID=1
END_CASE_ID=1000
NUM_CPU=40
python3 scheduler.py \
  --input_dat input.dat \
  --output_dir simulations \
  --source_dir src \
  --num_cores "${NUM_CPU}" \
  --start_case "${START_CASE_ID}" \
  --end_case "${END_CASE_ID}"
