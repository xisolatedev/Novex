# Drone Camera Viewer & Telemetry Tool (CooingDV Protocol)

A modular, lightweight Python RTSP camera viewer and UDP telemetry analysis platform reverse-engineered from the **CooingDV RC++ UFO (v1.9.6)** drone controller application.

---

## 1. Overview & Architecture

This application provides a real-time video pipeline tailored to the low-latency RTSP camera streams emitted by consumer toy and optical-flow drones, alongside a bidirectional UDP telemetry and command channel.

```
camera_stream/
├── main.py                    # Application entry point & CLI parser
├── config.py                  # Dataclass configurations (JSON export/import)
├── camera/
│   ├── stream.py              # CameraStream interface & low-latency RtspCameraStream
│   ├── orientation.py         # 0°, 90°, 180°, 270° rotation & mirror transforms
│   └── manager.py             # Single/Dual camera pipeline orchestrator
├── protocol/
│   ├── constants.py           # Ground-truth ports, command bytes, and trigger codes
│   └── camera_switch.py       # UDP camera switcher ([0x06, 0x01] / [0x06, 0x02])
├── telemetry/
│   ├── model.py               # DroneTelemetryPacket model (Verified vs Unknown fields)
│   ├── parser.py              # 20-byte UDP packet parser
│   ├── receiver.py            # Non-blocking UDP receiver & 1 Hz heartbeat worker
│   └── logger.py              # CSV/JSONL datagram recorder
├── drone/
│   └── state.py               # Thread-safe DroneState & DroneInfo telemetry container
├── ui/
│   ├── viewer.py              # OpenCV display loop & hotkey dispatcher
│   ├── hud.py                 # Top status bar, diagnostics, and standby cards
│   └── telemetry_panel.py     # Live UDP hex dump & decoded telemetry overlay
├── mock/
│   ├── stream.py              # Synthetic video test pattern generator
│   └── telemetry.py           # Simulated drone state for offline testing
├── tests/                     # Unit test suite (10 test cases)
├── requirements.txt           # Minimal dependencies (OpenCV, NumPy)
└── README.md
```

---

## 2. Key Reverse-Engineered Findings

### A. Camera Orientation & 90° Sensor Tilt
* **Source Evidence:** In `thread/MjpegThread.java`, the Android app executed `AppUtils.rotateBitmap(90, bitmap)` on incoming frames unless `WifiIdUtils.isNoRotate(fakeResolutionNumber)` was true (only hardware IDs `94` and `99` do not rotate).
* **Implementation:** `camera/orientation.py` provides exact 90° CW, 180°, and 270° rotations. The default is set to **90° CW** and can be rotated dynamically on the fly with hotkey `[R]`.

### B. Camera Switching Protocol (Single Multiplexed Stream)
* **Physical Reality:** Attempting to open `rtsp://192.168.1.1:7070/webcam_bottom` fails with `461 Unsupported Transport`. The physical drone possesses only **one** hardware RTSP video encoder associated with `rtsp://192.168.1.1:7070/webcam`.
* **Switching Mechanism:** Switching between the Front and Bottom cameras is triggered by sending a 2-byte datagram to **UDP port 7099**:
  * **Front / Primary Camera:** `[0x06, 0x01]`
  * **Bottom / Secondary Camera:** `[0x06, 0x02]`
* **Reconnection Timing:** Telemetry Byte 1 (`switchCameraReset`) indicates the required reset behavior:
  * **Mode 1 (`0x01`):** Immediate reload of the RTSP stream.
  * **Mode 2 (`0x02`):** Stop RTSP playback, wait ~600ms settling delay, then reconnect to `/webcam`.

### C. Downlink UDP Telemetry (Port 7099)
* **Client Registration:** The Android app creates an ephemeral UDP socket and sends a heartbeat datagram `[0x01, 0x01]` at 1 Hz (`HeartBeatTask` in `SocketClient.java`). This registers the client's IP and ephemeral port with the drone.
* **Telemetry Packet (20 Bytes):**
  * **Byte 0 `[VERIFIED]`:** Hardware ID / Fake Resolution code (evaluated by `WifiIdUtils.isGL()`).
  * **Byte 1 `[VERIFIED]`:** Camera switch reset mode (1 = immediate, 2 = 600ms delay).
  * **Byte 2 `[VERIFIED]`:** Remote trigger event (`0x4D` = Photo shutter pressed, `0x58` = Video record pressed, `0x66` = GL sync header).
  * **Byte 3 `[VERIFIED]`:** Photo sequence counter.
  * **Byte 4 `[VERIFIED]`:** Video sequence counter.
  * **Bytes 5..18 `[VERIFIED]`:** Wi-Fi password status flags and 8-character hex password.
  * **Unparsed Bytes `[UNKNOWN]`:** Unused bytes are isolated into `unknown_bytes` and presented in raw hex.

### D. IMU / Gyro / Sensor Reality
* **CRITICAL FINDING:** The drone **DOES NOT TRANSMIT** roll, pitch, yaw, accelerometer, altitude, or optical-flow coordinates in telemetry to the client.
* In the original Android application, "gravity tilt mode" (`GravityModel.java`) read the **phone's own built-in accelerometer** (`Sensor.TYPE_ACCELEROMETER`). Stationary gyro calibration was triggered by uplink commands from phone to drone.

---

## 3. Installation & Requirements

### Prerequisites
* Linux (or Windows/macOS) with Python 3.8+
* X11 / Wayland display server

```bash
cd camera_stream
pip install -r requirements.txt
```

---

## 4. Usage

### A. Live Drone Streaming & Telemetry
1. Connect your computer's Wi-Fi to the drone's access point (e.g., `WIFIPD_xxxx`).
2. Run the viewer:
```bash
python main.py
```
*(Automatically rotates 90° CW, connects to `rtsp://192.168.1.1:7070/webcam`, and starts UDP telemetry receiver on port 7099)*

### B. Record Raw Telemetry Datagrams to CSV
To capture all incoming 20-byte UDP packets for protocol analysis:
```bash
python main.py --record-telemetry drone_telemetry.csv
```

### C. Show Live Telemetry Overlay on Startup
```bash
python main.py --telemetry-panel
```

### D. Offline Simulation Mode (No Drone Required)
Test rendering, rotation, aspect ratio scaling, and UI overlays without physical hardware:
```bash
python main.py --mock
```

---

## 5. Hotkeys & Interactive Controls

While the viewer window is focused:

| Key | Action | Description |
| :---: | :---: | :--- |
| **`C`** | **Switch Camera** | Sends UDP `[0x06, 0x01]` or `[0x06, 0x02]` to port 7099 and restarts RTSP pipeline. |
| **`R`** | **Cycle Rotation** | Cycles orientation live: `0° -> 90° -> 180° -> 270° -> 0°`. Swaps dimensions without distortion. |
| **`T`** | **Toggle Telemetry Panel** | Displays real-time 20-byte raw hex dump and decoded fields overlay. |
| **`A`** | **Toggle Aspect Mode** | Toggles between `FIT` (letterboxed) and `CROP` (fill canvas). |
| **`H`** | **Toggle HUD** | Toggles diagnostic heads-up display overlay on/off. |
| **`F`** | **Toggle Fullscreen** | Enters/exits fullscreen mode. |
| **`Q` / `ESC`** | **Quit** | Disconnects RTSP, closes UDP telemetry socket, and exits. |

---

## 6. CLI Command-Line Arguments

```bash
usage: main.py [-h] [--url URL] [--rotation {0,90,180,270}] [--drone-ip DRONE_IP]
               [--udp-port UDP_PORT] [--telemetry-panel]
               [--record-telemetry [RECORD_TELEMETRY]] [--no-telemetry]
               [--mock] [--dual] [--width WIDTH] [--height HEIGHT]
               [--aspect-mode {fit,crop}] [--no-hud] [--fullscreen]
               [--config CONFIG] [--verbose]

Options:
  --url, -u            Primary RTSP stream URL (default: rtsp://192.168.1.1:7070/webcam)
  --rotation, -r       Camera rotation angle (0, 90, 180, 270). Default: 90
  --drone-ip           Drone IP address (default: 192.168.1.1)
  --udp-port           Drone UDP telemetry & command port (default: 7099)
  --telemetry-panel, -t Show UDP telemetry inspector overlay on startup
  --record-telemetry   Log incoming 20-byte UDP datagrams to CSV
  --no-telemetry       Disable background UDP receiver and heartbeat
  --mock, -m           Run synthetic video test patterns and mock telemetry
  --aspect-mode, -a    'fit' (letterbox) or 'crop' (fill window)
  --width, --height    Set custom window dimensions
  --verbose, -v        Enable detailed debug logging
```

---

## 7. Running Unit Tests

A comprehensive test suite verifies orientation math, UDP packet parsing, camera switching command generation, and CSV logging:

```bash
python -m unittest discover tests
```

---

## 8. Safety Policy

**Strict Scope Enforcement:**
This application **strictly excludes all flight-control commands** (takeoff, landing, throttle, yaw, pitch, roll, or motor engagement). The UDP channel is used solely for client heartbeat registration (`[0x01, 0x01]`), camera switching (`[0x06, 0x01]` / `[0x06, 0x02]`), and reading downlink telemetry.
