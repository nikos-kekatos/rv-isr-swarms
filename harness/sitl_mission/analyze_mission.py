#!/usr/bin/env python3
"""
analyze_mission.py -- read a mission telemetry log (from SITL or the kinematic fallback),
canonicalise the action events into the RV event schema, run the SAME L1/L3 monitors as
the reproducible core, and write the per-agent + mission verdicts to verdict.json.

  python3 analyze_mission.py telemetry.jsonl
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from swarm_rv import Event, l1_verdicts, Fabric, MISSION_PROPS, VIOLATION, UNKNOWN


def load_events(path):
    events, seq = [], {}
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("type") != "action":
            continue
        a = r["agent"]; n = seq.get(a, 0)
        events.append(Event(eid=f"{a}-{n}", t=int(float(r["t"])), agent=a, kind=r["kind"],
                            target=r.get("target"), attr=r.get("attr"),
                            sensor=r.get("sensor"), bytes=int(r.get("bytes", 0))))
        seq[a] = n + 1
    return events


def main(path):
    ev = load_events(path)
    l1 = {a: i.verdict for a, i in l1_verdicts(ev).items()}
    incs = Fabric(ev, evidence_aware=True).evaluate(MISSION_PROPS)
    print(f"loaded {len(ev)} action events from {path}")
    print(f"L1 per-robot verdicts: {l1}")
    out_incidents = []
    for i in incs:
        if i.verdict in (VIOLATION, UNKNOWN):
            print(f"  L3 {i.verdict.upper()} :: {i.prop} :: agents={list(i.agents)}")
        out_incidents.append(dict(prop=i.prop, verdict=i.verdict, agents=list(i.agents)))
    verdict = dict(n_action_events=len(ev), l1=l1, incidents=out_incidents,
                   mission_violation=any(i.verdict == VIOLATION for i in incs))
    d = os.path.dirname(os.path.abspath(path)) or "."
    with open(os.path.join(d, "verdict.json"), "w") as f:
        json.dump(verdict, f, indent=2)
    print("wrote verdict.json")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "telemetry.jsonl")
