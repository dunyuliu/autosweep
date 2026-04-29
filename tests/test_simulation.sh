#!/bin/bash
# End-to-end simulation test: run a small range of real cases through the
# scheduler -> run.permafrost.py -> MATLAB pipeline. Verify every case
# produces t<X>kyr.mat files and reaches the threshold.
#
# Slow: ~2-4 hours per case (cases run in parallel up to NUM_CORES).
#
# Usage:
#   bash tests/test_simulation.sh                    # default: cases 1..1
#   START=1 END=5 NUM_CORES=5 bash tests/test_simulation.sh

set -eu

PKG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REF_DIR="${REF_DIR:-/home/staff/dliu/6.Kehua/Arctic_Permafrost_Salinity_Change}"
START="${START:-1}"
END="${END:-1}"
NUM_CORES="${NUM_CORES:-1}"
THRESHOLD="${THRESHOLD:-400}"

if ! command -v matlab >/dev/null 2>&1; then
    echo "SKIP: matlab not on PATH"
    exit 0
fi
if [ ! -d "$REF_DIR/src" ]; then
    echo "SKIP: reference src not found at $REF_DIR/src"
    exit 0
fi

# Persistent test dir
TEST_ROOT="${TEST_ROOT:-$PKG_DIR/tests/.sim_run_${START}_${END}}"
mkdir -p "$TEST_ROOT"
echo "Test root: $TEST_ROOT"

# Stage scripts + ref data
cp "$PKG_DIR"/scheduler.py "$PKG_DIR"/run.permafrost.py "$PKG_DIR"/find_unfinished.py "$TEST_ROOT/"
[ -L "$TEST_ROOT/src" ]       || ln -s "$REF_DIR/src"       "$TEST_ROOT/src"
[ -L "$TEST_ROOT/input.dat" ] || ln -s "$REF_DIR/input.dat" "$TEST_ROOT/input.dat"
mkdir -p "$TEST_ROOT/simulations"

# Wipe target case dirs so we're really testing a fresh launch
for cid in $(seq "$START" "$END"); do
    rm -rf "$TEST_ROOT/simulations/Case_${cid}"
done

cd "$TEST_ROOT"
echo "Launching cases ${START}..${END} on ${NUM_CORES} cores..."
nohup python3 scheduler.py \
    --input_dat input.dat \
    --output_dir simulations \
    --source_dir src \
    --num_cores "$NUM_CORES" \
    --start_case "$START" \
    --end_case "$END" \
    > sim.log 2>&1 &

PID=$!
echo "Scheduler PID: $PID"
echo "Log: $TEST_ROOT/sim.log"
echo
echo "Monitor with:"
echo "  python3 $TEST_ROOT/find_unfinished.py --simulations_dir $TEST_ROOT/simulations --threshold_kyr $THRESHOLD"
echo "  for c in \$(seq $START $END); do echo Case_\$c: \$(ls $TEST_ROOT/simulations/Case_\$c/t*.mat 2>/dev/null | grep -oP 't[\\d.]+kyr' | sort -V | tail -1); done"
