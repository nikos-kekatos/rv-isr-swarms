#!/usr/bin/env python3
"""
mission_monitor.py -- the L3 mission monitor as a ROS 2 node.

Subscribes to every platform's /<ns>/action topic over real ROS 2 (DDS), canonicalises
each action into the shared event schema, and runs the SAME L1 (per-robot) and L3
(cross-agent) monitors as the reproducible core (swarm_rv.py). It periodically reports the
per-agent verdicts (all compliant) and the mission-level compositional verdicts with
provenance, so the distributed violation is seen to emerge only once enough platforms have
reported. This validates the ROS 2 integration end-to-end without Gazebo/GPU.

  python3 mission_monitor.py            # PYTHONPATH must include the harness dir
"""
import json
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from std_msgs.msg import String

from swarm_rv import Event, l1_verdicts, MISSION_PROPS, Fabric, VIOLATION, UNKNOWN

PLATFORMS = ["uav_1", "uav_2", "uav_3", "ugv_1"]


class MissionMonitor(Node):
    def __init__(self):
        super().__init__("mission_monitor")
        self.events = []
        self.seq = {}
        self.clock = 0
        for ns in PLATFORMS:
            self.create_subscription(String, f"/{ns}/action", self._cb(ns), 10)
        self.create_timer(4.0, self.report)   # report as evidence accumulates
        self.get_logger().info(f"subscribed to {['/'+p+'/action' for p in PLATFORMS]}")

    def _cb(self, ns):
        def cb(msg):
            a = json.loads(msg.data)
            self.clock += 1
            n = self.seq.get(ns, 0)
            self.events.append(Event(eid=f"{ns}-{n}", t=self.clock, agent=ns,
                                     kind=a.get("kind"), target=a.get("target"),
                                     attr=a.get("attr"), sensor=a.get("sensor"),
                                     bytes=int(a.get("bytes", 0))))
            self.seq[ns] = n + 1
        return cb

    def report(self):
        l1 = {a: i.verdict for a, i in l1_verdicts(self.events).items()}
        incs = Fabric(self.events, evidence_aware=True).evaluate(MISSION_PROPS)
        self.get_logger().info(f"[{len(self.events)} events] L1 per-robot: {l1 or 'none yet'}")
        fired = [i for i in incs if i.verdict in (VIOLATION, UNKNOWN)]
        if not fired:
            self.get_logger().info("  L3 mission: no violation yet")
        for i in fired:
            self.get_logger().info(
                f"  L3 {i.verdict.upper()} :: {i.prop} :: agents={list(i.agents)}")


def main():
    rclpy.init()
    node = MissionMonitor()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
