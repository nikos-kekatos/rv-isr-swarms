# rv-isr-swarms

Released under the MIT License (see `LICENSE`).

Artifact for *Mission-Level Runtime Assurance for LLM-Assisted ISR Swarms over a
Verification-Aware Fabric*.

The paper monitors mission-level policies over a swarm of LLM-assisted robots: obligations that no
single platform can check, such as a prohibited intelligence package assembled across four
platforms, a swarm-wide emission budget, or an unauthorised zone entry. Monitors run at three
layers, L1 (platform), L2 (squad coordinator) and L3 (mission), and verdicts carry both a security
value and an evidence-completeness status, so lost or delayed evidence becomes an explicit
`unknown` rather than a mission-wide all-clear.

Everything here is stdlib-only Python unless noted. No API keys are stored in the repository; the
LLM drivers read `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GEMINI_API_KEY` from the environment, and
the local-model path talks to Ollama.

## Quick start

```sh
cd harness
python3 run_demo.py            # the attack and benign missions, L1 vs L3 verdicts
python3 experiments.py         # four objectives x three faults
python3 exp_baselines.py --md  # baselines and complementary metrics
```

Or in Docker, which needs no ROS 2 and no GPU:

```sh
cd harness && docker build -t swarm-rv . && docker run --rm swarm-rv python3 experiments.py
```

## What reproduces what

| Script | Result |
|---|---|
| `run_demo.py` | attack-scenario incident preservation under the fault campaign |
| `experiments.py` | generalisation across four objectives and property kinds; scale sweep |
| `experiments_extra.py` | provenance, guarantee ablation, 500 randomised missions (seed 7) |
| `experiments_advanced.py` | no-silent-clear rate, compound faults, noisy-threshold missions (seed 11) |
| `experiments_hierarchy.py` | two-squad L1→L2→L3 composition, completeness propagating upward |
| `exp_baselines.py` | stronger baselines: central+seq+heartbeats, always-unknown, decision coverage |
| `experiments_properties.py` | the additional property kinds (count, coverage, corroboration, rate) |
| `threat_sweep.py` | split-cardinality sweep: no split evades both layers at these thresholds |
| `exp_timeout.py`, `exp_skew.py`, `exp_benign.py` | silence-timeout knee, clock skew, benign collaboration |
| `llm_loop.py`, `run_sweep.py`, `run_attacks.py` | LLM-planner campaign; archived in `*_archive.jsonl` |
| `swarm_to_monpoly.py` | exports the coordinated-collection property to MonPoly |
| `e2e_latency.py --real` | end-to-end verdict latency over live Mosquitto + NATS JetStream |
| `ros2_realism/run_ros2_demo.sh` | the same monitors over real ROS 2 / DDS, headless |
| `sitl_mission/run_sitl_mission.sh` | ArduPilot SITL mission, four copters over MAVLink |

`console/` serves a browser console that replays a mission over the same monitors and toggles the
evidence-aware fabric against a best-effort central monitor:

```sh
cd console && python3 serve_console.py    # http://localhost:8000
```

## Determinism

The deterministic suites use fixed seeds and have no wall-clock or network dependence, so they
reproduce exactly, and they were re-run on an independent Ubuntu VM. The LLM outputs are archived
with timestamps, model identifiers, request parameters and prompt hashes; because hosted models
change, those are *preserved* rather than regenerable.

## Layout

```
harness/          monitors (swarm_rv.py), mission generator, fault injection, experiments
harness/ros2_realism/   ROS 2 / DDS demo
harness/sitl_mission/   ArduPilot SITL mission and analysis
console/          browser console over the same monitors
```

## Environment and seeds

The paper's deterministic figures come from this environment:

| | |
|---|---|
| Host | Apple silicon workstation, 12 cores, 26 GB, macOS 15.3 |
| Reproduced on | Ubuntu 22.04 Lima VM, and a 4-vCPU Ubuntu 22.04 cloud instance |
| Runtime | Python 3.14; monitors and mission generator use only the standard library |
| Brokers | `eclipse-mosquitto:2` (MQTT, QoS 1) and `nats:2` (JetStream) |
| Middleware | ROS 2 Humble in a headless `ros:humble` container |
| Flight dynamics | ArduPilot SITL, four copters over MAVLink/TCP, 360 position samples |
| Formal engine | MonPoly, past-time metric first-order fragment |
| Mission clock | 1 Hz, verifier-resident |
| Event rate | about 2 events per platform-second, payloads under 1 kB |

Seeds and run sizes: latency runs use n=1000 events per condition at 15 ms producer pacing; the
randomised suites are 500 task-split missions (seed 7), 400 noisy-threshold missions (seed 11) and
300 jittery missions for the silence-timeout sweep. The deterministic suites have no wall-clock or
network dependence, so they reproduce exactly.

Two caveats. The scale timings (about 0.01 ms at 4 platforms rising to 1.2 ms at 1000) are wall-clock
measurements and vary slightly between runs. The LLM attack-success rates depend on hosted models
that change over time; the archived calls in `harness/*_archive.jsonl` preserve every prompt hash,
model identifier, request parameter and raw response, but exact regeneration is not guaranteed.
