"""
Tkinter controller window: live video, connection/telemetry status, keyboard
state, axis bars and the one-button actions.

Tk is used (not OpenCV's waitKey) because it delivers real KeyPress/KeyRelease
events, which continuous multi-key control needs. X11 autorepeat sends
release+press pairs while a key is held, so releases are debounced.
"""

import logging
import signal
import time
import tkinter as tk
from typing import Dict

import cv2

from controller.keyboard import FLIGHT_KEYS, KEY_LABELS, map_inputs_to_axes, normalize_key, normalized
from controller.protocol import DEVICE_TYPE_TC, normalize_axes
from session import ConnectionState, DroneSession

logger = logging.getLogger(__name__)

RELEASE_DEBOUNCE_MS = 40
VIDEO_W, VIDEO_H = 800, 600

BG = "#101418"
PANEL = "#1a2027"
FG = "#d8dee6"
DIM = "#7a8794"
GREEN = "#3ddc84"
AMBER = "#ffc233"
RED = "#ff4d4d"
BLUE = "#4da3ff"

STATE_COLORS = {
    ConnectionState.DISCONNECTED: RED,
    ConnectionState.CONNECTING: AMBER,
    ConnectionState.VIDEO_CONNECTED: BLUE,
    ConnectionState.TELEMETRY_CONNECTED: BLUE,
    ConnectionState.CONNECTED: GREEN,
}

# Command keys (fired once per physical press).
CMD_KEYS = {
    "Return": "control", "t": "takeoff", "l": "land", "space": "estop",
    "v": "camera", "g": "gyro", "p": "power", "h": "fixed_height", "r": "turn180",
    "f": "face_travel",
    "Escape": "quit",
}


class ControllerWindow:
    def __init__(self, session: DroneSession):
        self.s = session
        self.root = tk.Tk()
        self.root.title("fc-controller")
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._pending_release: Dict[str, str] = {}
        self._cmd_down = set()
        self._photo = None
        self._closed = False
        self._build()
        self._bind_keys()
        self._bind_gamepad()

    # ---- layout ---------------------------------------------------------------------

    def _label(self, parent, text="", fg=FG, font=("DejaVu Sans Mono", 10), **kw):
        return tk.Label(parent, text=text, fg=fg, bg=parent["bg"], font=font, anchor="w", justify="left", **kw)

    def _section(self, parent, title):
        frame = tk.Frame(parent, bg=PANEL, padx=8, pady=6)
        frame.pack(fill="x", pady=(0, 6))
        self._label(frame, title, fg=DIM, font=("DejaVu Sans", 9, "bold")).pack(anchor="w")
        return frame

    def _build(self):
        left = tk.Frame(self.root, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        right = tk.Frame(self.root, bg=BG, width=420)
        right.pack(side="right", fill="y", padx=(0, 8), pady=8)

        video_box = tk.Frame(left, bg="black", width=VIDEO_W, height=VIDEO_H)
        video_box.pack_propagate(False)   # size in pixels, independent of label content
        video_box.pack(fill="both", expand=True)
        self.video_label = tk.Label(video_box, bg="black", fg=DIM, font=("DejaVu Sans", 14),
                                    text="waiting for video...")
        self.video_label.pack(fill="both", expand=True)
        self.message = self._label(left, "", fg=AMBER, font=("DejaVu Sans", 11, "bold"))
        self.message.pack(fill="x", pady=(6, 0))

        # One-button actions
        bar = tk.Frame(left, bg=BG)
        bar.pack(fill="x", pady=(6, 0))
        self.btn_control = self._button(bar, "CONTROL OFF  [Enter]", self._do("control"), DIM)
        self._button(bar, "TAKEOFF  [T]", self._do("takeoff"), GREEN)
        self._button(bar, "LAND  [L]", self._do("land"), BLUE)
        self._button(bar, "EMERGENCY STOP  [Space]", self._do("estop"), RED)
        bar2 = tk.Frame(left, bg=BG)
        bar2.pack(fill="x", pady=(4, 0))
        self._button(bar2, "CAMERA SWITCH  [V]", self._do("camera"), FG)
        self._button(bar2, "GYRO CAL  [G]", self._do("gyro"), FG)
        self.btn_power = self._button(bar2, "POWER  [P]", self._do("power"), FG)
        self.btn_fixed = self._button(bar2, "FIXED HEIGHT  [H]", self._do("fixed_height"), FG)
        self._button(bar2, "TURN 180  [R]", self._do("turn180"), FG)
        self.btn_face = self._button(bar2, "FACE TRAVEL  [F]", self._do("face_travel"), DIM)

        # Connection
        sec = self._section(right, "CONNECTION")
        self.lbl_state = self._label(sec, "", font=("DejaVu Sans", 14, "bold"))
        self.lbl_state.pack(anchor="w")
        self.lbl_conn = self._label(sec)
        self.lbl_conn.pack(anchor="w")
        self.lbl_alarm = self._label(sec, "", fg=RED, font=("DejaVu Sans", 12, "bold"), wraplength=400)
        self.lbl_alarm.pack(anchor="w")

        sec = self._section(right, "DEVICE")
        self.lbl_device = self._label(sec)
        self.lbl_device.pack(anchor="w")

        sec = self._section(right, "TELEMETRY  (UDP 7099 downlink)")
        self.lbl_telem = self._label(sec, wraplength=400)
        self.lbl_telem.pack(anchor="w")

        sec = self._section(right, "CAMERA")
        self.lbl_camera = self._label(sec)
        self.lbl_camera.pack(anchor="w")

        sec = self._section(right, "FLIGHT")
        self.lbl_flight = self._label(sec, wraplength=400)
        self.lbl_flight.pack(anchor="w")

        sec = self._section(right, "FACE DIRECTION OF TRAVEL")
        self.lbl_face = self._label(sec, wraplength=400)
        self.lbl_face.pack(anchor="w")

        sec = self._section(right, "GAMEPAD")
        self.lbl_gamepad = self._label(sec, wraplength=400)
        self.lbl_gamepad.pack(anchor="w")

        sec = self._section(right, "KEYBOARD")
        grid = tk.Frame(sec, bg=PANEL)
        grid.pack(anchor="w")
        self.key_labels = {}
        for i, key in enumerate(FLIGHT_KEYS):
            glyph, name = KEY_LABELS[key]
            lbl = tk.Label(grid, text=f"{glyph:<2} {name:<10}", font=("DejaVu Sans Mono", 10),
                           bg=PANEL, fg=DIM, padx=4, pady=1)
            lbl.grid(row=i % 4, column=i // 4, sticky="w")
            self.key_labels[key] = lbl

        sec = self._section(right, "AXES  (next packet, raw byte / normalized)")
        self.axis_canvas = tk.Canvas(sec, width=400, height=96, bg=PANEL, highlightthickness=0)
        self.axis_canvas.pack(anchor="w")

    def _button(self, parent, text, cmd, color):
        b = tk.Button(parent, text=text, command=cmd, takefocus=0, bg=PANEL, fg=color,
                      activebackground="#2a323c", activeforeground=color, relief="flat",
                      font=("DejaVu Sans", 10, "bold"), padx=10, pady=6)
        b.pack(side="left", padx=(0, 6))
        return b

    # ---- keys -----------------------------------------------------------------------

    def _bind_keys(self):
        self.root.bind_all("<KeyPress>", self._on_press)
        self.root.bind_all("<KeyRelease>", self._on_release)
        self.root.bind("<FocusOut>", self._on_focus_out)
        self.root.focus_set()

    def _on_press(self, event):
        key = normalize_key(event.keysym)
        pending = self._pending_release.pop(key, None)
        if pending:
            self.root.after_cancel(pending)   # autorepeat: key never really released
        if key in FLIGHT_KEYS:
            self.s.flight.keyboard.press(key)
        elif key in CMD_KEYS and key not in self._cmd_down:
            self._cmd_down.add(key)
            self._do(CMD_KEYS[key])()
        return "break"

    def _on_release(self, event):
        key = normalize_key(event.keysym)
        if key in self._pending_release:
            self.root.after_cancel(self._pending_release[key])
        self._pending_release[key] = self.root.after(RELEASE_DEBOUNCE_MS, self._finalize_release, key)

    def _finalize_release(self, key):
        self._pending_release.pop(key, None)
        self.s.flight.keyboard.release(key)
        self._cmd_down.discard(key)

    def _bind_gamepad(self):
        pad = self.s.flight.gamepad
        if pad is None:
            return
        # The reader runs in its own thread; Tk work must happen on the main thread.
        pad.set_callbacks(
            on_button=lambda action: self.root.after(0, self._do(action)),
            on_disconnect=lambda: self.root.after(0, self._on_gamepad_lost),
        )

    def _on_gamepad_lost(self):
        # Axes are already neutral (Gamepad clears them on disconnect); make it visible.
        self._flash("GAMEPAD DISCONNECTED - all stick axes returned to neutral")

    def _on_focus_out(self, _event):
        # Losing focus means we will never see the releases: neutralize all axes.
        self.s.flight.keyboard.release_all()
        self._cmd_down.clear()

    # ---- actions ----------------------------------------------------------------------

    def _do(self, action):
        def run():
            f = self.s.flight
            if action == "control":
                msg = f"Control mode {'ON' if f.toggle_control_mode() else 'OFF'}"
            elif action == "takeoff":
                msg = f.takeoff()
            elif action == "land":
                msg = f.land()
            elif action == "estop":
                msg = f.emergency_stop()
            elif action == "gyro":
                msg = f.gyro_calibrate()
            elif action == "camera":
                if not self.s.video or not self.s.video.has_live_frames():
                    msg = "Camera switch ignored: video not active (the app requires isActive())"
                else:
                    msg = self.s.switcher.switch()
            elif action == "power":
                msg = f"Power level {f.state.cycle_power()} (half range {f.state.snapshot().half_len})"
            elif action == "fixed_height":
                msg = f.set_fixed_height(not f.state.fixed_height)
            elif action == "turn180":
                if self.s.video:
                    self.s.video.turn_180 = not self.s.video.turn_180
                    msg = f"Turn 180: {'ON' if self.s.video.turn_180 else 'OFF'}"
                else:
                    msg = "no video"
            elif action == "face_travel":
                ft = f.face_travel
                if ft is None:
                    msg = "Face travel unavailable: it needs measured motion (start with --vio)"
                else:
                    msg = f"Face direction of travel {'ON' if ft.toggle() else 'OFF'}"
            elif action == "quit":
                self.close()
                return
            else:
                msg = action
            self._flash(msg)
        return run

    def _flash(self, msg):
        logger.info(msg)
        self.message.config(text=msg)

    # ---- refresh loops -------------------------------------------------------------

    def _refresh_video(self):
        if self._closed:
            return
        video = self.s.video
        ok, frame, _ = video.read() if video else (False, None, 0.0)
        if ok and video.has_live_frames():
            w = max(self.video_label.winfo_width(), 160)
            h = max(self.video_label.winfo_height(), 120)
            fh, fw = frame.shape[:2]
            scale = min(w / fw, h / fh)
            frame = cv2.resize(frame, (max(1, int(fw * scale)), max(1, int(fh * scale))),
                               interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
            ok_enc, buf = cv2.imencode(".ppm", frame)
            if ok_enc:
                self._photo = tk.PhotoImage(data=buf.tobytes(), format="PPM")
                self.video_label.config(image=self._photo, text="")
        else:
            status = video.status() if video else "video disabled"
            url = video.url if video else ""
            self._photo = None
            self.video_label.config(image="", text=f"NO VIDEO\n{url}\n{status}")
        self.root.after(33, self._refresh_video)

    def _refresh_status(self):
        if self._closed:
            return
        s, f, link = self.s, self.s.flight, self.s.link
        now = time.time()

        state = s.connection_state()
        self.lbl_state.config(text=state.value, fg=STATE_COLORS[state])
        video = s.video
        vtxt = (f"video: {video.status()}  {video.fps():.1f} fps  {video.resolution()[0]}x{video.resolution()[1]}"
                if video else "video: disabled")
        age = f"{now - link.last_rx_time:.1f}s ago" if link.last_rx_time else "never"
        self.lbl_conn.config(text=(
            f"{vtxt}\n"
            f"udp: {'RUNNING' if link.running else 'STOPPED'}  {link.drone_ip}:{link.port}"
            f"  heartbeat 01 01 @1 Hz\n"
            f"telemetry: {link.rx_rate_hz():.1f} Hz  rx={link.rx_count}  last {age}"))

        # The drone stops hearing us the moment the link drops; make that impossible to miss.
        snap_control = f.state.control_mode
        if snap_control and not link.running:
            self.lbl_alarm.config(text="!! LINK DOWN WHILE CONTROL MODE IS ON !!\n"
                                       "the drone is receiving NOTHING from this PC")
        elif snap_control and f.stats.dropped and not f.stats.last_sent_ok:
            self.lbl_alarm.config(text="!! flight packets are being DROPPED !!")
        else:
            self.lbl_alarm.config(text="")

        dtype = link.effective_device_type()
        fmt = "9-byte (TC)" if dtype == DEVICE_TYPE_TC else "21-byte (GL / default)"
        ids = (f"device ID: {link.first_device_id if link.first_device_id is not None else '-'}"
               f"  (latest byte0: {link.last_device_id if link.last_device_id is not None else '-'})")
        self.lbl_device.config(text=(
            f"type: {s.device_summary()}  -> flight packet {fmt}\n{ids}\n"
            f"type changes seen: {link.device_type_changes}"))

        pkt = link.latest_packet()
        if pkt:
            unknown = " ".join(f"b{k}={v}" for k, v in sorted(pkt.unknown_bytes.items())) or "-"
            telem = (f"raw ({pkt.length}B): {pkt.raw_hex}\n"
                     f"byte1 camera reset mode: {pkt.camera_reset_mode}\n"
                     f"byte2: {pkt.remote_trigger_name}\n"
                     f"unknown: {unknown}\n")
        else:
            telem = "no telemetry received\n"
        telem += "battery / voltage: NOT IN PROTOCOL (app never reads them)"
        self.lbl_telem.config(text=telem)

        self.lbl_camera.config(text=(
            f"stream: {video.url if video else '-'}\n"
            f"active: {s.switcher.describe()}\n"
            f"switch reset mode (telemetry byte1): {link.switch_camera_reset}"
            f"{'  SWITCHING...' if s.switcher.is_switching else ''}"))

        snap = f.state.snapshot()
        pulses = ", ".join(f"{k} {v:.1f}s" for k, v in snap.pulse_remaining.items()) or "none"
        st = f.stats
        last = st.last_packet.hex() if st.last_packet else "-"
        self.lbl_flight.config(text=(
            f"control mode: {'ON (20 Hz)' if snap.control_mode else 'OFF (no flight packets)'}\n"
            f"fixed-height: {'ON' if snap.fixed_height else 'OFF'}   power: {snap.power} (±{snap.half_len})\n"
            f"active flags: {pulses}\n"
            f"TX sent={st.sent} dropped={st.dropped}\nlast TX: {last}"))
        self.btn_control.config(text=f"CONTROL {'ON' if snap.control_mode else 'OFF'}  [Enter]",
                                fg=GREEN if snap.control_mode else DIM)
        self.btn_power.config(text=f"POWER {snap.power}  [P]")
        self.btn_fixed.config(text=f"FIXED HEIGHT {'ON' if snap.fixed_height else 'OFF'}  [H]")

        self._refresh_face_travel()

        pad = f.gamepad
        if pad is None:
            self.lbl_gamepad.config(text="disabled (--gamepad to enable)", fg=DIM)
        elif not pad.connected:
            self.lbl_gamepad.config(text="NOT CONNECTED - searching /dev/input/js*\n"
                                         "keyboard control still works", fg=AMBER)
        else:
            ax = pad.axes()
            bars = "  ".join(f"{n[:3].upper()}={ax[n]:+.2f}" for n in ("roll", "pitch", "yaw", "throttle"))
            buttons = ", ".join(str(b) for b in pad.pressed_buttons()) or "-"
            self.lbl_gamepad.config(
                text=f"{pad.status()}\ndeadzone {pad.config.deadzone * 100:.0f}%   "
                     f"{'ACTIVE' if pad.active() else 'centred'}\n{bars}\nbuttons down: {buttons}",
                fg=GREEN if pad.active() else FG)

        held = f.keyboard.held()
        for key, lbl in self.key_labels.items():
            lbl.config(fg=BG if key in held else DIM, bg=GREEN if key in held else PANEL)

        self._draw_axes(held, snap)
        self.root.after(100, self._refresh_status)

    def _refresh_face_travel(self):
        ft = self.s.flight.face_travel
        vio = self.s.vio_client
        if ft is None:
            self.lbl_face.config(text="unavailable - needs measured motion (--vio)", fg=DIM)
            self.btn_face.config(text="FACE TRAVEL n/a  [F]", fg=DIM)
            return
        st = ft.status()
        vio_line = f"VIO: {vio.status()}" if vio else "VIO: -"
        if not ft.enabled:
            self.lbl_face.config(text=f"OFF - yaw is fully manual\n{vio_line}", fg=DIM)
            self.btn_face.config(text="FACE TRAVEL OFF  [F]", fg=DIM)
            return

        def deg(v):
            return "-" if v is None else f"{v:+6.1f}"

        if st.mode.value in ("FAULT",):
            color = RED
        elif st.active:
            color = GREEN
        else:
            color = AMBER
        lines = [f"{st.mode.value}{' - ' + st.reason if st.reason else ''}"]
        if st.active:
            lines.append(f"heading {deg(st.heading_deg)}  travel {deg(st.travel_deg)}  "
                         f"error {deg(st.error_deg)}")
            lines.append(f"speed {st.speed:.2f} m/s   auto-yaw {st.yaw_stick:+.2f}   "
                         f"sticks locked to {deg(st.reference_deg)}")
        else:
            lines.append("sticks behave normally until VIO data is usable")
        lines.append(vio_line)
        self.lbl_face.config(text="\n".join(lines), fg=color)
        self.btn_face.config(text=f"FACE TRAVEL {'ON' if st.active else st.mode.value.split()[0]}  [F]",
                             fg=color)

    def _draw_axes(self, held, snap):
        ft = self.s.flight.face_travel
        last = self.s.flight.stats.last_packet
        if ft is not None and ft.status().active and last is not None:
            # Face travel is stateful (filters, slew limit), so never re-run it for a
            # preview: show exactly what the flight loop last transmitted.
            axes = last.axes
        else:
            mapping = map_inputs_to_axes(held, snap.half_len, snap.fixed_height,
                                         self.s.flight.state.manual_throttle, self.s.flight.gamepad_axes())
            axes = normalize_axes(mapping.axes)
        c = self.axis_canvas
        c.delete("all")
        rows = [("ROLL", axes.roll), ("PITCH", axes.pitch), ("THROTTLE", axes.throttle), ("YAW", axes.yaw)]
        x0, x1 = 80, 300
        mid = (x0 + x1) / 2
        for i, (name, value) in enumerate(rows):
            y = 6 + i * 23
            n = normalized(value)
            c.create_text(4, y + 8, text=name, fill=FG, anchor="w", font=("DejaVu Sans Mono", 9))
            c.create_rectangle(x0, y, x1, y + 16, outline=DIM)
            c.create_line(mid, y, mid, y + 16, fill=DIM)
            end = mid + n * (x1 - x0) / 2
            c.create_rectangle(min(mid, end), y + 2, max(mid, end), y + 14,
                               fill=GREEN if n else DIM, outline="")
            c.create_text(x1 + 8, y + 8, text=f"{value:3d}  {n:+.2f}", fill=FG, anchor="w",
                          font=("DejaVu Sans Mono", 9))

    # ---- run / close -------------------------------------------------------------------

    def _poll_signals(self):
        # Tk's C mainloop starves Python signal handlers; a periodic callback lets them run.
        if not self._closed:
            self.root.after(200, self._poll_signals)

    def run(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: self.root.after(0, self.close))
        self._poll_signals()
        self._refresh_video()
        self._refresh_status()
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.close()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.s.flight.keyboard.release_all()   # release keyboard state before stopping
        try:
            self.root.unbind_all("<KeyPress>")
            self.root.unbind_all("<KeyRelease>")
        except tk.TclError:
            pass
        self.s.shutdown()
        self.root.destroy()
