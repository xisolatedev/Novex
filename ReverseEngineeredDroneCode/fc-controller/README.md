# fc-controller

PC flight controller for the CooingDV "RC++ UFO" drone. It uses the protocol reverse-engineered from the Android app (`../cooingdv.rcufo`) and reuses the RTSP and telemetry code from `../camera_stream`.

Nothing is simulated:

- Flight, heartbeat and camera commands go to `192.168.1.1:7099/udp`.
- Video comes from `rtsp://192.168.1.1:7070/webcam`.

Every protocol claim, with its source file and line, is in [DISCOVERY.md](DISCOVERY.md).

> **Status:** flown once (2026-09-20) with a failure: the UDP link was torn down mid-flight by our
> video-loss handling, after which the drone received neither control packets nor heartbeat. The flight
> packets themselves were byte-correct. See [DEBUG_REPORT.md](DEBUG_REPORT.md). **Do not fly again before
> the fix in "Exact files/functions to modify" is applied**; use props-off testing.

## Run

```bash
cd fc-controller
../camera_stream/.venv/bin/python main.py                        # the venv already has OpenCV
../camera_stream/.venv/bin/python main.py --log-packets --record-telemetry -v
```

Connect the PC to the drone's Wi-Fi first. On any other network, `192.168.1.1` is usually your router, and packets will go to it.

The startup sequence follows the app:

1. RTSP connects.
2. The UDP link starts: `01 01` heartbeat every 1 s, and the telemetry receiver.
3. The device type is detected from telemetry byte0.
4. You press **Enter** to turn control mode on. Only then are flight packets sent, every 50 ms.

## Controls

| Key | Action | Wire effect |
|---|---|---|
| W / S | forward / back | pitch 128 ± halfLen |
| A / D | left / right | roll 128 ± halfLen |
| ← / → | yaw | yaw 1 / 255 |
| ↑ / ↓ | ascend / descend | throttle 255 / 0 (released: 128 = hold height) |
| Enter | control mode on/off | starts the 20 Hz loop; off sends `08 01` |
| T | TAKEOFF | fastFly flag for 1 s |
| L | LAND | fastDrop flag for 1 s (same bit as takeoff on GL devices) |
| Space | EMERGENCY STOP | emergencyStop flag for 1 s |
| V | camera switch | `06 02` / `06 01`, then RTSP reload per telemetry byte1 |
| G | gyro calibration | gyroCorrection flag for 2 s |
| P | power level 4 → 9 → 14 | halfLen 40 / 60 / 127 |
| H | fixed-height on/off | TC only; GL devices are locked on |
| R | turn video 180° | display only |
| F | Face Direction of Travel on/off | auto-yaw + course lock; needs `--vio` |
| Esc | quit | control off, heartbeat stop, sockets and RTSP closed |

- Keys are tracked continuously, so combinations such as W+D or ↑+→ work.
- Releasing a key returns that axis to 128.
- If the window loses focus, every axis returns to neutral.

## Gamepad / joystick (proportional sticks)

Any pad the kernel exposes as `/dev/input/js*` works (joydev); it is auto-detected at
startup and hot-plugged afterwards. No extra Python package is needed.

The app's own rocker maths is already proportional —
`controlByte1 = (int)((x / r) * halfLen) + 128` in `DeviceBLFragment.onMove` — so a stick
position maps onto it directly: **centre = 128, and the byte moves in proportion to how far
the stick is pushed.** A small movement produces a small offset; the packet format is untouched.

| Stick | Axis | Byte | Range |
|---|---|---|---|
| Left X | yaw | `controlTurn` | 128 ± 127 → 1..255 |
| Left Y | throttle | `controlAccelerator` | 128 ± 127 → 0..255 (the app sends 1 as 0) |
| Right X | roll | `controlByte1` | 128 ± halfLen |
| Right Y | pitch | `controlByte2` | 128 ± halfLen |

**The roll/pitch range depends on the power level**, exactly as in the app (`getHalfLen`):
power 4 → ±40 (88..168), power 9 → ±60, power 14 → ±127 (**1..255**). The app's default is 4,
so for full-scale sticks press `P` twice or start with `--power 14`. Yaw and throttle always
use the full ±127.

Deadzone: values within `--deadzone` of centre read as exactly 0, and the rest is rescaled so
the first movement outside the deadzone is small rather than a jump. Default 8%, `--deadzone 0`
disables it.

Default buttons (Xbox-style numbering; emergency stop is deliberately **not** on a face button):

| Button | Action |
|---|---|
| 0 (A) | TAKEOFF |
| 1 (B) | LAND |
| 3 (Y) | gyro calibration |
| 4 (LB) | camera switch |
| 5 (RB) | power level |
| 6 (Back) | EMERGENCY STOP |
| 7 (Start) | control mode on/off |

Find your pad's numbers and preview the exact bytes it would send (transmits nothing):

```bash
python tools/gamepad_test.py
python tools/gamepad_test.py --power 14 --deadzone 0.10
```

Then write a mapping file and pass `--gamepad-map my_pad.json`:

```json
{
  "deadzone": 0.08,
  "axes": {"yaw": [0, false], "throttle": [1, true], "roll": [3, false], "pitch": [4, true]},
  "buttons": {"takeoff": 0, "land": 1, "gyro": 3, "camera": 4, "power": 5, "estop": 6, "control": 7}
}
```

Each axis is `[index, invert]`; Y axes usually need `true` because pushing up reports negative.

Safety and interaction with the keyboard:

- A stick outside its deadzone overrides the keyboard for that axis; a centred stick leaves the
  keyboard in charge, so both can be used together.
- If the pad is unplugged, every stick axis returns to neutral immediately and the HUD says so.
- With fixed-height **off**, the throttle stick acts as a rate (hold to climb, release to hold
  altitude), because the app's throttle rocker does not spring back but a gamepad stick does.
  This is a PC-side decision, like the keyboard's throttle ramp.

## Face Direction of Travel (`F`)

When on, the nose automatically turns to face the direction the drone is **actually**
moving. Off by default; `F`, the FACE TRAVEL button, `--face-travel`, or a gamepad button
mapped to `face_travel` toggles it.

**It needs measured motion, which the drone does not provide.** The drone's telemetry has
no velocity, heading or IMU data (DISCOVERY.md §8), so the feature runs only on the Novex
VIO (`../c_prog`): its measured `velocity` and `orientation`, plus the floor normal as "up"
(the VIO frame is not gravity-aligned). Without `--vio` the toggle reports "unavailable".

```bash
# on the PC, forward the daemon's socket from the Pi (it is local to the Pi by design)
ssh -N -L 7700:/tmp/novex-vio.sock pi@<pi-address>
python main.py --vio tcp://127.0.0.1:7700 --vio-record logs/vio.tsv
```

What it does while on:

- **Auto-yaw.** The direction of travel comes from the measured horizontal velocity
  vector (filtered as a vector). A proportional controller turns the nose towards it:
  capped (`--face-travel-max-yaw`, default 0.5), slew-rate limited so it never snaps,
  with a 6° alignment deadband so it doesn't jitter. Diagonals are just another angle.
- **Hover holds yaw.** Below 0.20 m/s (`--face-travel-min-speed`) the nose follows;
  it only stops following below half that, so hovering never causes hunting.
- **Course lock.** Roll/pitch are relative to the nose, so turning towards "right" would
  make "right" rotate too, and the drone would fly in circles. While active, your sticks
  are held in the frame the drone had when the feature engaged, and rotated by the
  measured heading each tick. Push right and it keeps travelling right while the nose
  swings round, ending in nose-first flight. Engaging is bumpless.
- **Altitude untouched.** Throttle is passed straight through in every mode.
- **Pilot overrides.** Any manual yaw input takes over; auto-yaw resumes smoothly from zero
  on release.
- **Off means off.** Disabled, the code path is not called at all; packets are
  byte-identical to before (tested).

Safety behaviour:

- It **suspends** (sticks behave normally, amber status) whenever the VIO is disconnected,
  stale (>0.35 s), not tracking, carrying the pose forward (`lost_frames`), or has no floor.
  It re-engages bumplessly when the data returns.
- **Yaw direction is not verified by any source.** The app calls a byte above 128 "right",
  which is INFERRED. The feature compares the turn it commands with the turn the VIO
  measures; if they disagree for 1 s it **FAULTS** off (red) instead of spinning the drone,
  and tells you to retry with `--face-travel-yaw-sign -1`. Toggle F off and on to clear it.

Mounting: `--face-travel-nose X,Y,Z` is the drone's nose in VIO camera coordinates
(X right, Y down, Z forward). `0,0,1` (default) for a forward-facing camera; `0,-1,0` for a
downward camera whose image top points at the nose.

Test offline before flying with it: record a session (`--vio-record`) and replay it:

```bash
python tools/face_travel_replay.py logs/vio.tsv --csv logs/replay.csv
```

## Offline packet debugging

Build and log every packet without transmitting anything (no socket is opened):

```bash
python main.py --dry-run --log-packets logs/dry.log -v
```

Inspect and compare packet streams:

```bash
python tools/packet_tools.py analyze logs/tx_packets.log
python tools/packet_tools.py compare logs/pc.log android.pcap --port 7099   # vs a tcpdump of the Android app
python tools/packet_tools.py decode 03 66 80 A8 80 FF 00 57 99
```

`analyze` reports send-interval statistics, flag runs, axis changes, bad checksums and link-down events.
`compare` aligns two streams and prints the differing byte offsets. Inputs may be an fc-controller TX log,
a file of hex lines, or a classic pcap (`tcpdump -w`, not pcapng).

See [DEBUG_REPORT.md](DEBUG_REPORT.md) for the audit of a real flight.

## Options

```
--device-type {auto,tc,gl}   force 9-byte or 21-byte flight packets (default: detect from telemetry)
--udp-independent            start UDP without waiting for video (diagnostic; the app waits)
--no-video                   no RTSP at all (implies --udp-independent)
--power {4,9,14}             initial power level (app default 4; 14 gives full-scale roll/pitch)
--gamepad [DEVICE]           joystick device (default: auto-detect /dev/input/js*)
--no-gamepad                 ignore any joystick
--deadzone FLOAT             stick deadzone as a fraction of full travel (default 0.08, 0 disables)
--gamepad-map FILE           JSON axis/button mapping
--vio ADDRESS                Novex VIO daemon: tcp://host:port or unix:/path (needed for Face Travel)
--vio-record FILE            record VIO replies for offline replay
--face-travel                start with Face Direction of Travel on
--face-travel-nose X,Y,Z     nose axis in VIO camera coordinates (default 0,0,1)
--face-travel-yaw-sign {1,-1} yaw byte > 128 turns clockwise (+1, INFERRED) or not (-1)
--face-travel-max-yaw FLOAT  cap on automatic yaw stick (default 0.5)
--face-travel-min-speed M/S  speed at which the nose starts following (default 0.20)
--no-fixed-height            start with fixed-height off (TC only)
--dry-run                    offline packet debug: build and log packets, transmit nothing
--log-packets [FILE]         log every TX datagram as hex + decoded fields (default logs/tx_packets.log)
--log-changes-only           ... skipping repeats of an identical flight packet
--log-rx                     ... and log received telemetry datagrams too
--record-telemetry [FILE]    raw RX telemetry to CSV (camera_stream TelemetryLogger)
--rtsp-transport {udp,tcp}
-v                           DEBUG logging, including every TX packet
```

Example `--log-packets` entry:

```
2026-09-19T16:34:57.475 TX FLIGHT dev=TC(10) fmt=TC-9 len=9 ok
  03 66 80 A8 80 FF 00 57 99
  roll=128 pitch=168 throttle=128 yaw=255 flags=[0x00] checksum=0x57
```

## Layout

```
main.py              CLI, wiring
session.py           video <-> UDP link coupling (SocketClient onPrepared / cancelUdpTask), connection state, shutdown
_bootstrap.py        puts ../camera_stream on sys.path
controller/
  protocol.py        9-byte / 21-byte packet builders, flags, checksum, clamping (FlyControlTask.run)
  state.py           control mode, fixed-height, power, 1 s / 2 s flag pulses
  keyboard.py        held keys + stick values -> control bytes (DeviceBLFragment.onMove scaling)
  axis_math.py       proportional stick maths, deadzone, keyboard/gamepad combination
  face_travel.py     Face Direction of Travel: auto-yaw from measured velocity, course lock
  gamepad.py         /dev/input/js* reader (stdlib only), deadzone, button mapping, hot-plug
  flight.py          20 Hz loop, takeoff / land / e-stop / gyro, control off
link/
  udp_link.py        one UDP socket: heartbeat, RX, device-type detection, photo/video ACKs
  parser.py          device-type rule on top of camera_stream's parser
  offline.py         --dry-run link: builds and logs packets, opens no socket
  vio_client.py      Novex VIO daemon client (GET_STATE / GET_FLOOR line protocol)
tools/
  packet_tools.py    analyze / compare / decode packet streams (txlog, hex, pcap)
  gamepad_test.py    live joystick readout and packet preview (transmits nothing)
  face_travel_replay.py  replay a recorded VIO session through Face Travel, offline
video/
  stream.py          camera_stream RtspCameraStream + the app's rotation rule
  switch.py          SocketClient.switchCamera semantics
gui/hud.py           Tk window: video, status, keys, axes, buttons
diagnostics/logger.py  logging setup, TX packet log
tests/               unit tests
```

`camera_stream` uses top-level package names such as `camera`, `telemetry` and `ui`. fc-controller therefore uses `video`, `link` and `gui` for its own packages, so both can be imported side by side without copying code.

## Tests

```bash
cd fc-controller
../camera_stream/.venv/bin/python -m unittest -v
```

- The expected packet bytes in the tests are written out by hand from the Java XOR formulas.
- The link tests run the real `DroneLink` against a UDP socket on `127.0.0.1`. They check the heartbeat timing, device-type detection and the shared socket.

## Not supported, because the protocol has no such thing

- Battery or voltage readout.
- Altitude readout, or commanding a specific height such as 2 feet. Takeoff climbs to the firmware's own preset height. See DISCOVERY.md §10.
