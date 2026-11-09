# SI Module 01: Client Integration Bridge (Symbiotic Intelligence)

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![ROS 2](https://img.shields.io/badge/ROS_2-Humble%20%7C%20Iron%20%7C%20Jazzy-orange.svg)](https://docs.ros.org/)

> ### Why Pre-Motor Telemetry?
> Today's commercial service robots and automated interactive stations are blind to human intent until it is too late. They rely on reactive tripwires, optical proximity triggers, and bounding boxes that only fire after a person has already reached into a handoff zone. By then, mechanical rotor and gearbox inertia (`150–300 ms`) takes over, forcing an awkward hesitation stutter or abrupt pause that disrupts fluid interaction.
>
> Human physical motion does not happen instantaneously. Long before a person reaches toward a counter, kiosk, or handoff tray, their gaze locks onto the target and their motor system initiates a ballistic reach trajectory. This anticipatory kinematic sequence gives downstream controllers **200 to 450 milliseconds** of advance notice.
>
> **Module 01** captures this deterministic kinematic lead time at the edge and translates it into 60Hz advisory machine directives, giving ROS 2 motion planners the foresight to pre-spool actuators and synchronize smoothly rather than freeze.

https://github.com/user-attachments/assets/4a85c5f7-9fec-4a04-ba12-6d8227e73b67

Open-source client integration bridges, wire schemas, and subscriber adapters for **Module 01**—Neuropatic's pre-motor kinematic telemetry engine.

Module 01 executes as an on-premise, compiled edge container (`si-module-01:rc1`) that ingests non-contact optical telemetry to decode human pre-motor kinematic intent 200–450 ms before physical contact or boundary entry occurs. Advisory intent directives are broadcast locally over low-latency WebSockets at 60Hz.

This repository provides client-side bindings to consume that stream directly into physical robot motion planners.

*Architectural Note: Module 01 operates strictly as an advisory pre-motor telemetry layer for trajectory pre-alignment and inertia compensation; downstream motion planners and hardware safety interlocks retain final kinematic arbitration.*

---

## Technical Specification & White Paper

- [The Architecture of Intent: Pre-Motor Kinematic Telemetry for Real-Time Human-Robot Synchronization](./architecture-of-intent-robotics.pdf)

---

## System Architecture

![Module 01 Tech Stack Architecture](Module01%20Tech%20Stack%20Simplified.png)

### Privacy & Compliance (BIPA / GDPR Ready)
Module 01 is engineered with an immutable non-retention protocol. Ingested optical frames are purged from volatile RAM within sub-17 ms execution windows. The engine outputs non-biometric geometric vectors (`gaze_vector`), maintaining **zero biometric identifier storage, facial templates, or cloud egress**, ensuring complete compliance with BIPA and GDPR biometric privacy mandates.

### 60 Hz Telemetry Wire Schema
The container broadcasts continuous deterministic packets at 60Hz over `ws://127.0.0.1:8000/ws`:

```json
{
  "timestamp": 1727280000.1842,
  "frame_id": 4021,
  "gaze_vector": [0.142, -0.051, 0.988],
  "target_xy_normalized": [0.684, 0.412],
  "target_identifier": "HANDOFF_TARGET_A",
  "gaze_locked": true,
  "reach_transit_active": true,
  "intent_directive": "PREEMPTIVE_ORIENT_AND_EXTEND",
  "measured_lead_time_ms": 234.0,
  "confidence": 0.95
}
```

### Telemetry Field Definitions

| Field | Type | Description |
| :--- | :--- | :--- |
| `timestamp` | Float | POSIX epoch timestamp in seconds (100-microsecond resolution) of optical capture. |
| `frame_id` | Integer | Monotonic frame sequence counter for 60Hz watchdog heartbeat tracking (33.3 ms dropout threshold). |
| `gaze_vector` | Float[3] | Normalized `[X, Y, Z]` unit vector of user foveal gaze direction in the sensor optical frame. |
| `target_xy_normalized` | Float[2] | Planar intersection coordinates `[0.0 - 1.0]` mapped to the calibrated workspace homography plane. |
| `target_identifier` | String | Discrete target interaction zone or service handoff coordinate ID (`HANDOFF_TARGET_A`, `NONE`). |
| `gaze_locked` | Boolean | `true` when foveal fixation stability satisfies the pre-motor spatio-temporal dwell filter. |
| `reach_transit_active` | Boolean | `true` when early ballistic limb kinematics confirm active transit toward the fixated target. |
| `intent_directive` | String | Discrete advisory directive (`IDLE`, `PREEMPTIVE_ORIENT_AND_EXTEND`, `HANDOFF_ZONE_OCCUPIED`, `ACTIVE_DECELERATION`, `HOLD`). |
| `measured_lead_time_ms` | Float | Elapsed pre-motor lead-time buffer (ms) clocked from initial ocular fixation lock to physical boundary entry. |
| `confidence` | Float | Multi-signal spatial confidence metric (`0.00` to `1.00`). |

### Repository Structure

```text
si-module-01-bridge/
├── README.md
├── LICENSE
├── architecture-of-intent-robotics.pdf
├── schema/
│   └── telemetry.v1.json
└── robotics/
    ├── mock_telemetry_server.py
    └── si_module_01_bridge.py
```

---

### Quickstart: Robotics (ROS 2)

Validate the 60Hz WebSocket stream and ROS 2 topic bridge locally in under 2 minutes using the synthetic telemetry generator (no physical camera or edge container required). Zero `colcon` compilation is needed.

#### Prerequisites
- Ubuntu 22.04 / 24.04
- ROS 2 (Humble, Iron, or Jazzy) installed and sourced:

```bash
sudo apt update && sudo apt install -y python3-websockets
git clone https://github.com/Neuropatic-Labs/si-module-01-bridge.git
cd si-module-01-bridge
```

#### Terminal 1: Run the Synthetic 60Hz Telemetry Stream
```bash
python3 robotics/mock_telemetry_server.py
```

#### Terminal 2: Launch the ROS 2 Client Bridge Node
```bash
source /opt/ros/$ROS_DISTRO/setup.bash
python3 robotics/si_module_01_bridge.py
```

This node connects to `ws://127.0.0.1:8000/ws`, validates incoming frames against the schema and 33.3 ms watchdog timer, and republishes directives to:  
`/si_layer/module_01/intent_directive`

#### Terminal 3: Inspect Live Directives (Optional)
```bash
source /opt/ros/$ROS_DISTRO/setup.bash
ros2 topic echo /si_layer/module_01/intent_directive
```

---

### Consuming Directives in Your Motion Planner (Reference Pattern)

Downstream ROS 2 nodes do not need to parse raw optical vectors or tune kinematic thresholds. Your motion planner or velocity controller simply subscribes to `/si_layer/module_01/intent_directive` and branches on `intent_directive`:

```python
import json

def on_intent_directive(msg):
    telemetry = json.loads(msg.data)
    directive = telemetry["intent_directive"]
    target = telemetry["target_identifier"]

    if directive == "PREEMPTIVE_ORIENT_AND_EXTEND" and telemetry["confidence"] >= 0.85:
        # 200-450ms head start: Pre-spool joint actuators & orient toward target
        motion_planner.pre_align_to_zone(target, velocity_scale=0.35)

    elif directive == "HANDOFF_ZONE_OCCUPIED":
        # Human hand has entered the exchange envelope: Complete synchronous handoff
        motion_planner.execute_handoff_completion(target)

    elif directive in ("HOLD", "ACTIVE_DECELERATION"):
        # Watchdog dropout or anomalous reach: Dampen velocity and hold position
        motion_planner.dampen_and_hold()
```

---

### On-Premise Evaluation Pilot

Neuropatic Research Laboratories LLC provides qualified commercial and service robotics developers 90-day sandbox licenses:

- **Container Binary:** Pre-compiled, cryptographically signed `si-module-01:rc1` edge container image.
- **On-Site Calibration:** Zero-intrusion optical baseline verification against existing cycle times.
- **Integration Templates:** Production Python/C++ ROS 2 nodes and MoveIt 2 configurations tailored to your runtime.

To initiate an evaluation sandbox:
- **Contact:** pilots@neuropatic.com
- **Web:** [neuropatic.com/api](https://neuropatic.com/api)

---

### License

This client bridge repository is licensed under the Apache License 2.0.  
The underlying Module 01 edge inference runtime (`si-module-01:rc1`) is proprietary software owned by Neuropatic Research Laboratories LLC.
