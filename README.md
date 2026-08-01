# rv-isr-swarms

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
