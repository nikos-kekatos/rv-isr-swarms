#!/usr/bin/env python3
"""
e2e_latency.py -- End-to-end verdict latency for the compositional RV fabric
(MESAS Paper 1, reviewer suggestion #3).

Measures  t_verdict - t_event_generation  across the full fabric pipeline the
paper describes:

    event generation
      -> MQTT publish (Mosquitto, QoS 1)
      -> squad/L2 sidecar (monotone ingest ts + persistent event-id + durable outbox)
      -> NATS JetStream (durable publish + ack)
      -> L3 mission monitor (swarm_rv.Fabric.evaluate(MISSION_PROPS))
      -> verdict emission

and reports median / p95 / p99 / max under two conditions:
    (a) fault-free
    (b) degraded-link  (extra per-hop delay + per-hop drop probability with
        at-least-once / durable retransmit)

TWO modes
---------
REAL     : publishes N mission events over the actual Mosquitto + NATS JetStream
           stack and times each stage on the wire. Needs paho-mqtt + nats-py and
           the brokers up (see E2E_LATENCY.md). Falls back with a clear message if
           either the deps or the brokers are unavailable.
OFFLINE  : (default, and the automatic fallback) models plausible per-hop latencies
SYNTHETIC  with a SEEDED RNG so it runs anywhere and is byte-for-byte reproducible.
           Clearly labelled -- it is NOT a live measurement.

Stdlib-first: paho-mqtt / nats-py are imported ONLY inside REAL mode (guarded).

Run:  python3 e2e_latency.py            # offline synthetic (default)
      python3 e2e_latency.py --real     # live, needs brokers + deps
"""
import argparse
import math
import random
import socket
import sys
from collections import deque

# The L3 mission monitor we call at the end of the pipeline (stdlib-only module).
from swarm_rv import Event, Fabric, MISSION_PROPS


# --- reproducibility ----------------------------------------------------------
# Fixed, date-derived constant (NOT time-based): the offline synthetic run is
# deterministic and identical on every host. Never call time.time()/random()
# without seeding from this.
SEED = 20260721

# Default number of mission events pushed through the pipeline per condition.
DEFAULT_N = 1000

# Fabric endpoints (match paper_cloudnet/rv-fabric-impl/docker-compose.yml).
MQTT_HOST, MQTT_PORT = "localhost", 1883
NATS_URL, NATS_MON_PORT = "nats://localhost:4222", 4222
MQTT_TOPIC = "swarm/{squad}/{plat}/mission/evt"
NATS_SUBJECT = "swarm.mission.verdict"
STREAM_NAME = "SWARMRV"


# --- per-hop latency model (OFFLINE SYNTHETIC) --------------------------------
# One entry per fabric hop. Latencies are lognormal (right-skewed, as real
# network/IO latencies are): median = exp(mu) ms, spread set by sigma. The
# degraded-link condition adds a fixed extra delay and an independent per-hop
# drop probability; a drop triggers an at-least-once / JetStream-durable
# retransmit that pays a redelivery-timeout penalty (this is what stretches the
# p95/p99/max tail, exactly as observed on a lossy WAN link).
#
# medians (ms): MQTT publish+QoS1 ack ~2, sidecar L1/L2+WAL fsync ~1.2,
# JetStream durable ack ~4 (the hop most exposed to link quality),
# L3 monitor eval ~0.4 (local compute, barely affected).
HOP_MODEL = [
    # name              median_ms sigma  degr_extra_ms  drop_p
    ("mqtt_publish",        2.0,   0.45,     10.0,       0.08),
    ("sidecar_ingest",      1.2,   0.50,      6.0,       0.05),
    ("jetstream_ack",       4.0,   0.50,     15.0,       0.10),
    ("monitor_eval",        0.4,   0.35,      1.0,       0.00),
]
# Retransmit penalty on a dropped hop (redelivery timeout), lognormal ms.
RETX_MEDIAN_MS, RETX_SIGMA = 120.0, 0.30


def _sample_e2e_offline(rng, degraded):
    """Sum per-hop latencies for one event; return end-to-end ms."""
    total = 0.0
    for _name, median_ms, sigma, extra_ms, drop_p in HOP_MODEL:
        total += rng.lognormvariate(math.log(median_ms), sigma)
        if degraded:
            total += extra_ms
            # at-least-once / durable: the event is never lost, only re-sent;
            # each redelivery adds a timeout penalty.
            while rng.random() < drop_p:
                total += rng.lognormvariate(math.log(RETX_MEDIAN_MS), RETX_SIGMA)
    return total


def run_offline(n, degraded):
    """Deterministic per-condition latency sample (ms). Seeded per condition so
    fault-free and degraded are each independently reproducible."""
    rng = random.Random(SEED + (1 if degraded else 0))
    return [_sample_e2e_offline(rng, degraded) for _ in range(n)]


# --- mission event stream -----------------------------------------------------
def build_mission_stream(n):
    """A representative distributed-attack mission stream, extended to n events
    with unique per-agent event-ids so the L3 fabric sees a well-formed stream.
    Content mirrors run_demo.build_attack (task-split prohibited package)."""
    agents = ["uav_1", "uav_2", "uav_3", "ugv_1"]
    template = [
        ("collect", dict(target="FacX", attr="coords", sensor="mapper")),
        ("transmit", dict(bytes=120)),
        ("collect", dict(target="FacX", attr="imagery", sensor="eo_camera")),
        ("enter", dict(attr="Zsens")),
        ("collect", dict(target="FacX", attr="comms", sensor="sigint")),
        ("transmit", dict(bytes=120)),
        ("collect", dict(target="FacX", attr="access_route", sensor="mapper")),
        ("transmit", dict(bytes=120)),
    ]
    seq = {a: 0 for a in agents}
    events = []
    for i in range(n):
        agent = agents[i % len(agents)]
        kind, kw = template[i % len(template)]
        eid = f"{agent}-{seq[agent]}"
        seq[agent] += 1
        t = 1 + i // len(agents)
        events.append(Event(eid=eid, t=t, agent=agent, kind=kind, **kw))
    return events


# --- statistics ---------------------------------------------------------------
def _percentile(sorted_vals, p):
    """Linear-interpolated percentile (numpy default 'linear' method)."""
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[int(k)]
    return sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo)


def summarize(latencies_ms):
    s = sorted(latencies_ms)
    return {
        "median": _percentile(s, 50),
        "p95": _percentile(s, 95),
        "p99": _percentile(s, 99),
        "max": s[-1] if s else 0.0,
        "n": len(s),
    }


def print_table(title, rows):
    """rows: list of (condition_label, summary_dict)."""
    print()
    print(title)
    print("-" * 74)
    print(f"{'condition':<22}{'median':>11}{'p95':>11}{'p99':>11}{'max':>11}{'n':>8}")
    print(f"{'':<22}{'(ms)':>11}{'(ms)':>11}{'(ms)':>11}{'(ms)':>11}{'':>8}")
    print("-" * 74)
    for label, st in rows:
        print(f"{label:<22}{st['median']:>11.2f}{st['p95']:>11.2f}"
              f"{st['p99']:>11.2f}{st['max']:>11.2f}{st['n']:>8d}")
    print("-" * 74)


# --- REAL mode ----------------------------------------------------------------
def _brokers_reachable():
    """Quick TCP probe of Mosquitto and NATS."""
    for host, port in ((MQTT_HOST, MQTT_PORT), ("localhost", NATS_MON_PORT)):
        try:
            with socket.create_connection((host, port), timeout=1.0):
                pass
        except OSError:
            return False, f"{host}:{port}"
    return True, None


def run_real(n, degraded):
    """Publish n mission events over the live Mosquitto + JetStream stack and
    time each event end-to-end. Returns list of latencies (ms) or None on
    unavailability (caller falls back to offline)."""
    try:
        import asyncio
        import json
        import os
        import time
        import paho.mqtt.client as mqtt
        import nats
    except ImportError as e:
        print(f"[real] dependency unavailable ({e}); paho-mqtt + nats-py required.")
        return None

    ok, where = _brokers_reachable()
    if not ok:
        print(f"[real] broker unreachable at {where}. Bring the stack up first:")
        print("       docker compose -f ../../../paper_cloudnet/rv-fabric-impl/"
              "docker-compose.yml up -d mosquitto nats")
        return None

    # Degraded-link injection knobs (seeded so runs are comparable).
    rng = random.Random(SEED + (1 if degraded else 0))
    events = build_mission_stream(n)

    async def pipeline():
        latencies = []
        received = asyncio.Event()
        # Bounded working set: the mission monitor evaluates over a recent window (real
        # incremental monitoring), so per-event evaluation is O(window), not O(stream) --
        # otherwise a growing buffer makes this an O(n^2) throughput artifact, not a latency.
        buffer = deque(maxlen=256)
        wal_path = os.environ.get("E2E_OUTBOX", f"/tmp/e2e-outbox.jsonl")
        wal = open(wal_path, "w")
        ingest_seq = {}

        nc = await nats.connect(NATS_URL)
        js = nc.jetstream()
        try:
            await js.add_stream(name=STREAM_NAME, subjects=[NATS_SUBJECT])
        except Exception:
            pass  # already exists

        # --- L3 mission monitor: consume from JetStream, evaluate per event ---
        async def on_verdict(msg):
            await msg.ack()
            rec = json.loads(msg.data)
            ev = rec["event"]
            buffer.append(Event(eid=ev["eid"], t=ev["t"], agent=ev["agent"],
                                kind=ev["kind"], target=ev.get("target"),
                                attr=ev.get("attr"), bytes=ev.get("bytes", 0),
                                sensor=ev.get("sensor")))
            # verdict emission point: monitor evaluates the mission properties.
            Fabric(buffer, evidence_aware=True).evaluate(MISSION_PROPS)
            t_verdict = time.perf_counter_ns()
            latencies.append((t_verdict - rec["t_gen_ns"]) / 1e6)  # -> ms
            if len(latencies) >= n:
                received.set()

        sub = await js.subscribe(NATS_SUBJECT, cb=on_verdict, durable="l3mon")

        # --- squad/L2 sidecar: MQTT -> stamp + eid + durable outbox -> NATS ---
        loop = asyncio.get_running_loop()
        mqueue = asyncio.Queue()
        mc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e-sidecar")
        mc.on_message = lambda c, u, m: loop.call_soon_threadsafe(
            mqueue.put_nowait, m.payload)
        mc.connect(MQTT_HOST, MQTT_PORT)
        mc.subscribe("swarm/+/+/mission/evt", qos=1)
        mc.loop_start()

        async def sidecar():
            handled = 0
            while handled < n:
                payload = await mqueue.get()
                rec = json.loads(payload)
                # monotone ingest ts + persistent event-id (guarantee #2)
                rec["ingest_us"] = time.monotonic_ns() // 1000
                a = rec["event"]["agent"]
                ingest_seq[a] = ingest_seq.get(a, 0) + 1
                rec["eid"] = f"{a}:{ingest_seq[a]}"
                if degraded:
                    # per-hop degraded-link emulation on the sidecar->JetStream leg
                    await asyncio.sleep(0.006)
                    while rng.random() < 0.10:  # durable retransmit on drop
                        await asyncio.sleep(0.120)
                line = json.dumps(rec)
                wal.write(line + "\n"); wal.flush(); os.fsync(wal.fileno())  # durable outbox
                await js.publish(NATS_SUBJECT, line.encode())               # durable ack
                handled += 1

        sc_task = asyncio.create_task(sidecar())

        # --- producer: event generation -> MQTT publish (QoS 1) ---
        pc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="e2e-producer")
        pc.connect(MQTT_HOST, MQTT_PORT)
        pc.loop_start()
        for ev in events:
            rec = {
                "t_gen_ns": time.perf_counter_ns(),  # t_event_generation
                "event": {"eid": ev.eid, "t": ev.t, "agent": ev.agent,
                          "kind": ev.kind, "target": ev.target, "attr": ev.attr,
                          "bytes": ev.bytes, "sensor": ev.sensor},
            }
            topic = MQTT_TOPIC.format(squad=ev.agent.split("_")[0], plat=ev.agent)
            if degraded:
                await asyncio.sleep(0.010)  # degraded publish leg
            pc.publish(topic, json.dumps(rec), qos=1)
            # Pace arrivals below the pipeline's service rate so no backlog builds -- otherwise
            # queued events inflate t_verdict-t_gen (a throughput artifact, not latency). Real
            # missions emit at ~1 Hz/platform; 15 ms spacing (~65/s swarm-wide) is well above that.
            await asyncio.sleep(0.015)

        try:
            await asyncio.wait_for(received.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            print(f"[real] timed out: received {len(latencies)}/{n} verdicts.")
        finally:
            await sub.unsubscribe()
            sc_task.cancel()
            pc.loop_stop(); mc.loop_stop()
            await nc.close()
            wal.close()
        return latencies

    return asyncio.run(pipeline())


# --- driver -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", action="store_true",
                    help="live measurement over Mosquitto + JetStream (needs deps + brokers)")
    ap.add_argument("-n", type=int, default=DEFAULT_N,
                    help=f"mission events per condition (default {DEFAULT_N})")
    args = ap.parse_args()

    mode = "REAL (live fabric)"
    rows = []
    used_offline = True

    if args.real:
        ff = run_real(args.n, degraded=False)
        dg = run_real(args.n, degraded=True) if ff is not None else None
        if ff is not None and dg is not None:
            rows = [("fault-free", summarize(ff)), ("degraded-link", summarize(dg))]
            used_offline = False
        else:
            print("[real] falling back to OFFLINE SYNTHETIC mode.\n")

    if used_offline:
        mode = ("OFFLINE SYNTHETIC (per-hop model) -- NOT a live measurement "
                f"(seed={SEED})")
        rows = [
            ("fault-free", summarize(run_offline(args.n, degraded=False))),
            ("degraded-link", summarize(run_offline(args.n, degraded=True))),
        ]

    title = (f"End-to-end verdict latency  (t_verdict - t_event_generation)\n"
             f"mode: {mode}\n"
             f"pipeline: gen -> MQTT(Mosquitto) -> squad/L2 sidecar -> "
             f"NATS JetStream -> L3 mission monitor")
    print_table(title, rows)
    if used_offline:
        print("Note: OFFLINE SYNTHETIC numbers come from the seeded per-hop model "
              "above,\n      not from live brokers. Use --real on a host with the "
              "stack up for wire numbers.")


if __name__ == "__main__":
    sys.exit(main())
