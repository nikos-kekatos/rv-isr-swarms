#!/usr/bin/env bash
# =============================================================================
# run_all_vm.sh -- ONE script to reproduce all quantitative results in the Lima VM.
#
#   bash run_all_vm.sh
#
# Runs the full RV suite, the extra experiments, the threat-model sweep, and the mission
# figure with plain python3 (stdlib) -- no Docker needed for the core results. Writes every
# output to a WRITABLE dir (default ~/swarm_results), since the repo may be a read-only
# Lima mount. matplotlib is installed via apt if available (for a PDF figure); otherwise the
# figure is SVG. Docker-based extras (real MonPoly, ROS 2 demo) are listed at the end.
# =============================================================================
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1
HARNESS="$(cd "$(dirname "$0")" && pwd)"
SITL="$HARNESS/sitl_mission"
OUT="${OUT:-$HOME/swarm_results}"; mkdir -p "$OUT"
echo "### outputs -> $OUT"

echo; echo "########## 0. matplotlib (optional; for a PDF figure) ##########"
if python3 -c "import matplotlib" 2>/dev/null; then
  echo "  matplotlib present"
elif command -v apt-get >/dev/null; then
  sudo apt-get update -qq && sudo apt-get install -y python3-matplotlib || echo "  (install failed; figure will be SVG)"
else
  echo "  no apt; figure will be SVG"
fi

echo; echo "########## 1. core experiments (4 objectives) ##########"
python3 "$HARNESS/experiments.py" | tee "$OUT/1_experiments.txt"

echo; echo "########## 2. extra (provenance/robustness/ablation/reorder/slow/scale/randomized) ##########"
python3 "$HARNESS/experiments_extra.py" | tee "$OUT/2_experiments_extra.txt"

echo; echo "########## 3. threat-model sweep (the squeeze) ##########"
python3 "$HARNESS/threat_sweep.py" | tee "$OUT/3_threat_sweep.txt"

echo; echo "########## 4. ISR mission figure (kinematic; no SITL) ##########"
python3 "$SITL/sim_telemetry.py" > "$OUT/telemetry.jsonl"
python3 "$SITL/analyze_mission.py" "$OUT/telemetry.jsonl" | tee "$OUT/4_mission_verdict.txt"
( cd "$OUT" && python3 "$SITL/plot_mission.py" telemetry.jsonl )

echo; echo "########## DONE ##########"
echo "results in $OUT :"; ls -1 "$OUT"
cat <<EOF

Optional Docker-based extras (run separately):
  real MonPoly cross-agent property:
    sudo docker build -t rvhier:latest $HARNESS/../../../hierarchical-rv-rtlola   # heavy, once
    ( cd $HARNESS && python3 swarm_to_monpoly.py )
  headless ROS 2 realism demo:
    bash $SITL/../ros2_realism/run_ros2_demo.sh attack
  real ArduPilot SITL flight (arm64, ~20 min build):
    bash $SITL/build_sitl.sh && bash $SITL/run_sitl_mission.sh
EOF
