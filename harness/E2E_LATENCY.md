# End-to-end verdict latency (`e2e_latency.py`)

Measures `t_verdict − t_event_generation` across the full fabric pipeline:

```
event generation → MQTT (Mosquitto) → squad/L2 sidecar (ingest ts + event-id + durable outbox)
                 → NATS JetStream (durable) → L3 mission monitor → verdict
```

Reports median / p95 / p99 / max under **fault-free** and **degraded-link** (added per-hop
delay + loss), for both a live stack and an offline model.

## Offline synthetic mode (default; runs anywhere)
```bash
python3 e2e_latency.py
```
Per-hop latencies come from a seeded model — deterministic, **not** a live measurement
(clearly labelled). Use it for a quick sanity/format check and CI.

## Real mode (live brokers, on a Linux/VM host with Docker)
```bash
# from the harness dir; brings up the reused RV-Fabric brokers
docker compose -f ../../../paper_cloudnet/rv-fabric-impl/docker-compose.yml up -d mosquitto nats
pip install paho-mqtt nats-py
python3 e2e_latency.py --real           # publishes N events over the real stack, times each stage
```
If `paho-mqtt`/`nats-py` or the brokers are unavailable, it falls back to offline mode with a
clear message.

## Reading the numbers
- **fault-free** is the nominal wire+compute latency; the mission-monitor evaluation itself is
  sub-millisecond (see the scale sweep), so the tail is dominated by broker delivery + durable
  acknowledgement.
- **degraded-link** adds delay + drop per hop; JetStream's durable delivery replays after loss,
  so latency grows but no accepted event is lost (the evidence-state transitions still fire).
- The paper's contribution concerns the complete fabric, so this end-to-end number complements
  the monitor-only timing.
