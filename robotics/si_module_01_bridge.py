#!/usr/bin/env python3
"""
Symbiotic Intelligence (SI) Layer - ROS 2 Client Bridge Node
Module 01: Pre-Motor Kinematic Lead-Time Telemetry
Target: Commercial Service Robotics & Interactive Kiosks

Subscribes to the si-module-01 60Hz edge WebSocket stream, enforces the
33.3ms (2-frame) watchdog heartbeat and schema contract, and publishes
validated pre-motor intent directives to native ROS 2 motion planning topics.
"""

import asyncio
import json
import threading
import time
from typing import Optional
import websockets

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from std_msgs.msg import String

REQUIRED_KEYS = {
    "timestamp",
    "frame_id",
    "gaze_vector",
    "target_xy_normalized",
    "target_identifier",
    "gaze_locked",
    "reach_transit_active",
    "intent_directive",
    "measured_lead_time_ms",
    "confidence",
}

VALID_DIRECTIVES = {
    "IDLE",
    "PREEMPTIVE_ORIENT_AND_EXTEND",
    "HANDOFF_ZONE_OCCUPIED",
    "ACTIVE_DECELERATION",
    "HOLD",
}

WATCHDOG_TIMEOUT_SEC = 0.035  # ~2 consecutive 60Hz frames (33.3 ms)


class SIModule01Bridge(Node):
    def __init__(self):
        super().__init__("si_module_01_bridge")

        # Low-latency QoS: Keep only latest 60Hz frame to prevent stale queue buildup
        qos_profile = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
        )

        self.directive_pub = self.create_publisher(
            String,
            "/si_layer/module_01/intent_directive",
            qos_profile,
        )
        self.last_frame_id: Optional[int] = None
        self.watchdog_triggered: bool = False
        self.get_logger().info(
            "SI Layer Module 01 Bridge initialized. Connecting to 60Hz edge stream..."
        )

    def validate_and_publish(self, raw_json: str) -> None:
        try:
            packet = json.loads(raw_json)
        except json.JSONDecodeError:
            self.get_logger().warn("Dropped malformed JSON frame from telemetry stream.")
            return

        if not REQUIRED_KEYS.issubset(packet.keys()):
            self.get_logger().warn("Dropped telemetry frame missing required schema keys.")
            return

        if packet.get("intent_directive") not in VALID_DIRECTIVES:
            self.get_logger().warn(
                f"Unknown intent_directive: {packet.get('intent_directive')}"
            )
            return

        frame_id = packet.get("frame_id")
        if self.last_frame_id is not None and frame_id <= self.last_frame_id:
            self.get_logger().warn(
                f"Non-monotonic frame_id detected ({frame_id} <= {self.last_frame_id})."
            )
        self.last_frame_id = frame_id
        self.watchdog_triggered = False

        msg = String()
        msg.data = raw_json
        self.directive_pub.publish(msg)

    def publish_watchdog_hold(self, reason: str) -> None:
        """Emits a deterministic HOLD directive if the 60Hz stream drops > 33.3ms."""
        if not self.watchdog_triggered:
            self.get_logger().warn(
                f"Watchdog triggered ({reason}) -> Emitting HOLD directive."
            )
            self.watchdog_triggered = True

        fallback_payload = {
            "timestamp": round(time.time(), 4),
            "frame_id": (self.last_frame_id or 0),
            "gaze_vector": [0.0, 0.0, 1.0],
            "target_xy_normalized": [0.0, 0.0],
            "target_identifier": "NONE",
            "gaze_locked": False,
            "reach_transit_active": False,
            "intent_directive": "HOLD",
            "measured_lead_time_ms": 0.0,
            "confidence": 0.0,
        }
        msg = String()
        msg.data = json.dumps(fallback_payload)
        self.directive_pub.publish(msg)


async def websocket_client_loop(
    node: SIModule01Bridge, uri: str = "ws://127.0.0.1:8000/ws"
) -> None:
    while rclpy.ok():
        try:
            async with websockets.connect(uri, ping_interval=None) as ws:
                node.get_logger().info(f"Connected to SI Layer Module 01 Stream at {uri}")
                while rclpy.ok():
                    try:
                        payload = await asyncio.wait_for(
                            ws.recv(), timeout=WATCHDOG_TIMEOUT_SEC
                        )
                        node.validate_and_publish(payload)
                    except asyncio.TimeoutError:
                        node.publish_watchdog_hold("Frame dropout > 33.3ms")
        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError):
            node.publish_watchdog_hold("Stream disconnected")
            node.get_logger().warn(
                "Waiting for si-module-01 container stream... Retrying in 1.0s"
            )
            await asyncio.sleep(1.0)


def start_ros_spin(node: SIModule01Bridge) -> None:
    try:
        rclpy.spin(node)
    except Exception:
        pass


def main() -> None:
    rclpy.init()
    node = SIModule01Bridge()

    spin_thread = threading.Thread(target=start_ros_spin, args=(node,), daemon=True)
    spin_thread.start()

    try:
        asyncio.run(websocket_client_loop(node))
    except KeyboardInterrupt:
        node.get_logger().info("Shutting down SI Layer Module 01 Bridge.")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
