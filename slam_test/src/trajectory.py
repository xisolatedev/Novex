"""
Pose bookkeeping for the Novex ORB-SLAM3 test.

ORB-SLAM3 hands back Tcw: the transform that takes a point from WORLD
coordinates into CAMERA coordinates. Almost everything a human wants
to look at needs the opposite, Twc, so the conversion happens here
once and in one place.

Coordinate conventions, stated explicitly because getting these wrong
silently produces a plausible-looking but meaningless trajectory:

  Camera frame (ORB-SLAM3, OpenCV):
      +X right, +Y DOWN, +Z forward along the optical axis

  World frame:
      Fixed at the pose where tracking initialised. It is not levelled
      and not gravity-aligned - there is no IMU in this test, so
      "up" is simply whichever way the camera happened to be pointing
      when SLAM started.

  Scale:
      Metric, in metres, and it comes from exactly one place: the
      stereo baseline measured during chessboard calibration. If the
      square size was entered wrongly, every number below is wrong by
      that same factor.
"""

import math
import threading

import numpy as np


def invert_pose(T):
    """Inverse of a 4x4 rigid transform, without a general inverse."""
    R = T[:3, :3]
    t = T[:3, 3]

    out = np.eye(4, dtype=np.float64)
    out[:3, :3] = R.T
    out[:3, 3] = -R.T @ t
    return out


def pose_to_position(Tcw):
    """Camera centre in world coordinates."""
    R = Tcw[:3, :3]
    t = Tcw[:3, 3]
    return -R.T @ t


def rotation_to_euler(R):
    """Roll, pitch, yaw in degrees from a world-from-camera rotation.

    Decomposition order is R = Ry(yaw) @ Rx(pitch) @ Rz(roll), chosen
    so each angle means what you would expect while holding a camera:

        yaw   - turning left / right   (about the camera's Y axis)
        pitch - looking up / down      (about the camera's X axis)
        roll  - tilting the camera     (about the optical axis Z)

    Because the camera Y axis points DOWN, a positive yaw is a turn to
    the right.
    """
    # R[1,2] = -sin(pitch)
    sp = -R[1, 2]
    sp = max(-1.0, min(1.0, float(sp)))
    pitch = math.asin(sp)

    cp = math.cos(pitch)

    if abs(cp) < 1e-6:
        # Gimbal lock: yaw and roll are not separable. Put all of the
        # rotation into yaw and report roll as zero rather than
        # returning noise.
        yaw = math.atan2(-R[2, 0], R[0, 0])
        roll = 0.0
    else:
        yaw = math.atan2(R[0, 2], R[2, 2])
        roll = math.atan2(R[1, 0], R[1, 1])

    return (
        math.degrees(roll),
        math.degrees(pitch),
        math.degrees(yaw),
    )


class Pose:
    """One camera pose, in the form the GUI wants to display."""

    __slots__ = ("Tcw", "Twc", "position", "roll", "pitch", "yaw", "timestamp", "valid")

    def __init__(self, Tcw, timestamp, valid=True):
        self.Tcw = np.asarray(Tcw, dtype=np.float64)
        self.timestamp = timestamp
        self.valid = valid

        self.Twc = invert_pose(self.Tcw)
        self.position = self.Twc[:3, 3].copy()

        self.roll, self.pitch, self.yaw = rotation_to_euler(self.Twc[:3, :3])

    @property
    def x(self):
        return float(self.position[0])

    @property
    def y(self):
        return float(self.position[1])

    @property
    def z(self):
        return float(self.position[2])

    def distance_to(self, other):
        return float(np.linalg.norm(self.position - other.position))


class Trajectory:
    """Thread-safe ring of estimated camera positions.

    Only poses from frames that ORB-SLAM3 actually tracked are added.
    Poses from lost frames are dropped rather than drawn, so a broken
    line in the 3D view is a truthful signal that tracking failed
    there, not a rendering artefact.
    """

    def __init__(self, max_points=20000):
        self.max_points = max_points
        self._lock = threading.Lock()
        self._points = []
        self._breaks = []
        self.total_distance = 0.0
        self._last = None

    def append(self, pose):
        with self._lock:
            if self._last is not None:
                self.total_distance += pose.distance_to(self._last)
            self._points.append(pose.position.copy())
            self._last = pose

            if len(self._points) > self.max_points:
                drop = len(self._points) - self.max_points
                self._points = self._points[drop:]
                self._breaks = [max(0, b - drop) for b in self._breaks if b - drop > 0]

    def mark_break(self):
        """Record that tracking was lost here, so the line is not drawn
        straight across the gap."""
        with self._lock:
            if self._points and (not self._breaks or self._breaks[-1] != len(self._points)):
                self._breaks.append(len(self._points))
            self._last = None

    def snapshot(self):
        with self._lock:
            if not self._points:
                return np.zeros((0, 3), dtype=np.float32), []
            return np.asarray(self._points, dtype=np.float32), list(self._breaks)

    def clear(self):
        with self._lock:
            self._points = []
            self._breaks = []
            self.total_distance = 0.0
            self._last = None

    def __len__(self):
        with self._lock:
            return len(self._points)
