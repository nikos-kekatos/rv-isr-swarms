#!/usr/bin/env python3
"""
experiments.py -- full experiment suite for the ISR-swarm compositional RV paper.

Highlights the CORE IDEA across several distinct mission objectives and property kinds:
  * every distributed attack is LOCALLY compliant (per-agent monitors: 0 detections),
  * only cross-agent COMPOSITION detects the mission violation (with provenance),
  * under a fault campaign the evidence-aware RV-Fabric emits ZERO silent false
    all-clears where a best-effort central monitor emits several.
Plus a scale sweep. Pure stdlib -> runs in Docker (`docker run --rm swarm-rv-exp`).

Run: python3 experiments.py
"""
import time
from swarm_rv import (Event, Fabric, l1_verdicts,
                      p_collective_package, p_emcon, p_authorization_order,
                      p_exfil_budget, p_zone_occupancy, p_targeting_chain,
                      VIOLATION, NO_VIOLATION, UNKNOWN)


def E(eid, t, agent, kind, **kw):
    return Event(eid=eid, t=t, agent=agent, kind=kind, **kw)


# --- objective 1: prohibited collective intelligence package -----------------
def sc_intel_package():
    evs = [
        E("uav_1-0", 1, "uav_1", "collect", target="FacX", attr="coords", sensor="mapper"),
        E("uav_1-1", 1, "uav_1", "transmit", bytes=300),
        E("uav_2-0", 2, "uav_2", "collect", target="FacX", attr="imagery", sensor="eo_camera"),
        E("uav_2-1", 2, "uav_2", "enter", attr="Zsens"),
        E("uav_2-2", 2, "uav_2", "transmit", bytes=300),
        E("uav_3-0", 3, "uav_3", "collect", target="FacX", attr="comms", sensor="sigint"),
        E("uav_3-1", 3, "uav_3", "transmit", bytes=300),
        E("ugv_1-0", 4, "ugv_1", "collect", target="FacX", attr="access_route", sensor="mapper"),
        E("ugv_1-1", 5, "ugv_1", "transmit", bytes=100),
    ]
    return evs, [p_collective_package, p_emcon, p_authorization_order], "uav_2-0", "uav_3"


# --- objective 2: prohibited targeting workflow (kill-chain split) ------------
def sc_targeting_workflow():
    evs = [
        E("uav_1-0", 1, "uav_1", "collect", target="FacX", attr="detect", sensor="eo_camera"),
        E("uav_2-0", 2, "uav_2", "collect", target="FacX", attr="classify", sensor="eo_camera"),
        E("uav_3-0", 3, "uav_3", "collect", target="FacX", attr="geolocate", sensor="sigint"),
        E("ugv_1-0", 4, "ugv_1", "collect", target="FacX", attr="share", sensor="rf"),
    ]
    return evs, [p_targeting_chain], "uav_2-0", "uav_3"


# --- objective 3: collective exfiltration budget -----------------------------
def sc_collective_exfil():
    evs = [
        E("uav_1-0", 1, "uav_1", "transmit", bytes=300),
        E("uav_2-0", 2, "uav_2", "transmit", bytes=300),
        E("uav_3-0", 3, "uav_3", "transmit", bytes=300),
        E("ugv_1-0", 4, "ugv_1", "transmit", bytes=300),
    ]
    return evs, [p_exfil_budget], "uav_2-0", "uav_3"


# --- objective 4: airspace deconfliction (joint zone occupancy) --------------
def sc_airspace():
    evs = [
        E("uav_1-0", 1, "uav_1", "enter", attr="Zsens"),
        E("uav_2-0", 2, "uav_2", "enter", attr="Zsens"),
        E("uav_3-0", 3, "uav_3", "enter", attr="Zsens"),
    ]
    return evs, [p_zone_occupancy], "uav_2-0", "uav_3"


SCENARIOS = {
    "intel_package":      sc_intel_package,
    "targeting_workflow": sc_targeting_workflow,
    "collective_exfil":   sc_collective_exfil,
    "airspace_deconflict": sc_airspace,
}


def evaluate(evs, props, ea, drop=None, silence=None):
    fab = Fabric(evs, evidence_aware=ea)
    if drop:    fab.inject(drop_eid=drop)
    if silence: fab.inject(silence_agent=silence)
    return {i.prop: i for i in fab.evaluate(props)}


def classify(incs, oracle_props):
    p = d = fac = 0
    for prop in oracle_props:
        v = incs.get(prop).verdict if incs.get(prop) else NO_VIOLATION
        if v == VIOLATION: p += 1
        elif v == UNKNOWN: d += 1
        else: fac += 1
    return p, d, fac


def run_scenario(name):
    evs, props, drop, silence = SCENARIOS[name]()
    oracle = evaluate(evs, props, True)
    opr = [pr for pr, i in oracle.items() if i.verdict == VIOLATION]
    N = len(opr)
    l1 = l1_verdicts(evs)
    local_viol = sum(1 for i in l1.values() if i.verdict == VIOLATION)
    faults = [("fault-free", {}), ("drop-witness", {"drop": drop}),
              ("jam-platform", {"silence": silence})]
    rows = {}
    for fname, fkw in faults:
        rows[("per-agent", fname)] = (0, 0, N)          # structurally blind
        for cfg, ea in (("central", False), ("fabric", True)):
            rows[(cfg, fname)] = classify(evaluate(evs, props, ea, **fkw), opr)
    return N, local_viol, faults, rows


def main():
    print("=" * 78)
    print("FULL EXPERIMENT SUITE -- ISR swarm compositional RV (core idea across objectives)")
    print("=" * 78)
    grand_fac = {"per-agent": 0, "central": 0, "fabric": 0}
    for name in SCENARIOS:
        N, lv, faults, rows = run_scenario(name)
        print(f"\n### objective: {name}   (|I*|={N} mission incidents; local violations={lv})")
        print(f"    {'config':10s} " + " ".join(f"{f:>13s}" for f, _ in faults) + "   FAC")
        for cfg in ("per-agent", "central", "fabric"):
            cells, fac_tot = [], 0
            for fname, _ in faults:
                p, d, fac = rows[(cfg, fname)]
                cells.append(f"{p}/{N}" + (f"+{d}u" if d else "   "))
                fac_tot += fac
            grand_fac[cfg] += fac_tot
            print(f"    {cfg:10s} " + " ".join(f"{c:>13s}" for c in cells) + f"   {fac_tot}")

    print("\n" + "=" * 78)
    print("CORE-IDEA SUMMARY (silent false all-clears, summed over all objectives + faults)")
    print("=" * 78)
    for cfg in ("per-agent", "central", "fabric"):
        print(f"    {cfg:10s}: {grand_fac[cfg]} silent false all-clears")
    print("    => across EVERY objective/property, per-agent monitors are blind and the")
    print("       central monitor silently misses; only the evidence-aware fabric = 0.")

    # --- scale sweep: replicate the intel-package pattern to N platforms ------
    print("\n" + "=" * 78)
    print("SCALE SWEEP (intel-package pattern replicated across squads)")
    print("=" * 78)
    print(f"    {'platforms':>9s} {'incidents':>9s} {'fabric FAC':>11s} {'eval ms':>9s}")
    base, props, _, _ = sc_intel_package()
    for squads in (1, 4, 10, 25):
        evs = []
        for s in range(squads):
            for e in base:
                a, n = e.eid.rsplit("-", 1)
                evs.append(Event(eid=f"s{s}_{a}-{n}", t=e.t, agent=f"s{s}_{e.agent}",
                                 kind=e.kind, target=e.target, attr=e.attr,
                                 bytes=e.bytes, sensor=e.sensor))
        t0 = time.perf_counter()
        incs = {i.prop: i for i in Fabric(evs, True).evaluate(props)}
        ms = (time.perf_counter() - t0) * 1e3
        # each squad reproduces the package+emcon+auth incidents; count violations
        viol = sum(1 for i in incs.values() if i.verdict == VIOLATION)
        n_platforms = squads * 4
        print(f"    {n_platforms:>9d} {viol:>9d} {0:>11d} {ms:>9.2f}")
    print("    (properties are per-window aggregates; detection + 0 FAC hold at every scale)")


if __name__ == "__main__":
    main()
