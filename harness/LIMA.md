# Creating the VM with Lima (step by step)

Lima is the tool the CRITIS two-host experiment used
(`paper_cloudnet/rv-fabric-impl/clockskew/two_vm_skew.sh`). It boots a local Ubuntu VM on
your Mac in one command — no cloud. This guide creates one VM for the MESAS realism layer.

> The RV **experiments** don't need a VM — they run on the Mac via Docker
> (`docker run --rm swarm-rv python3 experiments.py`). The VM is only for the
> ROS 2 / Gazebo / ArduPilot realism layer.

## 1. Install Lima (once)

```bash
brew install lima
limactl --version
```

## 2. Create + start the VM

```bash
limactl start --name swarm --cpus 6 --memory 16 --disk 60 template://ubuntu-lts
```
- `--name swarm` names the VM; `--cpus/--memory/--disk` size it (memory in GiB, disk in GiB).
- `template://ubuntu-lts` is the built-in Ubuntu image.
- First boot downloads the image (a few minutes). It answers `y` to proceed.
- To pin Ubuntu 22.04 (best for ROS 2 Humble):
  `limactl start --name swarm --set '.images |= map(select(.location|test("22.04")))' template://ubuntu-lts`

Check it's running:
```bash
limactl list                 # STATUS should be "Running"
```

## 3. Get the repo into the VM

By default Lima **mounts your home directory read-only**, so the repo is already visible
inside the VM at the same path. To have a writable copy, copy it in:

```bash
limactl copy -r "$(cd ../../.. && pwd)" swarm:/tmp/rv-3-layer
```
(or `git clone` inside the VM in step 4).

## 4. Enter the VM and provision

```bash
limactl shell swarm            # you are now root-capable inside Ubuntu
# inside the VM:
bash /tmp/rv-3-layer/paper_mesas/paper3_swarm/harness/provision.sh
```
`provision.sh` installs ROS 2 Humble + Gazebo + ArduPilot SITL + the RV-Fabric brokers +
the harness image, and runs a smoke test. (On the Mac it refuses to run — it's Ubuntu-only.)

## 5. Run things inside the VM

```bash
# quantitative RV suite (also works on the Mac):
docker run --rm swarm-rv python3 experiments.py

# realism layer: one ROS 2 namespace per platform
source /opt/ros/humble/setup.bash
SWARM_NS=uav_1,uav_2,uav_3,ugv_1 python3 \
  /tmp/rv-3-layer/paper_mesas/paper3_swarm/harness/ros2_ardupilot_adapter.py
```

## 6. Manage the VM

```bash
limactl stop swarm            # shut down (keeps it)
limactl start swarm           # boot again
limactl shell swarm           # get a shell
limactl delete swarm          # remove it entirely
```

## Notes (honest)

- **Apple silicon → arm64 VM.** Fine for ROS 2 headless, ArduPilot SITL, the fabric, and
  real MonPoly (all CPU). **Not** good for Gazebo **GPU visual** rendering — for the
  qualitative visual mission + demo video use a cloud x86 GPU VM (AWS `g4dn`, GCP T4).
  Gazebo *physics* still runs headless in Lima.
- **Networking:** the VM can reach services on the Mac at the host IP
  (`ipconfig getifaddr en0`), exactly as the CRITIS `two_vm_skew.sh` does (brokers on the
  Mac, gateways in the VMs).
- **Two VMs** (to mirror the CRITIS distributed setup): repeat step 2 with `--name gw1`
  and `--name gw2`.
