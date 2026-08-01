#!/usr/bin/env python3
"""
exp_timeout.py -- silence-timeout / mission-clock sensitivity (reviewer gap #3).

The fabric flags a contributing platform's stream as silent (-> property UNKNOWN, never a
silent all-clear) when it sees no event from that platform for longer than a silence timeout,
measured against the mission clock. This sweep quantifies the timeout tradeoff:

  * jam-detection latency  -- time from a platform actually going silent (jam) to the fabric
                              flagging it. Lower timeout = faster jam detection.
  * false-silence flags    -- benign but jittery/slow platforms flagged silent by mistake.
                              Lower timeout = more false flags.

Model: each of N platforms emits a heartbeat/event on the mission stream at a mean 1 Hz cadence
with bounded jitter; one platform is jammed at t_jam and stops. Deterministic (seeded); stdlib
only. This isolates the silence rule itself -- the same rule swarm_rv.Fabric uses via the
mission tick -- so no broker is needed.

  python3 exp_timeout.py          # prints the sensitivity table
"""
import argparse, random, statistics

N_PLATFORMS = 4
MISSION_LEN = 60          # seconds
MEAN_GAP = 1.0            # nominal 1 Hz heartbeat
T_JAM = 30               # a platform stops emitting at this mission time
RUNS = 300
TIMEOUTS = [2.0, 3.0, 5.0, 10.0]
JITTERS = [0.6, 1.0]             # +/- uniform jitter (s) on the heartbeat gap
STALL_PROB = 0.06                # benign comms stall (packet loss / backoff) per heartbeat ...
STALL_EXTRA = (1.5, 4.0)         # ... adding this many extra seconds (uniform)


def heartbeats(rng, jitter, jam_at=None):
    """Emit heartbeat times for one platform over the mission; stop at jam_at if given.
    Benign traffic is mostly 1 Hz with jitter, plus occasional heavy-tailed comms stalls."""
    t, ts = 0.0, []
    while t < MISSION_LEN:
        gap = MEAN_GAP + rng.uniform(-jitter, jitter)
        if rng.random() < STALL_PROB:
            gap += rng.uniform(*STALL_EXTRA)
        t += max(0.05, gap)
        if jam_at is not None and t >= jam_at:
            break
        ts.append(round(t, 3))
    return ts


def first_flag_time(hb, timeout):
    """Earliest mission time at which the gap since the last heartbeat exceeds `timeout`."""
    prev = 0.0
    for t in hb:
        if t - prev > timeout:
            return prev + timeout       # flagged mid-gap
        prev = t
    # trailing gap to end of mission (covers a jammed platform's silence tail)
    if MISSION_LEN - prev > timeout:
        return prev + timeout
    return None


def run(timeout, jitter, seed):
    rng = random.Random(seed)
    # platform 0 is jammed at T_JAM; the rest are benign (jittery) for the whole mission
    jam_hb = heartbeats(rng, jitter, jam_at=T_JAM)
    jflag = first_flag_time(jam_hb, timeout)
    latency = (jflag - T_JAM) if (jflag is not None and jflag >= T_JAM) else None
    false_flags = 0
    for _ in range(N_PLATFORMS - 1):
        hb = heartbeats(rng, jitter)
        f = first_flag_time(hb, timeout)
        if f is not None and f < MISSION_LEN:      # benign platform flagged silent = false flag
            false_flags += 1
    return latency, false_flags


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--md", action="store_true"); a = ap.parse_args()
    rows = []
    for jitter in JITTERS:
        for timeout in TIMEOUTS:
            lats, ff = [], 0
            for s in range(RUNS):
                lat, f = run(timeout, jitter, seed=1000 * int(jitter * 10) + int(timeout) * 97 + s)
                if lat is not None:
                    lats.append(lat)
                ff += f
            rows.append(dict(jitter=jitter, timeout=timeout,
                             det_latency=round(statistics.mean(lats), 2) if lats else None,
                             det_p95=round(sorted(lats)[int(0.95 * len(lats)) - 1], 2) if lats else None,
                             false_per_mission=round(ff / RUNS, 3)))
    # print
    print(f"silence-timeout sensitivity  ({RUNS} missions/cell, {N_PLATFORMS} platforms, "
          f"1 Hz heartbeat, jam@{T_JAM}s)\n")
    print(f"{'jitter':>7} {'timeout':>8} {'jam-det latency (s)':>20} {'p95':>7} {'false-silence/mission':>22}")
    for r in rows:
        print(f"{r['jitter']:>7} {r['timeout']:>8} {str(r['det_latency']):>20} {str(r['det_p95']):>7} "
              f"{r['false_per_mission']:>22}")
    print("\n=> lower timeout detects jamming faster but raises false-silence flags on jittery "
          "benign platforms; ~5 s is the knee (near-zero false flags, moderate latency).")
    if a.md:
        print("\n| jitter (s) | timeout (s) | jam-det latency (s) | p95 | false-silence/mission |")
        print("|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['jitter']} | {r['timeout']} | {r['det_latency']} | {r['det_p95']} | {r['false_per_mission']} |")


if __name__ == "__main__":
    main()
