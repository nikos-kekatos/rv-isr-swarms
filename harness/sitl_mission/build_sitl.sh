#!/usr/bin/env bash
# =============================================================================
# build_sitl.sh -- build ArduPilot SITL natively (works on arm64 Ubuntu / Lima, where the
# ardupilot dev-ros container is amd64-only). One-time; ~15-20 min. Run inside the VM.
# =============================================================================
set -euo pipefail
cd "$HOME"
# Resilient clone: HTTP/1.1 fixes the "curl 92 HTTP/2 stream ... CANCEL" error, and a
# shallow + shallow-submodule clone cuts ~2-3 GB down to a few hundred MB (helps on a
# flaky/slow connection).
git config --global http.version HTTP/1.1
git config --global http.postBuffer 524288000
if [ ! -d ardupilot/.git ]; then
  rm -rf ardupilot                       # clear any partial/failed clone
  ok=0
  for attempt in 1 2 3; do
    echo "clone attempt $attempt (shallow)..."
    if git clone --depth 1 --recurse-submodules --shallow-submodules \
         https://github.com/ArduPilot/ardupilot.git; then ok=1; break; fi
    echo "clone failed (network); retrying..."; rm -rf ardupilot; sleep 5
  done
  [ "$ok" = 1 ] || { echo "!! clone kept failing (flaky network). Use a stabler connection"
                     echo "   or a cloud VM. The mission figure needs NO clone: bash run_kinematic.sh"; exit 1; }
fi
cd ardupilot
Tools/environment_install/install-prereqs-ubuntu.sh -y
# shellcheck disable=SC1090
. "$HOME/.profile" 2>/dev/null || true
./waf configure --board sitl
./waf copter
SV="$HOME/ardupilot/Tools/autotest"
echo
echo "=== SITL built. sim_vehicle.py at $SV/sim_vehicle.py ==="
echo "Add to PATH (and to ~/.bashrc):  export PATH=\$PATH:$SV"
python3 -m pip install --user pymavlink matplotlib >/dev/null 2>&1 || \
  echo "pip: install pymavlink + matplotlib manually if needed"
