#!/bin/bash
# Detect every case below the simulation threshold and rerun them.
NUM_CPU=40
CASES=$(python3 find_unfinished.py --input_dat input.dat --simulations_dir simulations --threshold_kyr 400)
if [ -z "$CASES" ]; then
    echo "Nothing to rerun. All cases meet threshold."
    exit 0
fi
echo "Cases to rerun: ${CASES}"
python3 rerun_cases.py \
  --input_dat input.dat \
  --output_dir simulations \
  --source_dir src \
  --num_cores "${NUM_CPU}" \
  --cases "${CASES}"
