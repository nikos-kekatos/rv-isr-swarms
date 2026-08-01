# Headless ROS 2 realism demo (Lima-runnable, no GPU)

Validates the **realism-layer integration** of the paper: robot platforms publish their
high-level structured actions over **real ROS 2 (DDS)**, and the L3 mission monitor node
subscribes and runs the **same compositional monitors** as the reproducible core
(`../swarm_rv.py`). It shows the distributed violation being invisible to every per-robot
(L1) verdict yet detected at the mission (L3) level with platform provenance.

No Gazebo and no GPU are required: Gazebo/ArduPilot would sit *behind* the `/<ns>/action`
topics in a full deployment, supplying physics and sensors; here the actions are scripted
so the run is deterministic. This is exactly the part of the realism layer that runs
cleanly in an arm64 Lima VM.

## Run (in the Lima VM)

```bash
cd /tmp/rv-3-layer/paper_mesas/paper3_swarm/harness/ros2_realism   # or the mounted path
bash run_ros2_demo.sh attack     # or: benign
```

It uses the `ros:humble` Docker image (multi-arch, includes arm64), so it works on the
26.04 VM without a native ROS 2 install. Expected: the four platform nodes publish
`collect/transmit/enter` actions; the monitor logs per-robot verdicts (all compliant) and,
once enough platforms have reported, the mission-level `VIOLATION :: prohibited_collective_intel_package :: agents=[...]`
with provenance. On `benign` it reports no violation.

## Files
- `platform_node.py`  ROS 2 node: one robot platform's action publisher (`/<ns>/action`).
- `mission_monitor.py` ROS 2 node: L3 mission monitor; subscribes to all platforms, runs
  the L1/L3 monitors from `swarm_rv.py`, prints verdicts + provenance.
- `run_ros2_demo.sh`   brings up 4 platform nodes + the monitor in a `ros:humble` container.

## What this does and does not cover
- **Covers:** the ROS 2 transport integration (real DDS pub/sub across nodes) and the
  compositional monitor consuming a live ROS 2 stream.
- **Does not cover:** Gazebo physics/visual rendering (optional; needs a cloud x86 GPU VM),
  and the MQTT/NATS RV-Fabric hop (validated separately by the CRITIS fabric and the
  reproducible core). The full deployment chain is
  `LLM planner -> /<ns>/action (ROS 2) -> adapter -> MQTT/JetStream fabric -> L3 monitor`;
  this demo exercises the ROS 2 half end-to-end.
