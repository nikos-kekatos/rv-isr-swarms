# Building the VM on a Linux host (step by step)

Companion to `LIMA.md` (that guide is for a **macOS** host). This one is for when the
host is **Linux**. It stands up an **Ubuntu 22.04 x86-64** VM for the ISR-swarm realism
layer (ROS 2 Humble + Gazebo + ArduPilot SITL + RV-Fabric), then runs `provision.sh`
inside it.

> The RV **experiments** need no VM at all — on any Linux box with Docker:
> `docker run --rm swarm-rv python3 experiments.py`. The VM is only for the ROS 2 /
> Gazebo / ArduPilot realism layer, and an x86 Linux host is the *best* place to run it
> (native x86; a GPU here gives the visual Gazebo mission the arm64 Mac cannot).

---

## Option A — Multipass (recommended; the Lima analog for Linux)

Multipass boots a cloud-image Ubuntu VM in one command, backed by KVM on Linux.

### 1. Install Multipass (once)
```bash
sudo snap install multipass
multipass version
```

### 2. Create + start the VM (Ubuntu 22.04 → ROS 2 Humble)
```bash
multipass launch 22.04 --name swarm --cpus 6 --memory 16G --disk 60G
multipass list                       # STATE should be "Running"
```

### 3. Get the repo into the VM
Mount the repo read-write into the VM (run from this `harness/` dir):
```bash
multipass mount "$(cd ../../.. && pwd)" swarm:/tmp/rv-3-layer
```
(Alternatively `git clone` inside the VM in step 4.)

### 4. Enter the VM and provision
```bash
multipass shell swarm
# --- now inside the VM (Ubuntu 22.04) ---
REPO_DIR=/tmp/rv-3-layer \
  bash /tmp/rv-3-layer/paper_mesas/paper3_swarm/harness/provision.sh
```
`provision.sh` installs ROS 2 Humble + Gazebo + ArduPilot SITL (container) + the
RV-Fabric brokers + the `swarm-rv` image, and runs a smoke test. Setting `REPO_DIR`
points its steps 4–6 at the mounted repo instead of trying to clone.

### 5. Run things inside the VM
```bash
# quantitative RV suite (no ROS/GPU):
sudo docker run --rm swarm-rv python3 experiments.py

# realism layer, one ROS 2 namespace per platform:
source /opt/ros/humble/setup.bash
SWARM_NS=uav_1,uav_2,uav_3,ugv_1 python3 \
  /tmp/rv-3-layer/paper_mesas/paper3_swarm/harness/ros2_ardupilot_adapter.py
```

### 6. Manage the VM
```bash
multipass stop swarm      # shut down (keeps it)
multipass start swarm     # boot again
multipass shell swarm     # get a shell
multipass delete swarm && multipass purge   # remove entirely
```

---

## Option B — KVM / libvirt (more control; PCI GPU passthrough possible)

Use this if you want a longer-lived, tunable VM (or GPU passthrough for visual Gazebo).

```bash
sudo apt-get install -y virtinst libvirt-daemon-system cloud-image-utils qemu-system-x86
# fetch the Ubuntu 22.04 cloud image
wget https://cloud-images.ubuntu.com/releases/22.04/release/ubuntu-22.04-server-cloudimg-amd64.img \
  -O /var/lib/libvirt/images/swarm.img
sudo qemu-img resize /var/lib/libvirt/images/swarm.img 60G

# minimal cloud-init user so you can log in
cat > user-data <<'EOF'
#cloud-config
users: [{name: ubuntu, sudo: 'ALL=(ALL) NOPASSWD:ALL', shell: /bin/bash,
         lock_passwd: false, plain_text_passwd: ubuntu}]
ssh_pwauth: true
EOF
cloud-localds seed.iso user-data

sudo virt-install --name swarm --memory 16384 --vcpus 6 \
  --disk /var/lib/libvirt/images/swarm.img,device=disk,bus=virtio \
  --disk seed.iso,device=cdrom \
  --os-variant ubuntu22.04 --import --network default --graphics none --noautoconsole

sudo virsh console swarm          # log in ubuntu/ubuntu, then:
# clone or scp the repo in, then run provision.sh with REPO_DIR set
```
For the visual Gazebo mission add `--host-device <pci-id-of-GPU>` (VFIO passthrough).

---

## Option C — no VM (bare Ubuntu 22.04 x86 host)

If the Linux host *is* Ubuntu 22.04 x86 and you don't need isolation, skip the VM and
run the provisioner directly on it — this is the most reliable path to the **visual
Gazebo** mission because there's no GPU-passthrough hop:
```bash
cd paper_mesas/paper3_swarm/harness
REPO_DIR="$(cd ../../.. && pwd)" bash provision.sh
```

---

## Notes (honest)

- **x86 Linux is the right host for the realism layer.** ROS 2 + ArduPilot SITL + the
  fabric + real MonPoly are all CPU and run in any of the options above. **Visual Gazebo
  rendering wants a GPU** — easiest with Option C (bare host + `docker --gpus all` or
  native), harder through a VM (needs VFIO passthrough, Option B).
- **Ubuntu release ↔ ROS 2:** `provision.sh` is release-aware — jammy (22.04) → Humble,
  noble (24.04) → Jazzy; anything else skips native ROS 2 and points you at the
  `ros:humble` container. Pin **22.04** as above for the paper's Humble setup.
- **Networking:** the VM reaches services on the host at the host IP, exactly as the
  CRITIS `two_vm_skew.sh` distributed setup does (brokers on the host, agents in the VM).
  For two VMs mirroring that setup, repeat with `--name gw1` / `--name gw2`.
- Re-login (or `newgrp docker`) inside the VM after provisioning so `docker` works
  without `sudo`.
