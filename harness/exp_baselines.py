#!/usr/bin/env python3
"""exp_baselines.py -- stronger baselines and complementary metrics (reviewer gaps #3, #4).

The paper's original comparison was against (i) per-platform guardrails, blind by
construction, and (ii) a central best-effort monitor with no completeness handling. A
reviewer can object that both are straw men, and that NSCR is trivially satisfied by a
monitor that always abstains. This script closes both objections by adding:

  central+seq+hb (optimistic)   a central monitor that DOES have source sequence numbers
                               and heartbeats, so it observes loss and silence exactly as
                               the fabric does, but has no completeness axis: it must
                               answer violation or no_violation, and resolves missing
                               evidence optimistically
  central+seq+hb (pessimistic) the same monitor resolving missing evidence pessimistically
  always-unknown               the trivial monitor that abstains on everything

and by reporting, alongside the silent-clear count, the metrics that expose an
abstaining monitor: detection rate, abstention rate, decision coverage, and the benign
mission's false alarms and abstentions.

Run: python3 exp_baselines.py [--md]
"""

import argparse

from swarm_rv import (Event, Fabric, l1_verdicts, p_collective_package, p_emcon,
                      p_authorization_order, VIOLATION, NO_VIOLATION, UNKNOWN)
from experiments import SCENARIOS


def E(eid, t, agent, kind, **kw):
    return Event(eid=eid, t=t, agent=agent, kind=kind, **kw)


def benign_mission():
    """Permitted single-fragment recon, authorised entry, emissions within budget."""
    evs = [
        E("cmd-0", 0, "cmd", "authorize", attr="Zsens", target="Zsens"),
        E("uav_1-0", 1, "uav_1", "collect", target="FacX", attr="coords", sensor="mapper"),
        E("uav_1-1", 1, "uav_1", "transmit", bytes=200),
        E("uav_2-0", 2, "uav_2", "collect", target="SectorB", attr="imagery",
          sensor="eo_camera"),
        E("uav_2-1", 2, "uav_2", "enter", attr="Zsens"),
        E("uav_3-0", 3, "uav_3", "collect", target="SectorB", attr="comms", sensor="sigint"),
        E("ugv_1-0", 4, "ugv_1", "transmit", bytes=200),
    ]
    return evs, [p_collective_package, p_emcon, p_authorization_order], "uav_2-0", "uav_3"


def fabric_verdicts(evs, props, drop=None, silence=None, evidence_aware=True):
    fab = Fabric(evs, evidence_aware=evidence_aware)
    if drop:
        fab.inject(drop_eid=drop)
    if silence:
        fab.inject(silence_agent=silence)
    return {i.prop: i.verdict for i in fab.evaluate(props)}


def project(verdicts, policy):
    """A two-valued monitor that sees the same evidence signals but has no completeness
    axis: every unknown must be resolved one way or the other."""
    out = {}
    for prop, v in verdicts.items():
        if v == UNKNOWN:
            out[prop] = NO_VIOLATION if policy == "optimistic" else VIOLATION
        else:
            out[prop] = v
    return out


CONFIGS = ["per-platform", "central best-effort", "central+seq+hb (opt.)",
           "central+seq+hb (pess.)", "always-unknown", "RV-Fabric"]


def verdicts_for(cfg, evs, props, oracle_props, drop=None, silence=None):
    if cfg == "per-platform":
        # structurally blind: no representation of cross-platform incidents at all
        return {k: NO_VIOLATION for k in oracle_props}
    if cfg == "central best-effort":
        return fabric_verdicts(evs, props, drop, silence, evidence_aware=False)
    if cfg == "RV-Fabric":
        return fabric_verdicts(evs, props, drop, silence, evidence_aware=True)
    if cfg == "always-unknown":
        return {k: UNKNOWN for k in oracle_props}
    policy = "optimistic" if "opt." in cfg else "pessimistic"
    return project(fabric_verdicts(evs, props, drop, silence, evidence_aware=True), policy)


def score(verdicts, oracle):
    """oracle :: {prop -> verdict}. Returns detected, unknown, silent_clear, false_alarm."""
    det = unk = silent = false = 0
    for prop, ov in oracle.items():
        v = verdicts.get(prop, NO_VIOLATION)
        if v == VIOLATION and ov == VIOLATION:
            det += 1
        elif v == UNKNOWN:
            unk += 1
        elif v == NO_VIOLATION and ov == VIOLATION:
            silent += 1
        elif v == VIOLATION and ov != VIOLATION:
            false += 1
    return det, unk, silent, false


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", action="store_true")
    args = ap.parse_args()

    evs, props, drop, silence = SCENARIOS["intel_package"]()
    # ground truth: the property definitions over the complete pre-transport trace
    oracle = fabric_verdicts(evs, props, evidence_aware=True)
    n_incidents = sum(1 for v in oracle.values() if v == VIOLATION)

    bevs, bprops, bdrop, bsilence = benign_mission()
    boracle = fabric_verdicts(bevs, bprops, evidence_aware=True)

    faults = [("fault-free", {}), ("drop-witness", {"drop": drop}),
              ("jam-platform", {"silence": silence})]
    rows = []
    for cfg in CONFIGS:
        det = unk = silent = 0
        for _, fkw in faults:
            d, u, s, _ = score(verdicts_for(cfg, evs, props, oracle, **fkw), oracle)
            det += d
            unk += u
            silent += s
        # benign mission, under the same faults
        bfalse = babst = 0
        for _, fkw in [("fault-free", {}), ("drop", {"drop": bdrop}),
                       ("jam", {"silence": bsilence})]:
            _, u, _, f = score(verdicts_for(cfg, bevs, bprops, boracle, **fkw), boracle)
            bfalse += f
            babst += u
        total = n_incidents * len(faults)
        coverage = 100.0 * (total - unk) / total
        nscr = 100.0 * (total - silent) / total
        rows.append((cfg, det, total, unk, silent, nscr, coverage, bfalse, babst))

    hdr = ("configuration", "detected", "unknown", "silent clears", "NSCR",
           "decision coverage", "benign false alarms", "benign abstentions")
    if args.md:
        print("| " + " | ".join(hdr) + " |")
        print("|" + "---|" * len(hdr))
        for c, d, t, u, s, n, cov, bf, ba in rows:
            print(f"| {c} | {d}/{t} | {u} | {s} | {n:.0f}\\% | {cov:.0f}\\% | {bf} | {ba} |")
    else:
        print("=" * 96)
        print("STRONGER BASELINES AND COMPLEMENTARY METRICS "
              f"(intel-package objective, {len(faults)} faults, {n_incidents} oracle incidents each)")
        print("=" * 96)
        print(f"{'configuration':<24}{'detected':>10}{'unknown':>9}{'silent':>8}"
              f"{'NSCR':>7}{'coverage':>10}{'benignFA':>10}{'benignUnk':>11}")
        for c, d, t, u, s, n, cov, bf, ba in rows:
            print(f"{c:<24}{f'{d}/{t}':>10}{u:>9}{s:>8}{n:>6.0f}%{cov:>9.0f}%{bf:>10}{ba:>11}")
    print()
    print("Reading: the two central+seq+hb rows have exactly the fabric's evidence signals and")
    print("differ only in lacking the completeness axis. Optimistic resolution reproduces the")
    print("silent all-clears; pessimistic resolution removes them but pays in benign false")
    print("alarms. always-unknown scores NSCR 100% with detection 0 and abstains on every")
    print("benign mission, which is what excludes NSCR as a standalone metric.")


if __name__ == "__main__":
    main()
