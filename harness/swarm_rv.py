#!/usr/bin/env python3
"""
swarm_rv.py -- Compositional RV core for an LLM-assisted ISR robot swarm (MESAS Paper 1).

Self-contained, stdlib-only. Emulates the RV-Fabric in-process (event ids, mission
tick, fault injection) so the whole headline result runs with `python3 run_demo.py`
-- no ROS 2 / MQTT / NATS needed for the RV contribution (those are wired later,
reusing paper_cloudnet/rv-fabric-impl). The physics/simulator fidelity is NOT the
contribution; the event stream + monitors + evidence-aware fabric is.

Model mirrors the CRITIS RV-Fabric evidence-aware verdict algebra:
  security verdict  s in {VIOLATION, NO_VIOLATION, UNKNOWN}
  completeness      c in {SOUND > DEGRADED > INCOMPLETE > UNAVAILABLE}
A cross-agent (mission-level) property fires VIOLATION when the *combined* witnesses
across agents satisfy it; provenance names the agents + witness event ids. When a
witness is missing/re-ordered but the loss is OBSERVABLE (an event-id gap on a
contributing stream, or an order violation), the verdict is downgraded to
(UNKNOWN, INCOMPLETE) instead of a silent NO_VIOLATION -- no false all-clear.
"""
from dataclasses import dataclass, field
from typing import Optional

# --- verdict lattice ----------------------------------------------------------
VIOLATION, NO_VIOLATION, UNKNOWN = "violation", "no_violation", "unknown"
SOUND, DEGRADED, INCOMPLETE, UNAVAILABLE = "sound", "degraded", "incomplete", "unavailable"
_C_RANK = {SOUND: 3, DEGRADED: 2, INCOMPLETE: 1, UNAVAILABLE: 0}


def meet(*cs: str) -> str:
    """Greatest-lower-bound of completeness tags (worst wins)."""
    return min(cs, key=lambda c: _C_RANK[c]) if cs else SOUND


def downgrade(s: str, c: str) -> str:
    """A no_violation over non-sound evidence is not trustworthy -> unknown."""
    if s == NO_VIOLATION and _C_RANK[c] < _C_RANK[SOUND]:
        return UNKNOWN
    return s


# --- events -------------------------------------------------------------------
@dataclass(frozen=True)
class Event:
    eid: str            # fabric-assigned persistent id "<agent>-<seq>"
    t: int              # mission-clock timestamp (seconds)
    agent: str
    kind: str           # collect | transmit | enter | authorize | tick | observe
    target: Optional[str] = None   # e.g. "FacX" (facility), zone id
    attr: Optional[str] = None      # collect: {coords,imagery,comms,access_route}; enter/authorize: zone
    bytes: int = 0
    sensor: Optional[str] = None


@dataclass
class Incident:
    prop: str
    verdict: str
    completeness: str
    agents: tuple = ()
    witnesses: tuple = ()
    note: str = ""

    @property
    def key(self):            # identity for oracle comparison
        return (self.prop, self.target_key())

    def target_key(self):
        return self.witnesses[0].split("-")[0] if False else self.prop


# --- mission policy (thresholds fixed a priori) -------------------------------
PROHIBITED_TARGET = "FacX"
PACKAGE_PARTS = {"coords", "imagery", "comms", "access_route"}   # prohibited if all collected
EMCON_BUDGET = 900          # swarm-wide bytes over the mission window
LOCAL_TX_LIMIT = 500        # per-agent bytes (each agent stays under this)
SENSITIVE_ZONE = "Zsens"
AUTH_SENSORS = {"eo_camera", "sigint", "mapper", "rf"}


# --- L1 (per-robot) monitors --------------------------------------------------
def l1_verdicts(events):
    """Each robot checked on its OWN trace. In the attack every agent is compliant."""
    out = {}
    per = {}
    for e in events:
        per.setdefault(e.agent, []).append(e)
    for a, evs in per.items():
        tx = sum(e.bytes for e in evs if e.kind == "transmit")
        bad_sensor = any(e.sensor and e.sensor not in AUTH_SENSORS for e in evs)
        over_local = tx > LOCAL_TX_LIMIT
        s = VIOLATION if (bad_sensor or over_local) else NO_VIOLATION
        out[a] = Incident("l1_local_compliance", s, SOUND, agents=(a,),
                          note=f"tx={tx}B" + (" OVER" if over_local else "")
                               + (" bad-sensor" if bad_sensor else ""))
    return out


# --- L3 (mission) cross-agent properties --------------------------------------
def _stream_gaps(events, expected_seq):
    """Return set of agents whose event-id sequence has a gap (observable loss)."""
    seen = {}
    for e in events:
        a, n = e.eid.rsplit("-", 1)
        seen.setdefault(a, set()).add(int(n))
    gapped = set()
    for a, exp in expected_seq.items():
        if seen.get(a, set()) != exp:
            gapped.add(a)
    return gapped


def p_collective_package(events, gapped, evidence_aware):
    """HEADLINE: prohibited collective intelligence package on a protected site.
    Fires only across agents; invisible to any single L1 monitor. Prior command
    authorisation of collection on the protected site cancels the violation -- this is the
    non-authorised conjunct of P_pkg in the paper (so paper = code = console spec)."""
    authorised = any(e.kind == "authorize"
                     and (e.attr == PROHIBITED_TARGET or e.target == PROHIBITED_TARGET)
                     for e in events)
    if authorised:
        return Incident("prohibited_collective_intel_package", NO_VIOLATION, SOUND,
                        note="command-authorised collection on FacX")
    parts = {}
    for e in events:
        if e.kind == "collect" and e.target == PROHIBITED_TARGET and e.attr in PACKAGE_PARTS:
            parts[e.attr] = e
    if PACKAGE_PARTS.issubset(parts):
        ws = tuple(sorted(e.eid for e in parts.values()))
        ags = tuple(sorted({parts[p].agent for p in PACKAGE_PARTS}))
        return Incident("prohibited_collective_intel_package", VIOLATION, SOUND,
                        agents=ags, witnesses=ws, note=f"parts={sorted(parts)}")
    # not all parts present. Was a contributing stream observably lost? Any event-id
    # gap or silence means we cannot rule the package out -> withhold, don't clear.
    if evidence_aware and gapped:
        return Incident("prohibited_collective_intel_package", UNKNOWN, INCOMPLETE,
                        agents=tuple(sorted(gapped)),
                        note=f"missing part; observable loss on {sorted(gapped)}")
    return Incident("prohibited_collective_intel_package", NO_VIOLATION, SOUND)


def p_emcon(events, gapped, evidence_aware):
    """Mission-wide emissions budget: sum of swarm emissions over the window."""
    total = sum(e.bytes for e in events if e.kind == "transmit")
    agents = tuple(sorted({e.agent for e in events if e.kind == "transmit"}))
    if total > EMCON_BUDGET:
        wit = tuple(sorted(e.eid for e in events if e.kind == "transmit"))
        return Incident("emcon_emissions_budget", VIOLATION, SOUND, agents=agents,
                        witnesses=wit, note=f"sum={total}B > {EMCON_BUDGET}B")
    if evidence_aware and gapped:
        return Incident("emcon_emissions_budget", UNKNOWN, INCOMPLETE, agents=tuple(sorted(gapped)),
                        note=f"sum={total}B but eid gap on {sorted(gapped)}")
    return Incident("emcon_emissions_budget", NO_VIOLATION, SOUND)


def p_authorization_order(events, order_ok, evidence_aware):
    """Cross-agent causal order: enter(sensitive zone) only after an authorize."""
    auths = [e for e in events if e.kind == "authorize" and e.attr == SENSITIVE_ZONE]
    enters = [e for e in events if e.kind == "enter" and e.attr == SENSITIVE_ZONE]
    for en in enters:
        prior = [a for a in auths if a.t <= en.t]
        if not prior:
            if not order_ok and evidence_aware:
                return Incident("cross_agent_authorization", UNKNOWN, INCOMPLETE,
                                agents=(en.agent,), note="order violation on consumed stream")
            return Incident("cross_agent_authorization", VIOLATION, SOUND, agents=(en.agent,),
                            witnesses=(en.eid,), note=f"{en.agent} entered {SENSITIVE_ZONE} unauthorised")
    return Incident("cross_agent_authorization", NO_VIOLATION, SOUND)


EXFIL_BUDGET = 900          # swarm-wide transmit budget for the exfiltration objective
K_OCC = 2                   # max platforms allowed in the sensitive zone at once
CHAIN = ["detect", "classify", "geolocate", "share"]   # prohibited targeting workflow


def p_exfil_budget(events, missing, evidence_aware):
    """Collective exfiltration: aggregate transmitted bytes over the swarm exceed the
    mission budget, even though each platform stays under its local limit."""
    total = sum(e.bytes for e in events if e.kind == "transmit")
    agents = tuple(sorted({e.agent for e in events if e.kind == "transmit"}))
    if total > EXFIL_BUDGET:
        wit = tuple(sorted(e.eid for e in events if e.kind == "transmit"))
        return Incident("collective_exfiltration", VIOLATION, SOUND, agents=agents,
                        witnesses=wit, note=f"sum={total}B > {EXFIL_BUDGET}B")
    if evidence_aware and missing:
        return Incident("collective_exfiltration", UNKNOWN, INCOMPLETE,
                        agents=tuple(sorted(missing)), note=f"sum={total}B, evidence missing")
    return Incident("collective_exfiltration", NO_VIOLATION, SOUND)


def p_zone_occupancy(events, missing, evidence_aware):
    """Airspace deconfliction: no more than K_OCC platforms in the sensitive zone."""
    inside = sorted({e.agent for e in events if e.kind == "enter" and e.attr == SENSITIVE_ZONE})
    if len(inside) > K_OCC:
        wit = tuple(sorted(e.eid for e in events
                           if e.kind == "enter" and e.attr == SENSITIVE_ZONE))
        return Incident("joint_zone_occupancy", VIOLATION, SOUND, agents=tuple(inside),
                        witnesses=wit, note=f"{len(inside)} > {K_OCC} in {SENSITIVE_ZONE}")
    if evidence_aware and missing:
        return Incident("joint_zone_occupancy", UNKNOWN, INCOMPLETE, agents=tuple(sorted(missing)),
                        note="occupancy count over incomplete evidence")
    return Incident("joint_zone_occupancy", NO_VIOLATION, SOUND)


def p_targeting_chain(events, missing, evidence_aware):
    """Prohibited targeting workflow: detect < classify < geolocate < share on one target,
    split across platforms. No single platform completes the sequence. Loss of a chain
    step (event-id gap / silence) is observable and downgrades to unknown, not a
    silent all-clear."""
    # prior command authorisation of the workflow on the protected site cancels it (same
    # non-authorised conjunct as the package property -- an authorised workflow is permitted).
    if any(e.kind == "authorize" and (e.attr == PROHIBITED_TARGET or e.target == PROHIBITED_TARGET)
           for e in events):
        return Incident("prohibited_targeting_workflow", NO_VIOLATION, SOUND,
                        note="command-authorised workflow on FacX")
    steps = {}
    for e in events:
        if e.target == PROHIBITED_TARGET and e.attr in CHAIN:
            steps.setdefault(e.attr, e)
    if all(s in steps for s in CHAIN):
        ts = [steps[s].t for s in CHAIN]
        if all(ts[i] <= ts[i + 1] for i in range(len(ts) - 1)):
            ags = tuple(sorted({steps[s].agent for s in CHAIN}))
            wit = tuple(steps[s].eid for s in CHAIN)
            return Incident("prohibited_targeting_workflow", VIOLATION, SOUND, agents=ags,
                            witnesses=wit, note="detect<classify<geolocate<share")
        if evidence_aware:   # all steps present but observed out of order (e.g. clock skew):
            return Incident("prohibited_targeting_workflow", UNKNOWN, INCOMPLETE,   # cannot confirm
                            agents=tuple(sorted({steps[s].agent for s in CHAIN})),
                            note="chain steps present but not monotone; order unconfirmed")
    if evidence_aware and missing:   # a chain step was observably lost -> cannot clear it
        return Incident("prohibited_targeting_workflow", UNKNOWN, INCOMPLETE,
                        agents=tuple(sorted(missing)), note="chain step lost; evidence incomplete")
    return Incident("prohibited_targeting_workflow", NO_VIOLATION, SOUND)


# --- additional L3 property KINDS (each exercises a distinct monitoring pattern) --------
COORD_N = 3                 # >= this many distinct platforms collecting on FacX ...
COORD_WINDOW = 30           # ... within this window (s) = coordinated collection
REQUIRED_SECTORS = ["Alpha", "Bravo"]     # priority sectors that must be covered
EMCON_RATE_BUDGET = 500     # transmit bytes allowed within ...
EMCON_RATE_WINDOW = 5       # ... this sliding window (s): a burst, not just a total


def p_coordinated_collection(events, missing, evidence_aware):
    """COUNT: >= COORD_N distinct platforms collect on FacX within COORD_WINDOW seconds.
    The swarm analogue of the edge-IoT cross-gateway primitive; matches the real MonPoly
    property in p_coord.mfotl."""
    cols = [e for e in events if e.kind == "collect" and e.target == PROHIBITED_TARGET]
    agents = sorted({e.agent for e in cols})
    if len(agents) >= COORD_N and cols and (max(e.t for e in cols) - min(e.t for e in cols)) <= COORD_WINDOW:
        return Incident("coordinated_collection", VIOLATION, SOUND, agents=tuple(agents),
                        witnesses=tuple(sorted(e.eid for e in cols)),
                        note=f">={COORD_N} platforms on FacX within {COORD_WINDOW}s")
    if evidence_aware and missing:
        return Incident("coordinated_collection", UNKNOWN, INCOMPLETE,
                        agents=tuple(sorted(missing)), note="a contributing stream is lost/silent")
    return Incident("coordinated_collection", NO_VIOLATION, SOUND)


def p_sector_coverage(events, missing, evidence_aware):
    """COVERAGE / liveness: every REQUIRED_SECTORS sector must be observed (past-time ONCE).
    An uncovered sector is a coverage gap (violation); if a contributing platform is silent
    we cannot tell -> unknown, never a false 'covered'."""
    covered = {e.target for e in events if e.kind == "collect"}
    gap = [s for s in REQUIRED_SECTORS if s not in covered]
    if not gap:
        return Incident("sector_coverage", NO_VIOLATION, SOUND, note="all priority sectors covered")
    if evidence_aware and missing:
        return Incident("sector_coverage", UNKNOWN, INCOMPLETE, agents=tuple(sorted(missing)),
                        note=f"coverage unknown for {gap} (silent platform)")
    return Incident("sector_coverage", VIOLATION, SOUND, note=f"coverage gap: {gap}")


def p_corroboration(events, missing, evidence_aware):
    """INTEGRITY: cross-witness corroboration. A platform's self-reported emission (transmit)
    is compared with an independent RF-sentry observation (observe, target=platform). An
    under-report is an integrity violation; a platform with no independent witness -> unknown."""
    rep, obs = {}, {}
    for e in events:
        if e.kind == "transmit":
            rep[e.agent] = rep.get(e.agent, 0) + e.bytes
        elif e.kind == "observe":
            obs[e.target] = obs.get(e.target, 0) + e.bytes
    liars = sorted(a for a in obs if obs[a] - rep.get(a, 0) > 0)
    unobserved = sorted(a for a in rep if a not in obs)
    if liars:
        return Incident("integrity_corroboration", VIOLATION, SOUND, agents=tuple(liars),
                        note="self-report < independent observation")
    if evidence_aware and unobserved:
        return Incident("integrity_corroboration", UNKNOWN, INCOMPLETE, agents=tuple(unobserved),
                        note="no corroborating witness")
    return Incident("integrity_corroboration", NO_VIOLATION, SOUND)


def p_emcon_rate(events, missing, evidence_aware):
    """RATE: a transmit BURST -- more than EMCON_RATE_BUDGET bytes within any
    EMCON_RATE_WINDOW-second window -- even if the mission total stays within budget."""
    tx = sorted((e for e in events if e.kind == "transmit"), key=lambda e: e.t)
    for e in tx:
        win = [x for x in tx if e.t <= x.t <= e.t + EMCON_RATE_WINDOW]
        s = sum(x.bytes for x in win)
        if s > EMCON_RATE_BUDGET:
            return Incident("emcon_rate_burst", VIOLATION, SOUND,
                            agents=tuple(sorted({x.agent for x in win})),
                            witnesses=tuple(sorted(x.eid for x in win)),
                            note=f"{s}B within {EMCON_RATE_WINDOW}s > {EMCON_RATE_BUDGET}B")
    if evidence_aware and missing:
        return Incident("emcon_rate_burst", UNKNOWN, INCOMPLETE, agents=tuple(sorted(missing)))
    return Incident("emcon_rate_burst", NO_VIOLATION, SOUND)


MISSION_PROPS = [p_collective_package, p_emcon, p_authorization_order]
ORDER_PROPS = {p_authorization_order}   # these need order_ok; others receive `missing`


# --- emulated RV-Fabric with fault injection ----------------------------------
class Fabric:
    """Carries per-agent event streams to the mission (L3) monitor. Emulates the
    RV-Fabric guarantees + their loss under fault: eid continuity (G1), order (G2),
    mission tick (G3). `evidence_aware=False` = a best-effort central monitor that
    cannot lower completeness -> silent false all-clears."""

    def __init__(self, events, evidence_aware=True, see_gaps=True, see_silence=True):
        self.raw = list(events)
        self.evidence_aware = evidence_aware
        self.see_gaps = see_gaps        # G1: event-id gap detection (ablate to disable)
        self.see_silence = see_silence  # G3: mission-clock silence detection
        self.dropped = set()
        self.order_ok = True
        self.silenced = set()

    def inject(self, drop_eid=None, reorder=False, silence_agent=None):
        if drop_eid:
            self.dropped.add(drop_eid)
        if reorder:
            self.order_ok = False
        if silence_agent:
            self.silenced.add(silence_agent)

    def consumed(self):
        evs = [e for e in self.raw if e.eid not in self.dropped and e.agent not in self.silenced]
        return evs

    def evaluate(self, props=None):
        props = props if props is not None else MISSION_PROPS
        evs = self.consumed()
        # expected per-agent seq (what a sound stream should contain)
        expected = {}
        for e in self.raw:
            if e.agent in self.silenced:
                continue
            a, n = e.eid.rsplit("-", 1)
            expected.setdefault(a, set()).add(int(n))
        gapped = _stream_gaps(evs, expected) if (self.evidence_aware and self.see_gaps) else set()
        # a jammed (silent) contributor is observably-missing evidence too, but only
        # the evidence-aware fabric (mission tick) can see it; central cannot.
        seen_silence = self.silenced if (self.evidence_aware and self.see_silence) else set()
        missing = (gapped | seen_silence) if self.evidence_aware else set()
        incidents = []
        for a in sorted(seen_silence):
            if self.evidence_aware:
                incidents.append(Incident("subgroup_silence_coverage", UNKNOWN, UNAVAILABLE,
                                          agents=(a,), note=f"{a} silent; mission tick flags missing stream"))
        for prop in props:
            if prop in ORDER_PROPS:
                inc = prop(evs, self.order_ok, self.evidence_aware)
            else:
                inc = prop(evs, missing, self.evidence_aware)
            inc.verdict = downgrade(inc.verdict, inc.completeness)
            incidents.append(inc)
        return incidents
