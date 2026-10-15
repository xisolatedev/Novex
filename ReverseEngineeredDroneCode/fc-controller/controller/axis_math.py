"""
Analog axis maths shared by the gamepad and the HUD.

The Android rockers are already proportional; DeviceBLFragment.onMove() computes

    right rocker: controlByte1 = (int)((x / r) * halfLen) + 128     (roll)
                  controlByte2 = (int)((y / r) * halfLen) + 128     (pitch)
    left rocker:  controlTurn        = (int)((x / r) * 127.0f) + 128 (yaw)
                  controlAccelerator = (int)((y / r) * 127.0f) + 128 (throttle)

where x and y are the stick offset from the centre and r is the rocker radius, so
(x / r) is exactly a normalized -1..+1 stick position. A physical stick therefore
maps straight onto the same formula: no new protocol behaviour is invented here.

Java's (int) cast truncates towards zero, and so does Python's int(), so the byte
values match the app for every stick position.
"""

from typing import Tuple

CENTER = 128
LEFT_STICK_HALF = 127      # the 127.0f in onMove for the left rocker


def apply_deadzone(value: float, deadzone: float) -> float:
    """
    Zero out a small band around centre and rescale the rest, so the first movement
    outside the deadzone produces a small output rather than a jump.

    deadzone is a fraction of full travel (0.0 disables it, 0.08 = 8%).
    """
    value = max(-1.0, min(1.0, float(value)))
    if deadzone <= 0.0:
        return value
    deadzone = min(deadzone, 0.95)
    magnitude = abs(value)
    if magnitude <= deadzone:
        return 0.0
    scaled = (magnitude - deadzone) / (1.0 - deadzone)
    return scaled if value > 0 else -scaled


def stick_to_byte(value: float, half_range: int = LEFT_STICK_HALF) -> int:
    """
    Normalized -1..+1 stick position -> control byte, exactly as onMove does:
    (int)(value * half_range) + 128. Centre is 128; full deflection is 128 +/- half_range.

    Clamping to the protocol's 1..255 (and the throttle's 1 -> 0 rule) stays in
    protocol.normalize_axes, so every path through the app shares one clamp.
    """
    return CENTER + int(value * half_range)


def byte_to_normalized(value: int, half_range: int = LEFT_STICK_HALF) -> float:
    """Inverse of stick_to_byte, for display."""
    if half_range <= 0:
        return 0.0
    return max(-1.0, min(1.0, (value - CENTER) / half_range))


def raw_to_normalized(raw: int, full_scale: int = 32767, invert: bool = False) -> float:
    """Linux joystick axis value (-32767..32767) -> -1.0..+1.0."""
    value = max(-1.0, min(1.0, raw / float(full_scale)))
    return -value if invert else value


def combine(keyboard_value: float, gamepad_value: float) -> float:
    """
    One axis, two input devices. The gamepad wins whenever its stick is outside the
    deadzone; otherwise the keyboard's digital value is used. Neither can be silently
    overridden by a centred stick.
    """
    return gamepad_value if gamepad_value != 0.0 else keyboard_value


def describe(value: float, byte_value: int) -> Tuple[str, str]:
    return f"{value:+.2f}", f"{byte_value:3d}"
