"""
Continuous keyboard state -> control bytes.

A held key is the digital equivalent of pushing the matching on-screen rocker
to the edge of its travel. The scaling is DeviceBLFragment.onMove():

  Right rocker (rvHorizontal): controlByte1 = (x / r) * halfLen + 128   (x: right +)
                               controlByte2 = (y / r) * halfLen + 128   (y: up +)
  Left rocker (rvVertical):    controlAccelerator = (y / r) * 127 + 128
                               controlTurn        = (x / r) * 127 + 128

RockerView reports x = touchX - centerX and y = centerY - touchY, so "stick right"
and "stick up" are positive. halfLen comes from the power level (40/60/127).

The app's trim bars (horizontal/vertical adjust) default to 0 and are not exposed.
"""

import threading
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, Iterable, Optional

from .axis_math import LEFT_STICK_HALF, combine, stick_to_byte
from .protocol import CONTROL_VALUES_DEFAULT, Axes

FORWARD, BACKWARD, LEFT, RIGHT = "w", "s", "a", "d"
YAW_LEFT, YAW_RIGHT, ASCEND, DESCEND = "Left", "Right", "Up", "Down"
FLIGHT_KEYS = (FORWARD, BACKWARD, LEFT, RIGHT, YAW_LEFT, YAW_RIGHT, ASCEND, DESCEND)

KEY_LABELS = {
    FORWARD: ("W", "FORWARD"), BACKWARD: ("S", "BACKWARD"),
    LEFT: ("A", "LEFT"), RIGHT: ("D", "RIGHT"),
    YAW_LEFT: ("←", "YAW LEFT"), YAW_RIGHT: ("→", "YAW RIGHT"),
    ASCEND: ("↑", "ASCEND"), DESCEND: ("↓", "DESCEND"),
}

# LEFT_STICK_HALF (= 127, the 127.0f in onMove for rvVertical) comes from axis_math,
# which both the keyboard and the gamepad share.

# Non-fixed-height throttle: the Android left rocker does not spring back vertically
# when fixed-height is off (RockerView.onTouchEvent ACTION_UP keeps y). A key cannot
# "stay" at a position, so UP/DOWN ramp the held throttle instead. The step size is
# a PC-side choice (INFERRED, not from source): full range in ~1 s at 20 Hz.
MANUAL_THROTTLE_STEP = 13


def normalize_key(keysym: str) -> str:
    return keysym.lower() if len(keysym) == 1 else keysym


class KeyboardState:
    """Thread-safe set of currently held flight keys."""

    def __init__(self):
        self._held = set()
        self._lock = threading.Lock()

    def press(self, key: str) -> bool:
        key = normalize_key(key)
        if key not in FLIGHT_KEYS:
            return False
        with self._lock:
            self._held.add(key)
        return True

    def release(self, key: str) -> bool:
        key = normalize_key(key)
        with self._lock:
            if key in self._held:
                self._held.discard(key)
                return True
        return False

    def release_all(self) -> None:
        with self._lock:
            self._held.clear()

    def held(self) -> FrozenSet[str]:
        with self._lock:
            return frozenset(self._held)


def _dir(held: Iterable[str], positive: str, negative: str) -> int:
    return (1 if positive in held else 0) - (1 if negative in held else 0)


@dataclass(frozen=True)
class AxisMapping:
    axes: Axes
    manual_throttle: int   # value to carry to the next tick when fixed-height is off


def keys_to_normalized(held: FrozenSet[str]) -> Dict[str, float]:
    """Held keys -> normalized -1/0/+1 per axis. A key is a stick pushed to the edge."""
    return {
        "roll": float(_dir(held, RIGHT, LEFT)),
        "pitch": float(_dir(held, FORWARD, BACKWARD)),
        "yaw": float(_dir(held, YAW_RIGHT, YAW_LEFT)),
        "throttle": float(_dir(held, ASCEND, DESCEND)),
    }


def map_inputs_to_axes(held: FrozenSet[str], half_len: int, fixed_height: bool,
                       manual_throttle: int = CONTROL_VALUES_DEFAULT,
                       gamepad_axes: Optional[Dict[str, float]] = None,
                       transform: Optional[Callable[[Dict[str, float]], Dict[str, float]]] = None
                       ) -> AxisMapping:
    """
    Keyboard and/or analog stick -> raw FlyController control bytes (pre-normalization).

    Every axis is computed with the app's own proportional formula
    (axis_math.stick_to_byte), so a digital key is simply the +/-1.0 end of the same
    scale and small stick movements produce correspondingly small byte offsets.
    Opposite keys cancel; an analog stick outside its deadzone overrides the keyboard.
    """
    keys = keys_to_normalized(held)
    pad = gamepad_axes or {}
    value = {name: combine(keys[name], pad.get(name, 0.0)) for name in keys}
    if transform is not None:
        # e.g. Face Direction of Travel. It works on normalized stick values, so the
        # byte scaling, clamping and packet format below stay exactly the same.
        value = transform(value)

    roll = stick_to_byte(value["roll"], half_len)
    pitch = stick_to_byte(value["pitch"], half_len)
    yaw = stick_to_byte(value["yaw"], LEFT_STICK_HALF)
    vertical = value["throttle"]
    if fixed_height:
        # Rocker springs back to centre (setFixHeight(true)): 128 = hold altitude.
        throttle = stick_to_byte(vertical, LEFT_STICK_HALF)
        carry = CONTROL_VALUES_DEFAULT
    else:
        # The app's throttle stick does not spring back when fixed-height is off, and a
        # released gamepad stick does, so the stick drives a rate instead of a position.
        # PC-side decision (INFERRED), the same one already made for the keyboard.
        throttle = max(0, min(255, manual_throttle + int(round(MANUAL_THROTTLE_STEP * vertical))))
        carry = throttle
    return AxisMapping(Axes(roll=roll, pitch=pitch, throttle=throttle, yaw=yaw), carry)


def map_keys_to_axes(held: FrozenSet[str], half_len: int, fixed_height: bool,
                     manual_throttle: int = CONTROL_VALUES_DEFAULT) -> AxisMapping:
    """Keyboard-only mapping (kept for callers and tests that predate gamepad support)."""
    return map_inputs_to_axes(held, half_len, fixed_height, manual_throttle)


def normalized(value: int) -> float:
    """Byte value -> [-1, 1] around the 128 neutral, for display."""
    return max(-1.0, min(1.0, (value - CONTROL_VALUES_DEFAULT) / 127.0))
