#!/usr/bin/env python3
"""
sim_telemetry.py -- kinematic fallback that produces telemetry in the SAME JSONL format
the ArduPilot SITL collector (mavlink_collect.py) emits, so the analysis + figure run
identically whether the flight came from real SITL flight dynamics or this generator.

Each platform flies straight segments between its waypoints at cruise speed, sampling
position every DT; actions (collect/transmit/enter) are emitted as it reaches the tagged
waypoints. Pure stdlib -> runnable anywhere.

  python3 sim_telemetry.py > telemetry.jsonl
"""
import json, math, sys
from mission_plan import PLATFORMS, SPEED, DT


def leg(p0, p1, t0):
    """Sample positions along the segment p0->p1 at DT intervals; return (samples, t_end)."""
    (x0, y0), (x1, y1) = p0, p1
    dist = math.hypot(x1 - x0, y1 - y0)
    steps = max(1, int(dist / (SPEED * DT)))
    out = []
    for k in range(1, steps + 1):
        f = k / steps
        out.append((round(t0 + k * DT, 1), x0 + f * (x1 - x0), y0 + f * (y1 - y0)))
    return out, t0 + steps * DT


def main():
    rows = []
    for ns, p in PLATFORMS.items():
        t = 0.0
        pos = p["start"]
        rows.append(dict(type="pos", t=0.0, agent=ns, x=pos[0], y=pos[1]))
        for i, wp in enumerate(p["wps"]):
            samples, t = leg(pos, wp, t)
            for (ts, x, y) in samples:
                rows.append(dict(type="pos", t=ts, agent=ns, x=round(x, 1), y=round(y, 1)))
            pos = wp
            if i in p["action_at"]:
                a = dict(p["action_at"][i])
                a.update(type="action", t=round(t, 1), agent=ns, x=round(pos[0], 1), y=round(pos[1], 1))
                if a["kind"] == "collect":
                    a["sensor"] = p["sensor"]
                rows.append(a)
                if a["kind"] == "collect":     # each collection is followed by a transmit
                    rows.append(dict(type="action", t=round(t + 0.5, 1), agent=ns,
                                     x=round(pos[0], 1), y=round(pos[1], 1),
                                     kind="transmit", bytes=p["bytes"]))
    rows.sort(key=lambda r: (r["t"], r["agent"]))
    for r in rows:
        sys.stdout.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
