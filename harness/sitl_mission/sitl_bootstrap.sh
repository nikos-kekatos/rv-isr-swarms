#!/usr/bin/env bash
# =============================================================================
# sitl_bootstrap.sh -- run on a fresh Ubuntu 22.04 x86 droplet/VM to build ArduPilot
# SITL, fly the ISR mission, and produce verdict.json + mission.pdf.
#
# ArduPilot's install-prereqs-ubuntu.sh REFUSES to run as root, but DigitalOcean logs
# you in as root. So when invoked as root we create a non-root sudo user, copy the
# harness into its home, and re-run the build + mission as that user; outputs are then
# copied back to /root for retrieval.
#
#   bash sitl_bootstrap.sh
# =============================================================================
set -euo pipefail
BUILD_USER="${BUILD_USER:-sitl}"
log(){ echo -e "\n=== $* ==="; }

if [ "$(id -u)" = 0 ]; then
  export DEBIAN_FRONTEND=noninteractive
  log "0/3  root: base packages + non-root build user '$BUILD_USER' (ArduPilot refuses root)"
  echo "  waiting for cloud-init / boot-time apt to finish..."
  cloud-init status --wait >/dev/null 2>&1 || true
  APT="apt-get -o DPkg::Lock::Timeout=600"
  $APT update -y
  $APT install -y git python3-pip sudo
  id "$BUILD_USER" &>/dev/null || useradd -m -s /bin/bash "$BUILD_USER"
  echo "$BUILD_USER ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-$BUILD_USER"
  REPO_SRC="$(cd "$(dirname "$0")/../.." && pwd)"            # -> paper3_swarm
  rm -rf "/home/$BUILD_USER/paper3_swarm"
  cp -r "$REPO_SRC" "/home/$BUILD_USER/paper3_swarm"
  chown -R "$BUILD_USER:$BUILD_USER" "/home/$BUILD_USER/paper3_swarm"
  sudo -iu "$BUILD_USER" bash \
    "/home/$BUILD_USER/paper3_swarm/harness/sitl_mission/sitl_bootstrap.sh"
  log "root: collect outputs to /root for retrieval"
  OUT="/home/$BUILD_USER/paper3_swarm/harness/sitl_mission"
  for f in verdict.json mission.pdf mission.svg telemetry.jsonl; do
    cp "$OUT/$f" "/root/$f" 2>/dev/null && echo "  copied $f" || true
  done
  exit 0
fi

# ---- non-root path: the actual build + fly ----
cd "$(dirname "$0")"
log "1/3  build ArduPilot SITL (one-time, ~15-20 min; skipped if already built)"
if ! command -v sim_vehicle.py >/dev/null 2>&1 \
   && [ ! -x "$HOME/ardupilot/Tools/autotest/sim_vehicle.py" ]; then
  bash build_sitl.sh
fi
export PATH="$PATH:$HOME/ardupilot/Tools/autotest"
python3 -m pip install --user pymavlink matplotlib >/dev/null 2>&1 || \
  echo "(pip: install pymavlink/matplotlib manually if the run complains)"

log "2/3  fly the mission + runtime verification"
bash run_sitl_mission.sh

log "3/3  RESULT (verdict.json)"
cat verdict.json
echo
echo "=== outputs: verdict.json + mission.pdf (copied to /root by the root wrapper) ==="
