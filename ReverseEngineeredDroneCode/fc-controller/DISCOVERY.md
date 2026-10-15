# fc-controller: protocol discovery report

Source: decompiled RC++ UFO 1.9.6 (`cooingdv.rcufo/`, jadx output) and the existing `camera_stream/` Python tool.
All paths below are relative to `cooingdv.rcufo/`. Line numbers are in-file line numbers.

The tags mean:

- **VERIFIED**: read directly in the decompiled source.
- **INFERRED**: a reasoned conclusion that the source does not state outright.
- **UNKNOWN**: not determinable from the source.

Nothing here has been checked against the physical drone yet. The drone was powered off during development.

---

## 1. Flight-control path

```
DeviceBLFragment (RockerView.OnShakeListener.onMove / onClick)
  -> FlyController.setControlByte1/2, setControlAccelerator, setControlTurn, setFastFly/...
  -> FlyController.FlyControlTask.run()      (java.util.Timer, every 50 ms while control mode is on)
  -> SocketClient.debugSend(byte[])           (sendLock)
  -> UdpComm.send() -> SendDataThread queue -> DatagramSocket.send() -> 192.168.1.1:7099
```

| Item | Location | Behaviour | Tag |
|---|---|---|---|
| Loop period | `tools/FlyController.java` L20, L59 `timer.schedule(new FlyControlTask(), 50L, 50L)` | 50 ms (20 Hz), first packet 50 ms after enable | VERIFIED |
| Loop start/stop | `FlyController.setController` L53-70 | on: start timer. off: cancel timer, send `08 01` | VERIFIED |
| Who toggles it | `fragment/DeviceBLFragment.updateModeUI` L1244 | "control mode" tab. The app starts with control mode **off** (`isControlMode = false`, L32) | VERIFIED |
| Initial throttle on enable | `updateModeUI` L1253-1261 | 128 if fixed-height, else 0 | VERIFIED |
| `Config.SEND_COMMAND_INTERVAL = 40` | `socket/Config.java` L21 | not referenced anywhere; the flight timer uses FlyController's own 50 | VERIFIED |

### Packet formats (`FlyController.FlyControlTask.run`, L102-181)

Selected by `if (SocketClient.getInstance().getDeviceType() != 10)` (L149). **VERIFIED**

**TC (deviceType == 10): 9 bytes** (L174-178)
```
03 66 R P T Y F C 99
C = R ^ P ^ T ^ Y ^ F                       (L148)
```
**GL (deviceType != 10, including 0 before any telemetry): 21 bytes** (L168-172)
```
03 66 14 R P T Y F1 F2 00 00 00 00 00 00 00 00 00 00 C 99
C = F1 ^ P ^ R ^ T ^ Y ^ F2                 (0x14 is not included)
```
- `03` prefix: `bArr4[0] = 3` / `bArr2[0] = 3`. **VERIFIED**
- `66` = `CONTROL_VALUES_BYTE0 = 102`, `99` = `CONTROL_VALUES_BYTE7 = 153`, `14` = `Ascii.DC4` (20). **VERIFIED**
- R = `controlByte1`, P = `controlByte2`, T = `controlAccelerator`, Y = `controlTurn`. **VERIFIED**
- R is roll and P is pitch: the right rocker's X axis feeds byte1 and its Y axis feeds byte2 (`onMove` L1006-1033). **VERIFIED** (the mapping); the "roll"/"pitch" names are **INFERRED** from standard Mode-2 layout.

### Flag bytes

| Bit | TC `F` (L104-129) | GL `F1` (L150-162) | GL `F2` (L163-167) |
|---|---|---|---|
| 0 | fastFly (TAKEOFF) | fastFly **or** fastDrop | noHeadMode |
| 1 | fastDrop (LAND) | emergencyStop | fixedHeightMode |
| 2 | emergencyStop | gyroCorrection | - |
| 3 | circleTurnEnd | circleTurnEnd | - |
| 4 | noHeadMode | - | - |
| 5 | fastReturn \|\| unLock (always 0: no setter exists) | - | - |
| 6 | - | gestureMode | - |
| 7 | gyroCorrection | - | - |

All **VERIFIED**. Two decompiler artifacts:

- **Bit 5:** jadx overwrites `r1` right after adding 32 (L121-125). Neither `isFastReturn` nor `isUnLock` has a setter anywhere in the app (checked with grep), so the bit is always 0 in practice. **VERIFIED**
- **Fixed-height in TC packets:** fixed-height is **not** sent in the 9-byte format. It only changes the throttle neutral and how the stick behaves. **VERIFIED**

### Values and clamping (L130-147)
- Neutral 128, min 1, max 255 (`CONTROL_VALUES_*`, L22-24). **VERIFIED**
- Roll, pitch and yaw are clamped to [1, 255]. **VERIFIED**
- Throttle: the only rule is `if (controlAccelerator == 1) controlAccelerator = 0`. Full-down therefore transmits `00`. There is no upper clamp. fc-controller additionally clamps throttle to 0..255, which the stick math never exceeds anyway. **VERIFIED**

### Stick scaling (`DeviceBLFragment.onMove` L984-1075, `RockerView` L295-404)
- Sign convention: `RockerView.getRockerPositionPoint` uses `x = touch.x - center.x` and `y = center.y - touch.y`, so right and up are positive. **VERIFIED**
- Left rocker: `throttle = (y/r)*127 + 128`, `yaw = (x/r)*127 + 128 + yawTrim*4`. **VERIFIED**
- Right rocker: `roll = (x/r)*halfLen + 128 + trim*k`, `pitch = (y/r)*halfLen + 128 + trim*k`. **VERIFIED**
- Power levels (`currPower`, default 4, L179; cycled by the `tab_power` tab, L876): 4 → halfLen 40 (k=2), 9 → 60 (k=3), 14 → 127 (k=4) (`getHalfLen` L1092). **VERIFIED**
- In the `currPower == 14` branch, jadx drops the `+128` on pitch (L1026-1033). This is a duplicated-block artifact. fc-controller uses `+128` like the other branches. **INFERRED**
- Trims default to 0. fc-controller does not expose trims. **VERIFIED** (default)

### Keyboard mapping (fc-controller)
A held key is treated as the matching stick pushed fully to the edge. Values at the default power level 4:

| Key | Byte changed | Value |
|---|---|---|
| W / S | pitch | 168 / 88 (128 ± 40) |
| D / A | roll | 168 / 88 |
| → / ← | yaw | 255 / 1 |
| ↑ / ↓ (fixed-height on) | throttle | 255 / 1 → sent as 0 |
| release | axis | 128 (the stick springs back in fixed-height mode, `RockerView` ACTION_UP L316-323) |

- The values follow from the source formulas. Using full deflection for a digital key is **INFERRED** (a PC design choice).
- Opposite keys cancel each other.
- With fixed-height **off**, the app's throttle stick does not spring back (L324-342). fc-controller ramps a held throttle by 13 per tick instead. That ramp is **INFERRED** (a PC design choice).

Example packets (TC):
```
neutral   03 66 80 80 80 80 00 00 99
W         03 66 80 A8 80 80 00 28 99
W + →     03 66 80 A8 80 FF 00 57 99
↓         03 66 80 80 00 80 00 80 99
```

---

## 2. Device type

| Item | Location | Behaviour | Tag |
|---|---|---|---|
| Constants | `socket/SocketClient.java` L26, L31 | `GL = 2`, `TC = 10` | VERIFIED |
| Initial value | L49 | `mDeviceType = 0`, so the **21-byte** format is used until the first telemetry packet arrives | VERIFIED |
| Detection | `startUdpTask` receive lambda, L213-222 | `WifiIdUtils.isGL(byte0) ? 2 : 10`, evaluated on **every** received packet | VERIFIED |
| isGL | `utils/WifiIdUtils.java` L79 | `90..101`, `103`, `82`, `85`, `88` | VERIFIED |
| Device ID | L223-226 | first byte0 after each video "prepared" ("fake resolution number"), used for resolution and rotation decisions | VERIFIED |
| GL forces fixed-height | `DeviceBLFragment.onReceiver` L1341-1363; `onItemClick` L901-903 | a GL ID switches fixed-height on, and the toggle refuses to change it for GL | VERIFIED |
| Quirk | L216-222 | A packet whose byte0 is not a GL ID (for example 0x66 = 102, which `onReceiver` L1366 handles as a GL sub-packet) switches the type to TC until the next GL-ID packet. fc-controller reproduces this, logs every change, and provides `--device-type` to pin the format. | VERIFIED (code); effect on the real drone UNKNOWN |

---

## 3. TAKEOFF

`view_control_device_take_off` → `DeviceBLFragment.onClick` L604 → `FlyController.setFastFly` L260-277.

- It is **a flag, not a dedicated command.** `isFastFly = true` is ignored if already set, and is cleared after **1000 ms** (`postDelayed`). **VERIFIED**
- For that 1 s, every 50 ms packet carries the flag. That is about 20 packets. **VERIFIED**
- TC: F bit0 → `03 66 80 80 80 80 01 01 99`. **VERIFIED**
- GL: F1 bit0 → `03 66 14 80 80 80 80 01 02 …00 03 99` (F2 = 02 because fixed-height is on). **VERIFIED**
- The FlyCommand strings (`CMD_TAKE_OFF = "0143"`, `CMD_FAST_DROP = "0144"`, `CMD_EMERGENCY_STOP = "0145"`, …) are **never referenced** by any code. They are not the protocol. **VERIFIED** (checked with grep)
- The button is visible only in fixed-height mode (`updateFixHeightUI` L953). **VERIFIED**
- The button appears to sit inside the control-mode layout, but the layout XML is not in the repo. **INFERRED**
- fc-controller accepts takeoff only with control mode on and fixed-height on.

## 4. LAND (one-key landing)

`view_control_device_land` → `onClick` L651-652 → `FlyController.setFastDrop` L283-300.

- Also a 1000 ms flag. TC: F bit1 → `03 66 80 80 80 80 02 02 99`. **VERIFIED**
- **In the GL format, land and takeoff set the same bit** (`i2 = (isFastFly || isFastDrop) ? 1 : 0`). Their packets are byte-identical. **VERIFIED**
- The drone presumably interprets that bit as "take off if landed, land if flying". **INFERRED**
- Land is **not** throttle-down, not control-off (`08 01`), and not emergency stop. Those are separate code paths. **VERIFIED**
- The app has no "return home" feature: `isFastReturn` is never set. **VERIFIED**
- What the drone's firmware does after the flag (descent profile, motor cut on touchdown) is **UNKNOWN**.

## 5. EMERGENCY STOP

`view_control_device_emergency_stop` → `onClick` L634-635 → `FlyController.setEmergencyStop` L306-323.

- A 1000 ms flag. TC: F bit2 (0x04) → `03 66 80 80 80 80 04 04 99`. GL: F1 bit1 (0x02) → `… 02 02 … 00 99`. **VERIFIED**
- It differs from land on both formats. **VERIFIED**
- The expected effect (immediate motor stop) is **INFERRED** from the name.
- The app hides this button outside fixed-height mode. fc-controller keeps it available at all times; the packet is the same.

## 6. Control off

`FlyController.setController(false)` L64-69: cancel the timer, then send `08 01` once. **VERIFIED**

What the drone does on `08 01` is **UNKNOWN**; it could be "stop listening to app control" or a hand-off to the RC.

---

## 7. Heartbeat and link lifecycle

| Item | Location | Behaviour | Tag |
|---|---|---|---|
| Packet | `SocketClient.HeartBeatTask` L335-343 | `01 01` | VERIFIED |
| Timing | `startUdpTask` L190-192 | `schedule(task, 0, 1000)`: immediately, then every 1 s | VERIFIED |
| Socket | `UdpComm.createClient` L58-73 | one unbound `DatagramSocket` (ephemeral port) for everything: heartbeat, flight, camera, ACKs, and receive | VERIFIED |
| Start | `onPrepared` L53-62 | the UDP task starts **when RTSP playback is prepared**, unless the prepare completes a camera switch | VERIFIED |
| Stop | player error L173-177 → `cancelUdpTask` L375-392 | cancels the heartbeat and closes the socket (skipped while switching camera); playback restarts after 500 ms (L477-490) | VERIFIED |
| Relation to telemetry | - | The drone presumably learns the client address from the heartbeat and replies to it. | INFERRED |
| Authentication | - | None. Nothing waits for a reply. The "password" feature (L230-331) is about the Wi-Fi password, not control access. | VERIFIED |

fc-controller follows the video-gated start and stop by default. `--udp-independent` or `--no-video` start the link immediately; this is a diagnostic option and deviates from the app. While the link is down, flight ticks continue and are dropped, as in the app.

---

## 8. Telemetry (downlink on the same socket)

- The app's receive buffer is **20 bytes** (`UdpComm.RecvDataThread` L238), so longer datagrams are truncated. fc-controller reads up to 1024 bytes. **VERIFIED**
- **VERIFIED** fields used by the app:
  - byte0: device ID / resolution code (the type is derived from it).
  - byte1: `switchCameraReset`.
  - TC path, length > 4: byte2 `0x4D` with byte3 = photo counter → ACK `09 01`; byte2 `0x58` with byte4 = video counter → ACK `09 02`. An ACK is sent only when the counter advances (`onReceiver` L1424-1458).
  - Password status and 8-character password: byte5/6 plus bytes 7-14 (TC); byte8/9 plus bytes 11-18 (GL).
  - GL sub-packets with byte0 = `0x66`: byte1 = 0 → bytes 2 and 9 (1/1 or 2/2), or length 10/15 → byte4 (2 or 4). These only trigger the photo and record tabs (L1366-1422, lambdas L1485-1502): they are remote-control buttons, not flight state.
- **UNKNOWN**: every other byte. fc-controller shows them as `unknown: bN=..` and records raw datagrams with `--record-telemetry`.
- **Battery, voltage, altitude, attitude**: the app never reads any of them (a grep for battery, voltage, altitude or barometer finds nothing outside libraries). **VERIFIED.** fc-controller displays "NOT IN PROTOCOL".

Reused from `camera_stream`, unchanged: `telemetry/parser.py`, `telemetry/model.py`, `telemetry/receiver.py` (socket, heartbeat, receive loop), and `telemetry/logger.py`.

---

## 9. Camera

| Item | Location | Behaviour | Tag |
|---|---|---|---|
| Endpoint | `socket/Config.java` L17 | `rtsp://192.168.1.1:7070/webcam`, the only live-preview URL | VERIFIED |
| Reconnect | `SocketClient.stopAndRestartPlayback` L477-490 | stop, then restart after 500 ms (`Config.RECONNECTION_INTERVAL` L18) | VERIFIED |
| Switch command | `SocketClient.switchCamera` L399-444 | toggles `isSwitchCamera`; sends `06 02` when it becomes true and `06 01` when false; the first press sends `06 02` | VERIFIED |
| Switch reset | L405-443 | telemetry byte1: 2 = stop playback, then restart after 600 ms; 1 = restart immediately; other = no restart | VERIFIED |
| Guard | `onItemClick` L941-943 | switching is allowed only while video is playing (`isActive()`) | VERIFIED |
| Camera names | - | The app never labels which camera is `06 01` or `06 02`. "Front" and "bottom" are **INFERRED**. The camera active at power-on is **UNKNOWN**. | - |
| Other endpoints | - | no `/webcam_bottom` or similar in the source. `camera_stream`'s README reports that the drone rejects it with 461. | VERIFIED (source) |
| Rotation | `thread/MjpegThread.java` L251-263 | rotate 90° only for 240×320, 120×160 and 160×272 frames, and not for IDs 94 or 99 (`isNoRotate`, `WifiIdUtils` L83); rotate 180° when "turn 180" is on | VERIFIED |

`camera_stream`'s `RtspCameraStream` is reused for capture. fc-controller applies the app's rotation rule itself, instead of `camera_stream`'s fixed 90° default.

---

## 10. Altitude and "2 feet"

- **Altitude cannot be commanded or measured through this protocol.** No altitude value exists in either direction. **VERIFIED**
- "Fixed height" is a mode. On GL it is signalled by F2 bit1. On TC it is only the throttle-at-128 convention. In fixed-height mode, throttle 128 means "hold the current height" and ↑/↓ climb or descend. **VERIFIED** (encoding) / **INFERRED** (firmware meaning)
- The sensor behind the height hold is **UNKNOWN**. It is probably a barometer or, on the "FLOW" models, optical flow plus a range sensor (**INFERRED** from the WifiIdUtils constant names).
- Takeoff climbs to a height chosen by the firmware. That height is **UNKNOWN**.
- **A 2-foot start is therefore NOT supported.** fc-controller does not fake it. It starts with fixed-height on (the app's default); TAKEOFF sends the firmware's own takeoff; after that, the pilot adjusts the height by eye with ↑/↓.

---

## 11. Deviations and PC-side choices in fc-controller

- The emergency stop is always available (the app hides it when fixed-height is off).
- Takeoff and land need control mode on. The app shows them in the control layout (INFERRED).
- A held key means full stick deflection. With fixed-height off, throttle ramps by 13 per tick.
- Telemetry counts as "alive" if a packet arrived in the last 2 s. The app has no such timeout.
- `startUdpTask` is idempotent. In the app, a second "prepared" without an error in between would start a second heartbeat timer.
- Focus loss releases all keys, which returns every axis to neutral.
- `--device-type tc|gl` overrides detection.

## 12. Open questions for the first powered test

1. Which device ID does this drone report (byte0)? That determines TC or GL.
2. Does takeoff work with a single 1 s flag pulse, and how high does the drone climb?
3. On GL, does the same bit toggle between takeoff and land?
4. What does `08 01` do while flying?
5. Which physical camera does `06 01` select, and which does `06 02`?
6. Capture the Android app's traffic (for example on a phone hotspot, or with `tcpdump` on the drone's network) and compare it against `--log-packets` output.
