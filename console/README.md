# Mission RV Console

A browser demo of the ISR-swarm compositional RV result, in the 3-layer layout of the
perception-RV tool but driven entirely by the paper's real monitors (`../harness/swarm_rv.py`).
**Stdlib only** — no pip, no build step.

```bash
python3 serve_console.py          # -> http://localhost:8000   (PORT=8137 to change)
```

## Layout
- **Mission map** — platforms fly the ISR mission over the AO / FacX / Zsens (and priority
  sectors for the coverage scenario); collection events appear as markers, verdict live.
- **Relation layer (.cvspec)** — the cross-agent aspect spec (display of the active rules).
- **Property layer (L3)** — property chips: `hold` (green) / `violation` (red) / `unknown`
  (amber); provenance names the platforms that jointly triggered a violation.
- **Controls** — scenario, fault, monitor mode, `B_mission` (live threshold), eval.

## Scenarios
| Scenario | Shows |
|---|---|
| **intel-package** | task-split attack: every L1 compliant, L3 catches the collective package / EMCON / unauthorised entry with provenance |
| **benign control** | cooperative recon (authorised entry, within budget): all green, **0 false alarms** |
| **sector coverage** | jam a platform → its sector goes **`unknown`** (fabric) vs a silent **"covered"** (central) — subgroup-silence as a liveness property |
| **recovery** | a jammed platform returns mid-mission: the verdict resolves **`unknown` → `violation`** (the downgrade is provisional and sound) |

## Faults & monitor
- **Faults:** clean · drop-witness (G1) · jam-platform (G3) · reorder (G2).
- **Monitor:** `RV-Fabric` (evidence-aware — missing evidence → `unknown`) vs `central`
  (best-effort — a lost witness silently reads as `no_violation`). Toggling these under a
  fault is the paper's headline: silent false all-clear vs honest unknown.
- **run eval** — clean-vs-fault scoring (silent false all-clears, NSCR, provenance), the
  same instruments as `../harness/experiments.py`.

## Notes
- Monitor engine = the Python reference monitor in `swarm_rv.py` (always available). A
  MonPoly toggle (the DejaVu-equivalent "real formal engine") is the natural next addition.
- Data source is the kinematic mission generator; the same page will replay a real
  ArduPilot-SITL `telemetry.jsonl` once positions are captured (see `../sitl_mission/`).
