# ArduPilot SITL ISR mission (real flight dynamics, no GPU)

Flies the four-platform ISR mission on **real ArduPilot SITL** autopilots (CPU-only, no
Gazebo/GPU), runs the same L1/L3 monitors on the resulting telemetry, and produces the
mission figure. This is the "real M&S" run for the paper: real flight dynamics + real
MAVLink, with a headless publication figure. Gazebo 3D visuals are the optional cloud-GPU
upgrade; they are not needed here.

## Two paths, identical downstream

The analysis + figure consume a `telemetry.jsonl` log; it can come from either:

**A. Real SITL (in the Lima VM):**
```bash
bash build_sitl.sh                # one-time: native ArduPilot SITL build (~15-20 min)
bash run_sitl_mission.sh          # launches 4 SITL copters, flies routes, analyses, plots
```
On **arm64** (Apple-silicon Lima) build SITL **natively** with `build_sitl.sh` — the
`ardupilot/ardupilot-dev-ros` container is **amd64-only** and will not run. Also needs
`pip install pymavlink matplotlib`. Tune connection strings/altitudes if your setup differs.

**B. Kinematic fallback (tested, runs anywhere, no SITL):**
```bash
python3 sim_telemetry.py > telemetry.jsonl
python3 analyze_mission.py telemetry.jsonl      # -> verdict.json (L1 + L3 verdicts)
python3 plot_mission.py telemetry.jsonl         # -> mission.pdf (matplotlib) or mission.svg
```

Both produce the same telemetry schema, so the RV verdict and the figure are identical in
structure; SITL adds real flight dynamics.

## Expected result
Every per-robot (L1) verdict is compliant; the mission (L3) monitor reports
`prohibited_collective_intel_package`, `emcon_emissions_budget`, and
`cross_agent_authorization` violations with platform provenance. The figure shows the four
trajectories converging on Facility X, uav_2 crossing the sensitive zone, the split
collection events, and the verdict.

## Files
- `mission_plan.py`   shared mission (waypoints, protected/sensitive zones, per-platform actions).
- `sim_telemetry.py`  kinematic telemetry generator (tested fallback).
- `mavlink_collect.py` real ArduPilot SITL collector (pymavlink; run in the VM).
- `analyze_mission.py` telemetry -> RV L1/L3 verdicts (`verdict.json`).
- `plot_mission.py`   telemetry + verdict -> `mission.pdf` (matplotlib) / `mission.svg` (stdlib).
- `run_sitl_mission.sh` orchestrates the real SITL run end-to-end.
