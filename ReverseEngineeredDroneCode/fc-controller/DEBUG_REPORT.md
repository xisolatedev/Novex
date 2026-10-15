# FC Controller Debug Report

Audit of `fc-controller/` against the decompiled app in `cooingdv.rcufo/`, using
`DISCOVERY.md` as the authoritative protocol record. Java line numbers are in-file.

The primary evidence is your own flight log, `logs/tx_packets.log`
(2026-09-20T08:01:22, 507 flight packets over 25.3 s).

**Headline: the flight packets were correct. The UDP link was closed mid-flight, 12 s in,
after which the drone received nothing at all — no control packets and no heartbeat.**

---

## Observed behavior

Reported: the drone rose immediately, descended, then stopped responding, resembling a
failsafe or loss of control.

From the log (`python tools/packet_tools.py analyze logs/tx_packets.log`):

| Time (from first packet) | Event |
|---|---|
| 0.000 s | first flight packet, `03 66 80 80 80 80 00 00 99`, device already detected as TC(10) |
| 0.000-25.3 s | **all 507 packets are axis-neutral: R=128 P=128 T=128 Y=128.** No axis ever moved |
| 9.650 s | flags `0x80` (gyro correction) begins |
| 11.650 s | flags return to `0x00` (exactly 2.0 s, matching `setGyroCorrection`) |
| **11.950 s** | **every packet from here on is `DROPPED(link down)` — 269 of them, ~13 s** |
| 25.3 s | `08 01` (control off) also `DROPPED` — the drone never received it |

Facts established:

- **TAKEOFF was never sent.** Flag `0x01` appears nowhere in the log. The only flag used was `0x80` (gyro).
- **No axis input was ever registered** — no W/A/S/D or arrow key reached the controller.
- Timing was exact: mean interval 50.00 ms, max 52 ms, no cumulative drift.
- Zero bad checksums.

## Android reference behavior

| Concern | Android | Source |
|---|---|---|
| Flight loop | `Timer.schedule(FlyControlTask, 50, 50)` | `FlyController.java` L59 |
| Packet | `03 66 R P T Y F C 99` for TC, checksum `R^P^T^Y^F` | `FlyController.java` L148, L174-178 |
| Control on | throttle 128 when fixed-height, else 0; then start the timer | `DeviceBLFragment.updateModeUI` L1253-1263 |
| Fixed-height default | prefs default **true**, and `initStatus()` → `initFixHeight()` runs from `onResume()` | `DeviceBLFragment` L1767-1787, L1826-1829, L496-500 |
| Control off | cancel the timer, send `08 01` | `FlyController.setController` L64-69 |
| Heartbeat | `01 01`, `schedule(task, 0, 1000)`, same socket | `SocketClient` L190-192, L335-343 |
| UDP start | on RTSP "prepared" | `SocketClient` L53-62 |
| UDP stop | on player **error** or **completion** only | `SocketClient` L89-97, L173-177 |
| Player read timeout | **`readtimeout = 5 000 000 µs` (5 s)** | `SocketClient.applyOptionsToVideoView` L154 |
| Complete uplink set | `01 01`, `08 01`, `06 01`/`06 02`, `09 01`/`09 02`, `0A`+8 (password dialog), flight packets | exhaustive grep of every `debugSend` call site |

**No "arm", handshake or authentication packet exists.** The uplink set above is complete; fc-controller
implements all of it except the Wi-Fi password change, which is unrelated to flight. This rules out
"we are missing a command the app sends".

## Packet comparison

Every field was checked against `FlyControlTask.run()` using the actual bytes from your flight, not just the formulas.

| Field | Android | Ours (from the log) | Verdict |
|---|---|---|---|
| Length | 9 (TC) | 9 | match |
| `03` prefix | `bArr4[0] = 3` | `03` | match |
| `66` | `CONTROL_VALUES_BYTE0 = 102` | `66` | match |
| Format choice | `deviceType != 10` → 21-byte | TC(10) → 9-byte, correct for this drone | match |
| R / P / T / Y | 128 neutral | `80 80 80 80` | match |
| Flags | bit7 = gyro | `0x80` for exactly 2.0 s | match |
| Checksum | `R^P^T^Y^F` | `0x00` neutral, `0x80` with gyro; 0 bad in 507 | match |
| `99` terminator | `-103` | `99` | match |
| Throttle `1 → 0` | `if (accel == 1) accel = 0` | implemented, `controller/protocol.py` `normalize_axes` | match (not exercised: throttle never left 128) |
| Byte order / signedness | Java `(byte)` cast | Python `bytes()` 0-255 | match |

**Conclusion: packet construction is not the problem.** Nothing in the transmitted bytes differs from what
the Android app would have produced for the same inputs.

## Socket/lifecycle comparison

| Aspect | Android | Ours | Verdict |
|---|---|---|---|
| Socket | one `DatagramSocket()`, ephemeral port | one socket, `bind(("", 0))` | match |
| Shared by heartbeat + flight | yes (`debugSend`) | yes; proven by `test_heartbeat_continues_while_flight_packets_are_sent_on_same_port` (one source port) | match |
| Multiple sockets | no | no | match |
| Start | RTSP prepared | RTSP frames arriving | match in intent |
| **Stop** | **player error/completion (after a 5 s read timeout)** | **2 s of frame staleness, or ~150 ms of failed reads** | **MISMATCH — see Definite bug 1** |
| Send path | queue + `SendDataThread` | direct `sendto` from the timer thread | not a bug; ours is more deterministic |
| Reconnect | restart playback after 500 ms, re-prepare, restart UDP | RTSP retries every 500 ms; UDP restarts on new frames | match in intent |
| Shutdown order | timer, `08 01`, then socket | same | match |

## Timing comparison

Measured from your flight log: min 48.0, p50 50.0, p95 50.0, max 52.0, mean **50.00 ms**, drift over 25 s: **0 ms**.
No batching, no gaps over 60 ms. Android's `Timer` gives the same nominal 50 ms. **Not a problem.**

## Device-type comparison

- Android: `mDeviceType = 0` initially, then `isGL(byte0) ? 2 : 10` on **every** received packet (`SocketClient` L213-222).
- Ours: identical, in `link/udp_link.py::_on_packet` and `link/parser.py::classify_device_type`.
- In your flight, telemetry arrived **before** control mode, so the very first flight packet was already TC(10) — the correct format.
- `device_type_changes` never triggered a format flip: every packet in the log is `fmt=TC-9`. The "byte0 = 0x66 flips to TC" quirk did not occur (and for a TC drone it cannot cause a wrong format).
- Before any telemetry we use the 21-byte format, exactly like Android with `mDeviceType = 0`. Covered by `test_packet_format_follows_replayed_telemetry`.

**No device-type problem.**

## Fixed-height comparison

| Item | Android | Ours | Verdict |
|---|---|---|---|
| Default | `true` (prefs default, applied on every `onResume`) | `true` (`ControllerState.fixed_height`) | match |
| Throttle at control-on | 128 | 128 | match |
| Key release | rocker springs back to centre → 128 | 128 | match |
| TC encoding | fixed-height is **not** in the 9-byte packet | not encoded | match |
| GL encoding | F2 bit1 | F2 bit1 | match |
| Toggle on GL | blocked entirely (`getDeviceType() == 2` → return) | only blocked when disabling | Possible issue 5 |

**Throttle 128 from the first packet is faithful to Android.** What the firmware does with "hold altitude"
while sitting on the ground is **UNKNOWN**, and is the most plausible source-consistent explanation for the
immediate rise. Android would do exactly the same thing.

## Takeoff/land comparison

- Takeoff = `setFastFly`, a 1 s flag on top of the normal packets; land = `setFastDrop`; stop = `setEmergencyStop`.
  Ours matches, verified by `tests/test_flight.py` (pulse length, no re-trigger extension, distinct flags,
  and takeoff/land sharing the bit on GL).
- **In this flight none of them was used.** Takeoff was never sent, so the rise was *not* caused by a takeoff command.
- Why it was not sent is **UNKNOWN** from the log. Either the key was never pressed, or it was refused
  (control mode off, or fixed-height off) and the refusal was only shown briefly in the GUI.
  Refusals are now written to the TX log (`EVENT ACTION REFUSED`).

---

## Suspected bugs

### Definite bugs

**1. The UDP link is torn down mid-flight by a far more sensitive video-loss trigger than Android's.**

- FILE/FUNCTION/LINE: `fc-controller/session.py::_supervise` L87-95 and `::_on_video_error` L105-121;
  `fc-controller/video/stream.py::has_live_frames` L59-61;
  `camera_stream/camera/stream.py::_capture_worker` L290-291 and `::_open_capture` L213.
- CURRENT BEHAVIOR: video counts as lost after **2.0 s** without a fresh frame; additionally the reader drops
  `is_connected` after **15 consecutive failed reads at 10 ms (~150 ms)** or a 2 s FFmpeg `stimeout`.
  `_on_video_error` then calls `link.stop()`, which **closes the UDP socket and stops the heartbeat**.
- ANDROID BEHAVIOR: the UDP task is cancelled only from the ijkplayer `OnErrorListener` / `OnCompletionListener`
  (`SocketClient` L89-97, L173-177), and the player tolerates **5 s** (`readtimeout = 5 000 000`, L154).
- WHY IT COULD MATTER: this is exactly what happened. At t+11.95 s the log flips to `DROPPED(link down)` for the
  remaining ~13 s. Control packets **and** the 1 Hz heartbeat both stopped, so the drone lost its uplink
  entirely — the textbook trigger for the failsafe descent you saw. The final `08 01` was also dropped.
  A brief RTSP stall, which is likely with a flying drone on congested Wi-Fi, is enough to trigger it.

### Likely bugs

**2. Once the link is down it only returns if video returns, so control cannot recover when it matters most.**

- FILE/FUNCTION/LINE: `fc-controller/session.py::_on_video_prepared` L97-104 (`link.start()` only on new frames).
- CURRENT: no video → no UDP → no control, indefinitely. In your flight it never recovered in 13 s.
- ANDROID: the same coupling exists, but the player restarts after 500 ms and re-prepares, and the
  5 s timeout means a transient stall usually never reaches this state.
- WHY IT MATTERS: after the drone failsafed, its RTSP server most likely stopped too, which locks in the
  outage: no video → no control → cannot recover control to fly it back.

**3. The heartbeat was invisible in the logs, so an uplink outage could not be diagnosed from the evidence.**

- FILE/FUNCTION/LINE: heartbeats were sent inside `camera_stream/telemetry/receiver.py::_heartbeat_loop`,
  bypassing `diagnostics/logger.py::PacketLogger`.
- FIXED in this pass: `link/udp_link.py::_LoggingReceiver` now reports every heartbeat, and link up/down,
  video transitions, control-mode changes and refused actions are written to the same timeline.
  Socket timing and behaviour are unchanged.

### Possible issues

**4. Gyro calibration was triggered 2.3 s before the link died, while the drone was airborne.**

- `logs/tx_packets.log` t+9.65 s to t+11.65 s, flags `0x80` (`FlyController.setGyroCorrection`, 2000 ms).
- In the app this is a pre-flight action. Its effect in flight is **UNKNOWN**; gyro re-calibration while
  airborne could plausibly destabilize or stop the drone. Do not press `G` while flying.
  Whether this contributed to the behaviour is **UNKNOWN**.

**5. `set_fixed_height` only blocks *disabling* on GL devices.**

- FILE/FUNCTION/LINE: `fc-controller/controller/flight.py::set_fixed_height`.
- ANDROID: `DeviceBLFragment.onItemClick` L901-903 returns for `getDeviceType() == 2` in both directions.
- Irrelevant for your TC drone; cosmetic fidelity issue.

**6. No axis input registered during the whole flight.**

- Our GUI key path is verified working (synthetic `event_generate` test produced `03 66 80 A8 80 FF 00 57 99`).
- Possible causes, all **UNKNOWN** for this flight: keys were never pressed; the Tk window did not have
  keyboard focus (X11 sends keys only to the focused window); or focus was lost, which deliberately
  releases all keys (`gui/hud.py::_on_focus_out`).
- The `KEYBOARD` panel highlights held keys; watch it to confirm input is arriving.

**7. Confound: was the physical RC transmitter powered on at the same time?**

- If the RC and the PC both command the drone, the drone receives two conflicting control streams.
  Its arbitration is **UNKNOWN**. This must be controlled for in the next test.

### Not a bug (intentional or verified-matching)

- Packet bytes, length, header, terminator, checksum, clamping, throttle `1 → 0`: verified match.
- 50 ms timing: measured 50.00 ms mean, zero drift.
- Direct `sendto` instead of Android's queue + sender thread: more deterministic, same wire result.
- Device-type detection and the pre-telemetry 21-byte format: verified match.
- Fixed-height default ON with throttle 128: verified match with `initFixHeight` + `updateModeUI`.
- Heartbeat content `01 01`, immediate first send, 1 s interval, shared socket: verified match.
- Keyboard full-deflection values: PC-side decision, documented in DISCOVERY.md §1.

---

## Exact files/functions to modify

### Applied (approved by the operator on 2026-09-20)

1. **`session.py::_on_video_error`** — with `link_policy="keepalive"` (the new default), the UDP link is
   **never closed while control mode is ON**. It logs `EVENT LINK: video lost while control mode ON:
   link KEPT UP` and the UI raises a red banner instead. With control mode off, the app's teardown still
   happens. `--link-policy app` restores the original, app-faithful behaviour.
   *This is a deliberate deviation from the Android app, chosen because `cancelUdpTask()` mid-flight
   removes the drone's entire uplink, including the heartbeat.*
2. **`video/stream.py::DroneVideo.VIDEO_STALE_S`** — staleness threshold raised **2.0 s → 5.0 s**, matching
   `readtimeout = 5 000 000 µs` in `SocketClient.applyOptionsToVideoView` L154.
3. **`session.py::_log_video_diagnostics`** — `EVENT VIDEO STATUS` and `EVENT VIDEO GAP` lines put the RTSP
   state on the packet timeline, so the video failure itself is diagnosable next time.

Locked in by `tests/test_session.py` (link stays up during control mode, app policy still reproducible,
camera switching never tears the link down, threshold equals 5.0 s).

### Still open

4. `session.py::_on_video_prepared` — the link still only *starts* on video. If the link is ever down and
   video never returns, control cannot recover. A periodic retry independent of video is the fix.
   Less urgent now that the link is not torn down during flight.
5. `controller/flight.py::set_fixed_height` — block the GL toggle in both directions (fidelity only).
6. `gui/hud.py` — an audible alarm in addition to the on-screen `LINK DOWN` banner.

### Logging and tooling added in this pass (no flight-behaviour change)

- `diagnostics/logger.py`: `log_heartbeat`, `log_event`, `log_rx`.
- `link/udp_link.py`: `_LoggingReceiver` (heartbeats now appear in the TX log), link up/down events,
  local source port recorded, `--log-rx`.
- `session.py`, `controller/flight.py`: events for video loss, control-mode changes with the initial
  throttle, and refused actions.
- `gui/hud.py`: red `LINK DOWN WHILE CONTROL MODE IS ON` banner.
- `link/offline.py` + `--dry-run`: offline packet debugging, no socket opened.
- `tools/packet_tools.py`: `analyze`, `compare`, `decode` (TX log, hex, or classic pcap).

Already changed in this pass (logging and tooling only, no flight-behaviour change):

- `diagnostics/logger.py`: `log_heartbeat`, `log_event`, `log_rx`.
- `link/udp_link.py`: `_LoggingReceiver`, link up/down events, source port logged, `--log-rx` support.
- `session.py`, `controller/flight.py`: events for video loss, control-mode changes and refused actions.
- `gui/hud.py`: red `LINK DOWN WHILE CONTROL MODE IS ON` banner.
- `link/offline.py` + `--dry-run`: offline packet debugging with no socket.
- `tools/packet_tools.py`: `analyze`, `compare`, `decode`.

## Recommended offline tests

All of these run with the drone switched off.

1. **Dry run, no transmission:**
   `python main.py --dry-run --log-packets logs/dry.log -v`
   Press Enter, then keys, then T/L/Space, and confirm the built packets. No socket is opened.
2. **Analyze any log:**
   `python tools/packet_tools.py analyze logs/dry.log`
   Shows interval statistics, flag runs, axis changes, bad checksums, and link-down events.
3. **Compare against the Android app, byte for byte:**
   Capture the phone's traffic (`tcpdump -i <iface> -w android.pcap udp port 7099`, classic pcap), fly the same
   sequence in each, then:
   `python tools/packet_tools.py compare logs/tx_packets.log android.pcap --port 7099`
   This is the decisive test for any remaining packet-level doubt.
4. **Decode a single packet:** `python tools/packet_tools.py decode 03 66 80 A8 80 FF 00 57 99`
5. **Unit tests:** `python -m unittest` (76 tests, including the heartbeat/flight shared-socket test).

### Recommended first live test (props removed)

1. Remove the propellers.
2. Turn the RC transmitter **off**, to remove the dual-control confound.
3. Run with `--log-packets logs/live.log --log-rx --record-telemetry logs/telemetry.csv -v`.
4. Enable control mode and confirm: motors' response, `LINK UP` in the log, heartbeats every 1 s, telemetry arriving.
5. Press W/A/S/D and the arrows and confirm the axis bytes change in the log and in the KEYBOARD panel.
6. Only then press TAKEOFF, and confirm `flags=[0x01]` actually appears in the log.
7. Watch for any `EVENT VIDEO: LOST` / `EVENT LINK DOWN` line — that is the failure from this report.

## Remaining unknowns

- **UNKNOWN**: why the video stream stopped at t+11.95 s (drone-side, Wi-Fi, or OpenCV).
- **UNKNOWN**: what the drone's firmware does on uplink loss. A failsafe descent is consistent with what you
  saw, but is not proven by any source.
- **UNKNOWN**: what the firmware does with a neutral fixed-height packet stream (throttle 128) while on the
  ground. This is the most plausible explanation for the immediate rise, and Android behaves identically.
- **UNKNOWN**: whether takeoff was pressed and refused, or never pressed. Now recorded going forward.
- **UNKNOWN**: the effect of gyro correction while airborne.
- **UNKNOWN**: how the drone arbitrates between the RC transmitter and the app if both are active.
- **UNKNOWN**: whether the drone requires an active RTSP session for control to be accepted. The app always
  has one, which is the single most important reason not to assume the video coupling is irrelevant.
