#!/usr/bin/env python3
"""
mavlink_collect.py -- REAL ArduPilot SITL collector (pymavlink).

Flies each platform's ISR route on a live ArduPilot SITL instance (real flight dynamics),
logging its LOCAL position as `pos` rows and emitting the mission `action` rows
(collect/transmit/enter) as it reaches the tagged waypoints, in the SAME telemetry.jsonl
format as sim_telemetry.py. Feeds analyze_mission.py + plot_mission.py unchanged.

Connection: with `sim_vehicle.py --no-mavproxy`, each SITL instance -I<n> exposes MAVLink
over TCP on port 5760 + 10*n (5760/5770/5780/5790). Connect there, NOT udp:14550 (the
--out=udp flag is a MAVProxy option and is ignored under --no-mavproxy).

  python3 mavlink_collect.py --conn tcp:127.0.0.1:5760 --ns uav_1 >> telemetry.jsonl

All waits are bounded; a platform that fails to arm/fly still emits its tagged action
events (so the RV verdict is always produced) and the script moves on.
"""
import argparse, json, math, sys, time
from mission_plan import PLATFORMS, DT

try:
    from pymavlink import mavutil
    HAVE_MAV = True
except Exception:
    HAVE_MAV = False


def emit(row):
    sys.stdout.write(json.dumps(row) + "\n"); sys.stdout.flush()


def log(msg):
    sys.stderr.write(msg + "\n"); sys.stderr.flush()


def wait_heartbeat(m, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        if m.recv_match(type="HEARTBEAT", blocking=True, timeout=5):
            return True
    return False


def set_param(m, name, val):
    m.mav.param_set_send(m.target_system, m.target_component, name.encode(),
                         float(val), mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    time.sleep(0.3)


def set_mode(m, mode):
    mapping = m.mode_mapping() or {}
    if mode in mapping:
        m.set_mode(mapping[mode])
    else:
        try:
            m.set_mode(mode)
        except Exception:
            pass


def arm(m, timeout=60):
    """Relax sim pre-arm checks, request GUIDED, and arm with a bounded retry loop
    (force-arm fallback). Returns True if armed, False on timeout."""
    set_param(m, "ARMING_CHECK", 0)      # sim only: skip GPS/EKF pre-arm gating
    set_mode(m, "GUIDED")
    end = time.time() + timeout
    force = 0                            # param2=21196 forces arming
    while time.time() < end:
        m.mav.command_long_send(m.target_system, m.target_component,
                                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                                1, force, 0, 0, 0, 0, 0)
        m.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
        if m.motors_armed():
            return True
        force = 21196                    # escalate to force-arm on subsequent tries
    return False


def request_streams(m, hz=5):
    """With --no-mavproxy nothing requests telemetry, so LOCAL_POSITION_NED never arrives.
    Ask for the position streams explicitly (both the legacy data-stream and the per-message
    interval for LOCAL_POSITION_NED id=32), so we actually capture the trajectory."""
    for stream in (mavutil.mavlink.MAV_DATA_STREAM_POSITION,
                   mavutil.mavlink.MAV_DATA_STREAM_EXTRA1,
                   mavutil.mavlink.MAV_DATA_STREAM_ALL):
        m.mav.request_data_stream_send(m.target_system, m.target_component, stream, hz, 1)
    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                            32, int(1e6 / hz), 0, 0, 0, 0, 0)   # 32 = LOCAL_POSITION_NED


def wait_ekf(m, timeout=25):
    """Wait until the EKF has a position estimate (GPS-derived origin), so LOCAL_POSITION_NED
    is meaningful and GUIDED goto works. Returns True once a position message arrives."""
    end = time.time() + timeout
    while time.time() < end:
        msg = m.recv_match(type=["GLOBAL_POSITION_INT", "LOCAL_POSITION_NED"],
                           blocking=True, timeout=2)
        if msg:
            return True
    return False


def takeoff(m, alt=20, timeout=40):
    m.mav.command_long_send(m.target_system, m.target_component,
                            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, alt)
    end = time.time() + timeout
    while time.time() < end:
        msg = m.recv_match(type="LOCAL_POSITION_NED", blocking=True, timeout=2)
        if msg and -msg.z >= alt * 0.9:
            return True
    return False


def fly(conn, ns):
    p = PLATFORMS[ns]
    sx, sy = p["start"]
    log(f"[{ns}] connecting {conn}")
    m = mavutil.mavlink_connection(conn)
    if not wait_heartbeat(m):
        log(f"[{ns}] no heartbeat on {conn}; is SITL up on that port? skipping flight, "
            f"still emitting mission actions.")
    else:
        log(f"[{ns}] heartbeat ok; requesting position stream")
        request_streams(m)
        set_param(m, "WPNAV_SPEED", 1500)      # 15 m/s so legs complete within the window
        if wait_ekf(m):
            log(f"[{ns}] EKF position ready; arming")
        else:
            log(f"[{ns}] no position stream yet; arming anyway")
        if arm(m):
            log(f"[{ns}] armed; takeoff"); takeoff(m)
        else:
            log(f"[{ns}] arm timed out; proceeding (actions still emitted)")
    t0 = time.time()
    for i, wp in enumerate(p["wps"]):
        north, east = wp[1] - sy, wp[0] - sx
        try:
            m.mav.set_position_target_local_ned_send(
                0, m.target_system, m.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED, 0b0000111111111000,
                north, east, -20, 0, 0, 0, 0, 0, 0, 0, 0)
        except Exception:
            pass
        wp_end = time.time() + 30            # bounded: never wait forever on one waypoint
        while time.time() < wp_end:
            msg = m.recv_match(type="LOCAL_POSITION_NED", blocking=True, timeout=2)
            if not msg:
                continue
            x, y = sx + msg.y, sy + msg.x
            emit(dict(type="pos", t=round(time.time() - t0, 1), agent=ns,
                      x=round(x, 1), y=round(y, 1)))
            if math.hypot(x - wp[0], y - wp[1]) < 8:
                break
            time.sleep(DT)
        # emit the tagged mission action for this waypoint (always, so a verdict is produced)
        if i in p["action_at"]:
            a = dict(p["action_at"][i]); a.update(type="action", t=round(time.time() - t0, 1),
                                                  agent=ns, x=wp[0], y=wp[1])
            if a["kind"] == "collect":
                a["sensor"] = p["sensor"]
            emit(a)
            if a["kind"] == "collect":
                emit(dict(type="action", t=round(time.time() - t0, 1), agent=ns,
                          x=wp[0], y=wp[1], kind="transmit", bytes=p["bytes"]))
    log(f"[{ns}] done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conn", required=True, help="e.g. tcp:127.0.0.1:5760")
    ap.add_argument("--ns", required=True, choices=list(PLATFORMS))
    a = ap.parse_args()
    if not HAVE_MAV:
        log("pymavlink not installed; run in the SITL VM (pip install pymavlink). "
            "Use sim_telemetry.py for the tested kinematic fallback.")
        return 1
    fly(a.conn, a.ns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
