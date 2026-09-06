"""
ChArUco board support for the Novex fisheye stereo calibration.

Why ChArUco rather than a plain chessboard, for THIS camera:

A plain chessboard is only detected when the ENTIRE board is inside the
frame. On a ~112 degree fisheye that is a serious problem, because the
distortion you most need to measure lives in the frame corners - and
the board can never go there without part of it leaving the image. The
result is a calibration that is well constrained in the middle and
guessing at the edges, which is exactly where rectification then goes
wrong.

A ChArUco board is a chessboard with a unique ArUco marker in every
white square. Each marker identifies itself, so a PARTIAL view is still
usable: you can push the board half out of frame, into a corner, and
every corner still visible is identified and used. It is also markedly
more robust to strong distortion and uneven lighting.

The cost is that each view yields a different number of corners, which
is fine for cv2.fisheye.calibrate but NOT for cv2.fisheye.stereoCalibrate
(it reshapes its inputs and requires a uniform count). The stereo
extrinsics are therefore computed here per view with solvePnP and then
robustly averaged - see estimate_relative_pose().
"""

import numpy as np
import cv2


DICTIONARIES = {
    "DICT_4X4_50": cv2.aruco.DICT_4X4_50,
    "DICT_4X4_100": cv2.aruco.DICT_4X4_100,
    "DICT_4X4_250": cv2.aruco.DICT_4X4_250,
    "DICT_5X5_100": cv2.aruco.DICT_5X5_100,
    "DICT_5X5_250": cv2.aruco.DICT_5X5_250,
    "DICT_5X5_1000": cv2.aruco.DICT_5X5_1000,
    "DICT_6X6_250": cv2.aruco.DICT_6X6_250,
}


class CharucoBoardSpec:
    """A physical ChArUco board.

    square_length and marker_length are in METRES and must match the
    board you actually printed, measured with a ruler. square_length is
    the single most important number in the whole system: it is where
    metric scale enters, so every distance ORB-SLAM3 reports scales
    linearly with it.
    """

    def __init__(
        self,
        squares_x=8,
        squares_y=6,
        square_length=0.040,
        marker_length=0.030,
        dictionary="DICT_5X5_1000",
        wide_angle=False,
    ):
        if marker_length >= square_length:
            raise ValueError(
                f"marker_length ({marker_length}) must be smaller than "
                f"square_length ({square_length}); ~0.75x is typical"
            )

        self.squares_x = int(squares_x)
        self.squares_y = int(squares_y)
        self.square_length = float(square_length)
        self.marker_length = float(marker_length)
        self.dictionary_name = dictionary

        if dictionary not in DICTIONARIES:
            raise ValueError(
                f"unknown dictionary {dictionary}; "
                f"choose from {', '.join(DICTIONARIES)}"
            )

        self.dictionary = cv2.aruco.getPredefinedDictionary(DICTIONARIES[dictionary])

        self.board = cv2.aruco.CharucoBoard(
            (self.squares_x, self.squares_y),
            self.square_length,
            self.marker_length,
            self.dictionary,
        )

        self.wide_angle = bool(wide_angle)
        self.detector = cv2.aruco.CharucoDetector(
            self.board, cv2.aruco.CharucoParameters(),
            self._detector_params(self.wide_angle))

        # Total interior corners: one fewer than squares in each axis.
        self.num_corners = (self.squares_x - 1) * (self.squares_y - 1)

    # ----------------------------------------------------------
    @staticmethod
    def _detector_params(wide_angle):
        """ArUco detector settings, optionally tuned for a fisheye lens.

        The single most important one is polygonalApproxAccuracyRate.
        A fisheye BENDS the straight borders of a marker, and the
        detector finds markers by approximating contours as quadrilaterals
        - so near the frame edge, where the curvature is strongest, that
        approximation fails and the marker is simply never seen. Loosening
        the tolerance is what lets the board be detected out at the
        periphery, which is exactly where the distortion model most needs
        observations.

        The adaptive-threshold window range is widened for the same
        region, since the edges of a fisheye image are usually darker
        (vignetting), and the perimeter floor is lowered because a board
        at the edge projects small.

        Measured on real frames from this camera: 1735 corners detected
        versus 1634 with the defaults, and 54 of 58 images reaching 20+
        corners versus 47.
        """
        p = cv2.aruco.DetectorParameters()
        if not wide_angle:
            return p

        p.polygonalApproxAccuracyRate = 0.08   # default 0.03
        p.adaptiveThreshWinSizeMin = 3
        p.adaptiveThreshWinSizeMax = 53        # default 23
        p.adaptiveThreshWinSizeStep = 6
        p.minMarkerPerimeterRate = 0.01        # default 0.03
        p.maxMarkerPerimeterRate = 4.0
        p.minCornerDistanceRate = 0.03
        p.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        p.cornerRefinementWinSize = 5
        p.errorCorrectionRate = 0.8            # default 0.6
        return p

    @property
    def width_m(self):
        return self.squares_x * self.square_length

    @property
    def height_m(self):
        return self.squares_y * self.square_length

    def describe(self):
        return (
            f"ChArUco {self.squares_x}x{self.squares_y} squares, "
            f"{self.num_corners} corners\n"
            f"  square      : {self.square_length * 1000:.1f} mm\n"
            f"  marker      : {self.marker_length * 1000:.1f} mm\n"
            f"  dictionary  : {self.dictionary_name}\n"
            f"  detector    : {'WIDE-ANGLE tuned' if self.wide_angle else 'default'}\n"
            f"  printed size: {self.width_m * 100:.1f} x {self.height_m * 100:.1f} cm"
        )

    # ----------------------------------------------------------
    def detect(self, gray):
        """Detect the board in one grayscale image.

        Returns (obj_points Nx3 float64, img_points Nx2 float64, ids N)
        or (None, None, None) if too little was seen.

        Partial views are expected and welcome - that is the whole
        point of using ChArUco here.
        """
        charuco_corners, charuco_ids, _, _ = self.detector.detectBoard(gray)

        if charuco_ids is None or len(charuco_ids) < 4:
            return None, None, None

        obj_points, img_points = self.board.matchImagePoints(
            charuco_corners, charuco_ids
        )

        if obj_points is None or len(obj_points) < 4:
            return None, None, None

        return (
            np.asarray(obj_points, dtype=np.float64).reshape(-1, 3),
            np.asarray(img_points, dtype=np.float64).reshape(-1, 2),
            np.asarray(charuco_ids, dtype=np.int32).reshape(-1),
        )

    # ----------------------------------------------------------
    def generate_image(self, dpi=300, margin_mm=10):
        """Render the board for printing, at true physical scale.

        Printers rescale things. The returned image is sized so that at
        `dpi` it prints at exactly the specified square size - but you
        must still MEASURE a printed square, because "fit to page" and
        driver scaling silently break this.
        """
        px_per_m = dpi / 0.0254

        w_px = int(round(self.width_m * px_per_m))
        h_px = int(round(self.height_m * px_per_m))
        margin_px = int(round(margin_mm / 1000.0 * px_per_m))

        img = self.board.generateImage((w_px, h_px), marginSize=0)

        canvas = np.full(
            (h_px + 2 * margin_px, w_px + 2 * margin_px), 255, dtype=np.uint8
        )
        canvas[margin_px:margin_px + h_px, margin_px:margin_px + w_px] = img

        return canvas


# ==============================================================
# Stereo extrinsics from per-view board poses
# ==============================================================

# Minimum corners for a view to be trusted for EXTRINSICS.
#
# Intrinsics happily use a view with 8 corners, because every view adds
# independent constraints on the lens. A board pose is different: a
# handful of corners clustered at the frame edge gives a pose that is
# geometrically valid but poorly conditioned, and that noise goes
# straight into the camera-to-camera transform. Requiring a fuller view
# here costs a few views and buys a much steadier baseline.
MIN_CORNERS_FOR_POSE = 12


def _solve_board_pose(obj_points, img_points, K, D):
    """Pose of the board in one fisheye camera.

    The observations are first undistorted into normalised camera
    coordinates, after which the problem is an ordinary pinhole PnP
    with an identity intrinsic matrix. IPPE is used because the board
    is planar.
    """
    if len(obj_points) < MIN_CORNERS_FOR_POSE:
        return None

    pts = img_points.reshape(-1, 1, 2).astype(np.float64)
    undistorted = cv2.fisheye.undistortPoints(pts, K, D)

    ok, rvec, tvec = cv2.solvePnP(
        obj_points.reshape(-1, 1, 3).astype(np.float64),
        undistorted.reshape(-1, 1, 2).astype(np.float64),
        np.eye(3),
        None,
        flags=cv2.SOLVEPNP_IPPE,
    )

    if not ok:
        return None

    R, _ = cv2.Rodrigues(rvec)
    return R, tvec.reshape(3)


def _rotation_to_quat(R):
    q = np.empty(4)
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        q[0] = 0.25 * s
        q[1] = (R[2, 1] - R[1, 2]) / s
        q[2] = (R[0, 2] - R[2, 0]) / s
        q[3] = (R[1, 0] - R[0, 1]) / s
    else:
        i = int(np.argmax([R[0, 0], R[1, 1], R[2, 2]]))
        if i == 0:
            s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
            q[0] = (R[2, 1] - R[1, 2]) / s
            q[1] = 0.25 * s
            q[2] = (R[0, 1] + R[1, 0]) / s
            q[3] = (R[0, 2] + R[2, 0]) / s
        elif i == 1:
            s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
            q[0] = (R[0, 2] - R[2, 0]) / s
            q[1] = (R[0, 1] + R[1, 0]) / s
            q[2] = 0.25 * s
            q[3] = (R[1, 2] + R[2, 1]) / s
        else:
            s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
            q[0] = (R[1, 0] - R[0, 1]) / s
            q[1] = (R[0, 2] + R[2, 0]) / s
            q[2] = (R[1, 2] + R[2, 1]) / s
            q[3] = 0.25 * s
    return q / np.linalg.norm(q)


def _quat_to_rotation(q):
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def relative_pose_from_board_poses(rvecs1, tvecs1, rvecs2, tvecs2,
                                   weights=None, reject_sigma=2.5):
    """Camera-to-camera transform from per-view board poses.

    THIS is the reliable way to get the stereo extrinsics.
    cv2.fisheye.calibrate already solves the board pose for every view
    while fitting the intrinsics, and returns them as rvecs/tvecs. Those
    poses come from the full fisheye model and the same optimiser that
    produced K and D, so they are consistent with it by construction.

    The earlier approach here - undistorting the corners and running
    solvePnP separately - was materially worse for two reasons, both of
    which showed up as a baseline that changed between runs on
    identical images:

      * Planar targets have a two-fold pose ambiguity. IPPE returns one
        solution, and for a board viewed close to head-on the wrong one
        is easy to pick. A flipped board pose produces a wildly wrong
        relative transform.
      * cv2.fisheye.undistortPoints becomes inaccurate at the incidence
        angles this ~170 degree lens produces near the frame edge, so
        edge views fed corrupted rays into the PnP.

    For a rigid rig T_c1_c2 is identical in every view, so the per-view
    estimates are averaged (rotations via quaternions) after discarding
    outliers.
    """
    n = min(len(rvecs1), len(rvecs2))
    if weights is None:
        weights = np.ones(n)

    Rs, Ts, ws = [], [], []

    for i in range(n):
        R1, _ = cv2.Rodrigues(np.asarray(rvecs1[i]).reshape(3, 1))
        R2, _ = cv2.Rodrigues(np.asarray(rvecs2[i]).reshape(3, 1))
        t1 = np.asarray(tvecs1[i]).reshape(3)
        t2 = np.asarray(tvecs2[i]).reshape(3)

        # X_c2 = R_rel * X_c1 + T_rel
        R_rel = R2 @ R1.T
        T_rel = t2 - R_rel @ t1

        if not np.all(np.isfinite(R_rel)) or not np.all(np.isfinite(T_rel)):
            continue

        Rs.append(R_rel)
        Ts.append(T_rel)
        ws.append(float(weights[i]))

    return _average_relative_poses(Rs, Ts, ws, reject_sigma)


def _average_relative_poses(Rs, Ts, ws, reject_sigma=2.5):
    n_total = len(Rs)
    if n_total < 3:
        raise RuntimeError(
            f"only {n_total} usable stereo views; need at least 3")

    Ts_arr = np.array(Ts)
    ws = np.asarray(ws, dtype=np.float64)

    quats = np.array([_rotation_to_quat(R) for R in Rs])
    ref = quats[0]
    for i in range(len(quats)):
        if np.dot(quats[i], ref) < 0:
            quats[i] = -quats[i]

    med_t = np.median(Ts_arr, axis=0)
    dist_t = np.linalg.norm(Ts_arr - med_t, axis=1)

    med_q = np.median(quats, axis=0)
    med_q /= np.linalg.norm(med_q)
    ang = 2 * np.arccos(np.clip(np.abs(quats @ med_q), -1, 1))

    t_thresh = max(np.median(dist_t) * reject_sigma, 0.002)
    a_thresh = max(np.median(ang) * reject_sigma, np.radians(0.5))

    keep = (dist_t <= t_thresh) & (ang <= a_thresh)
    if keep.sum() < 3:
        keep = np.ones(len(Rs), dtype=bool)

    w = ws[keep]
    w = w / w.sum()

    q_mean = (quats[keep] * w[:, None]).sum(axis=0)
    q_mean /= np.linalg.norm(q_mean)

    R = _quat_to_rotation(q_mean)
    T = (Ts_arr[keep] * w[:, None]).sum(axis=0)

    baselines = np.linalg.norm(Ts_arr, axis=1)

    stats = {
        "views_used": int(keep.sum()),
        "views_total": int(n_total),
        "views_rejected": int(n_total - keep.sum()),
        "baseline_std_mm": float(np.linalg.norm(Ts_arr[keep].std(axis=0)) * 1000),
        "baseline_median_mm": float(np.median(baselines[keep]) * 1000),
        "rotation_spread_deg": float(np.degrees(ang[keep].std())),
    }

    return R, T.reshape(3, 1), stats


def estimate_relative_pose(views, K1, D1, K2, D2, reject_sigma=2.5):
    """Rigid transform from camera 1 to camera 2, from ChArUco views.

    `views` is a list of (obj1, img1, obj2, img2) - each eye's own
    observations for the same instant. The two eyes need NOT see the
    same corners.

    For each view the board pose is solved independently in each eye,
    giving T_c1_b and T_c2_b. The camera-to-camera transform is then
    T_c1_c2 = T_c2_b * T_c1_b^-1, which should be identical for every
    view because the rig is rigid. Per-view estimates are averaged
    (rotations via quaternions), after discarding outliers - a
    misdetected board or a motion-blurred frame shows up here as a
    wildly different transform.

    Returns (R, T, stats).
    """
    Rs, Ts, weights = [], [], []
    skipped_thin = 0

    for obj1, img1, obj2, img2 in views:
        if min(len(obj1), len(obj2)) < MIN_CORNERS_FOR_POSE:
            skipped_thin += 1
            continue

        p1 = _solve_board_pose(obj1, img1, K1, D1)
        p2 = _solve_board_pose(obj2, img2, K2, D2)

        if p1 is None or p2 is None:
            skipped_thin += 1
            continue

        R1, t1 = p1
        R2, t2 = p2

        # X_c2 = R_rel * X_c1 + T_rel
        R_rel = R2 @ R1.T
        T_rel = t2 - R_rel @ t1

        Rs.append(R_rel)
        Ts.append(T_rel)

        # A view seen fully by both eyes constrains the pose far better
        # than a sliver seen by one, so let it count for more.
        weights.append(float(min(len(obj1), len(obj2))))

    n_total = len(Rs)
    if n_total < 3:
        raise RuntimeError(
            f"only {n_total} usable stereo views; need at least 3 "
            f"(both eyes must see enough of the board in the same frame)"
        )

    Ts_arr = np.array(Ts)
    quats = np.array([_rotation_to_quat(R) for R in Rs])

    # Align quaternion signs (q and -q are the same rotation).
    ref = quats[0]
    for i in range(len(quats)):
        if np.dot(quats[i], ref) < 0:
            quats[i] = -quats[i]

    # Robust pass: drop views far from the median.
    med_t = np.median(Ts_arr, axis=0)
    dist_t = np.linalg.norm(Ts_arr - med_t, axis=1)

    med_q = np.median(quats, axis=0)
    med_q /= np.linalg.norm(med_q)
    ang = 2 * np.arccos(np.clip(np.abs(quats @ med_q), -1, 1))

    t_thresh = max(np.median(dist_t) * reject_sigma, 0.002)
    a_thresh = max(np.median(ang) * reject_sigma, np.radians(0.5))

    keep = (dist_t <= t_thresh) & (ang <= a_thresh)
    if keep.sum() < 3:
        keep = np.ones(len(Rs), dtype=bool)

    w = np.asarray(weights, dtype=np.float64)[keep]
    w = w / w.sum()

    q_mean = (quats[keep] * w[:, None]).sum(axis=0)
    q_mean /= np.linalg.norm(q_mean)

    R = _quat_to_rotation(q_mean)
    T = (Ts_arr[keep] * w[:, None]).sum(axis=0)

    stats = {
        "views_used": int(keep.sum()),
        "views_total": int(n_total),
        "views_rejected": int(n_total - keep.sum()),
        "views_too_thin": int(skipped_thin),
        "baseline_std_mm": float(np.linalg.norm(Ts_arr[keep].std(axis=0)) * 1000),
        "rotation_spread_deg": float(np.degrees(ang[keep].std())),
    }

    return R, T.reshape(3, 1), stats


def reprojection_error(obj_points, img_points, K, D, R, tvec):
    """RMS reprojection error in pixels for one view."""
    rvec, _ = cv2.Rodrigues(R)
    projected, _ = cv2.fisheye.projectPoints(
        obj_points.reshape(1, -1, 3), rvec, tvec.reshape(3, 1), K, D
    )
    projected = projected.reshape(-1, 2)
    return float(np.sqrt(np.mean(np.sum((projected - img_points) ** 2, axis=1))))
