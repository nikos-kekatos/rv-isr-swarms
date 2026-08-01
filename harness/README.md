# Harness — MESAS Paper 1 (LLM-assisted ISR swarm, compositional RV)

Two layers, per the paper's Sect. "Simulation Environment and Implementation". The RV
**contribution** is the event stream + monitors + evidence-aware fabric, *not* the
physics fidelity — so the quantitative results run in a stdlib-only reproducible core,
and ROS 2/Gazebo/ArduPilot is an optional realism layer.

## 1. Reproducible core (produces every paper number)

Stdlib Python, no external services.

```bash
python3 run_demo.py --md          # local
# or, preferred (Docker):
docker build -t swarm-rv .
docker run --rm swarm-rv
```

Expected headline (Table in the paper, |I*|=3 mission incidents):

| Configuration | fault-free | drop witness | jam platform | silent false all-clears |
|---|:--:|:--:|:--:|:--:|
| per-agent guardrails   | 0/3 | 0/3 | 0/3 | 9 |
| central (best-effort)  | 3/3 | 2/3 | 1/3 | 3 |
| RV-Fabric (evidence-aware) | 3/3 | 2/3 +1u | 1/3 +2u | **0** |

Every per-robot monitor stays green on the attack; only the compositional monitor
detects the mission violation (with agent provenance); under loss/jamming the
evidence-aware fabric emits **0** silent false all-clears vs 3 for the central monitor.

Files: `swarm_rv.py` (algebra + L1/L2/L3 monitors + emulated fabric with fault
injection), `run_demo.py` (benign + attack scenarios, fault campaign, report).

## 2. Realism layer (optional, Linux/GPU host)

`ros2_ardupilot_adapter.py` bridges ROS 2 + Gazebo + ArduPilot SITL to the same event
schema and publishes over the REAL RV-Fabric (MQTT + NATS JetStream) reused from
`../../../paper_cloudnet/rv-fabric-impl`. The identical monitors then run in
simulation. Not needed for the quantitative results.

```bash
# on a ROS 2 + ArduPilot SITL host:
docker compose -f ../../../paper_cloudnet/rv-fabric-impl/docker-compose.yml up -d mosquitto nats
# start ArduPilot SITL + ROS 2/Gazebo (one namespace per platform: /uav_1 .. /ugv_1)
SWARM_NS=uav_1,uav_2,uav_3,ugv_1 python3 ros2_ardupilot_adapter.py
```

Jamming = MAVLink/telemetry link loss; loss/reorder = broker-level fault injection.
Formal cross-agent properties are evaluated by the real MonPoly engine (rvhier image).

> NOTE: ROS 2 + Gazebo + ArduPilot SITL is a heavy Linux/GPU stack (multi-GB, hours to
> provision) and cannot be stood up on a macOS/arm64 laptop; the adapter runs an offline
> canonicaliser smoke test when `rclpy` is absent so the mapping can be checked anywhere.
