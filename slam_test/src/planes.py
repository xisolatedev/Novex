"""
Plane and ground detection from the ORB-SLAM3 map point cloud.

This works on the SAME 3D points ORB-SLAM3 triangulated - nothing new
is invented and nothing is meshed. A plane is reported only when enough
real map points actually lie on it.

Method: sequential RANSAC. Fit the plane with the most inliers, remove
those points, repeat. Vectorised in numpy so a few hundred hypotheses
over a few thousand points costs a couple of milliseconds, which is
cheap enough to re-run as the map grows.

About "ground": there is no IMU in this system, so gravity is unknown.
The world frame is wherever the camera happened to be when tracking
initialised. The ground is therefore identified by a stated assumption
rather than measured: the camera's own +Y axis points DOWN in the
OpenCV convention, so if you were holding the camera roughly upright at
start-up, world +Y is roughly down. The plane whose normal best aligns
with that direction, and which sits below the camera path, is reported
as the ground. If you started with the camera tilted, this will be
wrong - and it says so rather than pretending otherwise.
"""

import numpy as np


class Plane:
    """A detected planar surface: n . x + d = 0, with |n| = 1."""

    __slots__ = ("normal", "d", "inliers", "centroid", "basis", "extent",
                 "n_inliers", "kind", "score")

    def __init__(self, normal, d, inliers, points):
        self.normal = normal
        self.d = float(d)
        self.inliers = inliers
        self.n_inliers = int(len(inliers))
        self.kind = "plane"
        self.score = 0.0

        pts = points[inliers]
        self.centroid = pts.mean(axis=0)

        # An orthonormal basis in the plane, used to draw it and to
        # measure how far it actually extends - a plane fitted to a
        # thin sliver of points should not be drawn as a whole floor.
        a = np.array([1.0, 0.0, 0.0])
        if abs(np.dot(a, normal)) > 0.9:
            a = np.array([0.0, 0.0, 1.0])
        u = np.cross(normal, a)
        u /= max(np.linalg.norm(u), 1e-9)
        v = np.cross(normal, u)
        self.basis = (u, v)

        local = pts - self.centroid
        self.extent = (
            float(np.percentile(np.abs(local @ u), 95) * 2),
            float(np.percentile(np.abs(local @ v), 95) * 2),
        )

    def distance_to(self, points):
        return points @ self.normal + self.d

    def describe(self):
        return (
            f"{self.kind:6} n=({self.normal[0]:+.2f},{self.normal[1]:+.2f},"
            f"{self.normal[2]:+.2f}) pts={self.n_inliers} "
            f"size={self.extent[0]:.1f}x{self.extent[1]:.1f}m"
        )


def _fit_plane_svd(pts):
    """Least-squares plane through points; normal is the smallest
    singular vector of the centred cloud."""
    centroid = pts.mean(axis=0)
    _, _, vh = np.linalg.svd(pts - centroid, full_matrices=False)
    normal = vh[2]
    return normal, -float(normal @ centroid)


def detect_planes(
    points,
    max_planes=3,
    threshold=0.04,
    iterations=250,
    min_inliers=60,
    min_fraction=0.05,
    max_points=4000,
    rng=None,
):
    """Sequential RANSAC. Returns a list of Plane, largest first.

    threshold is the inlier band half-width in metres. 4 cm is a
    reasonable default for a room mapped by a short-baseline stereo
    rig, where the point cloud itself is a few centimetres noisy.
    """
    points = np.asarray(points, dtype=np.float64)
    if points.ndim != 2 or len(points) < min_inliers:
        return []

    rng = rng or np.random.default_rng(0)

    # Subsample for speed; the planes we care about are large, so they
    # survive subsampling comfortably.
    if len(points) > max_points:
        idx = rng.choice(len(points), max_points, replace=False)
        work = points[idx]
        back = idx
    else:
        work = points
        back = np.arange(len(points))

    remaining = np.ones(len(work), dtype=bool)
    planes = []
    total = len(work)

    for _ in range(max_planes):
        avail = np.flatnonzero(remaining)
        if len(avail) < max(min_inliers, int(total * min_fraction)):
            break

        pts = work[avail]

        # Vectorised hypotheses: sample all triples at once.
        tri = rng.integers(0, len(pts), size=(iterations, 3))
        p0, p1, p2 = pts[tri[:, 0]], pts[tri[:, 1]], pts[tri[:, 2]]

        n = np.cross(p1 - p0, p2 - p0)
        norms = np.linalg.norm(n, axis=1)
        ok = norms > 1e-9
        if not ok.any():
            break

        n = n[ok] / norms[ok, None]
        d = -np.einsum("ij,ij->i", n, p0[ok])

        # Inlier counts for every hypothesis at once.
        dist = np.abs(pts @ n.T + d)          # (n_pts, n_hyp)
        counts = (dist < threshold).sum(axis=0)

        best = int(np.argmax(counts))
        if counts[best] < max(min_inliers, int(total * min_fraction)):
            break

        inlier_mask = dist[:, best] < threshold

        # Refit properly to all inliers rather than keeping the
        # three-point hypothesis.
        normal, dd = _fit_plane_svd(pts[inlier_mask])
        refined = np.abs(pts @ normal + dd) < threshold
        if refined.sum() < min_inliers:
            break

        chosen = avail[refined]
        plane = Plane(normal, dd, back[chosen], points)
        plane.score = refined.sum() / total
        planes.append(plane)

        remaining[chosen] = False

    planes.sort(key=lambda p: -p.n_inliers)
    return planes


def classify_ground(planes, down_direction, camera_positions=None,
                    align_threshold=0.75):
    """Label whichever plane best matches the assumed 'down' direction.

    `down_direction` is a unit vector in WORLD coordinates that is
    believed to point downwards. With no IMU it is derived from the
    camera's own orientation, so it is an assumption, not a
    measurement - see the module docstring.

    Returns the ground plane or None. Sets plane.kind on the planes.
    """
    if not planes or down_direction is None:
        return None

    down = np.asarray(down_direction, dtype=np.float64)
    norm = np.linalg.norm(down)
    if norm < 1e-9:
        return None
    down = down / norm

    ground = None
    best = 0.0

    for p in planes:
        align = abs(float(p.normal @ down))

        if align >= align_threshold:
            p.kind = "horiz"
        else:
            p.kind = "wall" if align < 0.35 else "plane"

        if align < align_threshold:
            continue

        # Prefer a horizontal plane that lies BELOW the camera path;
        # a ceiling matches the normal test just as well as a floor.
        if camera_positions is not None and len(camera_positions):
            mean_cam = np.asarray(camera_positions, dtype=np.float64).mean(axis=0)
            # Positive means the plane is on the 'down' side of the camera.
            below = float((p.centroid - mean_cam) @ down)
            if below <= 0:
                p.kind = "ceil"
                continue

        weight = align * p.n_inliers
        if weight > best:
            best = weight
            ground = p

    if ground is not None:
        ground.kind = "GROUND"

    return ground


def down_from_poses(Twc_list):
    """Assumed world 'down', from the cameras' own +Y axes.

    In the OpenCV camera convention +Y points down in the image, so the
    second column of Twc is the camera's down axis expressed in world
    coordinates. Averaging over recent poses smooths out hand shake.
    """
    if not Twc_list:
        return None

    axes = np.array([T[:3, 1] for T in Twc_list], dtype=np.float64)
    mean = axes.mean(axis=0)
    n = np.linalg.norm(mean)
    if n < 1e-9:
        return None
    return mean / n
