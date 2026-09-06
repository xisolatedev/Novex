"""
Calibration for the Novex ORB-SLAM3 test.

READ THIS BEFORE CHANGING ANYTHING HERE.

There are two completely different things in this file and conflating
them is the single easiest way to get meaningless SLAM output:

1. TEMPORARY LENS MODEL  (TemporaryLensModel)
   The hand-tuned "source FOV / K1..K4 / centre" values produced by
   dragging sliders until straight lines look straight. They are a
   VISUAL correction only. They are not metric, they were not fitted
   to any known geometry, and above all they say NOTHING about where
   the two lenses are relative to each other. They cannot produce a
   baseline, so they cannot produce metric stereo depth, so ORB-SLAM3
   cannot use them for stereo. They are used for on-screen preview
   and nothing else.

2. REAL STEREO CALIBRATION  (StereoCalibration)
   Produced by src/calibrate_stereo.py from photographs of a
   chessboard of known square size. This yields, per eye, the fisheye
   intrinsics and distortion, plus the rigid transform between the
   two eyes - and therefore the baseline in metres. ORB-SLAM3 stereo
   needs all of it.

If the real calibration is absent, the application says
CALIBRATION REQUIRED and refuses to start SLAM. It does not guess.
"""

import math
import os
import datetime

import cv2
import numpy as np
import yaml


# ==============================================================
# 1. Temporary, visual-only lens model
# ==============================================================

class TemporaryLensModel:
    """The manual slider values. Preview only - never fed to SLAM.

    Implements the same equidistant-fisheye-to-perspective mapping as
    the existing Novex fast_camera.py, so the preview looks identical
    to what you already tuned.
    """

    IS_METRIC = False

    def __init__(
        self,
        source_fov=112.0,
        k1=0.141,
        k2=0.0135,
        k3=0.0,
        k4=0.003,
        center_x=0.0,
        center_y=0.0,
        virtual_fov=99.0,
    ):
        self.source_fov = float(source_fov)
        self.k = (float(k1), float(k2), float(k3), float(k4))
        self.center = (float(center_x), float(center_y))
        self.virtual_fov = float(virtual_fov)

    def build_maps(self, src_w, src_h, out_w, out_h):
        """Precompute remap tables once. cv2.remap then costs ~1 ms."""
        focal = (out_w / 2.0) / math.tan(math.radians(self.virtual_fov) / 2.0)

        px, py = np.meshgrid(np.arange(out_w), np.arange(out_h))

        x = (px.astype(np.float32) - out_w / 2.0) / focal
        y = (py.astype(np.float32) - out_h / 2.0) / focal
        z = np.ones_like(x)

        norm = np.sqrt(x * x + y * y + z * z)
        x /= norm
        y /= norm
        z /= norm

        theta = np.arccos(np.clip(z, -1.0, 1.0))

        t2 = theta * theta
        k1, k2, k3, k4 = self.k
        distorted = theta * (
            1.0 + k1 * t2 + k2 * t2 ** 2 + k3 * t2 ** 3 + k4 * t2 ** 4
        )

        fisheye_f = min(src_w, src_h) / math.radians(self.source_fov)
        radius = fisheye_f * distorted

        xy = np.sqrt(x * x + y * y)
        safe_xy = np.maximum(xy, 1e-8)

        cx = src_w / 2.0 + self.center[0] * src_w
        cy = src_h / 2.0 + self.center[1] * src_h

        map_x = cx + radius * x / safe_xy
        map_y = cy + radius * y / safe_xy

        centre_ray = xy < 1e-8
        map_x[centre_ray] = cx
        map_y[centre_ray] = cy

        outside = theta > math.radians(self.source_fov / 2.0)
        map_x[outside] = -1
        map_y[outside] = -1

        return map_x.astype(np.float32), map_y.astype(np.float32)

    def describe(self):
        return (
            f"TEMPORARY visual lens model - NOT a stereo calibration\n"
            f"  source FOV : {self.source_fov}\n"
            f"  k1..k4     : {self.k}\n"
            f"  centre     : {self.center}\n"
            f"  virtual FOV: {self.virtual_fov}\n"
            f"  baseline   : UNKNOWN (this model cannot provide one)"
        )


# ==============================================================
# 2. Real stereo calibration
# ==============================================================

def kb_theta_from_theta_d(theta_d, D, iterations=20):
    """Invert the Kannala-Brandt polynomial: recover the true incidence
    angle theta from the distorted radius theta_d.

    theta_d = theta * (1 + k1*t^2 + k2*t^4 + k3*t^6 + k4*t^8)

    There is no closed form, so Newton's method is used. Needed to work
    out what field of view a calibration actually describes.
    """
    k1, k2, k3, k4 = np.asarray(D, dtype=np.float64).reshape(-1)[:4]

    theta = float(theta_d)
    for _ in range(iterations):
        t2 = theta * theta
        t4 = t2 * t2
        t6 = t4 * t2
        t8 = t6 * t2
        f = theta * (1 + k1 * t2 + k2 * t4 + k3 * t6 + k4 * t8) - theta_d
        df = 1 + 3 * k1 * t2 + 5 * k2 * t4 + 7 * k3 * t6 + 9 * k4 * t8
        if abs(df) < 1e-12:
            break
        theta -= f / df

    return theta


def measured_fov(K, D, size):
    """The field of view a calibration actually describes, in degrees.

    Returns dict with horizontal, vertical and diagonal FOV. This is
    the honest answer to "how wide is my lens?" - it comes from the
    fitted model rather than from the number on the box, which is
    usually the diagonal and usually optimistic.
    """
    K = np.asarray(K, dtype=np.float64)
    w, h = int(size[0]), int(size[1])

    fx, fy = K[0, 0], K[1, 1]
    cx, cy = K[0, 2], K[1, 2]

    def theta_at(u, v):
        xp = (u - cx) / fx
        yp = (v - cy) / fy
        return kb_theta_from_theta_d(math.hypot(xp, yp), D)

    horizontal = theta_at(0, cy) + theta_at(w - 1, cy)
    vertical = theta_at(cx, 0) + theta_at(cx, h - 1)
    diagonal = theta_at(0, 0) + theta_at(w - 1, h - 1)

    return {
        "horizontal": math.degrees(horizontal),
        "vertical": math.degrees(vertical),
        "diagonal": math.degrees(diagonal),
    }


class CalibrationError(Exception):
    pass


class StereoCalibration:
    """A real, measured fisheye stereo calibration.

    Everything here comes from calibrate_stereo.py fitting a
    chessboard of known physical square size. Nothing is assumed.
    """

    REQUIRED = [
        "image_width",
        "image_height",
        "camera1",
        "camera2",
        "R",
        "T",
    ]

    def __init__(self, data, path=None):
        self.path = path
        self.raw = data

        self.image_size = (int(data["image_width"]), int(data["image_height"]))

        self.K1 = np.array(data["camera1"]["K"], dtype=np.float64).reshape(3, 3)
        self.D1 = np.array(data["camera1"]["D"], dtype=np.float64).reshape(4, 1)
        self.K2 = np.array(data["camera2"]["K"], dtype=np.float64).reshape(3, 3)
        self.D2 = np.array(data["camera2"]["D"], dtype=np.float64).reshape(4, 1)

        self.R = np.array(data["R"], dtype=np.float64).reshape(3, 3)
        self.T = np.array(data["T"], dtype=np.float64).reshape(3, 1)

        self.model = data.get("model", "fisheye")

        # Baseline is MEASURED - the length of the translation between
        # the two optical centres, in the units of the chessboard
        # square size that was given during calibration (metres).
        self.baseline = float(np.linalg.norm(self.T))

        self.rms = data.get("rms", {})
        self.num_pairs = int(data.get("num_pairs", 0))
        self.square_size = float(data.get("square_size_m", 0.0))
        self.created = data.get("created", "unknown")

    # ----------------------------------------------------------
    @classmethod
    def load(cls, path):
        if not os.path.exists(path):
            return None

        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise CalibrationError(f"{path} is not a valid calibration file")

        missing = [k for k in cls.REQUIRED if k not in data]
        if missing:
            raise CalibrationError(
                f"{path} is missing required fields: {', '.join(missing)}"
            )

        return cls(data, path=path)

    def save(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            yaml.safe_dump(self.raw, f, sort_keys=False, default_flow_style=False)

    # ----------------------------------------------------------
    def sanity_warnings(self):
        """Things that are suspicious but not fatal."""
        warn = []

        if self.baseline <= 0.0:
            warn.append("Baseline is zero - the calibration is degenerate.")
        elif self.baseline < 0.01:
            warn.append(
                f"Baseline is {self.baseline * 1000:.1f} mm, which is very small. "
                f"Check that square_size was given in METRES."
            )
        elif self.baseline > 0.095:
            warn.append(
                f"Baseline is {self.baseline * 1000:.0f} mm. The GXIVISION-LSM22100 "
                f"module is only 100 mm wide, so the lens separation cannot exceed "
                f"that. Either square_size was wrong, or the fit did not converge."
            )

        if self.T[0, 0] > 0:
            warn.append(
                "T[0] is positive, which means camera 2 sits to the LEFT of "
                "camera 1. Your eyes are probably swapped: set "
                "camera.swap_eyes: true in config/camera.yaml."
            )

        try:
            fov = measured_fov(self.K1, self.D1, self.image_size)
            if fov["diagonal"] < fov["horizontal"]:
                warn.append(
                    f"The fitted model gives a diagonal FOV ({fov['diagonal']:.0f} deg) "
                    f"SMALLER than the horizontal ({fov['horizontal']:.0f} deg), which "
                    f"is geometrically impossible. The distortion polynomial is being "
                    f"extrapolated past where it was constrained - typical when the "
                    f"frame corners were never covered. Usable, but do not trust the "
                    f"extreme corners."
                )
        except Exception:  # noqa: BLE001
            pass

        stereo_rms = self.rms.get("stereo")
        if stereo_rms is not None and stereo_rms > 1.0:
            warn.append(
                f"Stereo reprojection RMS is {stereo_rms:.2f} px. Above ~1 px the "
                f"calibration is poor and SLAM will struggle. Recapture with more "
                f"varied chessboard poses."
            )

        # Both eyes are the same part on the same board, so their focal
        # lengths should agree closely. A large disagreement means one
        # eye's fit did not converge - usually too few views, or poor
        # coverage on that side.
        fx1, fx2 = self.K1[0, 0], self.K2[0, 0]
        if fx1 > 0 and fx2 > 0:
            spread = abs(fx1 - fx2) / max(fx1, fx2)
            if spread > 0.10:
                warn.append(
                    f"The two eyes disagree on focal length by {spread * 100:.1f}% "
                    f"(left fx {fx1:.1f}, right fx {fx2:.1f}). They are identical "
                    f"lenses, so one of the fits is bad. Recapture with more "
                    f"coverage on the weaker eye."
                )

        for name, K in (("left", self.K1), ("right", self.K2)):
            aspect = abs(K[0, 0] - K[1, 1]) / max(K[0, 0], K[1, 1], 1e-9)
            if aspect > 0.10:
                warn.append(
                    f"The {name} eye has fx and fy differing by {aspect * 100:.1f}%. "
                    f"Square pixels are expected (this sensor is 3.0 x 3.0 um), so "
                    f"this points to an unstable fit."
                )

        if self.num_pairs and self.num_pairs < 15:
            warn.append(
                f"Only {self.num_pairs} chessboard pairs were used. 20-40 is "
                f"advisable for a stable fisheye fit."
            )

        return warn

    def describe(self):
        lines = [
            f"REAL stereo calibration ({self.model})",
            f"  source      : {self.path}",
            f"  created     : {self.created}",
            f"  image size  : {self.image_size[0]}x{self.image_size[1]} per eye",
            f"  pairs used  : {self.num_pairs}",
            f"  square size : {self.square_size * 1000:.1f} mm",
            f"  BASELINE    : {self.baseline * 1000:.2f} mm  (measured)",
        ]
        for k, v in self.rms.items():
            lines.append(f"  RMS {k:<8}: {v:.4f} px")

        try:
            fov = measured_fov(self.K1, self.D1, self.image_size)
            lines.append(
                f"  MEASURED FOV: {fov['horizontal']:.1f} deg horizontal, "
                f"{fov['vertical']:.1f} vertical, {fov['diagonal']:.1f} diagonal"
            )
        except Exception:  # noqa: BLE001
            pass

        return "\n".join(lines)


# ==============================================================
# 3. Rectification - fisheye pair -> ideal pinhole stereo pair
# ==============================================================

class StereoRectifier:
    """Turns a real fisheye stereo calibration into rectified images.

    ORB-SLAM3's stereo mode wants an ideal rectified pinhole pair:
    same intrinsics in both eyes, no distortion, epipolar lines along
    image rows. Our lens is a wide fisheye, and ORB-SLAM3's own
    rectification path only handles the pinhole radtan model, so the
    fisheye rectification is done here with cv2.fisheye and handed to
    ORB-SLAM3 as Camera.type "Rectified".

    The remap tables are built once and reused, so the per-frame cost
    is two cv2.remap calls.
    """

    def __init__(self, calib, out_size=None, balance=0.0, fov_scale=1.0,
                 target_hfov_deg=100.0):
        self.calib = calib
        self.balance = float(balance)
        self.fov_scale = float(fov_scale)
        self.target_hfov_deg = (
            float(target_hfov_deg) if target_hfov_deg else None
        )

        self.out_size = tuple(out_size) if out_size else tuple(calib.image_size)

        w, h = self.out_size

        # cv2.fisheye.stereoRectify gives us the rotations that make
        # the two image planes coplanar and row-aligned, plus the new
        # projection matrices P1/P2.
        R1, R2, P1, P2, Q = cv2.fisheye.stereoRectify(
            calib.K1, calib.D1,
            calib.K2, calib.D2,
            calib.image_size,
            calib.R, calib.T,
            cv2.CALIB_ZERO_DISPARITY,
            newImageSize=self.out_size,
            balance=self.balance,
            fov_scale=self.fov_scale,
        )

        self.R1, self.R2 = R1, R2
        self.Q = Q

        # ------------------------------------------------------
        # Choose the rectified intrinsics ourselves.
        #
        # cv2.fisheye.stereoRectify picks the new focal length from
        # `balance`, and on a very wide lens that choice degenerates:
        # measured on this 168 deg camera, balance=0 returned fx = 0.0
        # and a nominal 180 deg rectified field, which is not a usable
        # image at all (a pinhole cannot represent 180 deg - tan(90) is
        # infinite).
        #
        # R1/R2 are the part that actually matters, and they depend
        # only on R and T, so they stay. The projection matrices are
        # rebuilt to hit a chosen horizontal field of view, which makes
        # the result predictable instead of a side effect of `balance`.
        #
        # Rows stay aligned because both eyes get the same focal length
        # and the same cy; the baseline enters only through P2[0,3].
        # ------------------------------------------------------
        if self.target_hfov_deg:
            f = (w / 2.0) / math.tan(math.radians(self.target_hfov_deg) / 2.0)

            P1 = np.array([[f, 0.0, w / 2.0, 0.0],
                           [0.0, f, h / 2.0, 0.0],
                           [0.0, 0.0, 1.0, 0.0]], dtype=np.float64)

            P2 = P1.copy()
            # P2[0,3] = -f * baseline is the standard rectified stereo
            # convention, and is what ORB-SLAM3's Stereo.b encodes.
            P2[0, 3] = -f * calib.baseline

        self.P1, self.P2 = P1, P2

        self.map1x, self.map1y = cv2.fisheye.initUndistortRectifyMap(
            calib.K1, calib.D1, R1, P1, self.out_size, cv2.CV_16SC2
        )
        self.map2x, self.map2y = cv2.fisheye.initUndistortRectifyMap(
            calib.K2, calib.D2, R2, P2, self.out_size, cv2.CV_16SC2
        )

        # Rectified intrinsics. Both eyes share these by construction.
        self.fx = float(P1[0, 0])
        self.fy = float(P1[1, 1])
        self.cx = float(P1[0, 2])
        self.cy = float(P1[1, 2])

        # Baseline recovered from the rectified projection matrices.
        # P2[0,3] = -fx * baseline. This is a cross-check against
        # |T| from the calibration; they must agree.
        self.baseline = abs(float(P2[0, 3]) / self.fx) if self.fx else 0.0

    def rectify(self, left, right):
        """Rectify one synchronized pair. Both images are remapped with
        precomputed 16SC2 tables, which is the fastest cv2.remap path."""
        rl = cv2.remap(left, self.map1x, self.map1y, cv2.INTER_LINEAR)
        rr = cv2.remap(right, self.map2x, self.map2y, cv2.INTER_LINEAR)
        return rl, rr

    def consistency_warnings(self):
        warn = []

        # A pinhole image cannot represent a very wide field. Past
        # ~120 degrees the edge pixels are stretched so hard that ORB
        # finds nothing usable there, while the centre - where the
        # features actually are - loses resolution.
        hfov = math.degrees(
            2 * math.atan(self.out_size[0] / (2 * self.fx))
        ) if self.fx > 0 else 0.0

        if hfov > 130:
            warn.append(
                f"Rectified horizontal FOV is {hfov:.0f} deg. A pinhole image "
                f"cannot usefully hold that much: the edges are extremely "
                f"stretched and the centre loses resolution. Lower "
                f"rectification.fov_scale in config/camera.yaml until this is "
                f"90-110 deg."
            )
        elif hfov < 55:
            warn.append(
                f"Rectified horizontal FOV is only {hfov:.0f} deg. You are "
                f"throwing away most of a wide lens, which costs tracking "
                f"robustness. Raise rectification.fov_scale, or raise "
                f"rectification.balance towards 1."
            )

        drift = abs(self.baseline - self.calib.baseline)
        if self.calib.baseline > 0 and drift / self.calib.baseline > 0.02:
            warn.append(
                f"Rectified baseline ({self.baseline * 1000:.2f} mm) disagrees with "
                f"the calibrated baseline ({self.calib.baseline * 1000:.2f} mm) by "
                f"more than 2%. The calibration may be unstable."
            )
        return warn

    def describe(self):
        return (
            f"Rectified stereo geometry\n"
            f"  output size : {self.out_size[0]}x{self.out_size[1]}\n"
            f"  fx, fy      : {self.fx:.2f}, {self.fy:.2f}\n"
            f"  cx, cy      : {self.cx:.2f}, {self.cy:.2f}\n"
            f"  baseline    : {self.baseline * 1000:.2f} mm\n"
            f"  bf          : {self.fx * self.baseline:.4f}\n"
            f"  horiz FOV   : {2 * math.degrees(math.atan(self.out_size[0] / (2 * self.fx))):.1f} deg"
        )

    # ----------------------------------------------------------
    def write_orbslam3_settings(self, path, fps, orb=None, th_depth=40.0):
        """Emit the ORB-SLAM3 settings file for this exact geometry.

        This file is GENERATED. Editing it by hand is pointless -
        regenerate it by re-running calibration. ORB-SLAM3 parses it
        with cv2.FileStorage, so it needs the %YAML:1.0 header and
        the File.version key.
        """
        orb = orb or {}
        w, h = int(self.out_size[0]), int(self.out_size[1])

        # ORB-SLAM3 reads these with readParameter<int> and calls
        # exit(-1) - killing the whole process - if the YAML holds a
        # real number instead. "Camera.fps: 30.0" is fatal; it must be
        # "Camera.fps: 30". Coerce every int-typed key explicitly.
        fps_i = max(1, int(round(float(fps))))

        n_features = int(orb.get("n_features", 1200))
        n_levels = int(orb.get("n_levels", 8))
        ini_th_fast = int(orb.get("ini_th_fast", 20))
        min_th_fast = int(orb.get("min_th_fast", 7))
        scale_factor = float(orb.get("scale_factor", 1.2))

        text = f"""%YAML:1.0

#--------------------------------------------------------------------
# GENERATED FILE - do not edit by hand.
#
# Written by Novex src/calibration.py from
#   {self.calib.path}
# on {datetime.datetime.now().isoformat(timespec='seconds')}
#
# The images ORB-SLAM3 receives have ALREADY been undistorted and
# rectified by StereoRectifier using the fisheye model, so from
# ORB-SLAM3's point of view this is an ideal pinhole stereo pair with
# zero distortion. That is what Camera.type "Rectified" means.
#--------------------------------------------------------------------
File.version: "1.0"

Camera.type: "Rectified"

# Rectified intrinsics, identical for both eyes by construction
# (taken from P1 of cv2.fisheye.stereoRectify).
Camera1.fx: {self.fx:.6f}
Camera1.fy: {self.fy:.6f}
Camera1.cx: {self.cx:.6f}
Camera1.cy: {self.cy:.6f}

Camera.width: {w}
Camera.height: {h}
Camera.fps: {fps_i}

# Images are fed as grayscale, so this is ignored.
Camera.RGB: 0

# MEASURED baseline in metres, from the chessboard stereo calibration.
Stereo.b: {self.baseline:.8f}

# Points closer than ThDepth * baseline are treated as "close" and can
# be triangulated from a single stereo pair. Beyond that they are
# treated like monocular observations.
Stereo.ThDepth: {th_depth:.1f}

#--------------------------------------------------------------------
# ORB extractor
#--------------------------------------------------------------------
ORBextractor.nFeatures: {n_features}
ORBextractor.scaleFactor: {scale_factor}
ORBextractor.nLevels: {n_levels}
ORBextractor.iniThFAST: {ini_th_fast}
ORBextractor.minThFAST: {min_th_fast}

#--------------------------------------------------------------------
# Viewer
#
# Only used if ORB-SLAM3's own Pangolin viewer is enabled with
# --orbslam-viewer. The Novex GUI draws its own 3D view.
#--------------------------------------------------------------------
Viewer.KeyFrameSize: 0.05
Viewer.KeyFrameLineWidth: 1.0
Viewer.GraphLineWidth: 0.9
Viewer.PointSize: 2.0
Viewer.CameraSize: 0.08
Viewer.CameraLineWidth: 3.0
Viewer.ViewpointX: 0.0
Viewer.ViewpointY: -0.7
Viewer.ViewpointZ: -1.8
Viewer.ViewpointF: 500.0
"""

        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

        return path


# ==============================================================
# 3b. Native fisheye stereo (no rectification at all)
# ==============================================================

class FisheyeStereoModel:
    """Feed ORB-SLAM3 the RAW fisheye images, unrectified.

    Rectifying a ~168 degree lens into a pinhole image throws away most
    of the field of view - the default 100 degree target keeps well
    under half of it. The discarded periphery is exactly where features
    move fastest under rotation, so it is what most strongly constrains
    the rotation estimate. Cropping it away is a plausible cause of
    rotational drift.

    ORB-SLAM3 supports the Kannala-Brandt model natively
    (Camera.type "KannalaBrandt8"), which is what TUM-VI uses with 195
    degree lenses. In this mode the raw images go straight in:

      * the full field of view is kept
      * no resampling, so corners are not softened by interpolation
      * the ~13 ms per frame spent on cv2.remap disappears

    What it does NOT give you, and this is worth being clear about:

      * It is still SPARSE. ORB-SLAM3 computes depth at ORB keypoints
        only, never per pixel. Not rectifying does not produce a dense
        depth map, and cannot.
      * Depth still only exists where the two lenses OVERLAP. Features
        outside the overlap are treated as monocular: useful for
        rotation and for the map, but carrying no stereo depth.
      * Dense per-pixel depth needs a rectified pair, because block
        matchers search along image rows. That is the opposite
        requirement, so the two goals genuinely pull apart.
    """

    def __init__(self, calib, out_size=None, overlap_margin=0.0):
        self.calib = calib
        self.native_size = tuple(calib.image_size)

        # Downscaling is mathematically clean for this model, which is
        # what lets the speed profiles work without rectifying.
        #
        # Kannala-Brandt distortion is a function of the INCIDENCE
        # ANGLE theta, not of pixel size. Halving the image therefore
        # halves fx, fy, cx, cy and leaves k1..k4 completely unchanged,
        # and the field of view is identical. Nothing is cropped - the
        # whole fisheye circle is still there, just sampled less finely.
        self.image_size = tuple(out_size) if out_size else self.native_size

        self.scale = self.image_size[0] / float(self.native_size[0])
        vscale = self.image_size[1] / float(self.native_size[1])

        if abs(self.scale - vscale) > 1e-3:
            raise CalibrationError(
                f"Fisheye output size {self.image_size} does not preserve the "
                f"aspect ratio of {self.native_size}. Scaling the axes "
                f"differently would change the lens model."
            )

        self.K1 = calib.K1.copy()
        self.K2 = calib.K2.copy()
        if abs(self.scale - 1.0) > 1e-9:
            for K in (self.K1, self.K2):
                K[0, 0] *= self.scale
                K[1, 1] *= self.scale
                K[0, 2] *= self.scale
                K[1, 2] *= self.scale

        # Tlr: the pose of camera 2 expressed in camera 1's frame.
        #
        # Calibration gives X2 = R*X1 + T, so X1 = R^T*X2 - R^T*T,
        # which makes Tlr = [R^T | -R^T T]. ORB-SLAM3 calls this
        # Stereo.T_c1_c2 and uses it as X_left = Tlr * X_right.
        R = calib.R
        T = calib.T.reshape(3)

        self.Tlr = np.eye(4, dtype=np.float64)
        self.Tlr[:3, :3] = R.T
        self.Tlr[:3, 3] = -R.T @ T

        self.baseline = float(np.linalg.norm(self.Tlr[:3, 3]))
        self.overlap = self._compute_overlap(margin=overlap_margin)

    # ----------------------------------------------------------
    def _compute_overlap(self, margin=0.0, depth=3.0, samples=64):
        """Column range in each image that the other camera can also see.

        ORB-SLAM3 restricts stereo matching to this band
        (KannalaBrandt8::mvLappingArea). Rather than guessing, points
        are placed across the left camera's field at a typical room
        depth, projected into both cameras, and the columns where they
        land in both are taken as the overlap.
        """
        w, h = self.image_size
        K1, D1 = self.K1, self.calib.D1
        K2, D2 = self.K2, self.calib.D2

        # Sample a grid of pixels in the left image, back-project to a
        # sphere at `depth`, then project into the right image.
        us = np.linspace(0, w - 1, samples)
        vs = np.linspace(0, h - 1, max(8, samples // 4))
        grid = np.stack(np.meshgrid(us, vs), axis=-1).reshape(-1, 1, 2)

        undist = cv2.fisheye.undistortPoints(grid.astype(np.float64), K1, D1)
        xy = undist.reshape(-1, 2)
        rays = np.concatenate([xy, np.ones((len(xy), 1))], axis=1)
        rays /= np.linalg.norm(rays, axis=1, keepdims=True)
        pts1 = rays * depth

        # Into camera 2: X2 = R*X1 + T
        pts2 = pts1 @ self.calib.R.T + self.calib.T.reshape(3)

        in_front = pts2[:, 2] > 1e-6
        if not in_front.any():
            return {"cam1": (0, w - 1), "cam2": (0, w - 1)}

        proj, _ = cv2.fisheye.projectPoints(
            pts2[in_front].reshape(1, -1, 3),
            np.zeros(3), np.zeros(3), K2, D2)
        proj = proj.reshape(-1, 2)

        visible = (
            (proj[:, 0] >= 0) & (proj[:, 0] < w) &
            (proj[:, 1] >= 0) & (proj[:, 1] < h)
        )

        if visible.sum() < 10:
            return {"cam1": (0, w - 1), "cam2": (0, w - 1)}

        left_cols = grid.reshape(-1, 2)[in_front][visible][:, 0]
        right_cols = proj[visible][:, 0]

        pad = margin * w

        def band(cols):
            lo = max(0, int(np.floor(cols.min() - pad)))
            hi = min(w - 1, int(np.ceil(cols.max() + pad)))
            return (lo, hi)

        return {"cam1": band(left_cols), "cam2": band(right_cols)}

    # ----------------------------------------------------------
    def describe(self):
        w, h = self.image_size
        try:
            fov = measured_fov(self.K1, self.calib.D1, self.image_size)
            fov_txt = (f"{fov['horizontal']:.0f} deg horizontal "
                       f"(FULL, nothing cropped)")
        except Exception:  # noqa: BLE001
            fov_txt = "unknown"

        c1, c2 = self.overlap["cam1"], self.overlap["cam2"]
        lines = [
            "Native fisheye stereo (KannalaBrandt8) - NO rectification",
            f"  image size  : {w}x{h} per eye"
            + ("" if abs(self.scale - 1.0) < 1e-9 else
               f" (downscaled {self.scale:.2f}x from "
               f"{self.native_size[0]}x{self.native_size[1]}; FOV unchanged)"),
            f"  field of view: {fov_txt}",
            f"  baseline    : {self.baseline * 1000:.2f} mm",
            f"  overlap cam1: columns {c1[0]}-{c1[1]} "
            f"({100.0 * (c1[1] - c1[0]) / w:.0f}% of width)",
            f"  overlap cam2: columns {c2[0]}-{c2[1]} "
            f"({100.0 * (c2[1] - c2[0]) / w:.0f}% of width)",
            "  NOTE: stereo depth exists only inside the overlap.",
            "        Features outside it are tracked monocularly.",
        ]
        return "\n".join(lines)

    def rectify(self, left, right):
        """No undistortion, no rectification - only optional downscale.

        The name is kept so this is interchangeable with
        StereoRectifier from the SLAM worker's point of view.
        """
        if abs(self.scale - 1.0) < 1e-9:
            return left, right

        size = self.image_size
        return (
            cv2.resize(left, size, interpolation=cv2.INTER_AREA),
            cv2.resize(right, size, interpolation=cv2.INTER_AREA),
        )

    def consistency_warnings(self):
        warn = []
        w = self.image_size[0]
        c1 = self.overlap["cam1"]
        frac = (c1[1] - c1[0]) / w
        if frac < 0.25:
            warn.append(
                f"The two lenses only overlap over {frac * 100:.0f}% of the image "
                f"width, so most features will have no stereo depth. Check the "
                f"calibration, or that the eyes are not swapped."
            )
        return warn

    # ----------------------------------------------------------
    def write_orbslam3_settings(self, path, fps, orb=None, th_depth=40.0):
        """Emit a KannalaBrandt8 stereo settings file."""
        orb = orb or {}
        w, h = int(self.image_size[0]), int(self.image_size[1])
        fps_i = max(1, int(round(float(fps))))

        n_features = int(orb.get("n_features", 1200))
        n_levels = int(orb.get("n_levels", 8))
        ini_th_fast = int(orb.get("ini_th_fast", 20))
        min_th_fast = int(orb.get("min_th_fast", 7))
        scale_factor = float(orb.get("scale_factor", 1.2))

        K1, D1 = self.K1, self.calib.D1.reshape(-1)
        K2, D2 = self.K2, self.calib.D2.reshape(-1)
        c1, c2 = self.overlap["cam1"], self.overlap["cam2"]

        rows = ",\n         ".join(
            ", ".join(f"{v:.12f}" for v in self.Tlr[r]) for r in range(4)
        )

        text = f"""%YAML:1.0

#--------------------------------------------------------------------
# GENERATED FILE - do not edit by hand.
#
# Written by Novex src/calibration.py from
#   {self.calib.path}
# on {datetime.datetime.now().isoformat(timespec='seconds')}
#
# NATIVE FISHEYE STEREO. The images handed to ORB-SLAM3 are the RAW
# camera images - not undistorted, not rectified, nothing resampled.
# ORB-SLAM3 applies the Kannala-Brandt model itself, keeping the full
# field of view instead of the ~100 degrees a pinhole rectification
# would leave.
#
# Stereo depth exists only inside the overlapping column band below.
# Features outside it are tracked monocularly.
#--------------------------------------------------------------------
File.version: "1.0"

Camera.type: "KannalaBrandt8"

Camera1.fx: {K1[0, 0]:.6f}
Camera1.fy: {K1[1, 1]:.6f}
Camera1.cx: {K1[0, 2]:.6f}
Camera1.cy: {K1[1, 2]:.6f}

Camera1.k1: {D1[0]:.10f}
Camera1.k2: {D1[1]:.10f}
Camera1.k3: {D1[2]:.10f}
Camera1.k4: {D1[3]:.10f}

Camera2.fx: {K2[0, 0]:.6f}
Camera2.fy: {K2[1, 1]:.6f}
Camera2.cx: {K2[0, 2]:.6f}
Camera2.cy: {K2[1, 2]:.6f}

Camera2.k1: {D2[0]:.10f}
Camera2.k2: {D2[1]:.10f}
Camera2.k3: {D2[2]:.10f}
Camera2.k4: {D2[3]:.10f}

# Pose of camera 2 in camera 1's frame: X_left = T_c1_c2 * X_right.
# Derived from the calibration's X2 = R*X1 + T as [R^T | -R^T T].
Stereo.T_c1_c2: !!opencv-matrix
  rows: 4
  cols: 4
  dt: f
  data: [{rows}]

Camera.width: {w}
Camera.height: {h}
Camera.fps: {fps_i}
Camera.RGB: 0

# Columns over which the two lenses see the same scene. ORB-SLAM3
# restricts stereo matching to this band. Computed by projecting points
# through both calibrated lenses, not guessed.
Camera1.overlappingBegin: {c1[0]}
Camera1.overlappingEnd: {c1[1]}

Camera2.overlappingBegin: {c2[0]}
Camera2.overlappingEnd: {c2[1]}

Stereo.ThDepth: {th_depth:.1f}

#--------------------------------------------------------------------
# ORB extractor
#--------------------------------------------------------------------
ORBextractor.nFeatures: {n_features}
ORBextractor.scaleFactor: {scale_factor}
ORBextractor.nLevels: {n_levels}
ORBextractor.iniThFAST: {ini_th_fast}
ORBextractor.minThFAST: {min_th_fast}

#--------------------------------------------------------------------
# Viewer
#--------------------------------------------------------------------
Viewer.KeyFrameSize: 0.05
Viewer.KeyFrameLineWidth: 1.0
Viewer.GraphLineWidth: 0.9
Viewer.PointSize: 2.0
Viewer.CameraSize: 0.08
Viewer.CameraLineWidth: 3.0
Viewer.ViewpointX: 0.0
Viewer.ViewpointY: -0.7
Viewer.ViewpointZ: -1.8
Viewer.ViewpointF: 500.0
"""
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
        return path


# ==============================================================
# 4. Status reporting
# ==============================================================

MISSING_MEASUREMENTS = """\
What a real stereo calibration must provide, and why the temporary
slider values cannot provide it:

  1. Per-eye fisheye intrinsics  fx, fy, cx, cy
     The sliders give a single 'source FOV' for both eyes and assume a
     perfectly centred optical axis. Real lenses are neither identical
     nor centred.

  2. Per-eye fisheye distortion  k1, k2, k3, k4  (Kannala-Brandt)
     The slider k-values were fitted by eye to make lines look
     straight. They were never fitted to points of known geometry, so
     they carry no metric meaning.

  3. Rotation R between the two eyes
     Completely unknown from the sliders. Even a fraction of a degree
     of relative yaw destroys stereo matching, because ORB-SLAM3
     searches for matches along image rows.

  4. Translation T between the two eyes, and hence the BASELINE
     Completely unknown from the sliders. This is the fatal one:
     the baseline is what converts disparity into metres. Without it
     there is no scale, and stereo ORB-SLAM3 cannot initialise.

All four come out of photographing a chessboard whose square size you
have physically measured. That measurement is the only place real
metric scale enters the system.

To produce them:

    python src/calibrate_stereo.py --squares 9x6 --square-size 0.025
"""


# Physical upper bound on the lens separation, metres.
#
# Taken from the GXIVISION-LSM22100 spec sheet: the module is 100 mm
# long, so the optical centres cannot be further apart than that. It is
# a guard against a mis-declared square size, which is otherwise
# invisible - scale is not observable from images alone.
#
# If your module is physically larger, MEASURE the separation between
# the two lens centres and raise calibration.max_baseline_m in
# config/camera.yaml. Do not raise it just to silence the check.
DEFAULT_MAX_BASELINE_M = 0.095


def calibration_status(calib_path, max_baseline_m=DEFAULT_MAX_BASELINE_M):
    """Return (state, message, calibration_or_None).

    state is one of "OK", "MISSING", "INVALID".
    """
    if not os.path.exists(calib_path):
        return (
            "MISSING",
            f"No stereo calibration at {calib_path}.\n\n" + MISSING_MEASUREMENTS,
            None,
        )

    try:
        calib = StereoCalibration.load(calib_path)
    except (CalibrationError, yaml.YAMLError) as exc:
        return ("INVALID", f"Calibration file is unusable: {exc}", None)

    if calib.baseline <= 0:
        return (
            "INVALID",
            "Calibration has a zero baseline, which cannot be correct.",
            calib,
        )

    # A baseline wider than the module itself is not a borderline
    # result, it is proof the calibration is wrong. Refuse it outright
    # rather than produce a map that is silently misscaled.
    # An implausible baseline does NOT block SLAM.
    #
    # Scale is not observable from images, so a mis-declared square
    # size misscales every distance - but it leaves the intrinsics,
    # the rectification and the epipolar geometry completely intact.
    # ORB-SLAM3 therefore still initialises and tracks normally; only
    # the units of the reported pose are wrong.
    #
    # So this is surfaced as UNVERIFIED SCALE rather than a refusal:
    # the run proceeds, and the uncertainty is shown next to the
    # numbers it affects instead of being silently absorbed.
    calib.scale_unverified = False

    if max_baseline_m and calib.baseline > max_baseline_m:
        calib.scale_unverified = True
        ratio = calib.baseline / calib.square_size if calib.square_size else 0.0

        lines = [
            calib.describe(),
            "",
            "  " + "!" * 60,
            "  UNVERIFIED SCALE - distances may be wrong by a constant factor",
            "  " + "!" * 60,
            f"  Baseline came out as {calib.baseline * 1000:.1f} mm, above the "
            f"{max_baseline_m * 1000:.0f} mm plausibility",
            "  limit (calibration.max_baseline_m in config/camera.yaml).",
            "",
            f"  What was actually MEASURED is a baseline of {ratio:.4f} BOARD SQUARES.",
            "  That number is scale-free and trustworthy. Converting it to",
            f"  millimetres relies entirely on the square size you declared",
            f"  ({calib.square_size * 1000:.2f} mm), and nothing in the images can check that.",
            "",
            "  SLAM WILL STILL TRACK CORRECTLY - the geometry is unaffected.",
            "  Only the metric units of the reported pose are in question.",
            "",
            "  To settle it, measure the gap between the two lens centres:",
        ]
        if ratio:
            lines += [
                f"      lens gap {mm:3d} mm  ->  your squares are {mm / 1000 / ratio * 1000:5.2f} mm"
                for mm in (55, 60, 70, 80, 90, 110)
            ]
            lines += [
                "",
                "  Then re-solve without recapturing:",
                "      python src/calibrate_stereo.py --from-images \\",
                "          --squares 8x6 --square-size <measured_metres>",
            ]
        return ("OK", "\n".join(lines), calib)

    return ("OK", calib.describe(), calib)
