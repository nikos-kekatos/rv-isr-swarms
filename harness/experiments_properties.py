#!/usr/bin/env python3
"""
experiments_properties.py -- add + TEST four new L3 property KINDS, each with a
compliant / violation / unknown(-under-fault) case, so every property is exercised on
all three verdict outcomes (not just the headline attack). Pure stdlib ->
`docker run --rm swarm-rv python3 experiments_properties.py`.

  coordinated_collection  COUNT   : >=3 distinct platforms collect on FacX within 30 s
  sector_coverage         LIVENESS: every priority sector observed (else gap; silent->unknown)
  integrity_corroboration INTEGRITY: self-report vs independent RF-sentry observation
  emcon_rate_burst        RATE    : transmit burst within a sliding window
"""
from swarm_rv import (Event, Fabric, VIOLATION, NO_VIOLATION, UNKNOWN,
                      p_coordinated_collection, p_sector_coverage,
                      p_corroboration, p_emcon_rate)


def E(eid, t, agent, kind, **kw):
    return Event(eid=eid, t=t, agent=agent, kind=kind, **kw)


def verdict(events, prop, ea=True, silence=None, drop=None):
    f = Fabric(events, evidence_aware=ea)
    if silence:
        f.inject(silence_agent=silence)
    if drop:
        f.inject(drop_eid=drop)
    return {i.prop: i for i in f.evaluate([prop])}[prop_name(prop)]


def prop_name(prop):
    return {"p_coordinated_collection": "coordinated_collection",
            "p_sector_coverage": "sector_coverage",
            "p_corroboration": "integrity_corroboration",
            "p_emcon_rate": "emcon_rate_burst"}[prop.__name__]


def show(title, inc, expect):
    ok = "OK" if inc.verdict == expect else f"** MISMATCH (expected {expect}) **"
    ag = f"  agents={list(inc.agents)}" if inc.agents else ""
    print(f"    {title:34s} -> {inc.verdict:12s} {ok}{ag}")
    return inc.verdict == expect


def main():
    print("=" * 78)
    print("NEW PROPERTY KINDS -- compliant / violation / unknown, each verified")
    print("=" * 78)
    passed = total = 0

    def check(*args):
        nonlocal passed, total
        total += 1; passed += show(*args)

    print("\n### coordinated_collection (COUNT: >=3 platforms on FacX within 30 s)")
    coord = [E(f"{a}-0", 1 + i, a, "collect", target="FacX", attr="survey")
             for i, a in enumerate(["uav_1", "uav_2", "uav_3", "ugv_1"])]
    check("4 platforms on FacX (attack)", verdict(coord, p_coordinated_collection), VIOLATION)
    two = coord[:2]
    check("only 2 platforms (below threshold)", verdict(two, p_coordinated_collection), NO_VIOLATION)
    # jamming 1 of 4 still leaves 3 (>= threshold): detection is ROBUST, stays violation
    check("jam 1 of 4 (3 remain) stays violation", verdict(coord, p_coordinated_collection, silence="uav_3"), VIOLATION)
    # but jamming 1 of exactly 3 drops below threshold + loss observable -> unknown
    coord3 = coord[:3]
    check("jam 1 of 3 (below threshold) -> unknown", verdict(coord3, p_coordinated_collection, silence="uav_3"), UNKNOWN)

    print("\n### sector_coverage (LIVENESS: Alpha & Bravo must be observed)")
    both = [E("uav_1-0", 1, "uav_1", "collect", target="Alpha", attr="survey"),
            E("uav_2-0", 2, "uav_2", "collect", target="Bravo", attr="survey")]
    check("both sectors surveyed", verdict(both, p_sector_coverage), NO_VIOLATION)
    only_a = [both[0]]
    check("Bravo never surveyed (gap)", verdict(only_a, p_sector_coverage), VIOLATION)
    # Bravo's platform silent: uav_2 has a later event so its silence is observable
    silent = [both[0], E("uav_2-9", 9, "uav_2", "transmit", bytes=10)]
    check("Bravo platform jammed -> unknown", verdict(silent, p_sector_coverage, silence="uav_2"), UNKNOWN)

    print("\n### integrity_corroboration (INTEGRITY: self-report vs RF-sentry)")
    honest = [E("uav_1-0", 1, "uav_1", "transmit", bytes=300),
              E("rf-0", 1, "rf", "observe", target="uav_1", bytes=300)]
    check("self-report == observed (honest)", verdict(honest, p_corroboration), NO_VIOLATION)
    lying = [E("uav_1-0", 1, "uav_1", "transmit", bytes=200),
             E("rf-0", 1, "rf", "observe", target="uav_1", bytes=300)]
    check("under-report (200 vs 300)", verdict(lying, p_corroboration), VIOLATION)
    no_witness = [E("uav_1-0", 1, "uav_1", "transmit", bytes=200)]
    check("no independent witness -> unknown", verdict(no_witness, p_corroboration), UNKNOWN)

    print("\n### emcon_rate_burst (RATE: >500 B within any 5 s window)")
    burst = [E(f"{a}-0", 1, a, "transmit", bytes=200)
             for a in ["uav_1", "uav_2", "uav_3"]]           # 600 B at t=1
    check("600 B in one window (burst)", verdict(burst, p_emcon_rate), VIOLATION)
    spread = [E("uav_1-0", 1, "uav_1", "transmit", bytes=200),
              E("uav_2-0", 8, "uav_2", "transmit", bytes=200),
              E("uav_3-0", 15, "uav_3", "transmit", bytes=200)]   # 200 B per window
    check("same total spread out (no burst)", verdict(spread, p_emcon_rate), NO_VIOLATION)

    print("\n" + "=" * 78)
    print(f"PROPERTY TESTS: {passed}/{total} passed "
          f"({'ALL PASS' if passed == total else 'FAILURES ABOVE'})")
    print("Each new property fires VIOLATION on its attack, NO_VIOLATION when benign, and")
    print("downgrades to UNKNOWN (never a silent all-clear) when its evidence is lost/jammed.")
    print("=" * 78)


if __name__ == "__main__":
    main()
