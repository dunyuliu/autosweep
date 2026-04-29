#!/bin/bash
# Run all package tests. Python tests always run; MATLAB test runs only if
# matlab is on PATH and a reference project is available.

set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

echo "============================================================"
echo "  Python smoke tests (synthetic fixtures, no MATLAB needed)"
echo "============================================================"
python3 "$DIR/test_python.py"

echo
echo "============================================================"
echo "  MATLAB collection end-to-end test (requires matlab + reference data)"
echo "============================================================"
bash "$DIR/test_collection.sh"
