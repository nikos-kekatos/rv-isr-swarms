#!/usr/bin/env bash
# =============================================================================
# redeploy_fly.sh -- re-run ONLY the flight + verification on an EXISTING droplet
# (ArduPilot already built there), after editing the sitl_mission scripts. NO rebuild.
#
# Runs the (multi-minute) flight DETACHED on the droplet and polls with short SSH calls,
# so a dropped long-lived SSH session can't kill it (that was the exit-255) and you get
# live progress (telemetry row count) instead of a silent terminal.
#
#   bash redeploy_fly.sh [IP]        # IP optional; else looked up from doctl by name
# =============================================================================
set -euo pipefail
NAME="${NAME:-swarm-sitl}"
IP="${1:-$(doctl compute droplet get "$NAME" --format PublicIPv4 --no-header)}"
SSHOPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10
         -o ServerAliveInterval=15 -o ServerAliveCountMax=6 -o BatchMode=yes)
HERE="$(cd "$(dirname "$0")" && pwd)"
D=/home/sitl/paper3_swarm/harness/sitl_mission

echo "== push updated sitl_mission scripts to $IP =="
scp -q "${SSHOPTS[@]}" "$HERE"/*.py "$HERE"/*.sh root@"$IP":/tmp/

echo "== launch flight DETACHED on the droplet (survives SSH drop) =="
ssh "${SSHOPTS[@]}" root@"$IP" "
  set -e
  cp /tmp/*.py /tmp/*.sh '$D'/ ; chown -R sitl:sitl '$D'
  pkill -f arducopter 2>/dev/null || true; sleep 2
  rm -f '$D'/verdict.json '$D'/telemetry.jsonl /root/fly.log
  nohup sudo -iu sitl bash -c 'cd $D && export PATH=\$PATH:/home/sitl/ardupilot/Tools/autotest && bash run_sitl_mission.sh' > /root/fly.log 2>&1 &
  echo \"  launched (pid \$!); logging to /root/fly.log\"
"

echo "== poll for completion (up to ~8 min; telemetry rows should climb) =="
done=no
for i in $(seq 1 96); do
  sleep 5
  read -r LINES DONE < <(ssh "${SSHOPTS[@]}" root@"$IP" "
    L=\$(wc -l < '$D'/telemetry.jsonl 2>/dev/null || echo 0)
    if [ -f '$D'/verdict.json ] && grep -q mission_violation '$D'/verdict.json 2>/dev/null; then V=yes; else V=no; fi
    echo \"\$L \$V\"" 2>/dev/null || echo "0 no")
  printf "  [%3ds] telemetry rows=%s  verdict=%s\n" "$((i*5))" "${LINES:-?}" "${DONE:-?}"
  if [ "${DONE:-no}" = yes ]; then done=yes; break; fi
done

echo "== remote run log (tail) =="
ssh "${SSHOPTS[@]}" root@"$IP" 'tail -30 /root/fly.log' || true

echo "== pull results =="
got=0
for f in verdict.json mission.pdf mission.svg telemetry.jsonl; do
  if scp -q "${SSHOPTS[@]}" root@"$IP":"$D/$f" "./$f" 2>/dev/null; then echo "  got $f"; got=1; fi
done
[ "$got" = 1 ] || echo "  (nothing retrieved -- see the run log above)"
[ "$done" = yes ] && echo "== DONE (verdict produced) ==" || echo "== TIMED OUT waiting; check the log tail above =="
echo "droplet left running; destroy with: doctl compute droplet delete $NAME --force"
