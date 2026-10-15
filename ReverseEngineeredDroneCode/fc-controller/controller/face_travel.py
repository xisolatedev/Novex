"""
"Face Direction of Travel": yaw the nose towards the measured horizontal velocity.

Nothing in the drone's own protocol reports velocity or heading (DISCOVERY.md §8), so
this feature runs only on MEASURED motion from the Novex VIO (c_prog): its published
`velocity` and `orientation` (both in the VIO "reported" frame, StateEstimator.cpp
L120-122) and the floor normal from GET_FLOOR `reported_plane`, which points from the
floor towards the camera and so gives "up" in that same frame. The VIO world frame is
not gravity aligned (c_prog README), which is why the floor normal is required.

Two pieces work together while the feature is active:

1. Auto-yaw. The horizontal velocity vector (low-pass filtered as a vector, so the
   angle never jumps across +-180) gives the direction of travel; the nose direction
   comes from the VIO orientation. A proportional controller turns the error into a
   yaw stick value, capped and slew-rate limited so it never snaps or jitters, with a
   small alignment deadband. Below a speed threshold (with hysteresis) the yaw is held.

2. Course lock. Roll/pitch commands are relative to the nose, so turning towards
   "right" would make "right" rotate too and the drone would fly in circles. While
   active, the pilot's roll/pitch are therefore interpreted in a fixed frame: the
   heading at the moment the feature became active. Every tick they are rotated by
   the measured heading change, so the drone keeps travelling where the pilot pushed
   while the nose swings round, converging to nose-first flight. Activation is
   bumpless: at that instant the fixed frame IS the body frame.

Throttle is never touched. Manual yaw input always overrides auto-yaw. If the VIO
data is missing, stale, not tracking, or has no floor, the feature suspends and the
sticks behave exactly as with the feature off.

UNKNOWN, and therefore guarded rather than assumed:
  * which physical direction a yaw byte above 128 turns the drone. The app names it
    "right" (INFERRED). A runtime check compares the commanded turn with the measured
    turn and FAULTS the feature off if they disagree (`yaw_sign`).
  * how the VIO camera is mounted on the drone (`nose_axis_camera`).
  * the drone's yaw rate per unit of stick, which is why the loop is closed on the
    measured heading rather than computed open-loop.
"""

import enum
import logging
import math
import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

Vec3 = Tuple[float, float, float]
Quat = Tuple[float, float, float, float]      # x, y, z, w  (the VIO's order)


# --------------------------------------------------------------------------- vector maths

def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def norm(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Vec3) -> Optional[Vec3]:
    n = norm(a)
    return None if n < 1e-9 else scale(a, 1.0 / n)


def project_horizontal(v: Vec3, up: Vec3) -> Vec3:
    return sub(v, scale(up, dot(v, up)))


def quat_rotate(q: Quat, v: Vec3) -> Vec3:
    """Rotate v by unit quaternion q = (x, y, z, w)."""
    x, y, z, w = q
    u = (x, y, z)
    t = scale(cross(u, v), 2.0)          # v' = v + w t + u x t,  t = 2 (u x v)
    ut = cross(u, t)
    return (v[0] + w * t[0] + ut[0], v[1] + w * t[1] + ut[1], v[2] + w * t[2] + ut[2])


def wrap(angle: float) -> float:
    """Wrap to (-pi, pi]."""
    a = math.fmod(angle + math.pi, 2.0 * math.pi)
    if a <= 0.0:
        a += 2.0 * math.pi
    return a - math.pi


class HorizontalFrame:
    """
    A fixed 2-D basis in the horizontal plane: e1 = a reference axis projected flat,
    e2 = up x e1 (to the LEFT in a right-handed frame). Angles are counter-clockwise
    seen from above, so a positive heading change is a turn to the left.
    """

    def __init__(self, up: Vec3):
        self.up = up
        # Reference axis: the reported frame's Z, unless it is too close to vertical,
        # in which case X. Both cannot be near vertical at once.
        flat = project_horizontal((0.0, 0.0, 1.0), up)
        if norm(flat) < 0.2:
            flat = project_horizontal((1.0, 0.0, 0.0), up)
        self.e1 = normalize(flat)
        self.e2 = cross(up, self.e1)

    def coords(self, v: Vec3) -> Tuple[float, float]:
        return dot(v, self.e1), dot(v, self.e2)

    def angle(self, v: Vec3) -> Optional[float]:
        a, b = self.coords(v)
        if math.hypot(a, b) < 1e-6:
            return None
        return math.atan2(b, a)


# --------------------------------------------------------------------------- data types

@dataclass(frozen=True)
class MotionSample:
    """One VIO measurement as received on the PC."""
    received: float                 # PC monotonic clock at receipt
    velocity: Vec3                  # m/s, VIO reported frame
    orientation: Quat               # camera -> reported frame, (x, y, z, w)
    up: Optional[Vec3]              # floor normal (floor -> camera), reported frame
    tracking: bool = True
    lost_frames: int = 0
    floor_confidence: float = 1.0


@dataclass
class FaceTravelConfig:
    nose_axis_camera: Vec3 = (0.0, 0.0, 1.0)   # camera +Z = optical axis = nose (forward camera)
    yaw_sign: int = 1               # +1: stick > 0 (byte > 128) turns clockwise from above (INFERRED)
    start_speed: float = 0.20       # m/s: start turning above this ...
    stop_speed: float = 0.10        # ... hold yaw once below this (hysteresis)
    velocity_tau: float = 0.30      # s, low-pass on the horizontal velocity vector
    up_tau: float = 1.0             # s, low-pass on the floor normal
    gain: float = 1.2               # yaw stick per radian of heading error
    max_yaw: float = 0.5            # cap on the auto-yaw stick (fraction of full)
    slew_rate: float = 1.5          # max change of the yaw stick per second
    align_deadband_deg: float = 6.0 # no correction inside this error
    reverse_margin_deg: float = 20.0
    max_sample_age: float = 0.35    # s; older VIO data counts as stale
    min_floor_confidence: float = 0.2
    sign_check_min_stick: float = 0.2
    sign_check_min_rate_deg: float = 10.0
    sign_check_window: float = 1.0  # s of sustained wrong-way turning before FAULT


class Mode(enum.Enum):
    OFF = "OFF"
    WAITING = "WAITING FOR VIO"     # enabled, no usable data yet
    HOLDING = "HOLDING (hover)"     # active, too slow to have a travel direction
    TURNING = "TURNING"
    ALIGNED = "ALIGNED"
    OVERRIDE = "MANUAL YAW"
    SUSPENDED = "SUSPENDED"
    FAULT = "FAULT"


ACTIVE_MODES = (Mode.HOLDING, Mode.TURNING, Mode.ALIGNED, Mode.OVERRIDE)


@dataclass(frozen=True)
class FaceTravelStatus:
    mode: Mode
    reason: str = ""
    heading_deg: Optional[float] = None
    travel_deg: Optional[float] = None
    reference_deg: Optional[float] = None
    error_deg: Optional[float] = None
    speed: float = 0.0
    yaw_stick: float = 0.0

    @property
    def active(self) -> bool:
        return self.mode in ACTIVE_MODES


# --------------------------------------------------------------------------- controller

class FaceTravel:
    def __init__(self, motion_source: Callable[[], Optional[MotionSample]],
                 config: Optional[FaceTravelConfig] = None,
                 clock: Callable[[], float] = time.monotonic,
                 on_mode_change: Optional[Callable[[Mode, str], None]] = None):
        self.config = config or FaceTravelConfig()
        self._source = motion_source
        self._clock = clock
        self._on_mode_change = on_mode_change
        self._lock = threading.Lock()
        self._enabled = False
        self._reported: Tuple[Optional[Mode], str] = (None, "")
        self._reset()

    def _reset(self) -> None:
        self._mode = Mode.OFF if not self._enabled else Mode.WAITING
        self._reason = ""
        self._up: Optional[Vec3] = None
        self._vel2 = (0.0, 0.0)
        self._last_sample_time: Optional[float] = None
        self._moving = False
        self._out = 0.0
        self._last_tick: Optional[float] = None
        self._reference: Optional[float] = None
        self._prev_heading: Optional[float] = None
        self._prev_heading_time: Optional[float] = None
        self._prev_error_sign = 0
        self._wrong_way_time = 0.0
        self._status = FaceTravelStatus(self._mode)

    # ---- toggle ----------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            if enabled == self._enabled:
                return
            self._enabled = enabled
            self._reset()
            mode = self._mode
        logger.info("Face direction of travel %s", "ENABLED" if enabled else "DISABLED")
        self._report(mode, "")

    def toggle(self) -> bool:
        self.set_enabled(not self._enabled)
        return self._enabled

    def status(self) -> FaceTravelStatus:
        with self._lock:
            return self._status

    # ---- the per-tick transform ---------------------------------------------------

    def apply(self, inputs: Dict[str, float], now: Optional[float] = None) -> Dict[str, float]:
        """
        inputs: normalized {'roll','pitch','yaw','throttle'} from keyboard/gamepad.
        Returns the values to send. Throttle is always passed through unchanged.
        """
        if not self._enabled:
            return inputs
        now = self._clock() if now is None else now
        with self._lock:
            result = self._apply_locked(dict(inputs), now)
            status = self._status
        self._report(status.mode, status.reason)
        return result

    def _report(self, mode: Mode, reason: str) -> None:
        """Tell the logger about mode transitions only (not every tick)."""
        if (mode, reason) != self._reported:
            self._reported = (mode, reason)
            if self._on_mode_change:
                try:
                    self._on_mode_change(mode, reason)
                except Exception:
                    logger.exception("face travel mode-change handler failed")

    def _suspend(self, inputs, mode: Mode, reason: str):
        if self._mode != mode or self._reason != reason:
            logger.warning("Face travel %s: %s", mode.value, reason)
        self._mode, self._reason = mode, reason
        self._reference = None           # re-captured (bumpless) when data returns
        self._out = 0.0
        self._moving = False
        self._prev_heading = None
        self._wrong_way_time = 0.0
        self._status = FaceTravelStatus(mode, reason)
        return inputs                    # feature-off behaviour: sticks untouched

    def _apply_locked(self, inputs: Dict[str, float], now: float) -> Dict[str, float]:
        cfg = self.config
        dt = 0.05 if self._last_tick is None else max(1e-3, min(0.5, now - self._last_tick))
        self._last_tick = now

        if self._mode == Mode.FAULT:
            return inputs                # latched until the feature is toggled off/on

        sample = self._source()
        if sample is None:
            return self._suspend(inputs, Mode.WAITING, "no VIO data")
        if now - sample.received > cfg.max_sample_age:
            return self._suspend(inputs, Mode.SUSPENDED, f"VIO data stale ({now - sample.received:.2f}s)")
        if not sample.tracking:
            return self._suspend(inputs, Mode.SUSPENDED, "VIO not tracking")
        if sample.lost_frames > 0:
            return self._suspend(inputs, Mode.SUSPENDED, "VIO lost frames (pose carried forward)")
        if sample.up is None or sample.floor_confidence < cfg.min_floor_confidence:
            return self._suspend(inputs, Mode.SUSPENDED, "no floor estimate (up direction unknown)")

        # Up: low-pass the floor normal, renormalize.
        up_new = normalize(sample.up)
        if up_new is None:
            return self._suspend(inputs, Mode.SUSPENDED, "degenerate floor normal")
        if self._up is None:
            self._up = up_new
        else:
            a = 1.0 - math.exp(-dt / cfg.up_tau)
            self._up = normalize(tuple(u + a * (n - u) for u, n in zip(self._up, up_new))) or up_new
        frame = HorizontalFrame(self._up)

        nose = quat_rotate(sample.orientation, cfg.nose_axis_camera)
        heading = frame.angle(project_horizontal(nose, self._up))
        if heading is None or norm(project_horizontal(nose, self._up)) < 0.3:
            return self._suspend(inputs, Mode.SUSPENDED, "nose axis near vertical (check --face-travel-nose)")

        # Travel direction from the measured velocity VECTOR, filtered as a vector.
        vx, vy = frame.coords(project_horizontal(sample.velocity, self._up))
        if self._last_sample_time is None:
            self._vel2 = (vx, vy)
        elif sample.received != self._last_sample_time:
            a = 1.0 - math.exp(-dt / cfg.velocity_tau)
            self._vel2 = (self._vel2[0] + a * (vx - self._vel2[0]),
                          self._vel2[1] + a * (vy - self._vel2[1]))
        self._last_sample_time = sample.received
        speed = math.hypot(*self._vel2)
        travel = math.atan2(self._vel2[1], self._vel2[0]) if speed > 1e-6 else None

        # Bumpless (re)activation: the fixed stick frame starts equal to the body frame.
        if self._reference is None:
            self._reference = heading
            self._prev_error_sign = 0
            logger.info("Face travel active: course locked to heading %.1f deg", math.degrees(heading))

        # Speed hysteresis: hovering or drifting slowly keeps the current yaw.
        if self._moving and speed < cfg.stop_speed:
            self._moving = False
        elif not self._moving and speed > cfg.start_speed:
            self._moving = True

        out_inputs = dict(inputs)
        out_inputs.update(self._course_lock(inputs, heading))

        error = None
        manual = inputs.get("yaw", 0.0)
        if manual != 0.0:
            # Pilot always wins; auto-yaw resumes from zero when the stick is released.
            self._out = 0.0
            self._mode = Mode.OVERRIDE
            self._prev_error_sign = 0
            out_inputs["yaw"] = manual
        else:
            target = 0.0
            if self._moving and travel is not None:
                error = wrap(travel - heading)
                error = self._keep_turn_direction(error)
                if abs(error) <= math.radians(cfg.align_deadband_deg):
                    self._mode = Mode.ALIGNED
                else:
                    # Positive error = travel is to the LEFT (counter-clockwise).
                    u = max(-cfg.max_yaw, min(cfg.max_yaw, cfg.gain * error))
                    target = -cfg.yaw_sign * u
                    self._mode = Mode.TURNING
            else:
                self._mode = Mode.HOLDING
                self._prev_error_sign = 0
            step = cfg.slew_rate * dt
            self._out += max(-step, min(step, target - self._out))
            if abs(self._out) < 1e-4:
                self._out = 0.0
            out_inputs["yaw"] = self._out
            if self._sign_check(heading, now, dt):
                return inputs

        out_inputs["throttle"] = inputs.get("throttle", 0.0)   # never modified
        self._reason = ""
        self._status = FaceTravelStatus(
            self._mode, "", math.degrees(heading),
            None if travel is None else math.degrees(travel),
            math.degrees(self._reference), None if error is None else math.degrees(error),
            speed, out_inputs["yaw"])
        return out_inputs

    def _keep_turn_direction(self, error: float) -> float:
        """Near 180 degrees, keep turning the way we already are instead of flip-flopping."""
        margin = math.radians(self.config.reverse_margin_deg)
        if abs(error) > math.pi - margin and self._prev_error_sign != 0 \
                and (error > 0) != (self._prev_error_sign > 0):
            error += 2.0 * math.pi * self._prev_error_sign
        self._prev_error_sign = 1 if error > 0 else -1
        return error

    def _course_lock(self, inputs: Dict[str, float], heading: float) -> Dict[str, float]:
        """Rotate the pilot's roll/pitch from the locked frame into the current body frame."""
        forward = inputs.get("pitch", 0.0)
        left = -inputs.get("roll", 0.0)
        magnitude = math.hypot(forward, left)
        if magnitude > 1.0:             # the app's rocker is a circle; keep |stick| <= 1
            forward, left = forward / magnitude, left / magnitude
        delta = wrap(self._reference - heading)   # counter-clockwise
        c, s = math.cos(delta), math.sin(delta)
        f2 = forward * c - left * s
        l2 = forward * s + left * c
        return {"pitch": max(-1.0, min(1.0, f2)), "roll": max(-1.0, min(1.0, -l2))}

    def _sign_check(self, heading: float, now: float, dt: float) -> bool:
        """
        Closed-loop safety: if we command a turn and the measured heading turns the
        other way for `sign_check_window` seconds, the yaw sign is wrong and the loop
        would spin the drone. FAULT (latched) and give the sticks back to the pilot.
        """
        cfg = self.config
        if self._prev_heading is not None and self._prev_heading_time is not None:
            elapsed = now - self._prev_heading_time
            if elapsed > 0:
                rate = wrap(heading - self._prev_heading) / elapsed     # CCW rad/s
                intended_ccw = -cfg.yaw_sign * self._out                # >0 means turning left
                if abs(self._out) >= cfg.sign_check_min_stick and \
                        abs(rate) >= math.radians(cfg.sign_check_min_rate_deg) and \
                        (rate > 0) != (intended_ccw > 0):
                    self._wrong_way_time += elapsed
                else:
                    self._wrong_way_time = max(0.0, self._wrong_way_time - elapsed)
        self._prev_heading, self._prev_heading_time = heading, now
        if self._wrong_way_time >= cfg.sign_check_window:
            self._mode = Mode.FAULT
            self._reason = ("measured turn opposes commanded turn: yaw sign is inverted "
                            "(retry with --face-travel-yaw-sign %d)" % -cfg.yaw_sign)
            self._out = 0.0
            self._status = FaceTravelStatus(Mode.FAULT, self._reason)
            logger.error("Face travel FAULT: %s", self._reason)
            return True
        return False


def with_overrides(config: FaceTravelConfig, **kwargs) -> FaceTravelConfig:
    return replace(config, **{k: v for k, v in kwargs.items() if v is not None})
