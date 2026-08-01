#!/usr/bin/env python3
"""
experiments_hierarchy.py -- genuine three-tier L1 -> L2 -> L3 composition.

Addresses the review point that the headline scenario is essentially L1->L3 and leaves
L2 under-used. Here the prohibited intelligence package is split across TWO squads, so the
mission violation is only visible after each squad's L2 coordinator emits a PARTIAL-profile
verdict and L3 composes the two partials:

    robot evidence (L1)  ->  squad partial profile (L2)  ->  mission violation (L3)

Six robots, two squads:
    Squad Alpha : uav_1 (coords), uav_2 (imagery), uav_3 (comms)
    Squad Bravo : ugv_1 (access_route), uav_4 (relay, benign), ugv_2 (benign SectorC recon)

Alpha's L2 emits partial_profile(FacX,{coords,imagery,comms}); Bravo's L2 emits
partial_profile(FacX,{access_route}); L3 unions them into the complete prohibited profile.
Completeness propagates UP the hierarchy: an observable loss inside a squad makes that
squad's partial INCOMPLETE, and the evidence-aware L3 union downgrades to unknown rather
than silently clearing. Pure stdlib -> `docker run --rm swarm-rv python3 experiments_hierarchy.py`.
"""
from dataclasses import dataclass
from swarm_rv import (Event, l1_verdicts, PACKAGE_PARTS, PROHIBITED_TARGET,
                      VIOLATION, NO_VIOLATION, UNKNOWN, SOUND, INCOMPLETE,
                      meet, downgrade)


def E(eid, t, agent, kind, **kw):
    return Event(eid=eid, t=t, agent=agent, kind=kind, **kw)


SQUADS = {
    "Alpha": ["uav_1", "uav_2", "uav_3"],
    "Bravo": ["ugv_1", "uav_4", "ugv_2"],
}


def build_two_squad():
    """Each Alpha robot collects one FacX fragment (seq 0) and then transmits (seq 1),
    so a dropped collect leaves an event-id gap (observable loss). Bravo's ugv_1 supplies
    the fourth fragment; uav_4/ugv_2 run benign background."""
    return [
        # --- Squad Alpha: three fragments of the FacX profile ---
        E("uav_1-0", 1, "uav_1", "collect", target="FacX", attr="coords", sensor="mapper"),
        E("uav_1-1", 1, "uav_1", "transmit", bytes=150),
        E("uav_2-0", 2, "uav_2", "collect", target="FacX", attr="imagery", sensor="eo_camera"),
        E("uav_2-1", 2, "uav_2", "transmit", bytes=150),
        E("uav_3-0", 3, "uav_3", "collect", target="FacX", attr="comms", sensor="sigint"),
        E("uav_3-1", 3, "uav_3", "transmit", bytes=150),
        # --- Squad Bravo: fourth fragment + benign background ---
        E("ugv_1-0", 4, "ugv_1", "collect", target="FacX", attr="access_route", sensor="mapper"),
        E("ugv_1-1", 4, "ugv_1", "transmit", bytes=100),
        E("uav_4-0", 2, "uav_4", "transmit", bytes=100),                       # benign relay
        E("ugv_2-0", 3, "ugv_2", "collect", target="SectorC", attr="imagery", sensor="eo_camera"),
    ]


@dataclass
class L2Partial:
    squad: str
    parts: frozenset
    completeness: str
    agents: tuple
    witnesses: tuple


def _squad_gap(events, agents):
    """A squad's stream has an observable gap if some member's event-id sequence skips a
    number (a dropped event whose later siblings still arrived)."""
    seen = {}
    for e in events:
        if e.agent in agents:
            a, n = e.eid.rsplit("-", 1)
            seen.setdefault(a, set()).add(int(n))
    for a, ns in seen.items():
        if ns and max(ns) + 1 != len(ns):        # contiguous 0..k expected
            return True
    return False


def l2_partial(squad, events, evidence_aware):
    """L2 coordinator: aggregate its robots' FacX fragments into a partial profile,
    tagging completeness from any observable in-squad loss."""
    members = SQUADS[squad]
    frags = {}
    for e in events:
        if (e.agent in members and e.kind == "collect"
                and e.target == PROHIBITED_TARGET and e.attr in PACKAGE_PARTS):
            frags[e.attr] = e
    comp = SOUND
    if evidence_aware and _squad_gap(events, members):
        comp = INCOMPLETE
    return L2Partial(squad, frozenset(frags), comp,
                     agents=tuple(sorted(e.agent for e in frags.values())),
                     witnesses=tuple(sorted(e.eid for e in frags.values())))


def l3_compose(partials, evidence_aware):
    """L3 mission monitor: compose squad partials into the complete-profile verdict."""
    union = frozenset().union(*[p.parts for p in partials]) if partials else frozenset()
    agents = tuple(sorted({a for p in partials for a in p.agents}))
    wit = tuple(sorted({w for p in partials for w in p.witnesses}))
    comp = meet(*[p.completeness for p in partials]) if partials else SOUND
    if PACKAGE_PARTS.issubset(union):
        s = VIOLATION
    elif evidence_aware and comp != SOUND:
        s = UNKNOWN                     # a squad's evidence is incomplete: cannot clear
    else:
        s = NO_VIOLATION                # best-effort: silently clears on missing evidence
    return {"verdict": downgrade(s, comp), "completeness": comp,
            "parts": sorted(union), "agents": agents, "witnesses": wit}


def run(events, evidence_aware, drop=None):
    evs = [e for e in events if e.eid != drop]
    l1 = {a: i.verdict for a, i in l1_verdicts(evs).items()}
    partials = [l2_partial(s, evs, evidence_aware) for s in SQUADS]
    l3 = l3_compose(partials, evidence_aware)
    return l1, partials, l3


def main():
    print("=" * 78)
    print("THREE-TIER HIERARCHY:  L1 (robot) -> L2 (squad partial) -> L3 (mission)")
    print("=" * 78)
    events = build_two_squad()

    for title, ea, drop in [("fault-free  (evidence-aware fabric)", True, None),
                            ("drop uav_2 imagery witness  (fabric)", True, "uav_2-0"),
                            ("drop uav_2 imagery witness  (central best-effort)", False, "uav_2-0")]:
        l1, partials, l3 = run(events, ea, drop)
        print(f"\n### {title}")
        print(f"    L1 per-robot: {l1}")
        for p in partials:
            print(f"    L2[{p.squad:5s}] partial_profile(FacX)={sorted(p.parts)}  "
                  f"completeness={p.completeness}  agents={list(p.agents)}")
        print(f"    L3 compose -> {l3['verdict'].upper()}  (parts={l3['parts']}, "
              f"completeness={l3['completeness']})")
        if l3["verdict"] == VIOLATION:
            print(f"       provenance agents={list(l3['agents'])}  witnesses={list(l3['witnesses'])}")

    print("\n" + "=" * 78)
    print("=> Every L1 verdict is no_violation. Neither squad's L2 partial is a violation")
    print("   on its own; only the L3 COMPOSITION of the two squad partials is the prohibited")
    print("   profile -- a genuine L1->L2->L3 chain. Under a dropped in-squad witness the")
    print("   evidence-aware L3 inherits the squad's INCOMPLETE tag and returns 'unknown',")
    print("   whereas the best-effort L3 silently clears (false all-clear).")
    print("=" * 78)


if __name__ == "__main__":
    main()
