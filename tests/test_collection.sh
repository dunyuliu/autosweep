#!/bin/bash
# End-to-end test of the user-supplied collection script against real
# reference cases.
#
# Uses src/ and a few completed Case_<N>/ from a reference project (default:
# Arctic_Permafrost_Salinity_Change), runs the MATLAB collection script
# named by COLLECT_SCRIPT (default `collect_ML_data_all`), and verifies the
# expected output files appear.
#
# The collection .m file MUST be in the reference project's root (we copy
# it from there, since this package no longer ships project-specific MATLAB).
#
# Override with REF_DIR / COLLECT_SCRIPT / TEST_CASES env vars.

set -eu

PKG_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REF_DIR="${REF_DIR:-/home/staff/dliu/6.Kehua/Arctic_Permafrost_Salinity_Change}"
COLLECT_SCRIPT="${COLLECT_SCRIPT:-collect_ML_data_all}"
TEST_CASES="${TEST_CASES:-1 100 500}"   # case ids to collect

if ! command -v matlab >/dev/null 2>&1; then
    echo "SKIP: matlab not on PATH"
    exit 0
fi

if [ ! -d "$REF_DIR/simulations" ]; then
    echo "SKIP: reference simulations not found at $REF_DIR/simulations"
    exit 0
fi

if [ ! -f "$REF_DIR/${COLLECT_SCRIPT}.m" ]; then
    echo "SKIP: collection script $REF_DIR/${COLLECT_SCRIPT}.m not found."
    echo "      Set COLLECT_SCRIPT or REF_DIR to point at one."
    exit 0
fi

TMP=$(mktemp -d -t pmss_e2e_XXXXXX)
trap 'rm -rf "$TMP"' EXIT
echo "Test root: $TMP"

# Stage a minimal project layout. simulations/ is a *symlink* to the reference
# (we only read from it; we never delete or modify it).
ln -s "$REF_DIR/simulations" "$TMP/simulations"
ln -s "$REF_DIR/src"          "$TMP/src"
ln -s "$REF_DIR/input.dat"    "$TMP/input.dat"
ln -s "$REF_DIR/input.mat"    "$TMP/input.mat"  2>/dev/null || true
cp "$REF_DIR/${COLLECT_SCRIPT}.m" "$TMP/"

# Make sure collection is targeted: build a failed_cases.json that excludes
# nothing for this test (or copy the real one if you want known-failed
# behavior). Empty list = collect everything in range.
cat > "$TMP/failed_cases.json" <<EOF
{"failed": [], "reasons": {}}
EOF

# Pick a small contiguous range that includes our test cases
read -ra CASES <<<"$TEST_CASES"
START=${CASES[0]}
END=${CASES[-1]}
echo "Collection range: $START .. $END"

cd "$TMP"
PERMAFROST_ROOT="$TMP" START_CASE_ID="$START" END_CASE_ID="$END" \
    matlab -batch "${COLLECT_SCRIPT}" > collect.log 2>&1 || true

echo "--- collection log tail ---"
tail -5 collect.log

# Verify the expected files exist
fail=0
for cid in "${CASES[@]}"; do
    f="$TMP/output/full_results/Time_Evolution_Case${cid}.mat"
    if [ -f "$f" ]; then
        echo "  ok: collected Case_${cid}"
    else
        echo "  FAIL: missing $(basename "$f")"
        fail=1
    fi
done

if [ "$fail" -eq 0 ]; then
    echo
    echo "Collection test passed."
else
    echo
    echo "Collection test FAILED."
    exit 1
fi
