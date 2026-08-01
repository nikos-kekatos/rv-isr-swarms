#!/usr/bin/env bash
# =============================================================================
# provision.sh -- one-shot setup of the ISR-swarm realism-layer toolchain on a
# fresh Ubuntu 22.04 x86-64 VM (ROS 2 Humble + Gazebo + ArduPilot SITL + RV-Fabric).
#
# The QUANTITATIVE RV results need none of this -- they run with
#   python3 experiments.py      (or: docker run --rm swarm-rv python3 experiments.py)
# This script provisions the optional Gazebo/ArduPilot realism layer.
#
# Usage (on a fresh Ubuntu 22.04 VM):
#   curl -fsSL <this-url>/provision.sh | bash          # or: bash provision.sh
# Idempotent-ish; safe to re-run. A GPU (or headless Gazebo) is needed only for
# visual rendering. Re-login (or `newgrp docker`) after it finishes for docker perms.
# =============================================================================
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
log(){ echo -e "\n=== $* ==="; }

# --- guard: this is an UBUNTU script; it must run INSIDE a Linux VM, not on macOS ----
if ! command -v apt-get >/dev/null 2>&1; then
  cat <<'MSG'
!! apt-get not found -- you are NOT on Ubuntu (this looks like macOS).
   This script provisions an UBUNTU 22.04 VM and must run INSIDE that VM.

   Create the VM on your Mac first with Lima (same tool as the CRITIS experiment),
   then run this INSIDE it -- see harness/LIMA.md for the full guide:

     brew install lima
     limactl start --name swarm --cpus 6 --memory 16 --disk 60 template://ubuntu-lts
     limactl copy -r "$(cd ../../.. && pwd)" swarm:/tmp/rv-3-layer
     limactl shell swarm
     #  --- now inside the VM: ---
     bash /tmp/rv-3-layer/paper_mesas/paper3_swarm/harness/provision.sh

   (Apple-silicon Lima = arm64: good for ROS2/ArduPilot/fabric; for Gazebo GPU
    VISUAL rendering use a cloud x86 GPU VM. Gazebo physics runs headless in Lima.)

   NOTE: the RV EXPERIMENTS do NOT need this VM. They run on your Mac via Docker:
     docker run --rm swarm-rv python3 experiments.py
     docker run --rm swarm-rv python3 experiments_extra.py
MSG
  exit 1
fi

log "1/6  base packages + Docker"
sudo apt-get update -y
sudo apt-get install -y git curl gnupg lsb-release ca-certificates \
     python3-pip docker.io
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER" || true

# Compose v2: docker-compose-plugin lives only in Docker's OWN apt repo, not Ubuntu's
# universe (which is where docker.io comes from), so apt can't find it on a stock VM.
# Install the official CLI plugin binary directly (arch-aware). Skip if already present.
if ! sudo docker compose version >/dev/null 2>&1; then
  log "1b/6  docker compose v2 plugin (not in Ubuntu repos -> fetch official binary)"
  case "$(dpkg --print-architecture)" in
    amd64) CB=x86_64 ;; arm64) CB=aarch64 ;; *) CB="$(uname -m)" ;;
  esac
  sudo mkdir -p /usr/local/lib/docker/cli-plugins
  sudo curl -fsSL \
    "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${CB}" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
  sudo docker compose version
fi

log "2/6  ROS 2 (desktop) + Gazebo bridge"
CODENAME="$(. /etc/os-release && echo "$UBUNTU_CODENAME")"
case "$CODENAME" in
  jammy)  ROS_DISTRO=humble ;;   # 22.04
  noble)  ROS_DISTRO=jazzy  ;;   # 24.04
  *)      ROS_DISTRO="" ;;
esac
if [ -n "$ROS_DISTRO" ]; then
  sudo add-apt-repository -y universe
  sudo install -m0755 -d /usr/share/keyrings
  curl -fsSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
    | sudo tee /usr/share/keyrings/ros-archive-keyring.gpg >/dev/null
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
http://packages.ros.org/ros2/ubuntu $CODENAME main" \
    | sudo tee /etc/apt/sources.list.d/ros2.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y "ros-$ROS_DISTRO-desktop" ros-dev-tools "ros-$ROS_DISTRO-ros-gz"
  grep -q "source /opt/ros/$ROS_DISTRO/setup.bash" ~/.bashrc || \
    echo "source /opt/ros/$ROS_DISTRO/setup.bash" >> ~/.bashrc
else
  echo "!! Ubuntu '$CODENAME' has no native ROS 2 apt repo (ROS 2 targets 22.04/24.04)."
  echo "   Skipping native ROS 2. The RV experiments, real MonPoly, brokers, and ArduPilot"
  echo "   SITL all work here; run ROS 2 for the adapter via a 'ros:humble' Docker container:"
  echo "     docker run -it --rm --network host ros:humble bash"
fi

log "3/6  ArduPilot SITL + MAVLink (containerised)"
# The ardupilot/ardupilot-dev-ros image is published amd64-only (no arm64 manifest),
# so on an Apple-silicon (arm64) Lima VM the native pull fails. Don't abort the whole
# provisioner for it -- SITL is optional (the RV experiments + ros:humble demo don't
# need it). On arm64: either emulate amd64 (slow, needs binfmt/qemu) or build SITL from
# source (compiles natively on arm64).
ARCH="$(dpkg --print-architecture)"
if [ "$ARCH" = "amd64" ]; then
  sudo docker pull ardupilot/ardupilot-dev-ros:latest || \
    echo "!! ArduPilot image pull failed; SITL is optional, continuing."
else
  echo "!! arm64 host: ardupilot/ardupilot-dev-ros has no arm64 image. SITL is OPTIONAL."
  echo "   Options: (a) emulate  -> docker run --platform linux/amd64 ardupilot/ardupilot-dev-ros"
  echo "            (b) build from source (native arm64):"
  echo "                git clone --recursive https://github.com/ArduPilot/ardupilot && cd ardupilot"
  echo "                Tools/environment_install/install-prereqs-ubuntu.sh -y && ./waf configure --board sitl && ./waf copter"
  echo "   For realism WITHOUT ArduPilot, use the ros:humble demo: harness/ros2_realism/run_ros2_demo.sh"
fi
pip3 install --user pymavlink mavsdk || true

log "4/6  clone this repository"
REPO_DIR="${REPO_DIR:-$HOME/rv-3-layer}"
if [ ! -d "$REPO_DIR/.git" ]; then
  git clone "${REPO_URL:-https://example.invalid/rv-3-layer.git}" "$REPO_DIR" \
    || { echo "!! set REPO_URL to your repo, or copy it to $REPO_DIR"; }
fi

log "5/6  RV-Fabric: brokers + MonPoly/RTLola image"
if [ -d "$REPO_DIR/paper_cloudnet/rv-fabric-impl" ]; then
  cd "$REPO_DIR/paper_cloudnet/rv-fabric-impl"
  sudo docker build -t rvhier:latest ../../hierarchical-rv-rtlola   # heavy, once
  sudo docker compose up -d mosquitto nats
  pip3 install --user -r requirements.txt
fi

log "6/6  swarm harness image + smoke test"
if [ -d "$REPO_DIR/paper_mesas/paper3_swarm/harness" ]; then
  cd "$REPO_DIR/paper_mesas/paper3_swarm/harness"
  sudo docker build -t swarm-rv .
  sudo docker run --rm swarm-rv python3 experiments.py | tail -8
fi

cat <<'EOF'

=== DONE ===
Re-login (or run: newgrp docker) so docker works without sudo.
Reproducible RV results (no ROS/GPU needed):
    docker run --rm swarm-rv python3 experiments.py
Realism layer (ROS 2 + ArduPilot SITL, one namespace per platform):
    # terminal A: sim_vehicle.py -v ArduCopter -I0 ... (ardupilot container)
    # terminal B: source /opt/ros/humble/setup.bash
    #             SWARM_NS=uav_1,uav_2,uav_3,ugv_1 python3 ros2_ardupilot_adapter.py
EOF
