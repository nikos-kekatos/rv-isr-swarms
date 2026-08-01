#!/usr/bin/env bash
# =============================================================================
# run_sitl_mission.sh -- real ArduPilot SITL ISR mission -> RV verdict + figure.
#
# Launches 4 ArduPilot SITL copters (CPU-only, no GPU), flies each platform's ISR route
# with mavlink_collect.py (real flight dynamics + real MAVLink telemetry), runs the same
# L1/L3 monitors, and produces the mission figure. Run in the Lima VM.
#
#   bash run_sitl_mission.sh
#
# Requires: ArduPilot SITL (via the ardupilot container or a source build) + pymavlink +
# matplotlib. If SITL is unavailable, fall back to the tested kinematic generator:
#   python3 sim_telemetry.py > telemetry.jsonl && python3 analyze_mission.py && python3 plot_mission.py
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"
# With --no-mavproxy each SITL instance -I<n> serves MAVLink over TCP on 5760 + 10*n.
declare -A PORT=( [uav_1]=5760 [uav_2]=5770 [uav_3]=5780 [ugv_1]=5790 )
declare -A PROTO=( [uav_1]=tcp [uav_2]=tcp [uav_3]=tcp [ugv_1]=tcp )

# Locate a NATIVE sim_vehicle.py (arm64-friendly; the ardupilot dev-ros container is
# amd64-only and will not run on Apple-silicon/arm64 Lima).
SV="$(command -v sim_vehicle.py || true)"
[ -z "$SV" ] && [ -x "$HOME/ardupilot/Tools/autotest/sim_vehicle.py" ] && SV="$HOME/ardupilot/Tools/autotest/sim_vehicle.py"
if [ -z "$SV" ]; then
  cat <<'MSG'
!! ArduPilot SITL not found. On arm64 (Lima / Apple silicon) build it natively:
     bash build_sitl.sh              # one-time, ~15-20 min
   then re-run this script. (The ardupilot/ardupilot-dev-ros container is amd64-only.)

   To get the mission figure NOW without SITL (tested kinematic fallback):
     python3 sim_telemetry.py > telemetry.jsonl
     python3 analyze_mission.py telemetry.jsonl
     python3 plot_mission.py telemetry.jsonl
MSG
  exit 1
fi

echo "=== 1. launch 4 ArduPilot SITL copters (native: $SV) ==="
PIDS=()
for I in 0 1 2 3; do
  "$SV" -v ArduCopter -I"$I" --no-mavproxy --no-rebuild \
    >/tmp/sitl-$I.log 2>&1 &
  PIDS+=($!)
done
trap 'kill ${PIDS[*]} 2>/dev/null || true; pkill -f arducopter 2>/dev/null || true' EXIT
echo "waiting ~60s for SITL boot (TCP 5760/5770/5780/5790)"; sleep 60

echo "=== 2. fly each platform + collect telemetry ==="
: > telemetry.jsonl
FLY_T0=$SECONDS
for NS in uav_1 uav_2 uav_3 ugv_1; do
  CONN="${PROTO[$NS]}:127.0.0.1:${PORT[$NS]}"
  echo "  flying $NS on $CONN"
  python3 mavlink_collect.py --conn "$CONN" --ns "$NS" >> telemetry.jsonl || \
    echo "  (warn: $NS flight incomplete; see logs)"
done
FLY_SECS=$((SECONDS - FLY_T0))
kill "${PIDS[@]}" 2>/dev/null || true; pkill -f arducopter 2>/dev/null || true

echo "=== 3. runtime verification + figure (end-to-end verdict latency) ==="
VERDICT_T0=$SECONDS
python3 analyze_mission.py telemetry.jsonl
VERDICT_MS=$(python3 - <<'PY'
import json,time
# monitor evaluation latency: time to re-decide the L3 verdict from the collected log
import os,sys; sys.path.insert(0,"..")
from swarm_rv import Fabric, MISSION_PROPS
from analyze_mission import load_events
ev=load_events("telemetry.jsonl"); t=time.perf_counter()
Fabric(ev,evidence_aware=True).evaluate(MISSION_PROPS)
print(f"{(time.perf_counter()-t)*1e3:.2f}")
PY
)
python3 plot_mission.py telemetry.jsonl
echo "=== timing: real flight ${FLY_SECS}s; mission-monitor eval ${VERDICT_MS} ms ==="
echo "=== done: verdict.json + mission.pdf (or mission.svg) ==="
