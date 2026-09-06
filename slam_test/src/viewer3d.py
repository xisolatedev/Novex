"""
Real-time 3D view of the ORB-SLAM3 map and trajectory.

Deliberately drawn with QPainter and numpy rather than OpenGL. The
scene is a polyline, a few thousand points and a wireframe frustum -
software projection handles that at 60 fps without effort, and it
removes an entire class of driver and GL-context problems on Linux.
Functionality over beauty, as asked.

Everything drawn here comes from ORB-SLAM3: the trajectory is the
sequence of tracked camera centres, the point cloud is the current
map, and the frustum is the live pose.

Mouse:
    left drag   orbit
    right drag  pan
    wheel       zoom
"""

import math

import numpy as np

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF, QFont
from PySide6.QtWidgets import QWidget


BACKGROUND = QColor(18, 20, 24)
GRID = QColor(40, 44, 52)
TRAJ = QColor(90, 200, 255)
CAMERA = QColor(255, 210, 60)
POINTS = QColor(150, 150, 160)
TEXT = QColor(170, 175, 185)

AXIS_X = QColor(230, 80, 80)
AXIS_Y = QColor(110, 220, 110)
AXIS_Z = QColor(90, 150, 255)


class Viewer3D(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumHeight(240)
        self.setAutoFillBackground(False)

        # Orbit camera
        self.azimuth = math.radians(35.0)
        self.elevation = math.radians(-25.0)
        self.distance = 4.0
        self.target = np.zeros(3, dtype=np.float64)

        # Scene data (world coordinates, metres)
        self.trajectory = np.zeros((0, 3), np.float32)
        self.breaks = []
        self.map_points = np.zeros((0, 3), np.float32)
        self.keyframes = np.zeros((0, 3), np.float32)
        self.pose = None
        self.planes = []
        self.ground = None

        # Toggles
        self.show_points = True
        self.show_trajectory = True
        self.show_keyframes = True
        self.show_planes = True
        self.follow = True

        # First person: ride the camera instead of orbiting it.
        self.first_person = False
        self.fpv_fov_deg = 90.0

        # Aggressive extraction produces a much larger cloud, so draw
        # far more of it than the earlier 6000 cap allowed.
        self.max_points_drawn = 40000
        self.colour_by_depth = True

        self._last_mouse = None
        self._pan_mouse = None

    # ----------------------------------------------------------
    def update_scene(self, trajectory, breaks, map_points, keyframes, pose,
                     planes=None, ground=None):
        self.trajectory = trajectory
        self.breaks = breaks
        self.map_points = map_points
        self.keyframes = keyframes
        self.pose = pose
        if planes is not None:
            self.planes = planes
            self.ground = ground

        if self.follow and pose is not None:
            # Ease towards the camera so the view does not jitter.
            self.target += (pose.position - self.target) * 0.15

        self.update()

    def reset_view(self):
        self.azimuth = math.radians(35.0)
        self.elevation = math.radians(-25.0)
        self.distance = 4.0
        self.target = np.zeros(3, dtype=np.float64)
        self.update()

    # ----------------------------------------------------------
    def _rotation(self):
        # First person: the view rotation IS the camera's rotation.
        # Twc maps camera->world, so its transpose maps world->camera,
        # which is exactly the view matrix we need.
        if self.first_person and self.pose is not None:
            return self.pose.Twc[:3, :3].T

        ca, sa = math.cos(self.azimuth), math.sin(self.azimuth)
        ce, se = math.cos(self.elevation), math.sin(self.elevation)

        Ry = np.array([[ca, 0, -sa], [0, 1, 0], [sa, 0, ca]], dtype=np.float64)
        Rx = np.array([[1, 0, 0], [0, ce, -se], [0, se, ce]], dtype=np.float64)
        return Rx @ Ry

    def _view_params(self):
        """(rotation, eye position, forward offset, focal length)."""
        w, h = self.width(), self.height()

        if self.first_person and self.pose is not None:
            f = (w / 2.0) / math.tan(math.radians(self.fpv_fov_deg) / 2.0)
            # Sit at the camera centre; the small offset keeps points
            # from landing exactly on the z=0 singularity.
            return self._rotation(), self.pose.position, 0.0, f

        return self._rotation(), self.target, self.distance, min(w, h) * 0.9

    def _project(self, pts):
        """World points -> (Nx2 screen, N valid mask).

        Vectorised; this is called with the whole point cloud each
        repaint.
        """
        if len(pts) == 0:
            return np.zeros((0, 2), np.float32), np.zeros(0, bool)

        R, eye, offset, f = self._view_params()

        view = (np.asarray(pts, dtype=np.float64) - eye) @ R.T
        view[:, 2] += offset

        z = view[:, 2]
        valid = z > 0.05

        w, h = self.width(), self.height()

        screen = np.zeros((len(pts), 2), dtype=np.float64)
        safe_z = np.where(valid, z, 1.0)

        screen[:, 0] = w * 0.5 + f * view[:, 0] / safe_z
        screen[:, 1] = h * 0.5 + f * view[:, 1] / safe_z

        self._last_depth = z
        return screen, valid

    # ----------------------------------------------------------
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), BACKGROUND)

        self._draw_grid(p)
        self._draw_axes(p)

        if self.show_points and len(self.map_points):
            self._draw_map_points(p)

        if self.show_keyframes and len(self.keyframes):
            self._draw_keyframes(p)

        if self.show_planes and self.planes:
            self._draw_planes(p)

        if self.show_trajectory and len(self.trajectory) > 1:
            self._draw_trajectory(p)

        # In first person the camera is the viewpoint, so drawing its
        # own frustum would just smear geometry across the near plane.
        if self.pose is not None and not self.first_person:
            self._draw_camera(p, self.pose)

        self._draw_hud(p)
        p.end()

    # ----------------------------------------------------------
    def _draw_grid(self, p):
        """A 1 m grid on the world XZ plane.

        Note this plane is NOT the floor. Without an IMU the world
        frame is simply wherever the camera was when SLAM initialised,
        so the grid is a scale reference, not a horizon.
        """
        n = 6
        step = 1.0

        lines = []
        for i in range(-n, n + 1):
            lines.append([(-n * step, 0, i * step), (n * step, 0, i * step)])
            lines.append([(i * step, 0, -n * step), (i * step, 0, n * step)])

        flat = np.array([pt for line in lines for pt in line], dtype=np.float64)
        screen, valid = self._project(flat)

        p.setPen(QPen(GRID, 1))
        for i in range(0, len(flat), 2):
            if valid[i] and valid[i + 1]:
                p.drawLine(
                    QPointF(*screen[i]),
                    QPointF(*screen[i + 1]),
                )

    def _draw_axes(self, p):
        origin = np.array([[0, 0, 0]], dtype=np.float64)
        ends = np.array([[0.5, 0, 0], [0, 0.5, 0], [0, 0, 0.5]], dtype=np.float64)

        pts = np.vstack([origin, ends])
        screen, valid = self._project(pts)

        if not valid[0]:
            return

        for i, colour in enumerate((AXIS_X, AXIS_Y, AXIS_Z), start=1):
            if valid[i]:
                p.setPen(QPen(colour, 2))
                p.drawLine(QPointF(*screen[0]), QPointF(*screen[i]))

    def _draw_map_points(self, p):
        pts = self.map_points
        if len(pts) > self.max_points_drawn:
            # Uniform stride, so the cloud thins evenly instead of
            # showing only the oldest or newest points.
            stride = len(pts) // self.max_points_drawn + 1
            pts = pts[::stride]

        screen, valid = self._project(pts)
        if not len(screen):
            return

        w, h = self.width(), self.height()

        # Cull off-screen points before drawing. With an aggressive
        # extractor the cloud runs to tens of thousands of points, and
        # this is what keeps the repaint affordable.
        on = (valid
              & (screen[:, 0] > -20) & (screen[:, 0] < w + 20)
              & (screen[:, 1] > -20) & (screen[:, 1] < h + 20))
        idx = np.flatnonzero(on)
        if not len(idx):
            return

        if not self.colour_by_depth:
            p.setPen(QPen(POINTS, 1))
            for i in idx:
                p.drawPoint(QPointF(screen[i, 0], screen[i, 1]))
            return

        # Colour by distance from the viewer: near points bright, far
        # points dim. Batched into a few pens so the painter state is
        # not changed per point.
        z = self._last_depth[idx]
        lo, hi = np.percentile(z, 5), np.percentile(z, 95)
        span = max(hi - lo, 1e-6)
        bucket = np.clip(((z - lo) / span * 5).astype(int), 0, 5)

        for b in range(6):
            sel = idx[bucket == b]
            if not len(sel):
                continue
            shade = 235 - b * 28
            p.setPen(QPen(QColor(shade, shade, min(255, shade + 20)), 1))
            for i in sel:
                p.drawPoint(QPointF(screen[i, 0], screen[i, 1]))

    def _draw_keyframes(self, p):
        screen, valid = self._project(self.keyframes)
        p.setPen(QPen(QColor(90, 140, 200), 1))
        p.setBrush(Qt.NoBrush)
        for i in range(len(screen)):
            if valid[i]:
                # QRectF and plain floats: numpy scalars and the int
                # overload both misbehave here.
                p.drawRect(QRectF(float(screen[i][0]) - 2.0,
                                  float(screen[i][1]) - 2.0, 4.0, 4.0))

    def _draw_trajectory(self, p):
        screen, valid = self._project(self.trajectory)

        breaks = set(self.breaks)

        p.setPen(QPen(TRAJ, 2))
        for i in range(1, len(screen)):
            if i in breaks:
                continue
            if valid[i] and valid[i - 1]:
                p.drawLine(QPointF(*screen[i - 1]), QPointF(*screen[i]))

    def _draw_planes(self, p):
        """Draw each detected plane as a grid patch on the plane itself.

        Only the extent the inlier points actually cover is drawn, so a
        plane fitted to a small patch does not get rendered as an
        infinite floor.
        """
        for plane in self.planes:
            u, v = plane.basis
            eu, ev = plane.extent
            eu = min(max(eu, 0.3), 20.0)
            ev = min(max(ev, 0.3), 20.0)

            is_ground = plane.kind == "GROUND"
            colour = QColor(80, 220, 140) if is_ground else QColor(120, 130, 210)

            n = 6
            lines = []
            for i in range(n + 1):
                a = (i / n - 0.5)
                lines.append((plane.centroid + u * (a * eu) - v * (ev / 2),
                              plane.centroid + u * (a * eu) + v * (ev / 2)))
                lines.append((plane.centroid + v * (a * ev) - u * (eu / 2),
                              plane.centroid + v * (a * ev) + u * (eu / 2)))

            flat = np.array([q for line in lines for q in line], dtype=np.float64)
            screen, valid = self._project(flat)

            p.setPen(QPen(colour, 2 if is_ground else 1))
            for i in range(0, len(flat), 2):
                if valid[i] and valid[i + 1]:
                    p.drawLine(QPointF(*screen[i]), QPointF(*screen[i + 1]))

            # Normal arrow, so the orientation is unambiguous.
            tip = np.array([plane.centroid, plane.centroid + plane.normal * 0.35])
            s2, v2 = self._project(tip)
            if v2.all():
                p.setPen(QPen(colour, 2))
                p.drawLine(QPointF(*s2[0]), QPointF(*s2[1]))

    def _draw_camera(self, p, pose):
        """Wireframe frustum at the live pose, so orientation is visible
        and not just position."""
        s = 0.12
        local = np.array(
            [
                [0, 0, 0],
                [-s, -s * 0.75, s * 1.5],
                [s, -s * 0.75, s * 1.5],
                [s, s * 0.75, s * 1.5],
                [-s, s * 0.75, s * 1.5],
            ],
            dtype=np.float64,
        )

        R = pose.Twc[:3, :3]
        t = pose.Twc[:3, 3]
        world = local @ R.T + t

        screen, valid = self._project(world)
        if not valid.all():
            return

        p.setPen(QPen(CAMERA, 2))
        for i in (1, 2, 3, 4):
            p.drawLine(QPointF(*screen[0]), QPointF(*screen[i]))

        poly = QPolygonF([QPointF(*screen[i]) for i in (1, 2, 3, 4)])
        p.setBrush(QBrush(QColor(255, 210, 60, 40)))
        p.drawPolygon(poly)
        p.setBrush(Qt.NoBrush)

    def _draw_hud(self, p):
        p.setPen(QPen(TEXT))
        font = QFont("monospace", 8)
        p.setFont(font)

        mode = (f"FIRST PERSON  {self.fpv_fov_deg:.0f} deg"
                if self.first_person else
                f"orbit  zoom {self.distance:.1f} m" + ("  FOLLOW" if self.follow else ""))

        plane_txt = ""
        if self.planes:
            g = "ground yes" if self.ground is not None else "ground no"
            plane_txt = f"   planes {len(self.planes)} ({g})"

        lines = [
            f"points {len(self.map_points)}   keyframes {len(self.keyframes)}"
            f"   traj {len(self.trajectory)}{plane_txt}",
            f"{mode}   grid 1 m",
        ]

        y = self.height() - 8 - 12 * (len(lines) - 1)
        for line in lines:
            p.drawText(8, y, line)
            y += 12

    # ----------------------------------------------------------
    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._last_mouse = event.position()
        elif event.button() == Qt.RightButton:
            self._pan_mouse = event.position()

    def mouseMoveEvent(self, event):  # noqa: N802
        pos = event.position()

        if self._last_mouse is not None and (event.buttons() & Qt.LeftButton):
            d = pos - self._last_mouse
            self._last_mouse = pos
            self.azimuth += d.x() * 0.01
            self.elevation = max(
                -math.pi / 2 + 0.01,
                min(math.pi / 2 - 0.01, self.elevation + d.y() * 0.01),
            )
            self.update()

        elif self._pan_mouse is not None and (event.buttons() & Qt.RightButton):
            d = pos - self._pan_mouse
            self._pan_mouse = pos

            # Pan in the view plane, scaled by distance so it feels the
            # same at every zoom level.
            R = self._rotation()
            right = R[0, :]
            up = R[1, :]
            scale = self.distance * 0.002
            self.target -= right * d.x() * scale
            self.target -= up * d.y() * scale
            self.follow = False
            self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._last_mouse = None
        self._pan_mouse = None

    def wheelEvent(self, event):  # noqa: N802
        delta = event.angleDelta().y()

        if self.first_person:
            # In first person the wheel changes field of view, since
            # there is no distance to the subject to change.
            self.fpv_fov_deg = max(30.0, min(140.0,
                                             self.fpv_fov_deg + (-5 if delta > 0 else 5)))
        else:
            self.distance *= 0.9 if delta > 0 else 1.0 / 0.9
            self.distance = max(0.2, min(200.0, self.distance))
        self.update()

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        self.follow = not self.follow
        self.update()
