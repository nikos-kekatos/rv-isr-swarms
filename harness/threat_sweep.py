#!/usr/bin/env python3
"""
threat_sweep.py -- vary THREAT-MODEL parameters and evaluate the mission properties.

Three sweeps that answer "how do detection and evidence-honesty depend on the adversary's
choices and the mission thresholds?":
  A. Split cardinality (the squeeze): the adversary must split enough to stay under each
     platform's local limit, but then the cross-agent sum catches it -- no split evades both.
  B. Threshold sensitivity: where the EMCON budget sits relative to the swarm total decides
     whether the cross-agent property fires.
  C. Fault intensity: how many silent false all-clears the central vs evidence-aware monitor
     emits as loss/jamming increases.

Reuses the real monitors from swarm_rv (parameters set via module globals). Pure stdlib ->
`docker run --rm swarm-rv python3 threat_sweep.py`.
"""
import swarm_rv
from swarm_rv import (Event, l1_verdicts, Fabric, p_emcon,
                      VIOLATION, NO_VIOLATION, UNKNOWN)
from experiments import sc_intel_package


def E(eid, t, agent, kind, **kw):
    return Event(eid=eid, t=t, agent=agent, kind=kind, **kw)


def exfil(n, total):
    """Split `total` transmitted bytes evenly across n platforms."""
    per = total // n
    return [E(f"p{i}-0", 1, f"p{i}", "transmit", bytes=per) for i in range(n)]


def sweep_A():
    print("\n=== A. Split cardinality (the squeeze) ===")
    print("   swarm total=1200B, per-platform local limit=500B, EMCON budget=900B")
    swarm_rv.LOCAL_TX_LIMIT, swarm_rv.EMCON_BUDGET = 500, 900
    print(f"   {'split N':>7} {'B/platform':>11} {'L1 local?':>10} {'L3 EMCON':>10}  caught by")
    for n in (2, 3, 4, 6):
        evs = exfil(n, 1200)
        l1 = any(i.verdict == VIOLATION for i in l1_verdicts(evs).values())
        emc = Fabric(evs, True).evaluate([p_emcon])[0].verdict
        by = "L1 (local)" if l1 else ("L3 (cross-agent)" if emc == VIOLATION else "** MISSED **")
        print(f"   {n:>7} {1200//n:>11} {str(l1):>10} {emc:>10}  {by}")
    print("   => small split -> per-platform over the local limit (L1 catches); large split")
    print("      -> under the local limit but the swarm sum trips EMCON (L3 catches). No escape.")


def sweep_B():
    print("\n=== B. EMCON-budget sensitivity (swarm total fixed at 1200B, 4 platforms) ===")
    swarm_rv.LOCAL_TX_LIMIT = 500
    evs = exfil(4, 1200)
    print(f"   {'EMCON budget':>13} {'L3 EMCON verdict':>18}")
    for B in (600, 900, 1200, 1500):
        swarm_rv.EMCON_BUDGET = B
        v = Fabric(evs, True).evaluate([p_emcon])[0].verdict
        print(f"   {B:>13} {v:>18}")
    print("   => the property fires exactly when the budget is below the swarm total (1200B).")


def sweep_C():
    print("\n=== C. Fault intensity (intel-package attack; silent false all-clears) ===")
    swarm_rv.LOCAL_TX_LIMIT, swarm_rv.EMCON_BUDGET = 500, 900
    base, props, drop, silence = sc_intel_package()
    oracle = [p for p, i in {i.prop: i for i in Fabric(base, True).evaluate(props)}.items()
              if i.verdict == VIOLATION]
    N = len(oracle)

    def fac(evs_faults, ea):
        f = Fabric(base, ea)
        for kind, arg in evs_faults:
            f.inject(**{kind: arg})
        incs = {i.prop: i for i in f.evaluate(props)}
        return sum(1 for p in oracle
                   if (incs.get(p).verdict if incs.get(p) else NO_VIOLATION) == NO_VIOLATION)
    faults = [("none", []), ("drop 1", [("drop_eid", drop)]),
              ("jam 1", [("silence_agent", silence)]),
              ("drop 1 + jam 1", [("drop_eid", drop), ("silence_agent", silence)])]
    print(f"   {'fault level':>16} {'central FAC':>12} {'fabric FAC':>11}  (of {N})")
    for name, fl in faults:
        print(f"   {name:>16} {fac(fl, False):>12} {fac(fl, True):>11}")
    print("   => as faults intensify the central monitor accrues silent false all-clears;")
    print("      the evidence-aware fabric stays at 0 (downgrades to unknown instead).")


def main():
    print("=" * 74)
    print("THREAT-MODEL PARAMETER SWEEP -- properties vs adversary/mission parameters")
    print("=" * 74)
    sweep_A()
    sweep_B()
    sweep_C()


if __name__ == "__main__":
    main()
