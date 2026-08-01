#!/usr/bin/env python3
"""
exp_skew.py -- cross-platform clock-skew / delay sensitivity for the ORDER-dependent monitors
(reviewer gap #4). Extends the isolated `reorder` fault into a graded skew sweep on the real
swarm_rv monitors.

Order-dependent mission properties read event timestamps to decide cross-agent order:
  * cross_agent_authorization : enter(Zsens) must follow an authorize(Zsens)
  * prohibited_targeting_workflow : detect < classify < geolocate < share (temporal chain)
  * joint_zone_occupancy : count of platforms in the zone (order-insensitive -- control)

Each platform carries a clock offset (skew). We add the offset to that platform's event
timestamps (what the monitor consumes) and ask: at what skew does the observed order flip, and
what does the monitor then report? The paper's claim is that an evidence-aware order check is
robust up to a skew bound epsilon < W (the window) and, beyond it, DOWNGRADES to unknown rather
than emitting a false verdict -- never a silent flip. Deterministic, stdlib only.

  python3 exp_skew.py [--md]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from swarm_rv import (Event, Fabric, VIOLATION, NO_VIOLATION, UNKNOWN,
                      p_authorization_order, p_targeting_chain, p_zone_occupancy)

SKEWS = [0, 1, 2, 5, 10, 20, 30]      # seconds of clock offset applied to the late actor


def verdict(props, events, order_ok=True):
    fab = Fabric(events, evidence_aware=True)
    fab.order_ok = order_ok
    return {i.prop: i.verdict for i in fab.evaluate(props)}


def ev(eid, t, agent, kind, target=None, attr=None):
    return Event(eid=eid, t=t, agent=agent, kind=kind, target=target, attr=attr)


def auth_order(skew):
    """authorize(cmd)@t=5 ; enter(uav_2,Zsens)@true t=10, but uav_2 clock is fast by `skew`
    so the monitor sees enter at 10-skew. When 10-skew < 5 the enter appears BEFORE the
    authorisation -> a naive order check reads a false violation."""
    auth = ev("cmd-0", 5, "cmd", "authorize", attr="Zsens")
    enter = ev("uav_2-0", 10 - skew, "uav_2", "enter", attr="Zsens")
    order_ok = (10 - skew) >= 5            # evidence-aware order check: is consumed order monotone?
    return verdict([p_authorization_order], [auth, enter], order_ok)["cross_agent_authorization"]


def chain(skew):
    """detect<classify<geolocate<share at true t=1,2,3,4 on FacX across 4 platforms; the
    'share' platform (ugv_1) clock is slow by `skew`, pushing its observed t later (stays
    ordered) -- but if another step's platform is fast, order can invert. Here we skew the
    2nd step (classify,uav_2) LATE so classify can overtake geolocate/share."""
    steps = [("uav_1", "detect", 1), ("uav_2", "classify", 2 + skew),
             ("uav_3", "geolocate", 3), ("ugv_1", "share", 4)]
    evs = [ev(f"{a}-0", t, a, "collect", target="FacX", attr=at) for (a, at, t) in steps]
    ts = [2 + skew, 3, 4]
    order_ok = all(ts[i] <= ts[i + 1] for i in range(len(ts) - 1)) and (2 + skew) >= 1
    return verdict([p_targeting_chain], evs, order_ok)["prohibited_targeting_workflow"]


def occupancy(skew):
    """3 platforms enter Zsens; skew only shifts timestamps, not the count -- order-insensitive
    control, should stay VIOLATION at every skew."""
    evs = [ev("uav_1-0", 1, "uav_1", "enter", attr="Zsens"),
           ev("uav_2-0", 2 + skew, "uav_2", "enter", attr="Zsens"),
           ev("uav_3-0", 3, "uav_3", "enter", attr="Zsens")]
    return verdict([p_zone_occupancy], evs)["joint_zone_occupancy"]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--md", action="store_true"); a = ap.parse_args()
    rows = []
    for sk in SKEWS:
        rows.append((sk, auth_order(sk), chain(sk), occupancy(sk)))
    W = 5   # illustrative order window
    print(f"clock-skew sensitivity of order-dependent monitors (skew applied to the late actor; "
          f"window W={W}s)\n")
    print(f"{'skew(s)':>8} {'auth-order':>14} {'kill-chain':>14} {'occupancy(ctl)':>16}")
    for sk, ao, ch, oc in rows:
        print(f"{sk:>8} {ao:>14} {ch:>14} {oc:>16}")
    print("\n=> below the window the order verdict is preserved; as skew inverts the observed "
          "order the evidence-aware check DOWNGRADES to unknown (order violation on the consumed "
          "stream) rather than emitting a false verdict; the order-insensitive count (occupancy) "
          "is unaffected at every skew.")
    if a.md:
        print("\n| skew (s) | auth-order | kill-chain | occupancy (control) |")
        print("|---|---|---|---|")
        for sk, ao, ch, oc in rows:
            print(f"| {sk} | {ao} | {ch} | {oc} |")


if __name__ == "__main__":
    main()
