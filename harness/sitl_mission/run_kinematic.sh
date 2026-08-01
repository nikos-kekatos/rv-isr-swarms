#!/usr/bin/env bash
# One command: generate mission telemetry (kinematic, no SITL needed), run the RV
# monitors, and produce the mission figure. Tested; runs anywhere with python3.
# Writes outputs to a WRITABLE dir (the repo may be a read-only Lima mount).
# For a PDF figure: pip install matplotlib (otherwise it writes mission.svg).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"        # scripts (may be read-only)
OUT="${OUT:-$HOME/swarm_mission}"            # writable output dir
mkdir -p "$OUT"
python3 "$HERE/sim_telemetry.py" > "$OUT/telemetry.jsonl"
python3 "$HERE/analyze_mission.py" "$OUT/telemetry.jsonl"
( cd "$OUT" && python3 "$HERE/plot_mission.py" telemetry.jsonl )
echo "=== done: outputs in $OUT (telemetry.jsonl, verdict.json, mission.pdf or mission.svg) ==="
