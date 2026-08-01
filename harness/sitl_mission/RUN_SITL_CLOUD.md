# Running the real ArduPilot SITL ISR mission on a cloud x86 VM

Goal: produce **one real flight-dynamics mission** on ArduPilot SITL, run the same L1/L3
monitors over the resulting telemetry, and record the verdicts + timing + figure — the
"real M&S" result for the paper. **No GPU needed** for this (SITL + headless Gazebo physics
are CPU); a GPU is only for the optional Gazebo *visual* video (Step 6).

What is already verified on the arm64 dev machine: the entire pipeline **downstream** of
SITL (telemetry → RV verdict → figure) via the kinematic path — 9 action events, L1 all
`no_violation`, L3 three violations with provenance. The only link this runbook exercises
for real is the SITL flight producing that telemetry.

---

## 0. Simplest path — one command (DigitalOcean)

If you have `doctl` set up (`brew install doctl && doctl auth init`) and an SSH key
registered with DO, the whole experiment is a single command from your Mac:

```bash
cd harness/sitl_mission
bash do_experiment.sh          # create droplet -> build -> fly -> pull results -> destroy
```
It creates a `c-4` droplet in `ams3`, copies the harness, runs `sitl_bootstrap.sh`
(deps + ArduPilot build + mission), copies `verdict.json` + `mission.pdf` back to your
current directory, and destroys the droplet. Override defaults with env vars, e.g.
`SIZE=c-8 REGION=fra1 KEEP=1 bash do_experiment.sh` (`KEEP=1` leaves it running to debug).

To run it by hand instead (any provider), follow the steps below. The in-VM half is also
wrapped: `bash sitl_bootstrap.sh` does deps + build + fly in one shot.

---

## 1. Create the VM (Ubuntu 22.04 x86-64, no GPU)

```bash
# GCP
gcloud compute instances create swarm-sitl \
  --machine-type=e2-standard-8 --zone=europe-west1-b \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud --boot-disk-size=40GB
gcloud compute ssh swarm-sitl --zone=europe-west1-b
```
```bash
# AWS (pick the current Ubuntu 22.04 amd64 AMI for your region)
aws ec2 run-instances --image-id <ubuntu-2204-amd64-ami> --instance-type c6i.2xlarge \
  --key-name <key> --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=40}'
# then: ssh ubuntu@<public-ip>
```
Any x86 Ubuntu 22.04 box works (incl. Lima/Multipass on an x86 Mac/PC).

## 2. Get the repo onto the VM

```bash
# from your laptop, or git clone inside the VM
gcloud compute scp --recurse <repo>/paper_mesas/paper3_swarm swarm-sitl:~/paper3_swarm \
  --zone=europe-west1-b
# (AWS: scp -r ... ubuntu@<ip>:~/ )
```

## 3. Build ArduPilot SITL (one-time, ~15–20 min)

On x86 you can also use the `ardupilot/ardupilot-dev-ros` container, but the native build is
the most reliable and `run_sitl_mission.sh` expects `sim_vehicle.py` on `PATH`:

```bash
cd ~/paper3_swarm/harness/sitl_mission
bash build_sitl.sh
export PATH=$PATH:$HOME/ardupilot/Tools/autotest      # (build_sitl.sh prints this)
python3 -m pip install --user pymavlink matplotlib
```

## 4. Run the mission → verdicts + figure + timing

```bash
bash run_sitl_mission.sh
```
This launches 4 SITL copters, flies each platform's route (`mavlink_collect.py`, real
MAVLink), writes `telemetry.jsonl`, runs `analyze_mission.py` → `verdict.json`, plots
`mission.pdf`, and prints the real-flight duration + mission-monitor eval time.

**Expected (same as the emulator/kinematic result):** every L1 verdict `no_violation`;
L3 `prohibited_collective_intel_package` (all 4 platforms), `emcon_emissions_budget`,
`cross_agent_authorization` (uav_2), each with provenance. Figure shows the four
trajectories converging on Facility X, uav_2 crossing the sensitive zone, split-collection
markers, and the verdict box.

## 5. (Optional) Live end-to-end latency over the real fabric

To measure verdict latency over the actual MQTT/JetStream fabric (not just batch analysis),
bring up the brokers and stream through the adapter instead of the batch collector:

```bash
docker compose -f ../../../paper_cloudnet/rv-fabric-impl/docker-compose.yml up -d mosquitto nats
SWARM_NS=uav_1,uav_2,uav_3,ugv_1 NATS_URL=nats://localhost:4222 \
  python3 ../ros2_ardupilot_adapter.py     # SITL/MAVLink -> events -> fabric -> L1/L2/L3
```

## 6. (Optional, needs GPU) Gazebo visual + demo video

Only if you want rendered 3D. Use a GPU VM (AWS `g4dn.xlarge`, GCP `+nvidia-tesla-t4`):
```bash
sudo apt install -y ros-humble-ros-gz
gz sim -v4 <world.sdf>        # or headless server: gz sim -s -r <world.sdf>
```
The mission physics run headless without this; the video is pure optics.

## 7. Collect the outputs and send them back

```bash
cat verdict.json                         # the RV result
ls -la mission.pdf mission.svg           # the figure
# copy them off the VM:
gcloud compute scp swarm-sitl:~/paper3_swarm/harness/sitl_mission/verdict.json . --zone=...
```
Paste `verdict.json` + the `run_sitl_mission.sh` timing line (real-flight seconds +
mission-monitor ms) and we fold the real SITL numbers + `mission.pdf` into `main.tex`,
upgrading the paper from "ROS 2 executed" to "ArduPilot SITL flight-dynamics executed".

## 8. Tear down

```bash
gcloud compute instances delete swarm-sitl --zone=europe-west1-b     # stop billing
# AWS: aws ec2 terminate-instances --instance-ids <id>
```

---

### Notes / likely gotchas
- **Multi-instance SITL:** each copter uses a distinct `-I<n>` and UDP port (14550/60/70/80);
  `run_sitl_mission.sh` already sets this. Give SITL ~40 s to boot before flying.
- **Altitudes/connection strings:** `mavlink_collect.py` commands a 20 m local-NED goto and
  connects on `udp:127.0.0.1:<port>`; tune if your SITL config differs.
- **Semantic events are waypoint-tagged** in `mission_plan.py` (`action_at`): SITL supplies
  the real *spatial/timing* path (position, zone crossings), while the mission `collect`/
  `transmit` actions fire when a platform reaches its tagged waypoint. This is by design —
  the flight sim makes the trajectory real; the collection semantics are the mission script.
