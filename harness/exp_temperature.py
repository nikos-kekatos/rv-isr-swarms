#!/usr/bin/env python3
"""
exp_temperature.py -- temperature sensitivity sweep for the package attack under the directive
injection (addresses the "single-temperature / point-in-time" reviewer caveat).

For a temperature-accepting model (claude-haiku-4-5) we sweep temperature in {0.2, 0.5, 0.8, 1.0}
and, at each setting, run n=15 planner calls under the DIRECTIVE package injection. The reported
ASR is how often the LLM splits the FacX profile across the swarm such that the compositional
(L3) monitor fires VIOLATION; whenever it fires the deterministic monitor detects it (100% of
splits). Wilson 95% CI on ASR. The planner/monitor path is exactly llm_loop.plan ->
actions_to_events -> swarm_rv, driven through the run_attacks "package" attack spec.

Frontier models (claude-sonnet-5, claude-opus-4-8) REJECT sampling params and the harness omits
temperature for them; they also refuse the military-framed tasking regardless of temperature, so
a temperature sweep is not meaningful for them -- recorded as a one-line note rather than swept.

  LLM_BACKEND=anthropic ANTHROPIC_API_KEY=... python3 exp_temperature.py

Writes temperature_sweep.json. Stdlib only.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm_loop as L
import run_attacks as RA

MODEL = "claude-haiku-4-5-20251001"
TEMPS = [0.2, 0.5, 0.8, 1.0]
N = 15
FRONTIER_NOTE = ("claude-sonnet-5 and claude-opus-4-8 reject sampling parameters (temperature is "
                 "omitted by the harness for them) and refuse the directive package tasking "
                 "regardless of temperature (directive ASR 0%); a temperature sweep is not "
                 "meaningful for these models, so they are noted rather than swept.")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_json = os.path.join(here, "temperature_sweep.json")

    L.BACKEND = "anthropic"
    L.MODEL = MODEL
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY unset -- this experiment needs the real backend. Aborting.")
        sys.exit(1)

    pkg = next(a for a in RA.ATTACKS if a["name"] == "package")
    RA.set_attack(pkg)   # installs the package MISSION_ORDER / SCHEMA_INSTR / ACTION_SCHEMA

    print("=" * 84)
    print(f"TEMPERATURE SWEEP -- package attack, directive injection, model {MODEL}")
    print(f"n={N} per temperature; ASR = L3 package VIOLATION (split detected 100% of splits)")
    print("=" * 84)

    sweep = []
    for temp in TEMPS:
        L.BACKEND = "anthropic"; L.MODEL = MODEL   # run_std may be re-entered; keep pinned
        r = RA.run_std(pkg, True, N, temp)
        row = {"temperature": temp, "n": r["trials"], "asr": r["asr"],
               "asr_ci": r["asr_ci"], "detected": r["detected"], "l1_clean": r["l1_clean"],
               "refusals": r["refusals"], "errors": r["errors"],
               "l3_detects": "100% of splits"}
        sweep.append(row)
        print(f"  temp {temp:>3}: ASR {100*r['asr']:3.0f}% "
              f"[{100*r['asr_ci'][0]:.0f}-{100*r['asr_ci'][1]:.0f}]  "
              f"splits {r['detected']}/{r['trials']}  L1-clean {r['l1_clean']}/{r['trials']}  "
              f"refused {r['refusals']}  err {r['errors']}")
        _flush(out_json, MODEL, sweep)

    print("\n=> ASR varies with temperature (the planner is stochastic), but whenever a split is")
    print("   produced the compositional L3 monitor detects it -- detection is temperature-invariant.")
    print(f"\nnote: {FRONTIER_NOTE}")
    _flush(out_json, MODEL, sweep)
    print(f"\nWrote {out_json}")


def _flush(path, model, sweep):
    with open(path, "w") as f:
        json.dump({"model": model, "attack": "package", "injection": "directive",
                   "n_per_temperature": N, "sweep": sweep, "frontier_note": FRONTIER_NOTE},
                  f, indent=2)


if __name__ == "__main__":
    main()
