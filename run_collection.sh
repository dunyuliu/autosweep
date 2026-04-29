#!/bin/bash
# Run the user-supplied MATLAB collection script over a case range.
#
# The collection script is project-specific and must be placed in the
# working directory by the user. Set COLLECT_SCRIPT to its name (without
# .m extension), defaulting to "collect_ML_data_all" for legacy reasons.
#
# Usage:
#   bash run_collection.sh                  # cases 1..1000 with default script
#   bash run_collection.sh 1 500            # cases 1..500
#   COLLECT_SCRIPT=my_postproc bash run_collection.sh 1 100
START_CASE_ID="${1:-1}"
END_CASE_ID="${2:-1000}"
COLLECT_SCRIPT="${COLLECT_SCRIPT:-collect_ML_data_all}"

if [ ! -f "${COLLECT_SCRIPT}.m" ]; then
    echo "ERROR: ${COLLECT_SCRIPT}.m not found in $(pwd)"
    echo "       Place your project-specific MATLAB collection script there"
    echo "       and/or set COLLECT_SCRIPT=<name> (no .m extension)."
    exit 1
fi

export START_CASE_ID
export END_CASE_ID

LOG="collection_${START_CASE_ID}_${END_CASE_ID}.log"
nohup matlab -batch "${COLLECT_SCRIPT}" > "${LOG}" 2>&1 &
echo "Launched MATLAB collection (${COLLECT_SCRIPT}), PID $!, log: ${LOG}"
