#!/usr/bin/env bash
# =============================================================================
# run_ros2_demo.sh -- headless ROS 2 realism demo, runnable in the Lima VM (no GPU).
#
# Spins up four ROS 2 platform nodes (one per UAV/UGV) publishing the ISR attack's
# structured actions over real ROS 2 (DDS), plus the L3 mission-monitor node that
# subscribes and runs the SAME compositional monitors as the reproducible core. Shows
# that every per-robot verdict is compliant while the mission monitor detects the
# distributed violation with platform provenance.
#
#   bash run_ros2_demo.sh [attack|benign]
#
# Uses the ros:humble Docker image (multi-arch; works on the arm64 26.04 VM as-is),
# so no native ROS 2 install is needed. Gazebo/ArduPilot are NOT required for this
# integration test; they would sit behind the /<ns>/action topics in a full deployment.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"
SCEN="${1:-attack}"
HARNESS="$(cd .. && pwd)"     # mounts swarm_rv.py + ros2_realism/ into the container
IMG="ros:humble"

echo "=== pulling $IMG (once) ==="
sudo docker pull "$IMG" >/dev/null 2>&1 || docker pull "$IMG"

echo "=== headless ROS 2 realism demo (scenario=$SCEN) ==="
DOCKER="sudo docker"; command -v docker >/dev/null && docker info >/dev/null 2>&1 && DOCKER="docker"
$DOCKER run --rm -v "$HARNESS":/work -w /work/ros2_realism "$IMG" bash -lc '
  source /opt/ros/humble/setup.bash
  export PYTHONPATH=/work:${PYTHONPATH:-}
  export RCUTILS_LOGGING_BUFFERED_STREAM=1
  for ns in uav_1 uav_2 uav_3 ugv_1; do
    python3 platform_node.py --ns $ns --scenario '"$SCEN"' &
  done
  sleep 1
  timeout 14 python3 mission_monitor.py || true
  echo "=== demo complete ==="
'
