#!/usr/bin/env python3
"""
Neuropatic Research Laboratories LLC - Synthetic Telemetry Replay Server
Streams simulated 60Hz pre-motor optical intent telemetry over WebSocket.
Conforms strictly to schema/telemetry.v1.json.
"""

import asyncio
import json
import math
import time
import websockets

HOST = "127.0.0.1"
PORT = 8000
FRAME_PERIOD = 1.0 / 60.0  # 16.667 ms deterministic tick


async def handler(websocket, *args):
    """Handles incoming WebSocket connections (compatible with websockets v10 through v13+)."""
    print(f"[Mock Server] Client connected from {websocket.remote_address}")
    frame_id = 4000
    start_time = time.perf_counter()
    next_frame_time = start_time

    try:
        while True:
            now = time.perf_counter()
            t = now - start_time
            frame_id += 1

            # Simulate realistic 5.0-second service handoff cycle matching benchmark capture:
            # [0.00s - 2.00s]: IDLE (Ambient visual scanning outside interaction zone)
            # [2.00s - 2.09s]: OCULAR PRE-FETCH (Gaze locks on target; pre-motor clock starts)
            # [2.09s - 2.234s]: BALLISTIC REACH TRANSIT (Hand accelerating toward target)
            # [2.234s - 4.00s]: HANDOFF_ZONE_OCCUPIED (Hand enters zone; clocks 234.0 ms lead time)
            # [4.00s - 5.00s]: HOLD (Exchange complete / resetting workspace)
            phase = t % 5.0

            if phase < 2.0:
                gaze_locked = False
                reach_transit_active = False
                target_id = "NONE"
                directive = "IDLE"
                lead_time_ms = 0.0
                confidence = 0.42
            elif phase < 2.09:
                gaze_locked = True
                reach_transit_active = False
                target_id = "HANDOFF_TARGET_A"
                directive = "PREEMPTIVE_ORIENT_AND_EXTEND"
                lead_time_ms = round((phase - 2.0) * 1000.0, 1)
                confidence = 0.92
            elif phase < 2.234:
                gaze_locked = True
                reach_transit_active = True
                target_id = "HANDOFF_TARGET_A"
                directive = "PREEMPTIVE_ORIENT_AND_EXTEND"
                lead_time_ms = round((phase - 2.0) * 1000.0, 1)
                confidence = 0.95
            elif phase < 4.0:
                gaze_locked = True
                reach_transit_active = True
                target_id = "HANDOFF_TARGET_A"
                directive = "HANDOFF_ZONE_OCCUPIED"
                lead_time_ms = 234.0
                confidence = 0.98
            else:
                gaze_locked = False
                reach_transit_active = False
                target_id = "HANDOFF_TARGET_A"
                directive = "HOLD"
                lead_time_ms = 234.0
                confidence = 0.85

            # Compute normalized 3D unit gaze vector (||u_g|| = 1.0)
            raw_x = 0.142 + (0.004 if gaze_locked else 0.04) * math.cos(t * 2.0)
            raw_y = -0.051 + (0.004 if gaze_locked else 0.02) * math.sin(t * 2.0)
            raw_z = 0.988
            norm = math.sqrt(raw_x * raw_x + raw_y * raw_y + raw_z * raw_z)

            payload = {
                "timestamp": round(time.time(), 4),
                "frame_id": frame_id,
                "gaze_vector": [
                    round(raw_x / norm, 4),
                    round(raw_y / norm, 4),
                    round(raw_z / norm, 4),
                ],
                "target_xy_normalized": [
                    round(0.684 + (0.002 if gaze_locked else 0.015) * math.sin(t), 3),
                    round(0.412 + (0.002 if gaze_locked else 0.015) * math.cos(t), 3),
                ],
                "target_identifier": target_id,
                "gaze_locked": gaze_locked,
                "reach_transit_active": reach_transit_active,
                "intent_directive": directive,
                "measured_lead_time_ms": lead_time_ms,
                "confidence": confidence,
            }

            await websocket.send(json.dumps(payload))

            # Drift-free 60Hz sleep scheduling
            next_frame_time += FRAME_PERIOD
            sleep_duration = next_frame_time - time.perf_counter()
            if sleep_duration > 0:
                await asyncio.sleep(sleep_duration)
            else:
                next_frame_time = time.perf_counter()

    except websockets.exceptions.ConnectionClosed:
        print("[Mock Server] Client disconnected.")


async def main():
    print(f"[Mock Server] Broadcasting synthetic 60Hz stream on ws://{HOST}:{PORT}/ws")
    async with websockets.serve(handler, HOST, PORT):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Mock Server] Stopped.")
