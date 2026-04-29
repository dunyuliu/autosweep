#!/bin/bash
# Safely tear down everything: monitor, schedulers, MATLAB runners, collection.
# Order matters — kill parents first so children don't get re-spawned.
set -u

echo "[$(date)] kill_all.sh: stopping monitor + scheduler parents..."
pkill -9 -u "$USER" -f "monitor_loop.py" 2>/dev/null
pkill -9 -u "$USER" -f "scheduler.py" 2>/dev/null
pkill -9 -u "$USER" -f "rerun_cases.py" 2>/dev/null
pkill -9 -u "$USER" -f "run.permafrost.py" 2>/dev/null

sleep 2

echo "[$(date)] kill_all.sh: stopping MATLAB runners + clients..."
# The MATLAB process (-r runner) is the parent; its client-v1 child gets respawned
# until you kill the parent. Kill both to be safe.
pkill -9 -u "$USER" -f "MATLAB.*-r runner" 2>/dev/null
pkill -9 -u "$USER" -f "matlab.*-batch" 2>/dev/null
pkill -9 -u "$USER" -f "MathWorksServiceHost client-v1" 2>/dev/null

sleep 3

remaining=$(ps aux | grep -E "MATLAB|MathWorks|permafrost|scheduler|rerun_cases|monitor_loop" \
            | grep "$USER" | grep -v "grep" | wc -l)
echo "[$(date)] kill_all.sh: $remaining processes remaining"
if [ "$remaining" -gt 0 ]; then
    echo "Survivors:"
    ps aux | grep -E "MATLAB|MathWorks|permafrost|scheduler|rerun_cases|monitor_loop" \
        | grep "$USER" | grep -v "grep" | awk '{print "  PID="$2" "$11" "$12}'
fi
