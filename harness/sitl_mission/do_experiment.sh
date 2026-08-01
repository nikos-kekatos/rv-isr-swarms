#!/usr/bin/env bash
# =============================================================================
# do_experiment.sh -- ONE command on your MAC to run the real ArduPilot SITL ISR
# mission on DigitalOcean end-to-end: create droplet -> provision + build + fly ->
# pull verdict.json + mission.pdf back -> destroy the droplet.
#
#   doctl auth init                       # once: paste a DO API token
#   bash do_experiment.sh                 # uses your first DO ssh key, size c-4, ams3
#
# Override any default with env vars:
#   NAME=swarm-sitl SIZE=c-4 REGION=ams3 KEEP=0 DO_SSH_KEY=<fingerprint> bash do_experiment.sh
#   KEEP=1  -> leave the droplet running (don't destroy) for debugging.
# Requires: doctl (brew install doctl), and an ssh key registered with DO.
# =============================================================================
set -euo pipefail
NAME="${NAME:-swarm-sitl}"; SIZE="${SIZE:-c-4}"; REGION="${REGION:-ams3}"
IMAGE="ubuntu-22-04-x64"; KEEP="${KEEP:-0}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"          # -> paper3_swarm (contains harness/)
SSHOPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=8)

command -v doctl >/dev/null || { echo "install doctl first: brew install doctl && doctl auth init"; exit 1; }
KEY="${DO_SSH_KEY:-$(doctl compute ssh-key list --format FingerPrint --no-header 2>/dev/null | head -1)}"
[ -n "$KEY" ] || { echo "no DO ssh key found. Add one: doctl compute ssh-key import mykey --public-key-file ~/.ssh/id_ed25519.pub"; exit 1; }

echo "== 1/5 create droplet $NAME ($SIZE, $REGION, key=$KEY) =="
doctl compute droplet create "$NAME" --image "$IMAGE" --size "$SIZE" --region "$REGION" \
  --ssh-keys "$KEY" --wait >/dev/null
IP="$(doctl compute droplet get "$NAME" --format PublicIPv4 --no-header)"
echo "   droplet IP = $IP"

cleanup(){ [ "$KEEP" = 1 ] && { echo "== KEEP=1: droplet $NAME left at $IP (destroy: doctl compute droplet delete $NAME) =="; return; }
           echo "== destroy droplet =="; doctl compute droplet delete "$NAME" --force; }
trap cleanup EXIT

echo "== 2/5 wait for SSH =="
for i in $(seq 1 48); do ssh "${SSHOPTS[@]}" root@"$IP" true 2>/dev/null && break; sleep 5; done

echo "== 3/5 copy harness =="
scp -q "${SSHOPTS[@]}" -r "$REPO" root@"$IP":~/paper3_swarm

echo "== 4/5 provision + build + fly (streams; ~20-25 min first run) =="
ssh "${SSHOPTS[@]}" root@"$IP" "bash ~/paper3_swarm/harness/sitl_mission/sitl_bootstrap.sh"

echo "== 5/5 pull results (from /root, where sitl_bootstrap copies them) =="
got=0
for f in verdict.json mission.pdf mission.svg; do
  if scp -q "${SSHOPTS[@]}" root@"$IP":"$f" "./$f" 2>/dev/null; then echo "  got $f"; got=1; fi
done
[ "$got" = 1 ] || echo "  (no outputs retrieved -- check the run log above / re-run with KEEP=1)"
echo "== done =="
