# Next-test plan

Purpose: resolve the unknowns left by [DEBUG_REPORT.md](DEBUG_REPORT.md) without another uncontrolled flight.
Work through the phases in order. **Propellers stay off until phase 4.**

Baseline command for every powered phase:

```bash
cd fc-controller
../camera_stream/.venv/bin/python main.py \
    --log-packets logs/test_<phase>.log --log-rx --record-telemetry logs/telemetry_<phase>.csv -v
```

Afterwards, always: `python tools/packet_tools.py analyze logs/test_<phase>.log`

---

## Phase 0 - offline, drone off

No radio involved; confirms the controller builds what we think it builds.

```bash
python main.py --dry-run --log-packets logs/dry.log -v
python tools/packet_tools.py analyze logs/dry.log
python -m unittest              # 83 tests
```

Press Enter, hold each key in turn, then T, L, Space. Expected in the log:

- neutral `03 66 80 80 80 80 00 00 99`
- W → `03 66 80 A8 80 80 00 28 99`, D → `03 66 A8 80 80 80 00 28 99`
- TAKEOFF → `flags=[0x01]`, LAND → `flags=[0x02]`, STOP → `flags=[0x04]`
- `EVENT ACTION REFUSED` if an action is rejected — this is what was invisible last time

**Pass criterion:** every key and button produces the expected bytes, and `analyze` reports 0 bad checksums.

### Phase 0b - gamepad, if one is used

```bash
python tools/gamepad_test.py                 # discover axis/button numbers, transmits nothing
python tools/gamepad_test.py --power 14      # full-scale roll/pitch preview
```

Check before ever flying with the stick:

- centred sticks read exactly `R=128 P=128 T=128 Y=128`
- each stick moves the axis you expect, in the direction you expect (invert in the mapping if not)
- small movements give small offsets, full deflection reaches the ends of the range
- the buttons trigger the intended actions, especially that EMERGENCY STOP is where you expect
- unplug the pad and confirm every axis returns to neutral

---

## Phase 1 - RC transmitter confound (drone on, props OFF)

Unknown being resolved: whether the drone was receiving commands from the physical RC and from the PC
at the same time during the failed flight, and how it arbitrates. **UNKNOWN** in the source; the app has no
concept of the RC.

1. Record the answer for the failed flight: **was the RC transmitter powered on at 08:01 on 2026-09-20?**
   Write it down here; it changes how the whole log is read.
2. Test A — PC only: RC **off**. Connect to drone Wi-Fi, start the controller, enable control mode.
   Note whether the motors arm/spin.
3. Test B — RC only: controller running but control mode **off** (no flight packets). Arm with the RC.
   Confirm normal RC behaviour while our heartbeat and telemetry are active.
4. Test C — both, only if A and B are clean: RC on and idle, then enable PC control mode for ~5 s.
   Observe which one the drone obeys.

**Record for each:** motor behaviour, telemetry rate, any `EVENT` lines.
**Stop immediately** if behaviour differs from test A.

---

## Phase 2 - ground behaviour of throttle 128 (drone on, props OFF)

Unknown: what the firmware does with a neutral fixed-height stream on the ground. This is the most
plausible explanation for the immediate rise, and **the Android app sends exactly the same thing**
(`initFixHeight` default true → throttle 128; `updateModeUI` L1253-1261).

1. **Fixed-height ON (the app's default):**
   `python main.py --log-packets logs/test_fh_on.log -v`
   Enable control mode for ~10 s without touching any key. Watch the motors.
2. **Fixed-height OFF (also source-supported for TC: `updateModeUI` sets throttle 0):**
   `python main.py --no-fixed-height --log-packets logs/test_fh_off.log -v`
   Same 10 s. Expected first packet `03 66 80 80 00 80 00 80 99` (throttle byte `00`).
3. Compare: `python tools/packet_tools.py compare logs/test_fh_on.log logs/test_fh_off.log`
   The only difference must be the throttle byte and checksum.

**What this tells us:** if the motors spin up in case 1 and stay idle in case 2, the immediate rise is
explained, and `--no-fixed-height` becomes the safe way to start. Note that takeoff/land are then refused,
exactly as the app hides those buttons (`updateFixHeightUI` L953).

---

## Phase 3 - Android pcap comparison (drone on, props OFF)

This is the decisive test for any remaining packet-level doubt.

### Capturing the Android app

Pick whichever is available:

- **Rooted phone / Termux:** `tcpdump -i wlan0 -w /sdcard/android.pcap udp port 7099`
- **PC as the capture point:** put the PC on the drone's Wi-Fi and capture in monitor mode, or use a
  laptop hotspot the drone and phone both join, then
  `sudo tcpdump -i <iface> -w android.pcap udp port 7099`
- **Wireshark:** save as **classic pcap**, not pcapng (`File > Save As > Wireshark/tcpdump ... pcap`),
  or convert: `editcap -F pcap in.pcapng out.pcap`

Fly the identical sequence in each app: connect, enable control, 2 s neutral, W for 1 s, takeoff, land,
control off.

### Comparing

```bash
python tools/packet_tools.py analyze android.pcap --port 7099
python tools/packet_tools.py analyze logs/test_pcap.log
python tools/packet_tools.py compare logs/test_pcap.log android.pcap --port 7099
```

**Check specifically:**

- Does Android send anything we do not? (`distinct datagrams only in B`)
- Is Android's neutral packet byte-identical to ours?
- Android's real send interval and heartbeat interval (`flight interval ms`)
- What Android sends in the first second after control mode is enabled
- The exact takeoff packet and how many packets carry the flag

**Pass criterion:** `distinct datagrams only in B` is empty apart from packets we deliberately do not send
(`0A ..` password change), and matching sequences differ in no byte.

---

## Phase 4 - first flight retest (props ON, open space, hand on the RC)

Only after phases 1-3 are clean.

1. Confirm the fix is active: the log must show
   `EVENT LINK: video lost while control mode ON: link KEPT UP (policy=keepalive)` if video drops,
   and the UI must show the red `LINK DOWN` banner if the link ever really goes down.
2. Keep the flight under 30 s. Do **not** press `G` (gyro calibration) while airborne — its in-flight
   effect is **UNKNOWN** and it ran 2.3 s before the link died last time.
3. Watch the KEYBOARD panel to confirm key input is actually registering before trusting the controls.
4. Afterwards: `python tools/packet_tools.py analyze logs/test_flight.log` and check for
   `EVENT VIDEO GAP`, `EVENT VIDEO STATUS`, `LINK DOWN`, and any `DROPPED` packets.

### Abort criteria

- any `DROPPED(link down)` while airborne
- telemetry rate drops to 0 for more than 2 s
- the red LINK DOWN banner appears

---

## Face Direction of Travel bring-up (needs the VIO rig)

Do this only once the Pi + stereo camera is mounted on the drone and the base controller
has passed phases 0-4. Nothing here is verified yet; the feature has only been tested offline.

1. **Connect and check the data, feature OFF.**
   `ssh -N -L 7700:/tmp/novex-vio.sock pi@<pi>` then
   `python main.py --vio tcp://127.0.0.1:7700 --vio-record logs/vio_bench.tsv`.
   The FACE TRAVEL panel must show `tracking=yes` and `floor ok`.
2. **Mounting, by hand, props off.** Enable with `F`. Carry the drone forward nose-first:
   the panel's `heading` must stay constant and `travel` must match it. If travel is off by
   a fixed angle, the `--face-travel-nose` axis is wrong for how the camera is mounted.
3. **Direction logic, by hand.** Carry it sideways to the right: `travel` should read about
   -90 relative to `heading`, and `auto-yaw` should go positive (a yaw byte above 128).
4. **Yaw sign, on the ground, props ON, drone held or tethered, lowest power.** This is the
   one thing only the airframe can tell us. With the feature on, slide it right so it
   commands a turn, and watch which way it tries to rotate. If it turns away from the
   travel direction, the feature FAULTs within ~1 s; rerun with `--face-travel-yaw-sign -1`.
5. **Replay what you recorded**: `python tools/face_travel_replay.py logs/vio_bench.tsv`,
   and confirm there were no unexpected SUSPENDED periods.
6. **First flight with it**: a low, slow hover in open space, feature OFF. Then press F, give
   a short gentle sideways input, and let go. Press F again (or any yaw input) to take over.
   Abort criteria: a FAULT, the nose turning away from the travel direction, or oscillation.

## Diagnosing the video failure itself

`EVENT VIDEO STATUS` and `EVENT VIDEO GAP` lines are now written to the TX log, so the next capture shows
whether the RTSP stream stalled before the drone misbehaved or after. To also capture FFmpeg's own errors:

```bash
OPENCV_LOG_LEVEL=INFO ../camera_stream/.venv/bin/python main.py --log-packets logs/test.log --log-file logs/app.log -v
```

Correlate `logs/app.log` (FFmpeg/OpenCV messages) with the `EVENT` lines in `logs/test.log` by timestamp.

If video proves unreliable while flying, `--no-video` (control only, no RTSP) isolates the control link
completely — useful for judging whether video load is what destabilizes the link.
