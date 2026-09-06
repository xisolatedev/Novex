"""
Core of the Stereo Configuration Workbench - no Qt, so it can be tested.

Purpose: find the best RECTIFIED stereo configuration for a very wide
fisheye pair, judge it with real numbers rather than by eye, and export
a valid ORB-SLAM3 settings file.

The central discipline here is the separation between MEASURED and
EXPERIMENTAL values:

  * Measured values come from src/calibrate_stereo.py fitting a real
    chessboard. They are the only values with evidence behind them.
  * Experimental values are whatever you drag a slider to. They are
    perfectly legitimate for exploring - "what does 120 degrees look
    like?" - but they are guesses, and this module tracks every one of
    them so the GUI and the exported file can say so plainly.

Nothing here ever writes to config/stereo_calibration.yaml or to
config/orbslam3_stereo.yaml. The workbench is a read-only consumer of
your calibration and writes only where you tell it to.
"""

import copy
import datetime
import math
import os

import cv2
import numpy as np

from calibration import (
    StereoCalibration,
    StereoRectifier,
    FisheyeStereoModel,
    measured_fov,
)


# ==============================================================
# Parameter model
# ==============================================================

class Param:
    """One adjustable number, remembering what it was measured as."""

    __slots__ = ("key", "label", "measured", "value", "lo", "hi", "step",
                 "unit", "group", "decimals")

    def __init__(self, key, label, measured, lo, hi, step=0.1, unit="",
                 group="", decimals=4):
        self.key = key
        self.label = label
        self.measured = float(measured)
        self.value = float(measured)
        self.lo = float(lo)
        self.hi = float(hi)
        self.step = float(step)
        self.unit = unit
        self.group = group
        self.decimals = decimals

    @property
    def modified(self):
        # Tolerance scaled to the parameter's own magnitude, so a pixel
        # coordinate and a distortion coefficient are judged sensibly.
        scale = max(abs(self.measured), 1e-6)
        return abs(self.value - self.measured) > scale * 1e-9 + 1e-12

    @property
    def delta(self):
        return self.value - self.measured

    def reset(self):
        self.value = self.measured


class StereoParams:
    """Every intrinsic and extrinsic, as editable parameters.

    Built from a real calibration; `measured` on each parameter is that
    calibration's value and never changes.
    """

    def __init__(self, calib):
        self.source_calib = calib
        self.image_size = tuple(calib.image_size)
        self.params = {}

        w, h = self.image_size

        def add(*args, **kw):
            p = Param(*args, **kw)
            self.params[p.key] = p
            return p

        for eye, K, D in (("1", calib.K1, calib.D1), ("2", calib.K2, calib.D2)):
            name = "left" if eye == "1" else "right"
            g = f"Camera {eye} ({name})"
            add(f"fx{eye}", "fx", K[0, 0], 50, 2000, 0.5, "px", g, 3)
            add(f"fy{eye}", "fy", K[1, 1], 50, 2000, 0.5, "px", g, 3)
            add(f"cx{eye}", "cx", K[0, 2], -w, 2 * w, 0.5, "px", g, 3)
            add(f"cy{eye}", "cy", K[1, 2], -h, 2 * h, 0.5, "px", g, 3)
            d = np.asarray(D).reshape(-1)
            for i in range(4):
                add(f"k{i + 1}_{eye}", f"k{i + 1}", d[i], -1.0, 1.0, 0.0005,
                    "", g, 6)

        # Extrinsics. Rotation is exposed as Rodrigues components in
        # degrees, which is far easier to reason about than editing a
        # rotation matrix directly.
        rvec = cv2.Rodrigues(calib.R)[0].reshape(-1)
        g = "Stereo extrinsics"
        add("rx", "rot X", math.degrees(rvec[0]), -15, 15, 0.005, "deg", g, 5)
        add("ry", "rot Y", math.degrees(rvec[1]), -15, 15, 0.005, "deg", g, 5)
        add("rz", "rot Z", math.degrees(rvec[2]), -15, 15, 0.005, "deg", g, 5)

        T = calib.T.reshape(-1)
        add("tx", "T x", T[0] * 1000, -500, 500, 0.05, "mm", g, 4)
        add("ty", "T y", T[1] * 1000, -500, 500, 0.05, "mm", g, 4)
        add("tz", "T z", T[2] * 1000, -500, 500, 0.05, "mm", g, 4)

    # ----------------------------------------------------------
    def __getitem__(self, key):
        return self.params[key].value

    def set(self, key, value):
        self.params[key].value = float(value)

    def groups(self):
        out = {}
        for p in self.params.values():
            out.setdefault(p.group, []).append(p)
        return out

    def modified_keys(self):
        return [k for k, p in self.params.items() if p.modified]

    def reset_all(self):
        for p in self.params.values():
            p.reset()

    # ----------------------------------------------------------
    def arrays(self):
        """Current values as the matrices OpenCV wants."""
        def K(eye):
            return np.array([
                [self[f"fx{eye}"], 0.0, self[f"cx{eye}"]],
                [0.0, self[f"fy{eye}"], self[f"cy{eye}"]],
                [0.0, 0.0, 1.0],
            ], dtype=np.float64)

        def D(eye):
            return np.array([[self[f"k{i}_{eye}"]] for i in range(1, 5)],
                            dtype=np.float64)

        rvec = np.array([math.radians(self["rx"]),
                         math.radians(self["ry"]),
                         math.radians(self["rz"])], dtype=np.float64)
        R = cv2.Rodrigues(rvec)[0]

        T = np.array([[self["tx"] / 1000.0],
                      [self["ty"] / 1000.0],
                      [self["tz"] / 1000.0]], dtype=np.float64)

        return K(1), D(1), K(2), D(2), R, T

    @property
    def baseline(self):
        return float(np.linalg.norm(
            [self["tx"], self["ty"], self["tz"]])) / 1000.0

    # ----------------------------------------------------------
    def as_calibration(self):
        """A StereoCalibration carrying the CURRENT values.

        Marked so nothing downstream can mistake an experimental set of
        numbers for a measured one.
        """
        K1, D1, K2, D2, R, T = self.arrays()
        src = self.source_calib

        data = copy.deepcopy(src.raw) if isinstance(src.raw, dict) else {}
        data.update({
            "model": "fisheye",
            "image_width": int(self.image_size[0]),
            "image_height": int(self.image_size[1]),
            "camera1": {"name": "left",
                        "K": [float(v) for v in K1.reshape(-1)],
                        "D": [float(v) for v in D1.reshape(-1)]},
            "camera2": {"name": "right",
                        "K": [float(v) for v in K2.reshape(-1)],
                        "D": [float(v) for v in D2.reshape(-1)]},
            "R": [float(v) for v in R.reshape(-1)],
            "T": [float(v) for v in T.reshape(-1)],
            "baseline_m": self.baseline,
        })

        calib = StereoCalibration(data, path=src.path)
        calib.workbench_modified = self.modified_keys()
        return calib


# ==============================================================
# Output / rectification settings
# ==============================================================

FOV_PRESETS = [90.0, 100.0, 110.0, 120.0, 130.0]

RESOLUTION_PRESETS = [
    ("1280 x 720", 1280, 720),
    ("960 x 540", 960, 540),
    ("848 x 480", 848, 480),
    ("640 x 480", 640, 480),
    ("640 x 360", 640, 360),
]


class OutputConfig:
    def __init__(self, width=1280, height=720, hfov=120.0, model="rectified"):
        self.width = int(width)
        self.height = int(height)
        self.hfov = float(hfov)
        self.model = model          # "rectified" or "fisheye"
        self.zoom = 1.0             # >1 crops in, <1 pulls back
        self.cx_shift = 0.0         # principal point nudge, pixels
        self.cy_shift = 0.0
        self.fps = 30

    @property
    def size(self):
        return (self.width, self.height)

    def effective_hfov(self):
        """FOV after the zoom factor is applied."""
        f = (self.width / 2.0) / math.tan(math.radians(self.hfov) / 2.0)
        f *= self.zoom
        return math.degrees(2 * math.atan((self.width / 2.0) / f))


# ==============================================================
# Validation
# ==============================================================

def validate(params, output, module_width_mm=100.0):
    """Physical and numerical sanity. Returns [(severity, message)].

    severity is "error" for physically impossible, "warn" for
    suspicious, "info" for worth knowing.
    """
    out = []
    w, h = params.image_size

    baseline_mm = params.baseline * 1000.0
    if baseline_mm <= 0.5:
        out.append(("error",
                    f"Baseline is {baseline_mm:.2f} mm. With no separation "
                    f"there is no stereo geometry at all."))
    elif baseline_mm > module_width_mm:
        out.append(("warn",
                    f"Baseline {baseline_mm:.1f} mm exceeds the {module_width_mm:.0f} mm "
                    f"module width, so the lenses cannot physically be that far "
                    f"apart. Usually a wrong declared square size."))

    for eye in ("1", "2"):
        fx, fy = params[f"fx{eye}"], params[f"fy{eye}"]
        cx, cy = params[f"cx{eye}"], params[f"cy{eye}"]

        if fx <= 0 or fy <= 0:
            out.append(("error", f"Camera {eye}: focal length must be positive."))
            continue

        aspect = abs(fx - fy) / max(fx, fy)
        if aspect > 0.10:
            out.append(("warn",
                        f"Camera {eye}: fx and fy differ by {aspect * 100:.1f}%. "
                        f"This sensor has square 3.0 um pixels, so they should "
                        f"match closely."))

        if not (0 <= cx <= w) or not (0 <= cy <= h):
            out.append(("warn",
                        f"Camera {eye}: optical centre ({cx:.0f}, {cy:.0f}) is "
                        f"outside the image."))
        elif abs(cx - w / 2) > w * 0.2 or abs(cy - h / 2) > h * 0.2:
            out.append(("warn",
                        f"Camera {eye}: optical centre is far from the image "
                        f"centre. Possible, but unusual."))

    f1, f2 = params["fx1"], params["fx2"]
    if f1 > 0 and f2 > 0 and abs(f1 - f2) / max(f1, f2) > 0.10:
        out.append(("warn",
                    f"The two eyes disagree on focal length by "
                    f"{abs(f1 - f2) / max(f1, f2) * 100:.1f}%. They are the same "
                    f"part, so one of them is wrong."))

    rot = math.sqrt(params["rx"] ** 2 + params["ry"] ** 2 + params["rz"] ** 2)
    if rot > 5.0:
        out.append(("warn",
                    f"Relative rotation between the eyes is {rot:.2f} deg. "
                    f"Rigid stereo modules are usually well under 1 deg."))

    if abs(params["tx"]) < abs(params["ty"]) or abs(params["tx"]) < abs(params["tz"]):
        out.append(("warn",
                    "The baseline is not mostly along X. For a side-by-side "
                    "stereo pair it should be. Are the eyes swapped or the "
                    "axes mixed up?"))

    if params["tx"] > 0:
        out.append(("info",
                    "T x is positive, meaning camera 2 sits to the LEFT of "
                    "camera 1. If that is not physically true, your eyes are "
                    "swapped."))

    eff = output.effective_hfov()
    if output.model == "rectified":
        if eff >= 175:
            out.append(("error",
                        f"A pinhole image cannot represent {eff:.0f} deg - "
                        f"tan(90 deg) is infinite. Reduce the rectified FOV."))
        elif eff > 130:
            out.append(("warn",
                        f"Rectified FOV {eff:.0f} deg stretches the edges hard "
                        f"and costs centre resolution."))
        elif eff < 50:
            out.append(("warn",
                        f"Rectified FOV {eff:.0f} deg throws away most of a very "
                        f"wide lens."))

        try:
            native = measured_fov(*params.arrays()[:2], params.image_size)
            if eff > native["horizontal"] + 1.0:
                out.append(("warn",
                            f"Asking for {eff:.0f} deg from a lens that only "
                            f"measures {native['horizontal']:.0f} deg. The extra "
                            f"field does not exist and will be black border."))
        except Exception:  # noqa: BLE001
            pass

    if output.width % 2 or output.height % 2:
        out.append(("warn", "Odd output dimensions can upset some codecs."))

    return out


# ==============================================================
# Live metrics
# ==============================================================

class Metrics:
    __slots__ = ("features_left", "features_right", "matches", "inliers",
                 "match_pct", "epipolar_median", "epipolar_mean_inliers",
                 "epipolar_p95", "inlier_pct", "coverage",
                 "hfov", "vfov", "disparity_pct", "median_depth",
                 "baseline_mm", "fx", "process_ms")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k, 0.0))


class WorkbenchProcessor:
    """Builds the maps and measures how good the configuration is.

    The headline number is EPIPOLAR ERROR. After rectification a real
    3D point must land on the same image ROW in both eyes. Feature
    matches whose vertical offset is large are proof the geometry is
    wrong, and unlike a visual check it is a number you can minimise.
    ORB-SLAM3's rectified stereo matching searches along rows, so this
    error translates directly into stereo matches it can or cannot make.
    """

    def __init__(self, params, output, orb_features=1500):
        self.params = params
        self.output = output
        self.orb = cv2.ORB_create(orb_features)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.model = None
        self.error = None
        self.effective_size = tuple(output.size)
        self._build()

    # ----------------------------------------------------------
    def _build(self):
        calib = self.params.as_calibration()
        try:
            if self.output.model == "fisheye":
                # Scaling a fisheye is only valid if both axes scale
                # equally, so the height is snapped to the native
                # aspect rather than rejecting the resolution outright.
                # The user picked a width; that is the intent.
                nw, nh = calib.image_size
                w = int(self.output.width)
                h = int(round(w * nh / float(nw)))
                self.effective_size = (w, h)
                self.model = FisheyeStereoModel(calib, out_size=self.effective_size)
            else:
                self.effective_size = self.output.size
                self.model = StereoRectifier(
                    calib,
                    out_size=self.output.size,
                    target_hfov_deg=self.output.effective_hfov(),
                )
                # Optional principal-point nudge, for centring the
                # usable region inside the output frame.
                if self.output.cx_shift or self.output.cy_shift:
                    self._shift_principal_point()
            self.error = None
        except Exception as exc:  # noqa: BLE001
            self.model = None
            self.error = str(exc)

    def _shift_principal_point(self):
        m = self.model
        m.P1[0, 2] += self.output.cx_shift
        m.P1[1, 2] += self.output.cy_shift
        m.P2[0, 2] += self.output.cx_shift
        m.P2[1, 2] += self.output.cy_shift
        m.cx = float(m.P1[0, 2])
        m.cy = float(m.P1[1, 2])

        calib = m.calib
        m.map1x, m.map1y = cv2.fisheye.initUndistortRectifyMap(
            calib.K1, calib.D1, m.R1, m.P1, m.out_size, cv2.CV_16SC2)
        m.map2x, m.map2y = cv2.fisheye.initUndistortRectifyMap(
            calib.K2, calib.D2, m.R2, m.P2, m.out_size, cv2.CV_16SC2)

    # ----------------------------------------------------------
    def process(self, gray_left, gray_right, want_disparity=False):
        """Rectify a pair and measure the result."""
        import time
        t0 = time.perf_counter()

        if self.model is None:
            return None, None, None, Metrics(), []

        rl, rr = self.model.rectify(gray_left, gray_right)

        kp1, des1 = self.orb.detectAndCompute(rl, None)
        kp2, des2 = self.orb.detectAndCompute(rr, None)

        matches, dys = self._match(kp1, des1, kp2, des2)

        # Robust statistics, deliberately.
        #
        # Repetitive texture produces a tail of gross mismatches whose
        # dy is enormous, and a MEAN over that tail measures the
        # ambiguity of the scene rather than the quality of the
        # rectification: on real frames here the mean read 16.7 px
        # while the median read 0.00 px, and a 1 degree induced
        # rotation error barely moved it.
        #
        # So the headline numbers are the MEDIAN vertical offset and
        # the fraction of matches within a pixel and a half. Those move
        # sharply when the geometry is actually wrong, which is the
        # entire point of the metric.
        ady = np.abs(dys) if len(dys) else np.zeros(0)
        inlier_mask = ady < 1.5
        inliers = int(inlier_mask.sum())

        # Coverage: fraction of output pixels that came from real sensor
        # data rather than black border.
        coverage = float((rl > 0).mean()) if rl.size else 0.0

        disparity = None
        disp_pct = 0.0
        median_depth = 0.0
        if want_disparity:
            disparity, disp_pct, median_depth = self._disparity(rl, rr)

        try:
            if self.output.model == "fisheye":
                fov = measured_fov(self.model.K1, self.model.calib.D1,
                                   self.effective_size)
                hfov, vfov = fov["horizontal"], fov["vertical"]
            else:
                hfov = math.degrees(
                    2 * math.atan(self.output.width / (2 * self.model.fx)))
                vfov = math.degrees(
                    2 * math.atan(self.output.height / (2 * self.model.fy)))
        except Exception:  # noqa: BLE001
            hfov = vfov = 0.0

        m = Metrics(
            features_left=len(kp1),
            features_right=len(kp2),
            matches=len(matches),
            inliers=inliers,
            match_pct=100.0 * len(matches) / max(len(kp1), 1),
            epipolar_median=float(np.median(ady)) if len(ady) else 0.0,
            epipolar_mean_inliers=(float(ady[inlier_mask].mean())
                                   if inliers else 0.0),
            epipolar_p95=float(np.percentile(ady, 95)) if len(ady) else 0.0,
            inlier_pct=100.0 * inliers / max(len(matches), 1),
            coverage=coverage * 100.0,
            hfov=hfov, vfov=vfov,
            disparity_pct=disp_pct,
            median_depth=median_depth,
            baseline_mm=self.params.baseline * 1000.0,
            fx=getattr(self.model, "fx", 0.0),
            process_ms=(time.perf_counter() - t0) * 1000.0,
        )

        return rl, rr, disparity, m, matches

    # ----------------------------------------------------------
    def _match(self, kp1, des1, kp2, des2):
        """Stereo feature matches, filtered to be worth measuring.

        Every filter here removes a class of match that would corrupt
        the epipolar statistic rather than inform it:

          mutual nearest neighbour - a match both eyes agree on
          Lowe ratio 0.7          - rejects ambiguous descriptors
          Hamming cap             - rejects weak descriptor matches
          octave consistency      - the same surface should be found at
                                    a similar scale in both eyes
          positive, bounded disparity - in a rectified pair the right
                                    match must lie to the LEFT, and a
                                    disparity larger than the search
                                    range is not physical
        """
        if des1 is None or des2 is None or len(kp1) < 2 or len(kp2) < 2:
            return [], np.zeros(0)

        m12 = self.matcher.knnMatch(des1, des2, k=2)
        m21 = self.matcher.knnMatch(des2, des1, k=2)

        best21 = {}
        for pair in m21:
            if pair:
                best21[pair[0].queryIdx] = pair[0].trainIdx

        max_disp = max(64, self.effective_size[0] // 4)

        matches, dys = [], []
        for pair in m12:
            if len(pair) < 2:
                continue
            a, b = pair
            if a.distance >= 0.7 * b.distance or a.distance > 50:
                continue
            if best21.get(a.trainIdx, -1) != a.queryIdx:
                continue
            if abs(kp1[a.queryIdx].octave - kp2[a.trainIdx].octave) > 1:
                continue

            p1 = kp1[a.queryIdx].pt
            p2 = kp2[a.trainIdx].pt
            disp = p1[0] - p2[0]
            if disp <= 0 or disp > max_disp:
                continue

            matches.append((p1, p2))
            dys.append(p1[1] - p2[1])

        return matches, np.asarray(dys)

    # ----------------------------------------------------------
    def _disparity(self, rl, rr, downscale=2):
        """Dense disparity, for a visual check that geometry is sane.

        This is a diagnostic only - ORB-SLAM3 never uses it. It is
        computed on a downscaled pair because SGBM at full resolution
        costs far more than this tool needs.
        """
        small_l = cv2.resize(rl, (rl.shape[1] // downscale, rl.shape[0] // downscale))
        small_r = cv2.resize(rr, (rr.shape[1] // downscale, rr.shape[0] // downscale))

        sgbm = cv2.StereoSGBM_create(
            minDisparity=0,
            numDisparities=64,
            blockSize=7,
            P1=8 * 7 * 7,
            P2=32 * 7 * 7,
            uniquenessRatio=10,
            speckleWindowSize=100,
            speckleRange=2,
        )
        disp = sgbm.compute(small_l, small_r).astype(np.float32) / 16.0

        valid = disp > 0.5
        pct = float(valid.mean() * 100.0)

        median_depth = 0.0
        fx = getattr(self.model, "fx", 0.0) / downscale
        b = self.params.baseline
        if valid.any() and fx > 0 and b > 0:
            depths = fx * b / disp[valid]
            depths = depths[(depths > 0.05) & (depths < 50)]
            if len(depths):
                median_depth = float(np.median(depths))

        return disp, pct, median_depth


# ==============================================================
# Export
# ==============================================================

def export_orbslam3(path, params, output, notes=""):
    """Write a complete ORB-SLAM3 settings file for the current config.

    The file is self-describing: it records which values came from the
    calibration and which were adjusted by hand, so an experimental
    configuration can never be mistaken for a measured one later.
    """
    calib = params.as_calibration()
    modified = params.modified_keys()
    sidecar = os.path.splitext(path)[0] + ".novex.yaml"

    if output.model == "fisheye":
        model = FisheyeStereoModel(calib, out_size=output.size)
    else:
        model = StereoRectifier(calib, out_size=output.size,
                                target_hfov_deg=output.effective_hfov())

    model.write_orbslam3_settings(
        path, fps=output.fps,
        orb={"n_features": 1200, "scale_factor": 1.2, "n_levels": 8,
             "ini_th_fast": 12, "min_th_fast": 5},
        th_depth=60.0,
    )

    header = [
        "#" + "=" * 68,
        "# EXPORTED BY THE NOVEX STEREO WORKBENCH",
        f"# {datetime.datetime.now().isoformat(timespec='seconds')}",
        "#",
        f"# Source calibration : {calib.path}",
        f"# Camera model       : {output.model}",
        f"# Output resolution  : {output.width} x {output.height}",
    ]
    if output.model == "rectified":
        header.append(f"# Rectified FOV      : {output.effective_hfov():.2f} deg horizontal")
    header += [
        f"# Baseline           : {params.baseline * 1000:.3f} mm",
        "#",
    ]

    if modified:
        header += [
            "# " + "!" * 66,
            "# WARNING: THIS CONFIGURATION CONTAINS HAND-ADJUSTED VALUES.",
            "# " + "!" * 66,
            "# The parameters below were changed from the measured",
            "# calibration. They are experimental, not measured, and any",
            "# distance derived from them inherits that uncertainty:",
            "#",
        ]
        for key in sorted(modified):
            p = params.params[key]
            header.append(
                f"#   {p.group:22} {p.label:6} "
                f"measured {p.measured:.6f} -> set {p.value:.6f} {p.unit}")
        header.append("#")
    else:
        header += [
            "# All camera parameters are exactly as measured by",
            "# src/calibrate_stereo.py. Only the output geometry",
            "# (resolution / field of view) was chosen here.",
            "#",
        ]

    if notes:
        header += ["# Notes:"] + [f"#   {ln}" for ln in notes.splitlines()] + ["#"]

    header.append(f"# Pipeline sidecar   : {os.path.basename(sidecar)}")
    header.append("#   (lets main.py --settings rebuild the identical pipeline)")
    header.append("#" + "=" * 68)
    header.append("")

    # Sidecar.
    #
    # An ORB-SLAM3 "Rectified" settings file contains only the
    # RECTIFIED intrinsics - by design, because that is all ORB-SLAM3
    # needs. But the application also has to REBUILD the remap that
    # produced those images, and for that it needs the raw fisheye
    # K/D/R/T plus the chosen output geometry, none of which appear in
    # the ORB-SLAM3 file.
    #
    # So a companion file is written next to it. main.py --settings
    # picks it up automatically, which is what makes the export usable
    # without hand-converting anything.
    import yaml as _yaml
    K1, D1, K2, D2, R, T = params.arrays()
    with open(sidecar, "w") as f:
        _yaml.safe_dump({
            "novex_pipeline_version": 1,
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "source_calibration": calib.path,
            "camera_model": output.model,
            "output": {
                "width": int(output.width),
                "height": int(output.height),
                "hfov_deg": float(output.effective_hfov()),
                "zoom": float(output.zoom),
                "cx_shift": float(output.cx_shift),
                "cy_shift": float(output.cy_shift),
                "fps": int(output.fps),
            },
            "experimental_parameters": sorted(modified),
            "values_are_measured": not modified,
            "calibration": {
                "model": "fisheye",
                "image_width": int(params.image_size[0]),
                "image_height": int(params.image_size[1]),
                "square_size_m": float(getattr(calib, "square_size", 0.0)),
                "num_pairs": int(getattr(calib, "num_pairs", 0)),
                "camera1": {"name": "left",
                            "K": [float(v) for v in K1.reshape(-1)],
                            "D": [float(v) for v in D1.reshape(-1)]},
                "camera2": {"name": "right",
                            "K": [float(v) for v in K2.reshape(-1)],
                            "D": [float(v) for v in D2.reshape(-1)]},
                "R": [float(v) for v in R.reshape(-1)],
                "T": [float(v) for v in T.reshape(-1)],
                "baseline_m": float(params.baseline),
                "rms": getattr(calib, "rms", {}) or {},
            },
        }, f, sort_keys=False, default_flow_style=False)

    with open(path) as f:
        body = f.read()

    # The %YAML directive has to stay on the first line.
    lines = body.splitlines()
    first, rest = lines[0], lines[1:]

    with open(path, "w") as f:
        f.write(first + "\n")
        f.write("\n".join(header) + "\n")
        f.write("\n".join(rest) + "\n")

    return path
