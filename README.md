# Evidence-Aware Compositional RV for ISR Swarms — reproduction repository

Code, archived model outputs and run instructions for:

> **Evidence-Aware Compositional Runtime Verification for LLM-Assisted ISR
> Swarms in Contested Environments**
> Nikolaos Kekatos, Michael Ioannou, Panagiotis Katsaros, Alexios Lekidis,
> Theodoros Nestoridis, Tom Nianios, Dimitrios Nikou.
>
> (The same harness also backs an earlier variant of this work titled
> *Mission-Level Runtime Assurance for LLM-Assisted ISR Swarms over a
> Verification-Aware Fabric*.)

The paper presents a three-layer (platform / squad / mission) compositional
runtime-verification framework. A mission policy is decomposed into per-platform
and cross-platform aspects, per-platform verdicts are aggregated over an
evidence-aware fabric, and they are fused with a two-axis
(security × completeness) algebra whose provenance names the platforms that
jointly triggered a violation. Because the fabric makes evidence loss and
silence observable, unsupported negative verdicts become an explicit `unknown`
rather than a mission-wide all-clear.

The paper cites <https://github.com/nikos-kekatos/rv-isr-swarms>. **No local git
repository or remote checkout of that URL exists in the working tree**, so this
directory is the packaged artefact that URL is meant to serve.

---

## Requirements

- **Everything the paper's deterministic results need: Python 3.10+, standard
  library only.** Nothing to install. Verified on Python 3.14.
- Optional: `matplotlib`, only to render the mission figure as PDF instead of SVG.
- Optional: Docker, for the live-broker end-to-end latency run and for MonPoly.
- Optional: ROS 2 Humble + Gazebo + ArduPilot SITL, for the realism layer.

## Reproduce

```sh
./run_all.sh
```

Writes one file per experiment to `out/`. **Expected runtime: about one minute**
on a modern laptop. Exits non-zero if any step fails. Every step is
deterministic (fixed seeds) and calls no network service.

---

## What is reproducible here

### 1. Deterministic core — every headline number. Fully reproducible.

`swarm_rv.py` holds the verdict algebra, the L1/L2/L3 monitors and the emulated
fabric with fault injection; `run_demo.py` drives the benign and attack
scenarios and the fault campaign.

The headline table (|I*| = 3 mission incidents):

| Configuration | fault-free | drop witness | jam platform | silent false all-clears |
|---|:--:|:--:|:--:|:--:|
| per-platform guardrails | 0/3 | 0/3 | 0/3 | 9 |
| central (best-effort) | 3/3 | 2/3 | 1/3 | 3 |
| evidence-aware fabric | 3/3 | 2/3 +1u | 1/3 +2u | **0** |

Every per-platform monitor stays green on the attack; only the compositional
monitor detects the mission violation, with platform provenance. Under
loss/jamming the evidence-aware fabric emits **zero** silent false all-clears
against three for the best-effort central monitor.

| Script | Verified | Covers |
|---|---|---|
| `run_demo.py` | runs, ~1 s | the table above; benign + attack scenarios, fault campaign |
| `experiments.py` | runs | the four evaluation objectives |
| `experiments_extra.py` | runs | provenance, robustness, ablation, reorder, slow, scale, randomised |
| `experiments_advanced.py` | runs | advanced fault campaign |
| `experiments_hierarchy.py` | runs | layer generalisation (L1/L2/L3) |
| `experiments_properties.py` | runs | generalisation across mission objectives |
| `threat_sweep.py` | runs | threat-model sweep |
| `stats.py` | runs | significance statistics over a results JSON |
| `swarm_to_monpoly.py` | runs | exports `swarm.sig`, `swarm.log`, `p_coord.mfotl` for MonPoly |
| `sitl_mission/sim_telemetry.py` + `analyze_mission.py` + `plot_mission.py` | run | the kinematic ISR mission figure and verdict |

### 2. LLM results — archived, not regenerable. Reproducible *as analysis only*.

The paper is explicit that archived LLM outputs are **preserved rather than
regenerable**, because hosted models change. That is honest and it is what this
repository ships.

Committed archives (raw request/response records):

- `harness/gpt_archive.jsonl` (686 KB), `harness/gemini_archive.jsonl` (339 KB),
  `harness/sweep_archive.jsonl` (636 KB)

Committed derived results: `attack_results.json`,
`attack_results_ollama_n20.json`, `baseline.json`, `benign_n20.json`,
`defenses.json`, `dist_n20.json`, `injection_ablation.json`, `outcomes.json`,
`sweep_results.json`, `temperature_sweep.json`, `gpt_results*.json`,
`gpt_matrix_gpt-5-2.json`, `gemini_results_*.json`, plus the run logs.

`gen_frags.py` and `gen_upgrade_frags.py` rebuild the paper's LLM tables from
those JSON files with **no model call at all**. Both were verified to run.
They write their output one directory above the harness; in this repository that
is the repository root, which is harmless.

These offline drivers also run with no network: `exp_baselines.py`,
`exp_benign.py`, `exp_skew.py`, `exp_timeout.py`.

### 3. Realism and systems layers — need external services.

| Script | Needs |
|---|---|
| `e2e_latency.py` | a live Mosquitto broker and NATS JetStream (Docker) |
| `ros2_ardupilot_adapter.py`, `ros2_realism/` | ROS 2 Humble + Gazebo + ArduPilot SITL on a Linux/GPU host; runs an offline canonicaliser smoke test when `rclpy` is absent |
| `sitl_mission/build_sitl.sh`, `run_sitl_mission.sh` | ArduPilot SITL build (~20 min on arm64) |
| `swarm_to_monpoly.py` output | the real MonPoly engine, via the `rvhier` Docker image |
| `Dockerfile` | Docker, to run the deterministic core in a container |

`LIMA.md`, `LINUX_VM.md`, `SETUP_VM.md`, `create_vm.sh`, `provision.sh` and
`run_all_vm.sh` are the authors' Linux-VM reproduction path; the paper states the
deterministic suites were reproduced on an independent Ubuntu VM this way.

---

## What is NOT reproducible here, and why

Stated plainly so nobody wastes time on it.

1. **Live LLM numbers cannot be regenerated.** Every cross-model and
   multi-attack ASR figure came from hosted models that have since moved. Re-running
   `run_attacks.py`, `run_sweep.py`, `exp_defenses.py`, `exp_gpt.py`,
   `exp_gemini.py`, `exp_gpt_matrix.py`, `exp_injection_ablation.py`,
   `exp_outcomes.py`, `exp_temperature.py` or `exp_upgrade.py` would **cost money
   and would not reproduce the published numbers**. The archives are the record.
2. **Those scripts need provider credentials.** Environment variables only,
   never values, never committed: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
   `GEMINI_API_KEY` (or `GOOGLE_API_KEY`), `DEEPSEEK_API_KEY`. Backend and model
   are selected by `LLM_BACKEND` (`ollama` | `anthropic` | `openai` | `gemini` |
   `deepseek`) and the `*_MODEL` / `*_HOST` variables in `llm_loop.py`.
   `LLM_BACKEND=ollama` against a local Ollama server is the only free path, and
   it reproduces the *local-model* rows, not the frontier-model rows.
   `llm_loop.py` falls back to a deterministic stub when the selected backend's
   key is unset, which is a smoke test, not a result.
3. **The realism layer cannot run on macOS/arm64.** ROS 2 + Gazebo + ArduPilot
   SITL is a multi-GB Linux/GPU stack. The adapter's offline canonicaliser smoke
   test is the portable substitute.
4. **MonPoly results need the `rvhier` image**, built from a separate
   `hierarchical-rv-rtlola` tree that is not part of this repository. The export
   step runs anywhere; the engine step does not.

---

## Layout and provenance

```
harness/                 monitors, scenarios, drivers, archives, VM docs
harness/HARNESS_NOTES.md the harness author's own notes   <- harness/README.md
harness/sitl_mission/    kinematic mission + ArduPilot SITL scripts
harness/ros2_realism/    ROS 2 realism nodes
console/                 browser console that replays a mission
run_all.sh               top-level runner            (new, written for this repo)
```

Everything under `harness/` and `console/` was copied unmodified from
`papers/paper_mesas/paper3_swarm/`. See `PROVENANCE.md` for the mapping and for
the one file that was redacted.

## Related repositories

This repository covers **one** of three MESAS papers. It shares **no code** with
the other two — verified by content hash. See `../README.md`.

## Licence

See `LICENSE`. It is a placeholder: the authors must choose the licence before
release, and must confirm what terms apply to the archived third-party model
outputs in `harness/*_archive.jsonl`.
