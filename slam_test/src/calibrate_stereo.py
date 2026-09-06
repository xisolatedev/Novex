#!/usr/bin/env python3
"""
Novex stereo fisheye calibration.

This tool produces the ONLY metric information in the whole system: the
intrinsics of each fisheye lens and the rigid transform between them,
from which the baseline comes. Everything ORB-SLAM3 later reports in
metres traces back to what happens here.

Two board types are supported.

  charuco    (default, recommended)
      A chessboard with a unique ArUco marker in every white square.
      Partial views are usable, so the board can be pushed into and off
      the frame corners - which on a ~112 degree fisheye is the only
      way to constrain the distortion where it is strongest.

  chessboard
      Classic. Requires the ENTIRE board to be visible in both eyes,
      so the frame corners can never be covered. Kept for comparison.

Generate a board first:

    python src/make_board.py --squares 8x6 --square-size-mm 40

Print it at 100%, MEASURE a square with a ruler, then:

    python src/calibrate_stereo.py --squares 8x6 \\
        --square-size 0.0398 --marker-size 0.0298

Controls
    SPACE   capture the current pair
    A       toggle auto-capture (captures when the board has moved)
    C       run the calibration on what has been captured
    D       delete the last capture
    R       discard all captures
    ESC     quit

Advice, in order of how badly it hurts to get it wrong:

  * MEASURE the printed square. Printers rescale. Every distance
    ORB-SLAM3 reports scales linearly with this one number.
  * Keep the board rigid and FLAT. A slight curve corrupts everything.
  * Cover the whole frame, corners included. The coverage grid in the
    window shows which cells still have no data. With ChArUco you can
    and should let the board hang off the edges.
  * Tilt the board 30-45 degrees in several directions. Head-on views
    alone cannot separate focal length from distance.
  * Hold still at the moment of capture. This sensor has a rolling
    shutter, so motion shears the image and biases corner positions.
"""

import argparse
import datetime
import os
import sys

import cv2
import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from camera import StereoCamera  # noqa: E402
from charuco import (  # noqa: E402
    CharucoBoardSpec,
    relative_pose_from_board_poses,
)
import view_quality as vq  # noqa: E402


# --------------------------------------------------------------
# OpenCV moved the fisheye calibration flags out of the cv2.fisheye
# namespace into the top-level cv2 namespace in version 5. Resolve
# them once here so the tool works on both 4.x and 5.x.
# --------------------------------------------------------------
def _flag(name):
    for holder in (cv2.fisheye, cv2):
        value = getattr(holder, name, None)
        if value is not None:
            return value
    raise AttributeError(f"OpenCV is missing the calibration flag {name}")


FISHEYE_RECOMPUTE_EXTRINSIC = _flag("CALIB_RECOMPUTE_EXTRINSIC")
FISHEYE_FIX_SKEW = _flag("CALIB_FIX_SKEW")
FISHEYE_FIX_INTRINSIC = _flag("CALIB_FIX_INTRINSIC")

CALIB_FLAGS = FISHEYE_RECOMPUTE_EXTRINSIC | FISHEYE_FIX_SKEW
CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-9)

GRID = 8  # coverage grid resolution

# Width of each eye in the preview window.
DISPLAY_WIDTH = 640

# On-screen size of the drawn overlays, in DISPLAY pixels.
#
# These matter because the overlays are drawn on the full-resolution
# image and only then downscaled to DISPLAY_WIDTH. At 1280 px per eye
# that is a 2x reduction, so anything drawn at its nominal size arrives
# on screen at half of it - which is why a radius-4 dot looked like a
# speck. Everything below is therefore multiplied by the downscale
# factor at draw time, so these numbers mean what they say.
CORNER_RADIUS = 5          # detected chessboard/ChArUco corners
CORNER_OUTLINE = 2         # dark ring, so dots stay visible on white
GRID_THICKNESS = 2         # coverage grid lines


# ==============================================================
# Board wrappers - both expose detect() -> (obj, img, ids)
# ==============================================================

class ChessboardSpec:
    """Classic chessboard. `pattern` is INNER CORNERS."""

    def __init__(self, cols, rows, square_length):
        self.pattern = (int(cols), int(rows))
        self.square_length = float(square_length)
        self.num_corners = self.pattern[0] * self.pattern[1]

        objp = np.zeros((self.num_corners, 3), np.float64)
        grid = np.mgrid[0:self.pattern[0], 0:self.pattern[1]].T.reshape(-1, 2)
        objp[:, :2] = grid * self.square_length
        self._objp = objp

    @property
    def width_m(self):
        return (self.pattern[0] + 1) * self.square_length

    @property
    def height_m(self):
        return (self.pattern[1] + 1) * self.square_length

    def describe(self):
        return (
            f"Chessboard {self.pattern[0]}x{self.pattern[1]} inner corners\n"
            f"  square      : {self.square_length * 1000:.2f} mm\n"
            f"  printed size: ~{self.width_m * 100:.1f} x {self.height_m * 100:.1f} cm\n"
            f"  NOTE: the whole board must be visible, so the frame corners\n"
            f"        cannot be covered. Prefer --board charuco."
        )

    def detect(self, gray):
        ok, corners = False, None

        if hasattr(cv2, "findChessboardCornersSB"):
            ok, corners = cv2.findChessboardCornersSB(
                gray, self.pattern,
                flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY,
            )

        if not ok:
            ok, corners = cv2.findChessboardCorners(
                gray, self.pattern,
                flags=(cv2.CALIB_CB_ADAPTIVE_THRESH
                       | cv2.CALIB_CB_NORMALIZE_IMAGE
                       | cv2.CALIB_CB_FILTER_QUADS),
            )
            if ok:
                corners = cv2.cornerSubPix(
                    gray, corners, (5, 5), (-1, -1),
                    (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01),
                )

        if not ok:
            return None, None, None

        return (
            self._objp.copy(),
            np.asarray(corners, dtype=np.float64).reshape(-1, 2),
            np.arange(self.num_corners, dtype=np.int32),
        )


# ==============================================================
def px_per_square(img_points, ids, spec):
    """Rough apparent square size in pixels, for the live readout.

    This is the number that decides whether detection works at all:
    below ~10 px OpenCV gives up, and 20+ is needed for good subpixel
    corners.
    """
    if img_points is None or len(img_points) < 4:
        return 0.0

    pts = img_points.reshape(-1, 2)
    span = pts.max(axis=0) - pts.min(axis=0)

    if isinstance(spec, CharucoBoardSpec):
        n = max(spec.squares_x - 2, 1), max(spec.squares_y - 2, 1)
    else:
        n = max(spec.pattern[0] - 1, 1), max(spec.pattern[1] - 1, 1)

    # Only meaningful when a decent part of the board is visible.
    frac = len(pts) / spec.num_corners
    if frac < 0.3:
        return float(np.hypot(*span) / max(np.sqrt(len(pts)), 1))

    return float((span[0] / n[0] + span[1] / n[1]) / 2.0)


def update_confidence(conf, img_points, size, score=1.0):
    """Accumulate CONFIDENCE per cell, not just a raw hit count.

    A cell that has only been grazed by two corners of a badly tilted
    board is not covered in any useful sense. Weighting each cell by the
    quality of the view that touched it makes the grid say what you
    actually want to know: where is the calibration still guessing?
    """
    w, h = size
    pts = np.asarray(img_points).reshape(-1, 2)
    xs = np.clip((pts[:, 0] / w * GRID).astype(int), 0, GRID - 1)
    ys = np.clip((pts[:, 1] / h * GRID).astype(int), 0, GRID - 1)
    np.add.at(conf, (ys, xs), float(score))


def weakest_cell(conf):
    """The cell most in need of data - used for the on-screen hint."""
    idx = int(np.argmin(conf))
    return idx // GRID, idx % GRID


def draw_confidence(img, conf, draw_scale=1.0, target=None):
    """Confidence grid: red = nothing, amber = weak, green = solid."""
    h, w = img.shape[:2]
    cw, ch = w / GRID, h / GRID

    # Thinner than the corner markers on purpose: the grid is guidance,
    # not the subject. A heavy grid over the whole frame washes out the
    # board you are trying to aim.
    thickness = max(1, int(round(draw_scale)))
    overlay = img.copy()

    strong = max(float(conf.max()), 1e-6)
    for gy in range(GRID):
        for gx in range(GRID):
            x0, y0 = int(gx * cw), int(gy * ch)
            x1, y1 = int((gx + 1) * cw), int((gy + 1) * ch)
            c = conf[gy, gx]
            frac = c / strong
            if c <= 0:
                colour = (40, 40, 190)
            elif frac < 0.25:
                colour = (0, 150, 210)
            else:
                colour = (0, 170, 0)
            cv2.rectangle(overlay, (x0, y0), (x1, y1), colour, thickness)

    out = cv2.addWeighted(overlay, 0.30, img, 0.70, 0)

    if target is not None:
        gy, gx = target
        x0, y0 = int(gx * cw), int(gy * ch)
        x1, y1 = int((gx + 1) * cw), int((gy + 1) * ch)
        cv2.rectangle(out, (x0, y0), (x1, y1), (255, 255, 255),
                      max(2, thickness * 2))
        # Centred in the target cell, so it never collides with the
        # status text in the corner.
        label = "AIM HERE"
        fs = 0.42 * draw_scale
        (tw, th_), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, 1)
        cv2.putText(out, label,
                    (int(x0 + (cw - tw) / 2), int(y0 + (ch + th_) / 2)),
                    cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255),
                    max(1, int(round(draw_scale))), cv2.LINE_AA)

    return out


def draw_track(img, trail, detected, draw_scale=1.0):
    """Where the board has been, and where it was last seen.

    Tracking drops out most often exactly when you push the board into a
    corner, which is when you least want to be guessing where it went.
    The trail plus a last-known marker makes recovery quick.
    """
    if len(trail) > 1:
        pts = np.asarray(trail, np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [pts], False, (255, 200, 60),
                      max(1, int(round(2 * draw_scale))), cv2.LINE_AA)

    if trail:
        last = tuple(int(v) for v in trail[-1])
        radius = max(6, int(round(10 * draw_scale)))
        if detected:
            cv2.circle(img, last, radius, (80, 255, 120),
                       max(2, int(round(2 * draw_scale))), cv2.LINE_AA)
        else:
            # Lost: mark the last known position so it can be reacquired.
            cv2.drawMarker(img, last, (60, 90, 255), cv2.MARKER_TILTED_CROSS,
                           radius * 2, max(2, int(round(2 * draw_scale))))
            cv2.putText(img, "LOST", (last[0] + radius, last[1] - radius),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6 * draw_scale,
                        (60, 90, 255), max(1, int(draw_scale)), cv2.LINE_AA)


def update_coverage(grid, img_points, size):
    w, h = size
    pts = img_points.reshape(-1, 2)
    xs = np.clip((pts[:, 0] / w * GRID).astype(int), 0, GRID - 1)
    ys = np.clip((pts[:, 1] / h * GRID).astype(int), 0, GRID - 1)
    np.add.at(grid, (ys, xs), 1)


def draw_coverage(img, grid, draw_scale=1.0):
    """Overlay the coverage grid: red = never seen.

    `draw_scale` compensates for the later downscale to the preview
    window, so the lines are the intended thickness on screen.
    """
    h, w = img.shape[:2]
    cw, ch = w / GRID, h / GRID
    thickness = max(1, int(round(GRID_THICKNESS * draw_scale)))
    overlay = img.copy()
    for gy in range(GRID):
        for gx in range(GRID):
            x0, y0 = int(gx * cw), int(gy * ch)
            x1, y1 = int((gx + 1) * cw), int((gy + 1) * ch)
            n = grid[gy, gx]
            colour = (0, 0, 200) if n == 0 else (
                (0, 165, 255) if n < 20 else (0, 180, 0))
            cv2.rectangle(overlay, (x0, y0), (x1, y1), colour, thickness)
    return cv2.addWeighted(overlay, 0.35, img, 0.65, 0)


# ==============================================================
# A ChArUco view with only a handful of corners is not merely weak, it
# is harmful: the board pose it implies is badly conditioned, and
# cv2.fisheye.calibrate cannot solve a pose from it at all (it fails
# with an assertion once rvecs/tvecs are requested). Views this thin
# are dropped before fitting.
MIN_CORNERS_PER_VIEW = 12


def filter_captures(captures, min_corners=MIN_CORNERS_PER_VIEW):
    kept, dropped = [], []
    for c in captures:
        n1, n2 = len(c["obj1"]), len(c["obj2"])
        if min(n1, n2) < min_corners:
            dropped.append((n1, n2))
        else:
            kept.append(c)
    return kept, dropped


def draw_corners(img, points, draw_scale=1.0, colour=(0, 255, 0)):
    """Draw detected corners big enough to actually see.

    Each corner gets a dark ring under a bright fill, because a plain
    green dot disappears against the white squares of the board - which
    is exactly where half the corners sit.
    """
    if points is None or not len(points):
        return

    radius = max(2, int(round(CORNER_RADIUS * draw_scale)))
    outline = max(1, int(round(CORNER_OUTLINE * draw_scale)))

    for pt in points.reshape(-1, 2).astype(int):
        centre = (int(pt[0]), int(pt[1]))
        cv2.circle(img, centre, radius + outline, (0, 0, 0), -1, cv2.LINE_AA)
        cv2.circle(img, centre, radius, colour, -1, cv2.LINE_AA)


def calibrate_charuco(captures, spec, size, min_corners=MIN_CORNERS_PER_VIEW,
                      quality_cfg=None):
    """Per-eye fisheye intrinsics, then stereo extrinsics via solvePnP.

    cv2.fisheye.calibrate copes with a different number of points in
    every view, which is what makes partial ChArUco views usable.
    cv2.fisheye.stereoCalibrate does NOT - it reshapes its inputs and
    demands a uniform count - so the extrinsics are computed from
    per-view board poses instead. See charuco.estimate_relative_pose.
    """
    quality_cfg = quality_cfg or vq.QualityConfig()

    # ------------------------------------------------------
    # Quality filtering, before OpenCV gets a chance to die.
    #
    # fisheye.calibrate() aborts with an assertion rather than an
    # error when it cannot initialise a view's pose, and it does not
    # say which view. Everything unusable is therefore removed first,
    # with the reason stated, and the fit itself retries on a stricter
    # subset if OpenCV still refuses.
    # ------------------------------------------------------
    print("\n" + "-" * 58)
    print(" VIEW QUALITY FILTER")
    print("-" * 58)

    before = len(captures)
    captures, rejected = vq.prefilter(captures, size, quality_cfg)

    n = len(captures)
    if n < 6:
        raise RuntimeError(
            f"only {n} usable pairs of {before}; need at least 6, ideally 20+.\n"
            f"    Capture more views where BOTH eyes see a good part of the "
            f"board, and vary the board's tilt and position.")

    corner_counts = [min(len(c["obj1"]), len(c["obj2"])) for c in captures]
    print(f"\n  {n} views kept, {len(rejected)} rejected")
    print(f"  corners per view: {min(corner_counts)}-{max(corner_counts)} "
          f"(median {int(np.median(corner_counts))})")

    print("\nCalibrating LEFT eye (%d views)..." % n)
    rms1, K1, D1, rvecs1, tvecs1, kept_l = vq.robust_fisheye_calibrate(
        captures, size, CALIB_FLAGS, CRITERIA, "obj1", "img1",
        log=lambda m: print(m))
    print(f"  RMS: {rms1:.4f} px")

    # Both eyes must end up fitted over the SAME views, or the per-view
    # poses cannot be paired to recover the extrinsics.
    if len(kept_l) != len(captures):
        print(f"  (left fit used {len(kept_l)} of {n} views; "
              f"re-running the right eye on the same set)")
        captures = kept_l
        n = len(captures)

    print("Calibrating RIGHT eye (%d views)..." % n)
    rms2, K2, D2, rvecs2, tvecs2, kept_r = vq.robust_fisheye_calibrate(
        captures, size, CALIB_FLAGS, CRITERIA, "obj2", "img2",
        log=lambda m: print(m))
    print(f"  RMS: {rms2:.4f} px")

    if len(kept_r) != len(captures):
        # The right eye needed a stricter set, so redo the left on it
        # to keep the two view lists aligned.
        captures = kept_r
        n = len(captures)
        print(f"  (right fit used {n} views; re-fitting the left to match)")
        rms1, K1, D1, rvecs1, tvecs1, captures = vq.robust_fisheye_calibrate(
            captures, size, CALIB_FLAGS, CRITERIA, "obj1", "img1",
            log=lambda m: print(m))
        n = len(captures)
        rms2, K2, D2, rvecs2, tvecs2, captures = vq.robust_fisheye_calibrate(
            captures, size, CALIB_FLAGS, CRITERIA, "obj2", "img2",
            log=lambda m: print(m))
        n = len(captures)

    # The board poses come straight out of the two intrinsic fits, so
    # they are consistent with the K and D just computed. See
    # charuco.relative_pose_from_board_poses for why this beats
    # re-deriving poses with solvePnP.
    print("Estimating STEREO transform from the fitted board poses...")
    weights = np.array([min(len(c["obj1"]), len(c["obj2"])) for c in captures],
                       dtype=float)
    R, T, stats = relative_pose_from_board_poses(
        rvecs1, tvecs1, rvecs2, tvecs2, weights=weights)

    print(f"  views used: {stats['views_used']}/{stats['views_total']} "
          f"({stats['views_rejected']} rejected as outliers)")
    print(f"  baseline median across views: {stats['baseline_median_mm']:.3f} mm")
    print(f"  baseline spread across views: {stats['baseline_std_mm']:.3f} mm")
    print(f"  rotation spread across views: {stats['rotation_spread_deg']:.4f} deg")

    # ------------------------------------------------------
    # Per-view reprojection error, so a single bad view can be seen
    # rather than hidden inside an aggregate.
    # ------------------------------------------------------
    err_l = vq.reprojection_errors(captures, K1, D1, rvecs1, tvecs1,
                                   "obj1", "img1")
    err_r = vq.reprojection_errors(captures, K2, D2, rvecs2, tvecs2,
                                   "obj2", "img2")

    print("\n  Per-view reprojection error (px):")
    print(f"    left : mean {np.nanmean(err_l):.3f}  worst {np.nanmax(err_l):.3f}")
    print(f"    right: mean {np.nanmean(err_r):.3f}  worst {np.nanmax(err_r):.3f}")
    worst_idx = int(np.nanargmax(np.maximum(err_l, err_r)))
    print(f"    worst view is #{worst_idx} "
          f"({min(len(captures[worst_idx]['obj1']), len(captures[worst_idx]['obj2']))} corners)")

    return K1, D1, K2, D2, R, T, {
        "left": float(rms1),
        "right": float(rms2),
    }, stats, {"per_view_left": err_l, "per_view_right": err_r,
               "views_used": n, "views_rejected": len(rejected),
               "captures": captures}


def calibrate_chessboard(captures, spec, size, quality_cfg=None):
    """Classic path: uniform corner counts, so stereoCalibrate works."""
    n = len(captures)
    if n < 6:
        raise RuntimeError(f"only {n} pairs captured; need at least 6, ideally 20+")

    objs = [c["obj1"].reshape(1, -1, 3) for c in captures]
    imgs1 = [c["img1"].reshape(1, -1, 2) for c in captures]
    imgs2 = [c["img2"].reshape(1, -1, 2) for c in captures]

    print(f"\nCalibrating LEFT eye ({n} views)...")
    rms1, K1, D1, _, _ = cv2.fisheye.calibrate(
        objs, imgs1, size, np.zeros((3, 3)), np.zeros((4, 1)),
        flags=CALIB_FLAGS, criteria=CRITERIA)
    print(f"  RMS: {rms1:.4f} px")

    print("Calibrating RIGHT eye...")
    rms2, K2, D2, _, _ = cv2.fisheye.calibrate(
        objs, imgs2, size, np.zeros((3, 3)), np.zeros((4, 1)),
        flags=CALIB_FLAGS, criteria=CRITERIA)
    print(f"  RMS: {rms2:.4f} px")

    print("Calibrating STEREO transform...")
    out = cv2.fisheye.stereoCalibrate(
        objs, imgs1, imgs2, K1, D1, K2, D2, size,
        flags=FISHEYE_FIX_INTRINSIC | CALIB_FLAGS, criteria=CRITERIA)

    # OpenCV 4 returns 7 values; OpenCV 5 adds per-view rvecs/tvecs.
    rms_s, K1, D1, K2, D2, R, T = out[:7]
    print(f"  RMS: {rms_s:.4f} px")

    return K1, D1, K2, D2, R, T, {
        "left": float(rms1),
        "right": float(rms2),
        "stereo": float(rms_s),
    }, {}, {"views_used": n, "views_rejected": 0, "captures": captures}


# ==============================================================
def write_calibration(path, spec, board_kind, pattern, size, captures,
                      K1, D1, K2, D2, R, T, rms, stats, square_size):
    baseline = float(np.linalg.norm(T))

    data = {
        "model": "fisheye",
        "created": datetime.datetime.now().isoformat(timespec="seconds"),
        "image_width": int(size[0]),
        "image_height": int(size[1]),
        "square_size_m": float(square_size),
        "board": board_kind,
        "pattern": pattern,
        "num_pairs": int(len(captures)),
        "camera1": {"name": "left",
                    "K": [float(v) for v in np.asarray(K1).reshape(-1)],
                    "D": [float(v) for v in np.asarray(D1).reshape(-1)]},
        "camera2": {"name": "right",
                    "K": [float(v) for v in np.asarray(K2).reshape(-1)],
                    "D": [float(v) for v in np.asarray(D2).reshape(-1)]},
        "R": [float(v) for v in np.asarray(R).reshape(-1)],
        "T": [float(v) for v in np.asarray(T).reshape(-1)],
        "baseline_m": baseline,
        "rms": rms,
    }
    if stats:
        data["extrinsics_stats"] = {k: float(v) for k, v in stats.items()}

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)

    return baseline


def report_result(baseline, square_size, spec):
    """Print the result plus the scale cross-check.

    The baseline expressed in board squares is SCALE FREE - it is what
    the images actually measured. If the metric baseline looks wrong,
    this ratio tells you exactly what the square size should have been.
    """
    print(f"\n  MEASURED BASELINE: {baseline * 1000:.2f} mm")

    ratio = baseline / square_size
    print(f"  (that is {ratio:.4f} board squares - a scale-free number)")

    if baseline > 0.095:
        print()
        print("  ** IMPOSSIBLE BASELINE **")
        print("  The module is 100 mm wide, so the lenses cannot be further")
        print("  apart than that. The images are fine; the declared square")
        print("  size is wrong. Measure the printed square, then re-solve")
        print("  WITHOUT recapturing:")
        print()
        print("      python src/calibrate_stereo.py --from-images \\")
        print(f"          --squares {spec.squares_x}x{spec.squares_y} "
              f"--square-size <measured_metres>")
        print()
        print("  Or measure the lens separation on the module and read off")
        print("  the square size it implies:")
        for mm in (55, 60, 65, 70, 75):
            print(f"      baseline {mm} mm  ->  square {mm / 1000 / ratio * 1000:.2f} mm")


def report_quality(K1, D1, K2, D2, R, T, rms, extra, size, spec, out_path):
    """Everything you need to judge the calibration, in one place."""
    baseline = float(np.linalg.norm(T))

    print("\n" + "=" * 58)
    print(" CALIBRATION QUALITY")
    print("=" * 58)

    print(f"  views used        : {extra.get('views_used', 0)} "
          f"({extra.get('views_rejected', 0)} rejected by the filter)")
    print(f"  RMS left          : {rms['left']:.4f} px")
    print(f"  RMS right         : {rms['right']:.4f} px")
    if "stereo" in rms:
        print(f"  RMS stereo        : {rms['stereo']:.4f} px")

    if "per_view_left" in extra:
        el, er = extra["per_view_left"], extra["per_view_right"]
        print(f"  per-view left     : mean {np.nanmean(el):.3f}  "
              f"worst {np.nanmax(el):.3f} px")
        print(f"  per-view right    : mean {np.nanmean(er):.3f}  "
              f"worst {np.nanmax(er):.3f} px")

    print(f"  BASELINE          : {baseline * 1000:.3f} mm  (measured)")
    if spec is not None and getattr(spec, "square_length", 0):
        print(f"  ... which is       {baseline / spec.square_length:.4f} board "
              f"squares - a scale-free number")

    # Field of view and overlap, from the fitted model.
    try:
        from calibration import measured_fov, StereoCalibration, FisheyeStereoModel
        fov1 = measured_fov(K1, D1, size)
        print(f"  measured FOV      : {fov1['horizontal']:.1f} deg horizontal, "
              f"{fov1['vertical']:.1f} vertical, {fov1['diagonal']:.1f} diagonal")

        data = {
            "model": "fisheye",
            "image_width": int(size[0]), "image_height": int(size[1]),
            "camera1": {"K": [float(v) for v in np.asarray(K1).reshape(-1)],
                        "D": [float(v) for v in np.asarray(D1).reshape(-1)]},
            "camera2": {"K": [float(v) for v in np.asarray(K2).reshape(-1)],
                        "D": [float(v) for v in np.asarray(D2).reshape(-1)]},
            "R": [float(v) for v in np.asarray(R).reshape(-1)],
            "T": [float(v) for v in np.asarray(T).reshape(-1)],
        }
        calib = StereoCalibration(data)
        fm = FisheyeStereoModel(calib)
        c1 = fm.overlap["cam1"]
        pct = 100.0 * (c1[1] - c1[0]) / size[0]
        print(f"  stereo overlap    : columns {c1[0]}-{c1[1]} "
              f"({pct:.0f}% of image width)")
        print(f"  usable for 120 deg rectified output: "
              f"{'yes' if fov1['horizontal'] > 125 else 'MARGINAL'}")
    except Exception as exc:  # noqa: BLE001
        print(f"  (FOV/overlap unavailable: {exc})")

    grade, note, caveats = vq.quality_grade(
        rms["left"], rms["right"], rms.get("stereo"),
        n_views=extra.get("views_used", 0))

    colour = {"EXCELLENT": "", "GOOD": "", "ACCEPTABLE": "",
              "POOR": "", "UNUSABLE": ""}
    print(f"\n  QUALITY: {grade} - {note}")
    for c in caveats:
        print(f"    caveat: {c}")
    if grade in ("POOR", "UNUSABLE"):
        print("    Recapture with the board flatter, better lit, and held")
        print("    still at the moment of capture (this sensor has a")
        print("    rolling shutter, so motion shears the image).")

    print("=" * 58)
    return grade


def solve_from_images(image_dir, spec, args, a, b):
    """Re-run the whole solve from saved left_XXX/right_XXX pairs."""
    import glob

    lefts = sorted(glob.glob(os.path.join(image_dir, "left_*.png")))
    if not lefts:
        print(f"ERROR: no left_*.png found in {image_dir}")
        return 1

    print(f"Re-solving from {len(lefts)} saved pairs in {image_dir}")
    print(f"  declared square size: {args.square_size * 1000:.2f} mm\n")

    captures = []
    size = None
    for lp in lefts:
        rp = lp.replace("left_", "right_")
        if not os.path.exists(rp):
            continue

        gl = cv2.imread(lp, cv2.IMREAD_GRAYSCALE)
        gr = cv2.imread(rp, cv2.IMREAD_GRAYSCALE)
        if gl is None or gr is None:
            continue

        size = (gl.shape[1], gl.shape[0])

        o1, p1, i1 = spec.detect(gl)
        o2, p2, i2 = spec.detect(gr)
        if o1 is None or o2 is None:
            print(f"  skipped {os.path.basename(lp)} (board not found in both eyes)")
            continue

        captures.append({"obj1": o1, "img1": p1, "ids1": i1,
                         "obj2": o2, "img2": p2, "ids2": i2})

    print(f"  usable pairs: {len(captures)}")

    fn = calibrate_charuco if args.board == "charuco" else calibrate_chessboard
    K1, D1, K2, D2, R, T, rms, stats, extra = fn(
        captures, spec, size, quality_cfg=vq.QualityConfig(wide_angle=args.wide))

    report_quality(K1, D1, K2, D2, R, T, rms, extra, size, spec, args.out)

    baseline = write_calibration(
        args.out, spec, args.board, f"{a}x{b}", size,
        extra.get("captures", captures),
        K1, D1, K2, D2, R, T, rms, stats, args.square_size)

    report_result(baseline, args.square_size, spec)

    print(f"\nWritten: {args.out}")
    return 0


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)

    ap = argparse.ArgumentParser(
        description="Novex fisheye stereo calibration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--board", choices=("charuco", "chessboard"), default="charuco")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=2560)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument(
        "--squares", default="8x6",
        help="charuco: board size in SQUARES. chessboard: INNER CORNERS.")
    ap.add_argument(
        "--square-size", type=float, required=True,
        help="MEASURED square edge in METRES, e.g. 0.0398")
    ap.add_argument(
        "--marker-size", type=float, default=None,
        help="charuco only: measured marker edge in METRES "
             "(default: 0.75 x square size)")
    ap.add_argument("--dictionary", default="DICT_5X5_1000")
    ap.add_argument(
        "--out", default=os.path.join(root, "config", "stereo_calibration.yaml"))
    ap.add_argument(
        "--save-images", default=os.path.join(root, "calibration", "pairs"))
    ap.add_argument("--swap-eyes", action="store_true")
    ap.add_argument(
        "--wide", action="store_true",
        help="WIDE-ANGLE MODE for ~169-180 degree fisheye lenses. Tunes the "
             "ArUco detector for curved marker borders so the board is still "
             "found at the frame edge, and relaxes the corner-count and tilt "
             "limits so legitimate edge observations are kept. The degeneracy "
             "checks are NOT relaxed - a collinear view is unusable either way.")
    ap.add_argument(
        "--draw-scale", type=float, default=1.0, metavar="X",
        help="multiplier for the size of the drawn corners and coverage "
             "grid. 1.0 already compensates for the preview downscale; "
             "raise it if you want them chunkier still.")
    ap.add_argument(
        "--from-images", nargs="?", const="__default__", default=None,
        metavar="DIR",
        help="skip the camera and re-solve from previously captured pairs "
             "(calibration/pairs by default). Use this when you discover the "
             "printed square was not the size you thought: the images are "
             "still good, only the declared scale was wrong.")
    ap.add_argument(
        "--lock-exposure", type=float, default=None, metavar="MS",
        help="pin the sensor to manual exposure of MS milliseconds and "
             "disable auto white balance. Strongly recommended: it keeps "
             "both eyes at the same brightness and stops rolling-shutter "
             "motion blur. Try 20.")
    ap.add_argument("--gain", type=int, default=None,
                    help="manual gain, used with --lock-exposure")
    args = ap.parse_args()

    a, b = (int(v) for v in args.squares.lower().split("x"))

    if args.square_size > 0.2:
        print(f"WARNING: --square-size {args.square_size} is over 20 cm. "
              f"This value must be in METRES.")

    if args.board == "charuco":
        marker = args.marker_size or args.square_size * 0.75
        spec = CharucoBoardSpec(a, b, args.square_size, marker, args.dictionary,
                                wide_angle=args.wide)
    else:
        spec = ChessboardSpec(a, b, args.square_size)

    print()
    print("=" * 62)
    print(" NOVEX STEREO FISHEYE CALIBRATION")
    print("=" * 62)
    print(spec.describe())
    print(f"  output      : {args.out}")
    if args.wide:
        print("  MODE        : WIDE-ANGLE (edge observations kept, "
              "detector tuned for fisheye)")
    print()

    # ----------------------------------------------------------
    # Offline: re-solve from saved image pairs.
    #
    # Intrinsics are scale-invariant, so a wrong square size leaves K
    # and D correct and misscales only the baseline. The captured
    # images remain perfectly good; only the declared number was wrong.
    # ----------------------------------------------------------
    if args.from_images is not None:
        image_dir = (args.save_images if args.from_images == "__default__"
                     else args.from_images)
        return solve_from_images(image_dir, spec, args, a, b)

    cam = StereoCamera(index=args.camera, width=args.width,
                       height=args.height, fps=args.fps)
    if not cam.open():
        print(f"ERROR: {cam.error}")
        return 1

    for w in cam.mode_warnings():
        print(f"WARNING: {w}")

    if args.lock_exposure is not None:
        controls = {
            "auto_exposure": 1,
            "white_balance_automatic": 0,
            # UVC exposure_time_absolute is in units of 100 us.
            "exposure_time_absolute": max(1, int(round(args.lock_exposure * 10))),
        }
        if args.gain is not None:
            controls["gain"] = args.gain
        applied, failed = cam.apply_controls(controls)
        print(f"Exposure locked: {applied}")
        if failed:
            print(f"  controls REJECTED by the driver: {failed}")

    cam.start()

    eye_w = cam.actual["width"] // 2
    eye_h = cam.actual["height"]
    size = (eye_w, eye_h)
    print(f"  eye size    : {eye_w}x{eye_h}")

    os.makedirs(args.save_images, exist_ok=True)

    captures = []
    cov_left = np.zeros((GRID, GRID), dtype=int)
    conf_left = np.zeros((GRID, GRID), dtype=float)
    conf_right = np.zeros((GRID, GRID), dtype=float)
    descriptors = []            # for duplicate detection
    quality_cfg = vq.QualityConfig(wide_angle=args.wide)
    trail_l, trail_r = [], []
    detect_history = []
    auto = False
    last_centre = None
    last_id = 0

    cv2.namedWindow("NOVEX CALIBRATION", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("NOVEX CALIBRATION", 1400, 420)

    print()
    print("SPACE capture | A auto | C calibrate | D delete | R reset | ESC quit")
    print()

    while True:
        frame = cam.read_new(last_id)
        if frame is None:
            if (cv2.waitKey(1) & 0xFF) == 27:
                break
            continue
        last_id = frame.frame_id

        left, right = frame.left, frame.right
        if args.swap_eyes:
            left, right = right, left

        gl = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
        gr = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)

        o1, p1, i1 = spec.detect(gl)
        o2, p2, i2 = spec.detect(gr)

        both = o1 is not None and o2 is not None

        # --- live quality verdict for the CURRENT view ---------
        verdict = vq.score_view(o1, p1, i1, o2, p2, i2, size,
                                descriptors, quality_cfg,
                                coverage=cov_left, grid_n=GRID)

        # --- tracking trail ------------------------------------
        detect_history.append(1 if both else 0)
        if len(detect_history) > 60:
            detect_history.pop(0)

        if p1 is not None and len(p1):
            trail_l.append(p1.reshape(-1, 2).mean(axis=0))
            if len(trail_l) > 60:
                trail_l.pop(0)
        if p2 is not None and len(p2):
            trail_r.append(p2.reshape(-1, 2).mean(axis=0))
            if len(trail_r) > 60:
                trail_r.pop(0)

        vis_l, vis_r = left.copy(), right.copy()

        # Overlays are drawn at full resolution and downscaled to the
        # preview afterwards, so scale them up by exactly that factor.
        draw_scale = (eye_w / float(DISPLAY_WIDTH)) * args.draw_scale

        draw_corners(vis_l, p1, draw_scale)
        draw_corners(vis_r, p2, draw_scale)

        target = weakest_cell(conf_left)
        vis_l = draw_confidence(vis_l, conf_left, draw_scale, target)
        vis_r = draw_confidence(vis_r, conf_right, draw_scale)

        draw_track(vis_l, trail_l, p1 is not None, draw_scale)
        draw_track(vis_r, trail_r, p2 is not None, draw_scale)

        pps = px_per_square(p1, i1, spec) if p1 is not None else 0.0

        capture_now = False
        if both and auto and verdict.keep:
            # Auto-capture now respects the quality verdict, so it
            # stops filling the set with near-duplicates and views
            # that would be thrown away later anyway.
            centre = p1.reshape(-1, 2).mean(axis=0)
            if last_centre is None or np.linalg.norm(centre - last_centre) > eye_w * 0.06:
                capture_now = True

        scale = DISPLAY_WIDTH / float(eye_w)
        preview = (DISPLAY_WIDTH, int(eye_h * scale))
        disp = np.hstack((
            cv2.resize(vis_l, preview, interpolation=cv2.INTER_AREA),
            cv2.resize(vis_r, preview, interpolation=cv2.INTER_AREA),
        ))

        n1 = 0 if i1 is None else len(i1)
        n2 = 0 if i2 is None else len(i2)
        empty = int((cov_left == 0).sum())

        det_rate = 100.0 * sum(detect_history) / max(len(detect_history), 1)
        weak = int((conf_left <= 0).sum())

        if verdict.keep:
            v_text = f"KEEP  score {verdict.score:.2f}   {verdict.detail}"
            v_col = (0, 255, 0)
        else:
            v_text = f"REJECT  {verdict.reason}"
            v_col = (0, 100, 255)

        lines = [
            (f"pairs {len(captures)}   corners L{n1}/R{n2} of {spec.num_corners}"
             + ("   [WIDE]" if args.wide else ""),
             (255, 255, 255)),
            (v_text, v_col),
            (f"px/square {pps:5.1f}  " +
             ("TOO SMALL - move closer or print bigger" if 0 < pps < 12
              else "marginal" if pps < 20 else "good"),
             (0, 0, 255) if 0 < pps < 12 else (0, 165, 255) if pps < 20 else (0, 255, 0)),
            (f"confidence {GRID*GRID - weak}/{GRID*GRID} cells   "
             f"tracking {det_rate:3.0f}%" + ("   AUTO" if auto else ""),
             (0, 255, 0) if weak == 0 else (0, 165, 255)),
        ]
        for k, (text, colour) in enumerate(lines):
            cv2.putText(disp, text, (10, 26 + k * 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, colour, 2)

        cv2.imshow("NOVEX CALIBRATION", disp)
        key = cv2.waitKey(1) & 0xFF

        if key == 27:
            break
        elif key == ord(" "):
            capture_now = both
            if not both:
                print("Not captured: both eyes must see part of the board.")
        elif key in (ord("a"), ord("A")):
            auto = not auto
            print(f"auto-capture: {'ON' if auto else 'OFF'}")
        elif key in (ord("d"), ord("D")):
            if captures:
                captures.pop()
                descriptors.pop()
                cov_left[:] = 0
                conf_left[:] = 0
                conf_right[:] = 0
                for c in captures:
                    update_coverage(cov_left, c["img1"], size)
                    s = c.get("score")
                    w = s.score if s is not None else 1.0
                    update_confidence(conf_left, c["img1"], size, w)
                    update_confidence(conf_right, c["img2"], size, w)
                print(f"deleted last capture ({len(captures)} left)")
        elif key in (ord("r"), ord("R")):
            captures.clear()
            descriptors.clear()
            cov_left[:] = 0
            conf_left[:] = 0
            conf_right[:] = 0
            last_centre = None
            print("all captures discarded")
        elif key in (ord("c"), ord("C")):
            try:
                fn = (calibrate_charuco if args.board == "charuco"
                      else calibrate_chessboard)
                K1, D1, K2, D2, R, T, rms, stats, extra = fn(
                    captures, spec, size, quality_cfg=quality_cfg)
            except Exception as exc:  # noqa: BLE001
                print(f"\nCALIBRATION FAILED: {exc}\n")
                continue

            empty = int((cov_left == 0).sum())
            print(f"\n  Frame coverage: {GRID*GRID - empty}/{GRID*GRID} cells")
            if empty > 8:
                print("  WARNING: large parts of the frame were never covered. "
                      "The distortion model is unconstrained there.")

            report_quality(K1, D1, K2, D2, R, T, rms, extra, size, spec, args.out)

            baseline = write_calibration(
                args.out, spec, args.board, f"{a}x{b}", size,
                extra.get("captures", captures),
                K1, D1, K2, D2, R, T, rms, stats, args.square_size)

            report_result(baseline, args.square_size, spec)

            print(f"\nWritten: {args.out}")
            print("\nNow run:  python src/main.py")
            break

        if capture_now and both:
            if not verdict.keep:
                print(f"Not captured: {verdict.reason}")
                capture_now = False

        if capture_now and both:
            idx = len(captures)
            captures.append({"obj1": o1, "img1": p1, "ids1": i1,
                             "obj2": o2, "img2": p2, "ids2": i2,
                             "score": verdict})
            update_coverage(cov_left, p1, size)
            update_confidence(conf_left, p1, size, verdict.score)
            update_confidence(conf_right, p2, size, verdict.score)
            descriptors.append(vq.describe_view(o1, p1, size))
            last_centre = p1.reshape(-1, 2).mean(axis=0)

            cv2.imwrite(os.path.join(args.save_images, f"left_{idx:03d}.png"), left)
            cv2.imwrite(os.path.join(args.save_images, f"right_{idx:03d}.png"), right)
            print(f"captured pair {idx + 1}  score {verdict.score:.2f}  "
                  f"(L{n1}/R{n2} corners, {pps:.0f} px/square, {verdict.detail})")

    cam.stop()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
