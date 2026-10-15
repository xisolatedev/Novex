"""
Gamepad / joystick input via the Linux joystick API (/dev/input/js*).

No third-party dependency: the kernel's joydev interface is a stream of 8-byte
events, which is all we need. Events are:

    struct js_event { __u32 time; __s16 value; __u8 type; __u8 number; }

    type 0x01 = button, 0x02 = axis, 0x80 = "initial state" flag ORed in.

Axis values are -32767..32767 and map straight onto the app's proportional rocker
maths (see axis_math). Stick layout follows the Android app's two rockers:

    left stick  -> throttle (Y) and yaw (X)      [rvVertical]
    right stick -> pitch (Y) and roll (X)        [rvHorizontal]

Safety: if the device disappears, every axis returns to neutral immediately and the
session is told, exactly like the keyboard losing focus.
"""

import fcntl
import glob
import json
import logging
import os
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .axis_math import apply_deadzone, raw_to_normalized

logger = logging.getLogger(__name__)

JS_EVENT_SIZE = 8
JS_EVENT_FORMAT = "=IhBB"
JS_EVENT_BUTTON = 0x01
JS_EVENT_AXIS = 0x02
JS_EVENT_INIT = 0x80

DEFAULT_DEADZONE = 0.08

# Defaults follow the usual Xbox-style layout reported by joydev:
#   axis 0 = left X, 1 = left Y, 3 = right X, 4 = right Y (2 and 5 are the triggers).
# Y axes report negative when pushed up, so they are inverted.
# Use tools/gamepad_test.py to discover the numbers for any other pad.
DEFAULT_AXES: Dict[str, Tuple[int, bool]] = {
    "yaw": (0, False),
    "throttle": (1, True),
    "roll": (3, False),
    "pitch": (4, True),
}

# Emergency stop is deliberately NOT on a face button: an accidental press cuts the
# motors. Start toggles control mode; Back is the emergency stop.
DEFAULT_BUTTONS: Dict[str, int] = {
    "takeoff": 0,        # A
    "land": 1,           # B
    "gyro": 3,           # Y
    "camera": 4,         # LB
    "power": 5,          # RB
    "estop": 6,          # Back / Select
    "control": 7,        # Start
}


@dataclass
class GamepadConfig:
    device: Optional[str] = None        # None = auto-detect the first /dev/input/js*
    deadzone: float = DEFAULT_DEADZONE
    axes: Dict[str, Tuple[int, bool]] = field(default_factory=lambda: dict(DEFAULT_AXES))
    buttons: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_BUTTONS))

    @classmethod
    def load(cls, path: str) -> "GamepadConfig":
        """JSON: {"deadzone": 0.08, "axes": {"roll": [3, false], ...}, "buttons": {"takeoff": 0, ...}}"""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        cfg = cls()
        if "device" in data:
            cfg.device = data["device"]
        if "deadzone" in data:
            cfg.deadzone = float(data["deadzone"])
        for name, spec in data.get("axes", {}).items():
            if name not in ("roll", "pitch", "yaw", "throttle"):
                raise ValueError(f"unknown axis {name!r}")
            index, invert = (spec, False) if isinstance(spec, int) else (spec[0], bool(spec[1]))
            cfg.axes[name] = (int(index), invert)
        for name, index in data.get("buttons", {}).items():
            cfg.buttons[name] = int(index)
        return cfg

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"device": self.device, "deadzone": self.deadzone,
                       "axes": {k: [v[0], v[1]] for k, v in self.axes.items()},
                       "buttons": self.buttons}, f, indent=2)


def parse_event(data: bytes) -> Tuple[int, int, int, bool]:
    """(type, number, value, is_init) for one 8-byte joystick event."""
    _time, value, ev_type, number = struct.unpack(JS_EVENT_FORMAT, data)
    return ev_type & ~JS_EVENT_INIT, number, value, bool(ev_type & JS_EVENT_INIT)


def find_device() -> Optional[str]:
    devices = sorted(glob.glob("/dev/input/js*"))
    return devices[0] if devices else None


def device_name(fd: int) -> str:
    """JSIOCGNAME(128); best effort, the device works fine without a name."""
    try:
        buf = bytearray(128)
        fcntl.ioctl(fd, 0x80806A13, buf)     # _IOC_READ, 'j', 0x13, len 128
        return buf.split(b"\x00")[0].decode("utf-8", "replace") or "joystick"
    except Exception:
        return "joystick"


class Gamepad:
    """
    Reads a joystick device in a background thread and exposes normalized,
    deadzoned axis values plus button edges.
    """

    def __init__(self, config: Optional[GamepadConfig] = None,
                 on_button: Optional[Callable[[str], None]] = None,
                 on_disconnect: Optional[Callable[[], None]] = None,
                 reconnect_interval: float = 1.0):
        self.config = config or GamepadConfig()
        self._on_button = on_button
        self._on_disconnect = on_disconnect
        self._reconnect_interval = reconnect_interval

        self._lock = threading.Lock()
        self._raw_axes: Dict[int, int] = {}
        self._buttons: Dict[int, bool] = {}
        self._fd: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self.connected = False
        self.name = "-"
        self.path: Optional[str] = None
        self.events_seen = 0
        self._session_events = 0

    def set_callbacks(self, on_button=None, on_disconnect=None) -> None:
        """Used by the UI, which is created after the gamepad."""
        if on_button is not None:
            self._on_button = on_button
        if on_disconnect is not None:
            self._on_disconnect = on_disconnect

    # ---- lifecycle -------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="GamepadReader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._close()

    def _open(self) -> bool:
        path = self.config.device or find_device()
        if not path or not os.path.exists(path):
            return False
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError as e:
            logger.debug("cannot open %s: %s", path, e)
            return False
        self._fd = fd
        self.path = path
        self.name = device_name(fd)
        self.connected = True
        self._session_events = 0
        with self._lock:
            self._raw_axes.clear()
            self._buttons.clear()
        logger.info("Gamepad connected: %s (%s), deadzone %.0f%%",
                    self.name, path, self.config.deadzone * 100)
        return True

    def _close(self) -> None:
        was_connected = self.connected
        self.connected = False
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        # Safety: a vanished stick must never leave an axis deflected.
        with self._lock:
            self._raw_axes.clear()
        # Only a session that actually delivered events counts as a real disconnect;
        # a device node that opens but never reads must not spam the operator.
        if was_connected and self._session_events:
            logger.error("Gamepad disconnected: all axes returned to neutral")
            if self._on_disconnect:
                try:
                    self._on_disconnect()
                except Exception:
                    logger.exception("gamepad disconnect handler failed")

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._fd is None and not self._open():
                self._stop.wait(self._reconnect_interval)
                continue
            try:
                self._read_available()
            except (OSError, ValueError):
                # The node can still exist after an unplug, or open but fail to read.
                # Back off before retrying so a broken device cannot spin the CPU.
                self._close()
                self._stop.wait(self._reconnect_interval)
                continue
            self._stop.wait(0.005)
        self._close()

    def _read_available(self) -> None:
        assert self._fd is not None
        while True:
            try:
                data = os.read(self._fd, JS_EVENT_SIZE * 32)
            except BlockingIOError:
                return
            if not data:
                raise OSError("joystick device closed")
            for offset in range(0, len(data) - JS_EVENT_SIZE + 1, JS_EVENT_SIZE):
                self.feed(data[offset:offset + JS_EVENT_SIZE])
            if len(data) < JS_EVENT_SIZE * 32:
                return

    # ---- event handling ---------------------------------------------------------

    def feed(self, event: bytes) -> None:
        """Apply one raw event. Public so tests can drive it without hardware."""
        ev_type, number, value, is_init = parse_event(event)
        self.events_seen += 1
        self._session_events += 1
        if ev_type == JS_EVENT_AXIS:
            with self._lock:
                self._raw_axes[number] = value
        elif ev_type == JS_EVENT_BUTTON:
            pressed = bool(value)
            with self._lock:
                was = self._buttons.get(number, False)
                self._buttons[number] = pressed
            # Fire on the press edge only, and never on the initial-state burst.
            if pressed and not was and not is_init and self._on_button:
                action = self.action_for_button(number)
                if action:
                    self._on_button(action)

    def action_for_button(self, number: int) -> Optional[str]:
        for action, index in self.config.buttons.items():
            if index == number:
                return action
        return None

    # ---- output -----------------------------------------------------------------

    def raw_axis(self, index: int) -> int:
        with self._lock:
            return self._raw_axes.get(index, 0)

    def raw_axes(self) -> Dict[int, int]:
        """Every axis the device has reported so far, for discovery and diagnostics."""
        with self._lock:
            return dict(self._raw_axes)

    def axis(self, name: str) -> float:
        """Deadzoned, normalized -1..+1 value for 'roll', 'pitch', 'yaw' or 'throttle'."""
        if not self.connected:
            return 0.0
        spec = self.config.axes.get(name)
        if spec is None:
            return 0.0
        index, invert = spec
        raw = self.raw_axis(index)
        return apply_deadzone(raw_to_normalized(raw, invert=invert), self.config.deadzone)

    def axes(self) -> Dict[str, float]:
        return {name: self.axis(name) for name in ("roll", "pitch", "yaw", "throttle")}

    def active(self) -> bool:
        """True when any stick is outside the deadzone."""
        return any(v != 0.0 for v in self.axes().values())

    def status(self) -> str:
        if not self.connected:
            return "no gamepad"
        return f"{self.name} ({self.path})"

    def pressed_buttons(self) -> List[int]:
        with self._lock:
            return sorted(n for n, down in self._buttons.items() if down)
