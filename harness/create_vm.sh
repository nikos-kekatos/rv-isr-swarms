#!/usr/bin/env bash
# =============================================================================
# create_vm.sh -- ONE command, run on your MAC, to stand up the whole realism-layer
# toolchain in a Lima VM (same tool as the CRITIS experiment).
#
#   bash create_vm.sh
#
# It: installs Lima if needed, boots an Ubuntu VM, copies this repo in, and runs
# provision.sh INSIDE the VM (ROS 2 + Gazebo + ArduPilot SITL + RV-Fabric + harness).
# Re-runnable. Override defaults with env vars, e.g.  VM=swarm CPUS=6 MEM=16 DISK=60.
# =============================================================================
set -euo pipefail

VM="${VM:-swarm}"; CPUS="${CPUS:-6}"; MEM="${MEM:-16}"; DISK="${DISK:-60}"
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"     # -> rv-3-layer repo root
log(){ echo -e "\n=== $* ==="; }

[ "$(uname -s)" = "Darwin" ] || { echo "run this on the macOS host (it drives Lima)"; exit 1; }

log "1/4  Lima"
command -v limactl >/dev/null || brew install lima

log "2/4  VM '$VM' ($CPUS vCPU, ${MEM} GiB, ${DISK} GiB disk, Ubuntu 22.04 for ROS 2 Humble)"
# ubuntu-lts now defaults to a newer release (e.g. 26.04) that ROS 2 Humble does NOT
# target, so pin 22.04 explicitly. (NB: the download comes from Ubuntu's cloud-images
# CDN and can be slow; if it stalls, retry, or use a cloud VM where the pull is fast.)
case "$(uname -m)" in
  arm64|aarch64) IMG_ARCH=arm64; LIMA_ARCH=aarch64 ;;
  *)             IMG_ARCH=amd64; LIMA_ARCH=x86_64 ;;
esac
UBUNTU_IMG="https://cloud-images.ubuntu.com/releases/22.04/release/ubuntu-22.04-server-cloudimg-${IMG_ARCH}.img"
if limactl list --format '{{.Name}}' 2>/dev/null | grep -qx "$VM"; then
  echo "VM exists; starting if stopped"; limactl start "$VM" 2>/dev/null || true
else
  limactl start --name "$VM" --cpus "$CPUS" --memory "$MEM" --disk "$DISK" --tty=false \
    --set ".images=[{\"location\":\"$UBUNTU_IMG\",\"arch\":\"$LIMA_ARCH\"}]" template://ubuntu-lts
fi

log "3/4  copy repo -> $VM:/tmp/rv-3-layer  (may take a minute)"
limactl copy -r "$REPO" "$VM:/tmp/rv-3-layer"

log "4/4  provision inside the VM"
limactl shell "$VM" bash /tmp/rv-3-layer/paper_mesas/paper3_swarm/harness/provision.sh

cat <<EOF

=== DONE ===
Enter the VM:            limactl shell $VM
Run the RV experiments:  limactl shell $VM docker run --rm swarm-rv python3 experiments.py
Stop / delete the VM:    limactl stop $VM   |   limactl delete $VM
EOF
