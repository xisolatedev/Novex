"""
Controller state mirroring the fields of FlyController and the parts of
DeviceBLFragment that feed it (power level, fixed-height mode).

Timed flags use deadlines on an injectable monotonic clock instead of Android
Handler.postDelayed, so behaviour is deterministic under test.
"""

import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from .protocol import CONTROL_VALUES_DEFAULT, FlightFlags

# FlyController.setFastFly / setFastDrop / setEmergencyStop: postDelayed(..., 1000L)
PULSE_FAST_FLY_S = 1.0
PULSE_FAST_DROP_S = 1.0
PULSE_EMERGENCY_STOP_S = 1.0
# FlyController.setGyroCorrection: postDelayed(..., 2000L)
PULSE_GYRO_CORRECTION_S = 2.0

# DeviceBLFragment.currPower cycles 4 -> 9 -> 14 -> 4 (onItemClick, tab_power); default 4.
# getHalfLen(): 4 -> 40, 9 -> 60, 14 -> 127. Right-stick deflection is (f / r) * halfLen.
POWER_LEVELS = (4, 9, 14)
POWER_HALF_LEN = {4: 40, 9: 60, 14: 127}
DEFAULT_POWER = 4


@dataclass(frozen=True)
class ControllerSnapshot:
    control_mode: bool
    fixed_height: bool
    power: int
    half_len: int
    flags: FlightFlags
    pulse_remaining: Dict[str, float]


class ControllerState:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self.control_mode = False            # FlyController.isControlMode, default false
        # DeviceBLFragment.initFixHeight(): prefs FIX_HEIGHT_SHARE_KEY default TRUE.
        self.fixed_height = True
        self.power = DEFAULT_POWER
        self.no_head = False
        # Held throttle for non-fixed-height mode (controlAccelerator persists between ticks).
        self.manual_throttle = CONTROL_VALUES_DEFAULT
        self._deadlines: Dict[str, float] = {}

    # ---- timed pulses -----------------------------------------------------------

    def _pulse(self, name: str, duration: float) -> bool:
        """``if (isX) return; isX = true; postDelayed(isX = false, duration)``."""
        now = self._clock()
        with self._lock:
            if self._deadlines.get(name, 0.0) > now:
                return False
            self._deadlines[name] = now + duration
            return True

    def fast_fly(self) -> bool:
        return self._pulse("fast_fly", PULSE_FAST_FLY_S)

    def fast_drop(self) -> bool:
        return self._pulse("fast_drop", PULSE_FAST_DROP_S)

    def emergency_stop(self) -> bool:
        return self._pulse("emergency_stop", PULSE_EMERGENCY_STOP_S)

    def gyro_correction(self) -> bool:
        return self._pulse("gyro_correction", PULSE_GYRO_CORRECTION_S)

    # ---- modes -------------------------------------------------------------------

    def set_power(self, power: int) -> None:
        if power not in POWER_HALF_LEN:
            raise ValueError(f"power must be one of {POWER_LEVELS}")
        with self._lock:
            self.power = power

    def cycle_power(self) -> int:
        with self._lock:
            self.power = POWER_LEVELS[(POWER_LEVELS.index(self.power) + 1) % len(POWER_LEVELS)]
            return self.power

    def snapshot(self, now: Optional[float] = None) -> ControllerSnapshot:
        now = self._clock() if now is None else now
        with self._lock:
            active = {k: d - now for k, d in self._deadlines.items() if d > now}
            flags = FlightFlags(
                fast_fly="fast_fly" in active,
                fast_drop="fast_drop" in active,
                emergency_stop="emergency_stop" in active,
                gyro_correction="gyro_correction" in active,
                no_head=self.no_head,
                fixed_height=self.fixed_height,
            )
            return ControllerSnapshot(
                control_mode=self.control_mode,
                fixed_height=self.fixed_height,
                power=self.power,
                half_len=POWER_HALF_LEN[self.power],
                flags=flags,
                pulse_remaining=active,
            )
