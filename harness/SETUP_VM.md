# Linux VM for the ISR-swarm realism layer (ROS 2 + Gazebo + ArduPilot SITL + RV-Fabric)

The reproducible RV results need **none** of this (run `python3 run_demo.py` or the
`swarm-rv` Docker image). This guide provisions the **realism layer** for the
qualitative Gazebo/ArduPilot mission and the scale experiments.

## 0. VM

**Recommended: Lima** — the same tool the CRITIS two-host clock-skew experiment used
(`paper_cloudnet/rv-fabric-impl/clockskew/two_vm_skew.sh`). Free, macOS-native, boots a
local Ubuntu VM in one command:

```bash
brew install lima
limactl start --name swarm --cpus 6 --memory 16 --disk 60 template://ubuntu-lts
limactl copy -r "$(cd ../../.. && pwd)" swarm:/tmp/rv-3-layer     # copy the repo in
limactl shell swarm
#  --- now inside the VM, on Ubuntu: ---
bash /tmp/rv-3-layer/paper_mesas/paper3_swarm/harness/provision.sh
```

- **Guest:** Ubuntu LTS (Lima default; use 22.04 for ROS 2 Humble). 6+ vCPU, 16 GB RAM.
- **Caveat (honest):** on Apple-silicon, Lima gives an **arm64** VM. That's fine for the
  CRITIS-style distributed experiment, for **ROS 2 headless + ArduPilot SITL + the fabric
  + real MonPoly** (all CPU). It is **not** good for **Gazebo GPU visual rendering** — for
  the qualitative visual mission + demo video, use a **cloud x86 GPU VM** (AWS `g4dn`,
  GCP T4). Gazebo *physics* still runs headless in Lima.
- Alternatives: Multipass (`multipass launch 22.04 --name swarm --cpus 6 --memory 16G`),
  or any cloud Ubuntu 22.04 instance.

## 1. Base

```bash
sudo apt update && sudo apt install -y git curl python3-pip docker.io docker-compose-plugin
sudo usermod -aG docker $USER   # re-login
```

## 2. ROS 2 Humble + Gazebo

```bash
# ROS 2 Humble (desktop)
sudo apt install -y software-properties-common && sudo add-apt-repository universe
sudo curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
  -o /usr/share/keyrings/ros-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] \
  http://packages.ros.org/ros2/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) main" \
  | sudo tee /etc/apt/sources.list.d/ros2.list
sudo apt update && sudo apt install -y ros-humble-desktop ros-dev-tools
# Gazebo (Harmonic) + ROS 2 bridge
sudo apt install -y ros-humble-ros-gz
echo "source /opt/ros/humble/setup.bash" >> ~/.bashrc && source ~/.bashrc
```

## 3. ArduPilot SITL (flight dynamics)

Easiest via the maintained container (no source build):

```bash
docker pull ardupilot/ardupilot-dev-ros:latest       # SITL + MAVProxy + ROS deps
# one instance per platform, e.g. 4 copters on ports 5760,5770,5780,5790:
docker run --rm -it --network host ardupilot/ardupilot-dev-ros \
  /bin/bash -lc "sim_vehicle.py -v ArduCopter -I0 --out=udp:127.0.0.1:14550"
```
(Native alternative: `git clone --recursive https://github.com/ArduPilot/ardupilot &&
cd ardupilot && Tools/environment_install/install-prereqs-ubuntu.sh -y && ./waf configure --board sitl && ./waf copter`.)

MAVLink→Python: `pip install pymavlink mavsdk`.

## 4. The RV-Fabric (brokers + monitors)

```bash
git clone <this repo> && cd <repo>/paper_cloudnet/rv-fabric-impl
docker build -t rvhier:latest ../../hierarchical-rv-rtlola   # MonPoly + RTLola (heavy, once)
docker compose up -d mosquitto nats                          # MQTT + JetStream
pip install -r requirements.txt                              # paho-mqtt, nats-py
```

## 5. Wire it together

```bash
cd <repo>/paper_mesas/paper3_swarm/harness
# one ROS 2 namespace per platform: /uav_1 /uav_2 /uav_3 /ugv_1
SWARM_NS=uav_1,uav_2,uav_3,ugv_1 NATS_URL=nats://localhost:4222 \
  python3 ros2_ardupilot_adapter.py
# adapter: ROS2 action/telemetry topics -> canonical events -> MQTT/JetStream -> L1/L2/L3 monitors
```
Jamming = drop a platform's MAVLink link; loss/reorder = broker fault knobs.

## 6. Smoke test (no ROS 2 needed anywhere)

```bash
python3 run_demo.py --md          # the paper's headline numbers
docker run --rm swarm-rv          # same, in Docker
```

## One-shot provisioning script

A `provision.sh` collecting steps 1–4 is the natural next artifact; each block above is
copy-paste runnable on a fresh Ubuntu 22.04 VM.
