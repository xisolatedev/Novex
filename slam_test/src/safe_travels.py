#!/usr/bin/env python3
"""
NOVEX - safe travels: proximity warning layer over the ORB-SLAM3 stereo test.

    python safe_travels.py              live camera, with proximity warnings
    python safe_travels.py --fast       same profile flags as main.py
    python safe_travels.py --replay DIR

This does NOT replace main.py. It imports it, lets it do the entire
start-up (camera, calibration, rectification, ORB-SLAM3, GUI) exactly as
it always has, and adds one thing: a warning marker drawn on top of any
reconstructed 3D feature that is dangerously close to the camera.

How it hooks in without touching main.py
----------------------------------------
main.py resolves the GUI class late, inside main():

    from gui import MainWindow
    window = MainWindow(state)

Because that import happens at call time rather than at module import
time, replacing `gui.MainWindow` before calling main.main() is enough to
substitute a subclass. main.py is not modified, not copied, and its
behaviour is unchanged when it is run on its own.

Where the 3D points come from
-----------------------------
ORB-SLAM3 already triangulates the stereo pair every frame, so nothing
is re-reconstructed here. `SlamResult` (see slam.py) carries, per
keypoint:

    keypoints[i]  - the 2D position in the SAME rectified image the GUI
                    is about to display. This is the projection: the
                    feature was detected in image space, so no second
                    projection implementation is needed or wanted.
    kp_stereo[i]  - True when stereo matching found a correspondence,
                    i.e. when this feature has a real depth at all.
    kp_depth[i]   - the triangulated depth Z in the CAMERA frame,
                    in metres, straight out of ORB-SLAM3's stereo match.

So the coordinate convention is whatever ORB-SLAM3 established:
camera-relative, +Z forward along the optical axis, metres. Nothing here
assumes a world frame or re-derives one.

IMPORTANT - about the metre scale
---------------------------------
Every distance below is only as trustworthy as the stereo baseline in
config/stereo_calibration.yaml, because that baseline is what converts
disparity into metres. At the time of writing that calibration still
reports a baseline wider than the camera module physically is, which
main.py already flags as SCALE UNVERIFIED. This tool re-states that
warning rather than hiding it: if the scale is wrong by a factor, every
threshold here is wrong by the same factor. Treat the warnings as
relative until the baseline is confirmed with a ruler.
"""

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import gui                      # noqa: E402  (patched below)
import main as novex_main       # noqa: E402  (reused wholesale)
from gui import VIEW_RAW        # noqa: E402


# ==============================================================
# Safety configuration
# ==============================================================
# All distances are in METRES, measured from the camera's optical
# centre to the triangulated 3D feature point.
#
#   >= SAFE_DISTANCE        nothing is drawn; the feature is left as a
#                           normal ORB dot.
#   <  WARNING_DISTANCE     amber marker - something is getting close.
#   <  CRITICAL_DISTANCE    red marker - treat as an obstacle.
#
# Points between WARNING_DISTANCE and SAFE_DISTANCE are tracked for the
# heads-up readout but not marked, so the view does not fill with
# clutter the moment anything enters the room.

SAFE_DISTANCE = 2.00        # beyond this, ignore entirely
WARNING_DISTANCE = 1.00     # amber marker below this
CRITICAL_DISTANCE = 0.45    # red marker below this

# Ignore obviously bogus triangulations. A stereo rig with a few-cm
# baseline cannot resolve anything at 2 cm, and depths beyond this are
# not what a proximity check is for.
MIN_VALID_DEPTH = 0.02
MAX_VALID_DEPTH = 40.0

# Cap how many markers are drawn per frame. With an aggressive ORB
# extractor a close-up wall can put thousands of features inside the
# warning band, and drawing all of them would both cost time and hide
# the image underneath. The nearest ones are the ones that matter.
MAX_MARKERS = 120

# BGR, because these are drawn with OpenCV onto the frame itself.
COLOUR_WARNING = (0, 170, 255)     # amber
COLOUR_CRITICAL = (0, 0, 255)      # red
COLOUR_HUD_OK = (120, 220, 120)
COLOUR_HUD_ALERT = (0, 0, 255)

WARNING_RADIUS = 11
CRITICAL_RADIUS = 16


# ==============================================================
# Camera intrinsics, taken from whichever model main.py built
# ==============================================================

class Intrinsics:
    """Back-projection parameters for the live camera model.

    main.py builds either a StereoRectifier (ideal pinhole output) or a
    FisheyeStereoModel (raw Kannala-Brandt images, no rectification).
    Both are read here rather than re-deriving anything, so the numbers
    always match the images ORB-SLAM3 is actually being given.
    """

    def __init__(self, model):
        self.ok = False
        self.fisheye = False
        self.fx = self.fy = self.cx = self.cy = 0.0
        self.K = None
        self.D = None

        if model is None:
            return

        # Rectified path: P1 gives an exact pinhole, so back-projection
        # is the textbook one.
        fx = getattr(model, "fx", None)
        if fx:
            self.fx = float(model.fx)
            self.fy = float(getattr(model, "fy", model.fx))
            self.cx = float(getattr(model, "cx", 0.0))
            self.cy = float(getattr(model, "cy", 0.0))
            self.ok = self.fx > 0 and self.fy > 0
            return

        # Fisheye path: the image is not rectified, so a pixel maps to a
        # ray through the Kannala-Brandt model rather than a pinhole.
        K = getattr(model, "K1", None)
        calib = getattr(model, "calib", None)
        if K is not None and calib is not None:
            self.fisheye = True
            self.K = np.asarray(K, dtype=np.float64)
            self.D = np.asarray(calib.D1, dtype=np.float64).reshape(4, 1)
            self.fx = float(self.K[0, 0])
            self.fy = float(self.K[1, 1])
            self.cx = float(self.K[0, 2])
            self.cy = float(self.K[1, 2])
            self.ok = self.fx > 0 and self.fy > 0

    def describe(self):
        if not self.ok:
            return "unavailable (distances fall back to raw depth)"
        kind = "fisheye (Kannala-Brandt)" if self.fisheye else "rectified pinhole"
        return (f"{kind}  fx {self.fx:.1f}  fy {self.fy:.1f}  "
                f"cx {self.cx:.1f}  cy {self.cy:.1f}")


def distances_from_depth(keypoints, depths, intr):
    """Euclidean distance from the camera centre for each keypoint.

    ORB-SLAM3 reports DEPTH, which is Z along the optical axis - not the
    same thing as distance once a feature is off to the side. A feature
    1 m ahead and a feature 1 m ahead but 40 degrees off-axis have the
    same depth and very different distances, and for a proximity warning
    the distance is what matters.

    So each pixel is back-projected to a unit ray and scaled by its
    depth:

        rectified:  x = (u - cx) / fx,  y = (v - cy) / fy
        fisheye:    the ray comes from cv2.fisheye.undistortPoints,
                    which inverts the Kannala-Brandt model properly

        point_3d = (x * Z, y * Z, Z)
        distance = |point_3d|

    If the intrinsics are unavailable or the maths fails, this falls
    back to the raw depth. Depth is always <= the true distance, so the
    fallback under-reports how far away something is, never over-reports
    it - the safe direction to be wrong in for a warning system.
    """
    depths = np.asarray(depths, dtype=np.float64)

    if not intr.ok or keypoints is None or len(keypoints) != len(depths):
        return depths

    try:
        pts = np.asarray(keypoints, dtype=np.float64).reshape(-1, 1, 2)

        if intr.fisheye:
            # Inverts the fisheye model to normalised camera coordinates.
            norm = cv2.fisheye.undistortPoints(pts, intr.K, intr.D)
            xy = norm.reshape(-1, 2)
        else:
            xy = np.empty((len(depths), 2), dtype=np.float64)
            xy[:, 0] = (pts[:, 0, 0] - intr.cx) / intr.fx
            xy[:, 1] = (pts[:, 0, 1] - intr.cy) / intr.fy

        if not np.isfinite(xy).all():
            return depths

        # |(x*Z, y*Z, Z)| == Z * sqrt(x^2 + y^2 + 1)
        return depths * np.sqrt(xy[:, 0] ** 2 + xy[:, 1] ** 2 + 1.0)

    except (cv2.error, ValueError, TypeError):
        return depths


# ==============================================================
# Hazard evaluation
# ==============================================================

class Hazards:
    """What the current frame found, ready to draw and to summarise."""

    __slots__ = ("warning", "critical", "nearest", "considered")

    def __init__(self):
        self.warning = []       # [(u, v, distance), ...]
        self.critical = []
        self.nearest = None
        self.considered = 0

    @property
    def count(self):
        return len(self.warning) + len(self.critical)


def evaluate(result, intr):
    """Find every reconstructed feature that is too close.

    Every guard here corresponds to a real way this can go wrong:
    a frame with no features at all, a feature ORB-SLAM3 could not
    triangulate, a NaN or infinite depth, or a point behind the camera.
    None of them should stop the display.
    """
    hz = Hazards()

    if result is None:
        return hz

    keypoints = getattr(result, "keypoints", None)
    depths = getattr(result, "kp_depth", None)
    stereo = getattr(result, "kp_stereo", None)

    # No features detected, or a build that does not report depth.
    if keypoints is None or depths is None or len(keypoints) == 0:
        return hz

    keypoints = np.asarray(keypoints, dtype=np.float64).reshape(-1, 2)
    depths = np.asarray(depths, dtype=np.float64).reshape(-1)

    if len(keypoints) != len(depths):
        return hz

    # Only features with a stereo correspondence have a depth at all.
    # Everything else is effectively monocular - it has a direction but
    # no distance, so it cannot be judged and is left alone.
    if stereo is not None and len(stereo) == len(depths):
        valid = np.asarray(stereo, dtype=bool).copy()
    else:
        valid = np.ones(len(depths), dtype=bool)

    # Reject NaN/inf, points behind the camera (depth <= 0), and
    # implausible triangulations.
    valid &= np.isfinite(depths)
    valid &= depths > MIN_VALID_DEPTH
    valid &= depths < MAX_VALID_DEPTH
    valid &= np.isfinite(keypoints).all(axis=1)

    if not valid.any():
        return hz

    idx = np.flatnonzero(valid)
    dist = distances_from_depth(keypoints[idx], depths[idx], intr)

    good = np.isfinite(dist) & (dist > 0)
    idx, dist = idx[good], dist[good]
    if not len(idx):
        return hz

    hz.considered = len(idx)
    hz.nearest = float(dist.min())

    # Anything beyond SAFE_DISTANCE is simply not interesting.
    near = dist < SAFE_DISTANCE
    idx, dist = idx[near], dist[near]
    if not len(idx):
        return hz

    # Nearest first, so the cap keeps the most urgent markers.
    order = np.argsort(dist)[:MAX_MARKERS]
    idx, dist = idx[order], dist[order]

    for i, d in zip(idx, dist):
        u, v = keypoints[i]
        entry = (float(u), float(v), float(d))
        if d < CRITICAL_DISTANCE:
            hz.critical.append(entry)
        elif d < WARNING_DISTANCE:
            hz.warning.append(entry)

    return hz


# ==============================================================
# Drawing
# ==============================================================

def draw_hazards(image, hz, scale_unverified=False):
    """Draw the warnings onto the frame with OpenCV.

    Drawing into the image itself, rather than over the widget, keeps
    the markers locked to the pixels they refer to - they cannot drift
    out of sync with the frame no matter what the GUI does with it
    afterwards.

    The markers are deliberately nothing like a normal ORB dot (a small
    filled dot or a 4 px square): these are large open rings with
    crosshair ticks, so they read as an overlay rather than as another
    feature.
    """
    if image is None:
        return image

    # left_rect is grayscale; colour is needed for the warnings to be
    # legible, and the GUI panel accepts a 3-channel BGR image happily.
    canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image.copy()

    if hz.count == 0 and not scale_unverified:
        return canvas

    h, w = canvas.shape[:2]

    def on_screen(u, v):
        return -50 < u < w + 50 and -50 < v < h + 50

    # ---- warning band: amber ring with tick marks ----------
    for u, v, _d in hz.warning:
        if not on_screen(u, v):
            continue
        c = (int(round(u)), int(round(v)))
        cv2.circle(canvas, c, WARNING_RADIUS, COLOUR_WARNING, 2, cv2.LINE_AA)
        for dx, dy in ((WARNING_RADIUS + 4, 0), (-WARNING_RADIUS - 4, 0),
                       (0, WARNING_RADIUS + 4), (0, -WARNING_RADIUS - 4)):
            cv2.line(canvas, c, (c[0] + dx, c[1] + dy), COLOUR_WARNING, 1, cv2.LINE_AA)

    # ---- critical band: red double ring, X, and a distance label ----
    for u, v, d in hz.critical:
        if not on_screen(u, v):
            continue
        c = (int(round(u)), int(round(v)))
        cv2.circle(canvas, c, CRITICAL_RADIUS, COLOUR_CRITICAL, 3, cv2.LINE_AA)
        cv2.circle(canvas, c, CRITICAL_RADIUS // 2, COLOUR_CRITICAL, -1, cv2.LINE_AA)
        r = CRITICAL_RADIUS
        cv2.line(canvas, (c[0] - r, c[1] - r), (c[0] + r, c[1] + r),
                 COLOUR_CRITICAL, 2, cv2.LINE_AA)
        cv2.line(canvas, (c[0] - r, c[1] + r), (c[0] + r, c[1] - r),
                 COLOUR_CRITICAL, 2, cv2.LINE_AA)
        cv2.putText(canvas, f"{d:.2f}m", (c[0] + r + 3, c[1] - r),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, COLOUR_CRITICAL, 1, cv2.LINE_AA)

    _draw_hud(canvas, hz, scale_unverified)
    return canvas


def _draw_hud(canvas, hz, scale_unverified):
    """Small status strip, so the state is readable without counting dots."""
    h, w = canvas.shape[:2]

    if hz.critical:
        text = f"CRITICAL  {len(hz.critical)} point(s) < {CRITICAL_DISTANCE:.2f} m"
        colour = COLOUR_HUD_ALERT
    elif hz.warning:
        text = f"WARNING  {len(hz.warning)} point(s) < {WARNING_DISTANCE:.2f} m"
        colour = COLOUR_WARNING
    else:
        text = "CLEAR"
        colour = COLOUR_HUD_OK

    if hz.nearest is not None:
        text += f"   nearest {hz.nearest:.2f} m"
    if hz.considered:
        text += f"   ({hz.considered} with depth)"

    y = h - 12
    cv2.rectangle(canvas, (0, y - 20), (w, h), (0, 0, 0), -1)
    cv2.putText(canvas, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, colour, 1, cv2.LINE_AA)

    if scale_unverified:
        cv2.putText(canvas, "SCALE UNVERIFIED - distances are relative",
                    (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    COLOUR_WARNING, 1, cv2.LINE_AA)


# ==============================================================
# GUI integration
# ==============================================================

class _AnnotatedResult:
    """A SlamResult with the left image swapped for an annotated copy.

    The real result object is shared with the SLAM worker thread and
    uses __slots__, so it is neither safe nor possible to just assign a
    new image onto it. This forwards every attribute to the original and
    intercepts only `left_rect`, which lets the whole of MainWindow's
    existing view-mode logic run untouched.
    """

    __slots__ = ("_wrapped", "left_rect")

    def __init__(self, wrapped, left_rect):
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "left_rect", left_rect)

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_wrapped"), name)


class SafeTravelsWindow(gui.MainWindow):
    """MainWindow plus the proximity layer.

    Only _update_images is overridden. Everything else - the 3D viewer,
    pose panel, plane detection, recording, every keyboard shortcut -
    is inherited unchanged.
    """

    def __init__(self, state):
        super().__init__(state)
        self.intrinsics = Intrinsics(getattr(state, "rectifier", None))
        self.hazards = Hazards()

        self.setWindowTitle(self.windowTitle() + "  -  SAFE TRAVELS")

        print()
        print("SAFE TRAVELS: proximity layer active")
        print(f"  intrinsics : {self.intrinsics.describe()}")
        print(f"  thresholds : safe {SAFE_DISTANCE:.2f} m | "
              f"warning {WARNING_DISTANCE:.2f} m | "
              f"critical {CRITICAL_DISTANCE:.2f} m")
        print("  markers    : shown in the Rectified and ORB features views")
        print("               (the Raw view has no reconstructed geometry)")
        if getattr(state, "scale_unverified", False):
            print("  WARNING    : the calibration scale is unverified, so these")
            print("               distances may be wrong by a constant factor.")
        print()

    # ----------------------------------------------------------
    def _update_images(self, result):
        """Annotate the left image, then let MainWindow display it."""
        try:
            self.hazards = evaluate(result, self.intrinsics)
        except Exception as exc:  # noqa: BLE001
            # A failure in the safety layer must never take the viewer
            # down with it - fall through and show the plain image.
            print(f"safe_travels: hazard evaluation failed: {exc}")
            self.hazards = Hazards()
            return super()._update_images(result)

        # The raw view is the unrectified sensor image; the keypoint
        # coordinates belong to the rectified one, so they would be
        # drawn in the wrong places. Leave that view alone.
        if self.view_mode == VIEW_RAW or result is None:
            return super()._update_images(result)

        left = getattr(result, "left_rect", None)
        if left is None:
            return super()._update_images(result)

        try:
            annotated = draw_hazards(
                left, self.hazards,
                scale_unverified=getattr(self.state, "scale_unverified", False))
        except Exception as exc:  # noqa: BLE001
            print(f"safe_travels: drawing failed: {exc}")
            return super()._update_images(result)

        return super()._update_images(_AnnotatedResult(result, annotated))


# ==============================================================
def main():
    """Install the safety layer, then hand over to main.py unchanged."""
    print()
    print("NOVEX - SAFE TRAVELS")
    print("--------------------")
    print("Proximity warnings layered over the standard ORB-SLAM3 test.")
    print("All start-up, calibration and SLAM handling is main.py's.")

    # main() does `from gui import MainWindow` at call time, so this
    # substitution is picked up without main.py being touched.
    gui.MainWindow = SafeTravelsWindow

    return novex_main.main()


if __name__ == "__main__":
    sys.exit(main())
