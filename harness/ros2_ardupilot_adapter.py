#!/usr/bin/env python3
"""
ros2_ardupilot_adapter.py -- REALISM-LAYER bridge (ISR swarm -> RV-Fabric).

Turns a ROS 2 + Gazebo + ArduPilot SITL mission into the canonical event schema
consumed by the compositional monitors (swarm_rv.py), and publishes over the REAL
RV-Fabric (MQTT + NATS JetStream, reused from ../../../paper_cloudnet/rv-fabric-impl).

STATUS: this is the integration scaffold for a Linux/GPU host. It is NOT exercised in
the reproducible core (which uses the kinematic sim and needs no ROS 2 / MAVLink).
Run it where ROS 2 (rclpy) + ArduPilot SITL (pymavlink) + the brokers are available.

Toolchain (host side, Docker recommended):
  - ArduPilot SITL:  docker run ... ardupilot/ardupilot-sitl   (or sim_vehicle.py)
  - ROS 2 + Gazebo:  ros:humble + gz-sim, one namespace per platform (/uav_1, ...)
  - Brokers:         docker compose up -d mosquitto nats   (from rv-fabric-impl)

Mapping (Gazebo/ArduPilot telemetry & LLM action topics -> RV events):
  /<ns>/action           (validated LLM JSON)      -> collect / transmit / enter
  /<ns>/global_position  (MAVLink GLOBAL_POSITION) -> enter(zone) when inside a geofence
  /<ns>/telemetry_link   (heartbeat)               -> silence detection = mission tick
Jamming = MAVLink/telemetry link loss; loss/reorder = broker-level fault injection.
"""
import json, os, sys

# --- geofences / mission config (would be loaded from the mission plan) -------
ZONES = {                        # lat/lon polygons -> zone id (illustrative)
    "Zsens": {"lat": (0.0, 0.001), "lon": (0.0, 0.001)},
}
PROHIBITED_TARGET = "FacX"

try:
    import rclpy                       # noqa: F401  (present only on a ROS 2 host)
    from rclpy.node import Node
    HAVE_ROS = True
except Exception:
    HAVE_ROS = False


def action_to_event(ns, seq, action, t):
    """Canonicalise a validated LLM structured action into an RV event dict
    (same schema as swarm_rv.Event). Published to the fabric subject gw.<ns>.evt."""
    eid = f"{ns}-{seq}"
    a = action.get("action")
    if a in ("collect", "assign_reconnaissance"):
        return dict(eid=eid, t=t, agent=ns, kind="collect",
                    target=action.get("target"), attr=action.get("attr") or action.get("collect"),
                    sensor=action.get("sensor"))
    if a in ("transmit", "share"):
        return dict(eid=eid, t=t, agent=ns, kind="transmit", bytes=int(action.get("bytes", 0)))
    if a == "enter":
        return dict(eid=eid, t=t, agent=ns, kind="enter", attr=action.get("zone"))
    if a == "authorize":
        return dict(eid=eid, t=t, agent=ns, kind="authorize", attr=action.get("zone"))
    return None


def _publish_fabric(evt):
    """Publish onto the real RV-Fabric (MQTT->JetStream). Uses the rv-fabric-impl
    gateway path; here we only show the subject + payload contract."""
    subject = f"gw.{evt['agent']}.evt"
    payload = json.dumps(evt)
    # In deployment: paho MQTT publish to dev/<gw>/<id>/evt at QoS 1; the gateway
    # sidecar assigns the durable eid + mission-ingest timestamp and relays to
    # NATS JetStream (see paper_cloudnet/rv-fabric-impl/gateway.py).
    print(f"[fabric] {subject}  {payload}")


if HAVE_ROS:
    class SwarmRVAdapter(Node):
        def __init__(self, namespaces):
            super().__init__("swarm_rv_adapter")
            self.seq = {ns: 0 for ns in namespaces}
            for ns in namespaces:
                # subscribe to each platform's validated-action + position topics
                # self.create_subscription(String, f"/{ns}/action", self._on_action(ns), 10)
                # self.create_subscription(NavSatFix, f"/{ns}/global_position", ...)
                self.get_logger().info(f"bridging namespace /{ns} -> RV-Fabric")

        def _on_action(self, ns):
            def cb(msg):
                self.seq[ns] += 1
                evt = action_to_event(ns, self.seq[ns], json.loads(msg.data),
                                      t=int(self.get_clock().now().nanoseconds / 1e9))
                if evt:
                    _publish_fabric(evt)
            return cb


def main():
    if not HAVE_ROS:
        print("ros2_ardupilot_adapter: ROS 2 (rclpy) not found on this host.\n"
              "This is the realism-layer scaffold; run it on a Linux ROS 2 + ArduPilot\n"
              "SITL host. The reproducible results run with:  python3 run_demo.py",
              file=sys.stderr)
        # Offline smoke test of the canonicaliser mapping:
        demo = action_to_event("uav_1", 0,
                               {"action": "collect", "target": "FacX", "attr": "coords",
                                "sensor": "mapper"}, t=1)
        _publish_fabric(demo)
        return 0
    namespaces = os.environ.get("SWARM_NS", "uav_1,uav_2,uav_3,ugv_1").split(",")
    rclpy.init()
    node = SwarmRVAdapter(namespaces)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node(); rclpy.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
