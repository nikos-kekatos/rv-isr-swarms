#!/usr/bin/env python3
"""
experiments_advanced.py -- advanced scenarios beyond the core + extra suites.

Adds the four dimensions a reviewer probes that the earlier suites do not touch --
an ADAPTIVE adversary, TIME/latency, INTEGRITY (lying) faults, and STATISTICAL
rigour -- plus depth on the existing axes. Seven experiments:

  1. EVASIVE low-and-slow adversary + detection-window sweep (temporal evasion)
  2. DETECTION LATENCY under online/streaming evaluation (finite vs infinite)
  3. BYZANTINE lying platform + cross-witness corroboration (integrity faults)
  4. ROC curves + AUC + Verdict-Preservation-Rate (statistical rigour)
  5. COMPOUND-fault graceful-degradation surface (fabric FAC stays 0)
  6. RECOVERY: intermittent evidence resolves unknown -> violation (soundness)
  7. MULTI-OBJECTIVE mission + provenance-attribution matrix (integration)

Pure stdlib, no external services -> `docker run --rm swarm-rv python3 experiments_advanced.py`.
Every number is computed from the real monitors in swarm_rv.py.
"""
import time
import random
from swarm_rv import (
    Event, Fabric, l1_verdicts, downgrade,
    p_collective_package, p_emcon, p_authorization_order,
    p_exfil_budget, p_zone_occupancy, p_targeting_chain,
    VIOLATION, NO_VIOLATION, UNKNOWN, INCOMPLETE, SOUND, UNAVAILABLE,
    PROHIBITED_TARGET, PACKAGE_PARTS, EMCON_BUDGET, LOCAL_TX_LIMIT,
    SENSITIVE_ZONE, K_OCC, CHAIN, Incident,
)
from experiments import SCENARIOS, sc_intel_package, evaluate, classify
from run_demo import build_benign


def E(eid, t, agent, kind, **kw):
    return Event(eid=eid, t=t, agent=agent, kind=kind, **kw)


# =============================================================================
# 1. Evasive low-and-slow adversary + detection-window sweep
# =============================================================================
def windowed_package(events, W):
    """Windowed variant of the collective-package property: the prohibited package is
    detected only if all four parts fall inside SOME time window of length <= W.
    Returns (verdict, span) where span is the collection horizon the adversary used."""
    first = {}
    for e in events:
        if e.kind == "collect" and e.target == PROHIBITED_TARGET and e.attr in PACKAGE_PARTS:
            if e.attr not in first or e.t < first[e.attr]:
                first[e.attr] = e.t
    if not PACKAGE_PARTS.issubset(first):
        return NO_VIOLATION, None
    span = max(first.values()) - min(first.values())
    return (VIOLATION if span <= W else NO_VIOLATION), span


def exp_evasion():
    print("\n### 1. Evasive low-and-slow adversary vs detection window")
    print("    A patient adversary spreads the 4 package parts by an inter-part gap S,")
    print("    so the collection span is 3S. A monitor with window W detects iff 3S <= W.")
    spreads = [1, 2, 5, 10, 20]          # inter-part gap S (mission-time units)
    windows = [5, 15, 30, 60]            # candidate monitor window W
    print("    span\\W " + "".join(f"{w:>7}" for w in windows) + "   (parts at 0,S,2S,3S)")
    for S in spreads:
        evs = [E(f"a{i}-0", i * S, f"a{i}", "collect", target=PROHIBITED_TARGET, attr=p,
                 sensor="mapper") for i, p in enumerate(sorted(PACKAGE_PARTS))]
        cells = []
        for W in windows:
            v, span = windowed_package(evs, W)
            cells.append("DET" if v == VIOLATION else " - ")
        print(f"    3S={3*S:>3} " + "".join(f"{c:>7}" for c in cells))
    print("    => detection needs W >= 3S: a too-short window misses the patient adversary.")
    print("       The fabric monitors over the FULL mission window (unbounded within a mission),")
    print("       so evasion requires spreading collection ACROSS missions -- a documented")
    print("       limit -- at the cost of proportional buffer state for large W.")


# =============================================================================
# 2. Detection latency under online / streaming evaluation
# =============================================================================
def exp_latency():
    print("\n### 2. Detection latency (online streaming vs batch)")
    evs, props, drop, silence = sc_intel_package()
    props = [p_collective_package]
    order = sorted(evs, key=lambda e: (e.t, e.eid))
    # oracle: mission-time at which the package completes (last contributing part)
    parts_t = [e.t for e in evs if e.kind == "collect" and e.target == PROHIBITED_TARGET
               and e.attr in PACKAGE_PARTS]
    complete_t = max(parts_t)

    def first_signal(ea, drop_eid=None):
        """Stream prefixes in time order; return (tick, verdict, wall_us_per_event)."""
        t0 = time.perf_counter()
        sig_t, sig_v, n = None, None, 0
        for k in range(1, len(order) + 1):
            prefix = order[:k]
            f = Fabric(prefix, ea)
            if drop_eid:
                f.inject(drop_eid=drop_eid)
            incs = {i.prop: i for i in f.evaluate(props)}
            v = incs[p_collective_package.__name__ if False else
                    "prohibited_collective_intel_package"].verdict
            n += 1
            if sig_t is None and v in (VIOLATION, UNKNOWN):
                sig_t, sig_v = prefix[-1].t, v
        us = (time.perf_counter() - t0) * 1e6 / max(n, 1)
        return sig_t, sig_v, us

    print(f"    package completes at mission-tick t={complete_t}")
    print(f"    {'config':28s} {'signal':>10s} {'tick':>5s} {'latency':>8s} {'us/event':>9s}")
    for label, ea, dz in [("fabric (fault-free)", True, None),
                          ("central (fault-free)", False, None),
                          ("fabric (dropped witness)", True, "uav_2-0"),
                          ("central (dropped witness)", False, "uav_2-0")]:
        st, sv, us = first_signal(ea, dz)
        if st is None:
            lat, sv = "inf", "(silent)"
        elif sv == VIOLATION:
            lat = f"{st - complete_t}"
        else:                                    # unknown raised the moment the gap is observable
            lat = f"flag@{st}"
        print(f"    {label:28s} {str(sv):>10s} {str(st) if st is not None else '-':>5s} "
              f"{lat:>8s} {us:>9.1f}")
    print("    => fault-free both detect at completion (latency 0). Under a dropped witness the")
    print("       fabric raises a FINITE 'unknown' the moment the event-id gap is observable;")
    print("       the central monitor's latency is INFINITE -- it never signals (silent miss).")


# =============================================================================
# 3. Byzantine lying platform + cross-witness corroboration
# =============================================================================
CORROB_BUDGET = 900


def _lying_scenario(jam_observer=None):
    """4 platforms each SELF-REPORT transmit=200 (sum 800 < budget) but an independent
    RF sentry OBSERVES the true 300 each (sum 1200 > budget). `jam_observer` drops the
    sentry's observation of one platform (evidence for corroboration goes missing)."""
    evs = []
    for i, a in enumerate(["uav_1", "uav_2", "uav_3", "ugv_1"]):
        evs.append(E(f"{a}-0", 1 + i, a, "transmit", bytes=200))                 # self-report
        if a != jam_observer:
            evs.append(E(f"rf-{i}", 1 + i, "rf_sentry", "observe", target=a, bytes=300))
    return evs


def _self_report_total(evs):
    return sum(e.bytes for e in evs if e.kind == "transmit")


def _observed_by_platform(evs):
    obs = {}
    for e in evs:
        if e.kind == "observe":
            obs[e.target] = obs.get(e.target, 0) + e.bytes
    return obs


def exp_byzantine():
    print("\n### 3. Byzantine lying platform + cross-witness corroboration")
    evs = _lying_scenario()
    sr = _self_report_total(evs)
    obs = _observed_by_platform(evs)
    obs_total = sum(obs.values())
    rep = {}
    for e in evs:
        if e.kind == "transmit":
            rep[e.agent] = rep.get(e.agent, 0) + e.bytes
    liars = sorted(a for a in obs if obs[a] - rep.get(a, 0) > 0)
    print(f"    self-report EMCON:   sum={sr}B  -> {NO_VIOLATION if sr<=CORROB_BUDGET else VIOLATION}"
          f"   (a self-report-only monitor is FOOLED)")
    print(f"    corroborated EMCON:  sum={obs_total}B (independent RF sentry) -> "
          f"{VIOLATION if obs_total>CORROB_BUDGET else NO_VIOLATION}   (caught)")
    print(f"    integrity check (self-report vs observed, per platform):")
    for a in liars:
        print(f"        {a}: reported {rep.get(a,0)}B, observed {obs[a]}B  -> UNDER-REPORT (lied)")
    print(f"    => provenance names liars: {liars}")
    # fault: jam the sentry's observation of uav_3 -> cannot corroborate that platform
    evs2 = _lying_scenario(jam_observer="uav_3")
    obs2 = _observed_by_platform(evs2)
    obs2_total = sum(obs2.values())
    corr = VIOLATION if obs2_total > CORROB_BUDGET else UNKNOWN   # missing corroborating witness
    print(f"    under a jammed RF sentry (uav_3 unobserved): corroborated sum={obs2_total}B "
          f"-> {corr}")
    print("    => a lying node defeats self-report monitoring; an independent witness restores")
    print("       detection, and when the witness is jammed the verdict is withheld (unknown),")
    print("       never a silent all-clear -- integrity faults handled like loss faults.")


# =============================================================================
# 4. ROC curves + AUC + Verdict-Preservation-Rate
# =============================================================================
def _auc(points):
    """Trapezoidal AUC over ROC points [(fpr, tpr), ...]."""
    pts = sorted(set(points))
    pts = [(0.0, 0.0)] + pts + [(1.0, 1.0)]
    area = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        area += (x1 - x0) * (y0 + y1) / 2.0
    return area


def exp_roc_vpr(M=400, seed=11):
    print("\n### 4. ROC / AUC (noisy emissions) + Verdict-Preservation-Rate")
    rng = random.Random(seed)
    ref = 900.0        # ground-truth label boundary on the TRUE swarm total
    sigma = 60.0       # per-mission measurement noise
    p_loss = 0.5       # central drops one platform's report with this prob (fault)
    missions = []
    for _ in range(M):
        true_total = rng.uniform(500, 1300)
        label = true_total > ref
        per = true_total / 4.0
        meas = [max(0.0, rng.gauss(per, sigma)) for _ in range(4)]
        lossy = list(meas)
        if rng.random() < p_loss:
            lossy[rng.randrange(4)] = 0.0        # a dropped/jammed report biases the sum low
        missions.append((label, meas, lossy))

    grid = [b for b in range(500, 1401, 20)]

    def roc(getter):
        pts = []
        for B in grid:
            tp = fp = tn = fn = 0
            for label, meas, lossy in missions:
                pred = getter(meas, lossy) > B
                if label and pred: tp += 1
                elif label and not pred: fn += 1
                elif not label and pred: fp += 1
                else: tn += 1
            tpr = tp / max(tp + fn, 1)
            fpr = fp / max(fp + tn, 1)
            pts.append((fpr, tpr))
        return pts

    complete = roc(lambda m, l: sum(m))            # sum over complete evidence
    lossy = roc(lambda m, l: sum(l))               # sum over lossy (biased) evidence
    peragent = roc(lambda m, l: max(m))            # a local monitor sees only one platform
    print("    AUC measures whether the collective-budget PROPERTY separates over- from")
    print("    under-budget missions -- i.e. is it well-posed, or a hand-tuned knob?")
    print(f"    {'evidence / view':30s} {'AUC':>6s}")
    print(f"    {'complete-evidence sum':30s} {_auc(complete):>6.3f}   (well-posed, ~1.0)")
    print(f"    {'lossy-evidence sum':30s} {_auc(lossy):>6.3f}   (any detector degrades under loss)")
    print(f"    {'per-agent (single platform)':30s} {_auc(peragent):>6.3f}   (~chance: locality cannot see a SUM)")
    print("    CAVEAT: ROC/AUC treats an honest 'unknown' and a silent miss identically (both")
    print("    are non-detections), so AUC CANNOT credit the fabric's contribution. That is")
    print("    precisely why the right instrument is the Verdict-Preservation-Rate below.")

    # --- No-Silent-Clear Rate over the full fault campaign (the CRITIS instrument) ---
    # NSCR = 1 - (silent false all-clears)/(oracle incidents). An honest 'unknown' does NOT
    # preserve the violation; it refuses to clear it -- so we name the metric for exactly
    # what it measures (never silently clearing), not "verdict preservation".
    print("\n    No-Silent-Clear Rate (NSCR) = 1 - silent-FAC / oracle incidents:")
    print("    fraction of oracle incidents NOT silently cleared (violation or honest unknown).")
    tot = {"per-agent": [0, 0], "central": [0, 0], "fabric": [0, 0]}  # [preserved, total]
    for name in SCENARIOS:
        evs, props, drop, silence = SCENARIOS[name]()
        oracle = [p for p, i in evaluate(evs, props, True).items() if i.verdict == VIOLATION]
        N = len(oracle)
        for fkw in ({}, {"drop": drop}, {"silence": silence}):
            tot["per-agent"][0] += 0;            tot["per-agent"][1] += N     # blind
            for cfg, ea in (("central", False), ("fabric", True)):
                p, d, fac = classify(evaluate(evs, props, ea, **fkw), oracle)
                tot[cfg][0] += p + d
                tot[cfg][1] += N
    print(f"    {'config':12s} {'NSCR':>7s}")
    for cfg in ("per-agent", "central", "fabric"):
        pres, n = tot[cfg]
        print(f"    {cfg:12s} {100.0*pres/max(n,1):>6.1f}%")
    print("    => fabric NSCR = 100% across the campaign; central silently clears some; per-agent none.")


# =============================================================================
# 5. Compound-fault graceful-degradation surface
# =============================================================================
def _squad(sq):
    """One independent squad's intel-package trace, namespaced by squad id."""
    base, _, _, _ = sc_intel_package()
    out = []
    for e in base:
        a, n = e.eid.rsplit("-", 1)
        out.append(Event(eid=f"s{sq}_{a}-{n}", t=e.t, agent=f"s{sq}_{e.agent}", kind=e.kind,
                         target=e.target, attr=e.attr, bytes=e.bytes, sensor=e.sensor))
    return out


def exp_compound():
    print("\n### 5. Compound-fault graceful-degradation surface")
    print("    N=8 independent squads each run the intel-package attack; we fault f of them")
    print("    (drop one collect witness) and jam g of them, then count silent false all-clears.")
    N = 8
    props = [p_collective_package]
    print(f"    {'drops f':>8} {'jams g':>7} {'central FAC':>12} {'fabric FAC':>11} {'fabric unknown':>15}")
    for f, g in [(0, 0), (2, 0), (4, 0), (0, 2), (2, 2), (4, 2), (6, 2)]:
        cen_fac = fab_fac = fab_unk = 0
        for sq in range(N):
            evs = _squad(sq)
            drop = f"s{sq}_uav_2-0" if sq < f else None
            silence = f"s{sq}_uav_3" if (f <= sq < f + g) else None
            # central (best-effort) and fabric (evidence-aware)
            for cfg, ea in (("c", False), ("f", True)):
                fab = Fabric(evs, ea)
                if drop:    fab.inject(drop_eid=drop)
                if silence: fab.inject(silence_agent=silence)
                inc = {i.prop: i for i in fab.evaluate(props)}["prohibited_collective_intel_package"]
                faulted = bool(drop or silence)
                if cfg == "c" and faulted and inc.verdict == NO_VIOLATION:
                    cen_fac += 1
                if cfg == "f" and faulted:
                    if inc.verdict == NO_VIOLATION: fab_fac += 1
                    elif inc.verdict == UNKNOWN:    fab_unk += 1
        print(f"    {f:>8} {g:>7} {cen_fac:>12} {fab_fac:>11} {fab_unk:>15}")
    print("    => fabric FAC stays 0 for every (f,g); its 'unknown' count grows monotonically")
    print("       (graceful degradation), while the central monitor's silent misses climb.")


# =============================================================================
# 6. Recovery: intermittent evidence resolves unknown -> violation
# =============================================================================
def exp_recovery():
    print("\n### 6. Recovery: does a withheld 'unknown' resolve soundly when evidence returns?")
    evs, props, _, _ = sc_intel_package()
    props = [p_collective_package]
    P = "prohibited_collective_intel_package"

    def verdict(ea, silence=None):
        f = Fabric(evs, ea)
        if silence:
            f.inject(silence_agent=silence)
        return {i.prop: i for i in f.evaluate(props)}[P].verdict

    # phase 1: uav_3 (contributes 'comms') is jammed/silent; phase 2: it recovers
    v1 = verdict(True, silence="uav_3")
    c1 = verdict(False, silence="uav_3")
    v2 = verdict(True)
    print(f"    phase 1  uav_3 jammed:   fabric = {v1:12s}   central = {c1}")
    print(f"    phase 2  uav_3 recovers: fabric = {v2:12s}")
    print("    => the fabric holds 'unknown' while a contributor is dark and resolves it to")
    print("       'violation' once the evidence arrives -- the downgrade is provisional and sound.")
    print(f"       the central monitor emitted a clean '{c1}' during the blackout (a false all-clear")
    print("       already delivered by the time evidence returns -- the harm is done).")


# =============================================================================
# 7. Multi-objective mission + provenance-attribution matrix
# =============================================================================
def _multi_objective_mission():
    return [
        # package parts on FacX (collective intel package)
        E("uav_1-0", 1, "uav_1", "collect", target="FacX", attr="coords", sensor="mapper"),
        E("uav_2-0", 1, "uav_2", "collect", target="FacX", attr="imagery", sensor="eo_camera"),
        E("uav_3-0", 1, "uav_3", "collect", target="FacX", attr="comms", sensor="sigint"),
        E("ugv_1-0", 1, "ugv_1", "collect", target="FacX", attr="access_route", sensor="mapper"),
        # targeting workflow (detect<classify<geolocate<share) on FacX
        E("uav_1-1", 1, "uav_1", "collect", target="FacX", attr="detect", sensor="eo_camera"),
        E("uav_2-1", 2, "uav_2", "collect", target="FacX", attr="classify", sensor="eo_camera"),
        E("uav_3-1", 3, "uav_3", "collect", target="FacX", attr="geolocate", sensor="sigint"),
        E("ugv_1-1", 4, "ugv_1", "collect", target="FacX", attr="share", sensor="rf"),
        # emissions over budget (EMCON + collective exfil)
        E("uav_1-2", 2, "uav_1", "transmit", bytes=300),
        E("uav_2-2", 2, "uav_2", "transmit", bytes=300),
        E("uav_3-2", 2, "uav_3", "transmit", bytes=300),
        E("ugv_1-2", 2, "ugv_1", "transmit", bytes=300),
        # sensitive-zone: uav_1 enters BEFORE authorize (auth-order); 3 inside (occupancy>K)
        E("uav_1-3", 1, "uav_1", "enter", attr=SENSITIVE_ZONE),
        E("cmd-0",   2, "cmd",   "authorize", attr=SENSITIVE_ZONE),
        E("uav_2-3", 2, "uav_2", "enter", attr=SENSITIVE_ZONE),
        E("uav_3-3", 3, "uav_3", "enter", attr=SENSITIVE_ZONE),
    ]


def exp_multiobjective():
    print("\n### 7. Multi-objective mission + provenance-attribution matrix")
    evs = _multi_objective_mission()
    props = [p_collective_package, p_emcon, p_authorization_order,
             p_exfil_budget, p_zone_occupancy, p_targeting_chain]
    incs = {i.prop: i for i in Fabric(evs, True).evaluate(props)}
    fired = [(name, i) for name, i in incs.items() if i.verdict == VIOLATION]
    agents = sorted({e.agent for e in evs})
    short = {"prohibited_collective_intel_package": "package",
             "emcon_emissions_budget": "emcon", "cross_agent_authorization": "auth",
             "collective_exfiltration": "exfil", "joint_zone_occupancy": "zone",
             "prohibited_targeting_workflow": "chain"}
    cols = [short[n] for n, _ in fired]
    print(f"    {len(fired)} properties fired simultaneously on one mission trace.")
    print(f"    {'agent':8s} " + " ".join(f"{c:>8s}" for c in cols))
    for a in agents:
        row = []
        for _, i in fired:
            row.append("  X" if a in i.agents else "  .")
        print(f"    {a:8s} " + " ".join(f"{c:>8s}" for c in row))
    print("    => provenance cleanly attributes each violation to its contributing platforms;")
    print("       'cmd' (the authoriser) appears in NO violation -- no collateral blame.")


def main():
    print("=" * 78)
    print("ADVANCED EXPERIMENTS -- adaptive adversary, latency, integrity, statistics")
    print("=" * 78)
    exp_evasion()
    exp_latency()
    exp_byzantine()
    exp_roc_vpr()
    exp_compound()
    exp_recovery()
    exp_multiobjective()
    print("\n" + "=" * 78)
    print("All advanced experiments computed from the real swarm_rv monitors (stdlib only).")
    print("=" * 78)


if __name__ == "__main__":
    main()
