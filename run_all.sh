#!/usr/bin/env bash
# Reproduce every result that needs nothing but a Python interpreter.
# Output lands in out/, one file per experiment. Exits non-zero if any fails.
# No step here calls a model provider, a broker, Docker or ROS.
set -uo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"
mkdir -p out
export PYTHONDONTWRITEBYTECODE=1
fail=0

run () {                                   # run <name> <command...>
  local name=$1; shift
  printf '%-28s ' "$name"
  if "$@" > "$ROOT/out/$name.txt" 2>&1; then
    echo "ok    -> out/$name.txt"
  else
    echo "FAILED (see out/$name.txt)"; fail=1
  fi
}

cd harness

echo "=== deterministic core (the headline table) ==="
run demo                     python3 run_demo.py
run experiments              python3 experiments.py
run experiments_extra        python3 experiments_extra.py
run experiments_advanced     python3 experiments_advanced.py
run experiments_hierarchy    python3 experiments_hierarchy.py
run experiments_properties   python3 experiments_properties.py
run threat_sweep             python3 threat_sweep.py
run stats                    python3 stats.py

echo
echo "=== offline analysis over the archived LLM runs (no model call) ==="
run exp_baselines            python3 exp_baselines.py
run exp_benign               python3 exp_benign.py
run exp_skew                 python3 exp_skew.py
run exp_timeout              python3 exp_timeout.py

echo
echo "=== engine export (MonPoly input generation) ==="
run export_monpoly           python3 swarm_to_monpoly.py

echo
echo "=== kinematic ISR mission (no SITL) ==="
printf '%-28s ' mission_telemetry
if python3 sitl_mission/sim_telemetry.py > "$ROOT/out/telemetry.jsonl" 2>"$ROOT/out/mission_telemetry.err"; then
  echo "ok    -> out/telemetry.jsonl"
else
  echo "FAILED (see out/mission_telemetry.err)"; fail=1
fi
run mission_verdict          python3 sitl_mission/analyze_mission.py "$ROOT/out/telemetry.jsonl"

echo
echo "NOT RUN, deliberately (see README.md):"
echo "  run_attacks.py, run_sweep.py, exp_gpt.py, exp_gemini.py, exp_defenses.py,"
echo "  exp_outcomes.py, exp_temperature.py, exp_upgrade.py, exp_gpt_matrix.py,"
echo "  exp_injection_ablation.py  -- these call a hosted model, cost money, and"
echo "  do NOT reproduce the published numbers. The archived runs are the record."
echo "  e2e_latency.py (needs Mosquitto + NATS), ros2_ardupilot_adapter.py (ROS 2),"
echo "  sitl_mission/build_sitl.sh (ArduPilot SITL)."
echo
[ $fail -eq 0 ] && echo "ALL OK" || echo "SOME FAILED"
exit $fail
