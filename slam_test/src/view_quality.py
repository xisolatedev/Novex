"""
View quality scoring and degeneracy filtering for stereo calibration.

Why this exists
---------------
cv2.fisheye.calibrate() dies with

    InitExtrinsics: Assertion failed (fabs(norm_u1) > 0)

when it cannot estimate a starting pose for a view. Internally it fits
a homography from the board's (X, Y) coordinates to the normalised
image points. If that homography is degenerate the first column of the
result is a zero vector, and OpenCV asserts rather than reporting a
bad view.

The dominant cause with a ChArUco board is a PARTIAL view whose
detected corners happen to lie along a single board row or column.
Those corners are collinear in OBJECT space, so no homography exists,
no matter how clean the image is. A plain "at least N corners" test
does not catch it: twelve corners in one row is a perfectly healthy
count and a guaranteed crash.

So the checks here are geometric, not just numeric, and they run on the
object points as well as the image points.

Nothing here alters a measurement. Views are kept or dropped; the
corner positions that survive are exactly as detected.
"""

import math

import cv2
import numpy as np


# ==============================================================
class QualityConfig:
    """Thresholds. `wide_angle` relaxes what a very wide lens needs.

    On a 169-180 degree lens the useful observations at the frame edge
    are legitimately small, foreshortened and sparse. Rejecting them
    would leave the distortion model unconstrained exactly where it
    matters most, so wide-angle mode keeps them and only tightens the
    checks that predict an actual solver failure.
    """

    def __init__(self, wide_angle=False):
        self.wide_angle = wide_angle

        # Corner counts.
        self.min_corners = 8 if wide_angle else 12
        self.min_shared = 6 if wide_angle else 8

        # Degeneracy. This is the crash predictor, so it is NOT relaxed
        # for wide angle - a collinear view is unusable either way.
        self.min_object_spread = 0.12
        self.min_image_spread = 0.06
        self.min_rows = 2
        self.min_cols = 2

        # Pose. Grazing views localise corners poorly, but a wide lens
        # legitimately sees the board at sharper angles near the edge.
        self.max_tilt_deg = 78.0 if wide_angle else 70.0
        self.min_distance_m = 0.05
        self.max_distance_m = 6.0

        # Near-duplicate suppression, in normalised image units.
        self.duplicate_centre = 0.05
        self.duplicate_area = 0.15

        # Reprojection sanity for the stereo pair.
        self.max_pair_scale_ratio = 3.0


# ==============================================================
class ViewScore:
    __slots__ = ("keep", "reason", "score", "parts", "detail")

    def __init__(self, keep, reason="", score=0.0, parts=None, detail=""):
        self.keep = keep
        self.reason = reason
        self.score = float(score)
        self.parts = parts or {}
        self.detail = detail

    def __repr__(self):
        tag = "KEEP  " if self.keep else "REJECT"
        return f"{tag} {self.score:.2f} {self.reason}"


# ==============================================================
def spread_ratio(points):
    """How two-dimensional a point set is: 0 = a line, 1 = isotropic.

    The ratio of the singular values of the centred coordinates. This
    is the quantity that decides whether a homography can be fitted, so
    it is the direct predictor of the InitExtrinsics assertion.
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, points.shape[-1])
    if len(pts) < 3:
        return 0.0

    centred = pts[:, :2] - pts[:, :2].mean(axis=0)
    if not np.isfinite(centred).all():
        return 0.0

    sv = np.linalg.svd(centred, compute_uv=False)
    if sv[0] <= 1e-12:
        return 0.0
    return float(sv[1] / sv[0])


def grid_rank(obj_points, tol=1e-6):
    """Distinct board rows and columns the detected corners occupy.

    A ChArUco board's object points sit on an exact grid, so counting
    unique X and Y values is an exact, cheap statement about whether
    the view spans two dimensions of the board.
    """
    pts = np.asarray(obj_points, dtype=np.float64).reshape(-1, 3)
    xs = np.unique(np.round(pts[:, 0] / max(tol, 1e-9)).astype(np.int64))
    ys = np.unique(np.round(pts[:, 1] / max(tol, 1e-9)).astype(np.int64))
    return len(xs), len(ys)


def board_pose(obj_points, img_points, K, D):
    """Board pose in one camera, or None if it cannot be solved.

    Used for the tilt test and for pose-diversity scoring. Points are
    undistorted first, so this works on a strongly fisheye image.
    """
    if len(obj_points) < 6:
        return None
    try:
        pts = np.asarray(img_points, np.float64).reshape(-1, 1, 2)
        und = cv2.fisheye.undistortPoints(pts, K, D)
        ok, rvec, tvec = cv2.solvePnP(
            np.asarray(obj_points, np.float64).reshape(-1, 1, 3),
            und.reshape(-1, 1, 2), np.eye(3), None,
            flags=cv2.SOLVEPNP_IPPE)
        if not ok:
            return None
        R, _ = cv2.Rodrigues(rvec)
        return R, tvec.reshape(3)
    except cv2.error:
        return None


def board_tilt_deg(R):
    """Angle between the board normal and the camera's viewing axis."""
    normal = R @ np.array([0.0, 0.0, 1.0])
    cos = abs(float(normal[2]))
    return math.degrees(math.acos(max(0.0, min(1.0, cos))))


# ==============================================================
def describe_view(obj, img, size):
    """Cheap geometric descriptor used for duplicate detection."""
    pts = np.asarray(img, np.float64).reshape(-1, 2)
    w, h = size
    centre = np.array([pts[:, 0].mean() / w, pts[:, 1].mean() / h])
    span = np.array([(pts[:, 0].max() - pts[:, 0].min()) / w,
                     (pts[:, 1].max() - pts[:, 1].min()) / h])
    area = float(span[0] * span[1])
    return {"centre": centre, "area": area, "n": len(pts)}


def is_duplicate(desc, existing, cfg):
    """Near-duplicate of a view already held?

    More frames of the same pose add no information to a calibration
    but do bias it, so they are declined rather than stored.
    """
    for other in existing:
        d = float(np.linalg.norm(desc["centre"] - other["centre"]))
        if d > cfg.duplicate_centre:
            continue
        a1, a2 = desc["area"], other["area"]
        if max(a1, a2) <= 0:
            continue
        if abs(a1 - a2) / max(a1, a2) < cfg.duplicate_area:
            return True
    return False


# ==============================================================
def score_view(obj1, img1, ids1, obj2, img2, ids2, size, existing,
               cfg, K1=None, D1=None, coverage=None, grid_n=8):
    """Judge one captured stereo pair.

    Returns a ViewScore with keep/reject, the reason in plain words,
    and the component scores that produced it.
    """
    parts = {}

    n1 = 0 if obj1 is None else len(obj1)
    n2 = 0 if obj2 is None else len(obj2)

    if n1 == 0 or n2 == 0:
        return ViewScore(False, "board not seen in both eyes")

    if min(n1, n2) < cfg.min_corners:
        return ViewScore(
            False,
            f"too few corners ({n1}L/{n2}R, need {cfg.min_corners})")

    # ---- left/right correspondence -----------------------------
    #
    # Corner IDS are what make this checkable: ChArUco corners are
    # individually identified, so the overlap between the eyes is an
    # exact set intersection rather than a guess. When ids are not
    # available the check is skipped rather than failed - refusing a
    # view for a missing annotation would be a bug, not a measurement.
    if ids1 is not None and ids2 is not None:
        shared = len(np.intersect1d(np.asarray(ids1).reshape(-1),
                                    np.asarray(ids2).reshape(-1)))
        if shared < cfg.min_shared:
            return ViewScore(
                False,
                f"only {shared} corners seen by BOTH eyes "
                f"(need {cfg.min_shared})")
    else:
        shared = min(n1, n2)

    # ---- degeneracy: the actual crash predictor ----------------
    for tag, obj, img, n in (("left", obj1, img1, n1), ("right", obj2, img2, n2)):
        cols, rows = grid_rank(obj)
        if cols < cfg.min_cols or rows < cfg.min_rows:
            return ViewScore(
                False,
                f"{tag} corners lie on a single board line "
                f"({cols} col x {rows} row) - no homography exists, "
                f"this is what crashes fisheye.calibrate")

        obj_spread = spread_ratio(np.asarray(obj).reshape(-1, 3)[:, :2])
        if obj_spread < cfg.min_object_spread:
            return ViewScore(
                False,
                f"{tag} board points nearly collinear "
                f"(spread {obj_spread:.3f} < {cfg.min_object_spread})")

        img_spread = spread_ratio(np.asarray(img).reshape(-1, 2))
        if img_spread < cfg.min_image_spread:
            return ViewScore(
                False,
                f"{tag} image points nearly collinear "
                f"(spread {img_spread:.3f}) - extreme foreshortening")

        parts[f"spread_{tag}"] = min(obj_spread, img_spread)

    # ---- pose plausibility -------------------------------------
    tilt = None
    distance = None
    if K1 is not None and D1 is not None:
        pose = board_pose(obj1, img1, K1, D1)
        if pose is not None:
            R, t = pose
            tilt = board_tilt_deg(R)
            distance = float(np.linalg.norm(t))

            if tilt > cfg.max_tilt_deg:
                return ViewScore(
                    False,
                    f"board too edge-on ({tilt:.0f} deg, limit "
                    f"{cfg.max_tilt_deg:.0f}) - corner positions unreliable")
            if not (cfg.min_distance_m <= distance <= cfg.max_distance_m):
                return ViewScore(
                    False,
                    f"implausible board distance ({distance:.2f} m)")

    # ---- scale consistency between the eyes --------------------
    d1 = describe_view(obj1, img1, size)
    d2 = describe_view(obj2, img2, size)
    if d1["area"] > 0 and d2["area"] > 0:
        ratio = max(d1["area"], d2["area"]) / min(d1["area"], d2["area"])
        if ratio > cfg.max_pair_scale_ratio:
            return ViewScore(
                False,
                f"the eyes disagree wildly on board size (x{ratio:.1f}) - "
                f"probably a misdetection in one of them")
        parts["pair"] = 1.0 / ratio

    # ---- near duplicate ----------------------------------------
    if is_duplicate(d1, existing, cfg):
        return ViewScore(
            False, "nearly identical to a view already captured - "
                   "adds no new information")

    # ---- scoring (all in 0..1) ---------------------------------
    full = max(len(obj1), 1)
    parts["corners"] = min(1.0, min(n1, n2) / 30.0)
    parts["shared"] = min(1.0, shared / 20.0)
    parts["geometry"] = min(1.0, min(parts.get("spread_left", 0),
                                     parts.get("spread_right", 0)) / 0.5)

    # Pose diversity: a tilted board constrains focal length far better
    # than a head-on one, so tilt is rewarded up to the usable limit.
    if tilt is not None:
        parts["tilt"] = min(1.0, tilt / 45.0)
    else:
        parts["tilt"] = 0.5

    # Novelty: how much of what this view covers is not covered yet.
    if coverage is not None:
        pts = np.asarray(img1).reshape(-1, 2)
        w, h = size
        gx = np.clip((pts[:, 0] / w * grid_n).astype(int), 0, grid_n - 1)
        gy = np.clip((pts[:, 1] / h * grid_n).astype(int), 0, grid_n - 1)
        cells = set(zip(gy.tolist(), gx.tolist()))
        fresh = sum(1 for (r, c) in cells if coverage[r, c] == 0)
        parts["novelty"] = min(1.0, fresh / max(len(cells), 1) * 2.0)
    else:
        parts["novelty"] = 0.5

    weights = {"corners": 0.25, "shared": 0.15, "geometry": 0.20,
               "tilt": 0.20, "novelty": 0.20}
    score = sum(parts.get(k, 0.0) * wgt for k, wgt in weights.items())

    detail = f"{n1}L/{n2}R corners, {shared} shared"
    if tilt is not None:
        detail += f", tilt {tilt:.0f} deg"
    if distance is not None:
        detail += f", {distance:.2f} m"

    return ViewScore(True, "ok", score, parts, detail)


# ==============================================================
def prefilter(captures, size, cfg, K1=None, D1=None, log=print):
    """Drop unusable views before calibration, saying exactly why."""
    kept, rejected, existing = [], [], []
    coverage = np.zeros((8, 8), dtype=int)

    for i, c in enumerate(captures):
        s = score_view(c["obj1"], c["img1"], c.get("ids1"),
                       c["obj2"], c["img2"], c.get("ids2"),
                       size, existing, cfg, K1, D1, coverage)
        c["score"] = s
        if s.keep:
            kept.append(c)
            existing.append(describe_view(c["obj1"], c["img1"], size))
            pts = np.asarray(c["img1"]).reshape(-1, 2)
            gx = np.clip((pts[:, 0] / size[0] * 8).astype(int), 0, 7)
            gy = np.clip((pts[:, 1] / size[1] * 8).astype(int), 0, 7)
            np.add.at(coverage, (gy, gx), 1)
        else:
            rejected.append((i, s))

    if rejected:
        log(f"\n  Pre-filter removed {len(rejected)} of {len(captures)} views:")
        for i, s in rejected:
            log(f"    view {i:3d}  REJECT  {s.reason}")
    else:
        log(f"\n  Pre-filter: all {len(captures)} views usable.")

    return kept, rejected


# ==============================================================
def degeneracy_rank(captures):
    """Views ordered from most to least likely to break the solver."""
    scored = []
    for i, c in enumerate(captures):
        s_obj = spread_ratio(np.asarray(c["obj1"]).reshape(-1, 3)[:, :2])
        s_img = spread_ratio(np.asarray(c["img1"]).reshape(-1, 2))
        cols, rows = grid_rank(c["obj1"])
        n = min(len(c["obj1"]), len(c["obj2"]))
        risk = (min(s_obj, s_img), min(cols, rows), n)
        scored.append((risk, i, c))
    scored.sort(key=lambda x: x[0])
    return scored


def _try_calibrate(caps, size, flags, criteria, key_obj, key_img):
    objs = [np.asarray(c[key_obj], np.float64).reshape(1, -1, 3) for c in caps]
    imgs = [np.asarray(c[key_img], np.float64).reshape(1, -1, 2) for c in caps]
    return cv2.fisheye.calibrate(
        objs, imgs, size, np.zeros((3, 3)), np.zeros((4, 1)),
        flags=flags, criteria=criteria)


def identify_bad_views(captures, size, flags, key_obj, key_img, criteria,
                       seed=12, log=print):
    """Find exactly which views break the solver, by construction.

    Geometric heuristics cannot do this job. Measured on a real dataset
    here, exactly 3 views out of 52 poisoned the fit, and all three
    looked immaculate: 33-35 corners, spanning 7x5 board lines, object
    spread 0.68-0.71, well distributed across the frame. Whatever upsets
    OpenCV's homography initialisation for those views is not visible in
    the point geometry, so the only reliable test is to run the solver.

    The method: establish a BASE set that is verified to calibrate, then
    offer every remaining view to it one at a time. A view whose
    addition breaks the fit is recorded and left out.

    The base must be verified, not assumed. An earlier version seeded
    from the highest-quality views without checking them, and when the
    seed happened to contain a poisoned view every subsequent candidate
    appeared to fail - blaming 40 views for the sins of one. So the seed
    is repaired by leave-one-out before it is trusted.

    Costs roughly one calibration per view, with loose termination
    criteria; the caller refits properly on the clean set afterwards.
    """
    # The SAME termination criteria as the real fit, deliberately.
    #
    # With CALIB_RECOMPUTE_EXTRINSIC set, OpenCV re-runs InitExtrinsics
    # on every iteration against the evolving intrinsics - so a view
    # can survive 15 iterations and still blow up at 200. Validating
    # with looser criteria than the final fit produced a "verified" set
    # that promptly failed, which is worse than not checking at all.
    def works(indices):
        if len(indices) < 6:
            return False
        try:
            _try_calibrate([captures[i] for i in indices], size, flags,
                           criteria, key_obj, key_img)
            return True
        except cv2.error:
            return False

    # Quality ordering, so the base is built from the most solid views.
    order = sorted(
        range(len(captures)),
        key=lambda i: -(
            spread_ratio(np.asarray(captures[i][key_obj]).reshape(-1, 3)[:, :2])
            * min(len(np.asarray(captures[i][key_obj]).reshape(-1, 3)), 40)))

    bad = []
    base = order[:min(seed, len(order))]
    pool = [i for i in order if i not in base]

    # ---- repair the base until it actually calibrates ----------
    repairs = 0
    while not works(base) and repairs < seed * 2:
        repairs += 1
        culprit = None
        for i in list(base):
            if works([j for j in base if j != i]):
                culprit = i
                break

        if culprit is None:
            # No single member explains it; drop the least 2D one and
            # top the base up from the pool.
            culprit = min(
                base,
                key=lambda i: spread_ratio(
                    np.asarray(captures[i][key_obj]).reshape(-1, 3)[:, :2]))

        bad.append(culprit)
        base = [j for j in base if j != culprit]
        if pool:
            base.append(pool.pop(0))

    if not works(base):
        return list(range(len(captures))), []

    log(f"      base of {len(base)} views verified"
        + (f" after removing {repairs}" if repairs else ""))

    # ---- offer every remaining view to the verified base --------
    work = list(base)
    for n, idx in enumerate(pool):
        if works(work + [idx]):
            work.append(idx)
        else:
            bad.append(idx)
            if len(bad) <= 12:
                c = captures[idx]
                cols, rows = grid_rank(c[key_obj])
                sp = spread_ratio(np.asarray(c[key_obj]).reshape(-1, 3)[:, :2])
                n_pts = len(np.asarray(c[key_obj]).reshape(-1, 3))
                log(f"      view {idx:3d} breaks the fit: {n_pts} corners, "
                    f"{cols}x{rows} board lines, spread {sp:.3f}")

        if n and n % 25 == 0:
            log(f"      ... {n + 1}/{len(pool)} checked, {len(bad)} bad so far")

    return bad, [captures[i] for i in work]


def robust_fisheye_calibrate(captures, size, flags, criteria, key_obj, key_img,
                             log=print, max_rounds=3):
    """cv2.fisheye.calibrate that narrows the dataset instead of dying.

    Three stages, cheapest first:

      1. Try the whole set.
      2. Drop the least two-dimensional views a few at a time - fast,
         and enough when one obviously collinear view is to blame.
      3. Identify the culprits exactly by incremental reconstruction.

    Every stage reports what it removed and why, so a failure is
    explainable rather than mysterious.
    """
    working = list(captures)

    # ---- stage 1 & 2 -------------------------------------------
    for attempt in range(max_rounds):
        try:
            rms, K, D, rvecs, tvecs = _try_calibrate(
                working, size, flags, criteria, key_obj, key_img)
            if attempt:
                log(f"    succeeded after dropping "
                    f"{len(captures) - len(working)} view(s)")
            return rms, K, D, rvecs, tvecs, working
        except cv2.error as exc:
            msg = str(exc).splitlines()[-1][:90]
            if len(working) <= 8:
                break

            ranked = degeneracy_rank(working)
            drop = max(1, len(working) // 20)
            dropping = {i for _, i, _ in ranked[:drop]}
            log(f"    round {attempt + 1}: fisheye.calibrate failed; "
                f"dropping {drop} least-2D view(s)")
            working = [c for j, c in enumerate(working) if j not in dropping]

    # ---- stage 3: find them exactly ----------------------------
    log(f"    heuristic dropping did not help - identifying the offending "
        f"views exactly ({len(captures)} to check, one full fit each; "
        f"this takes a minute)")

    bad, work = identify_bad_views(captures, size, flags, key_obj, key_img,
                                   criteria, log=log)

    if len(bad) > 12:
        log(f"      ... and {len(bad) - 12} more")

    if not work or len(work) < 6:
        raise RuntimeError(
            f"only {len(work)} views survive; {len(bad)} of {len(captures)} "
            f"break fisheye.calibrate.\n"
            f"    The captured set cannot support a calibration. Recapture "
            f"with the board flatter, filling more of the frame, and held "
            f"still at the moment of capture.")

    log(f"    {len(bad)} view(s) removed, {len(work)} kept - refitting")
    rms, K, D, rvecs, tvecs = _try_calibrate(
        work, size, flags, criteria, key_obj, key_img)
    return rms, K, D, rvecs, tvecs, work


# ==============================================================
def reprojection_errors(captures, K, D, rvecs, tvecs, key_obj, key_img):
    """Per-view RMS reprojection error, in pixels."""
    out = []
    for c, rvec, tvec in zip(captures, rvecs, tvecs):
        obj = np.asarray(c[key_obj], np.float64).reshape(1, -1, 3)
        img = np.asarray(c[key_img], np.float64).reshape(-1, 2)
        try:
            proj, _ = cv2.fisheye.projectPoints(
                obj, np.asarray(rvec).reshape(3, 1),
                np.asarray(tvec).reshape(3, 1), K, D)
            proj = proj.reshape(-1, 2)
            err = np.sqrt(np.mean(np.sum((proj - img) ** 2, axis=1)))
            out.append(float(err))
        except cv2.error:
            out.append(float("nan"))
    return np.array(out)


def quality_grade(rms_left, rms_right, rms_stereo=None, n_views=0, coverage=0):
    """A plain-words verdict, with the reasoning shown."""
    worst = max(rms_left, rms_right, rms_stereo or 0.0)

    if worst < 0.3:
        grade, note = "EXCELLENT", "sub-third-pixel fit"
    elif worst < 0.5:
        grade, note = "GOOD", "well within what SLAM needs"
    elif worst < 1.0:
        grade, note = "ACCEPTABLE", "usable, but could be tighter"
    elif worst < 2.0:
        grade, note = "POOR", "expect weak stereo matching"
    else:
        grade, note = "UNUSABLE", "recapture before relying on this"

    caveats = []
    if n_views and n_views < 15:
        caveats.append(f"only {n_views} views (20-40 is advisable)")
    if coverage and coverage < 40:
        caveats.append(f"only {coverage:.0f}% of the frame was covered")

    return grade, note, caveats
