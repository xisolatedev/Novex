"""
Novex ORB-SLAM3 test GUI (PySide6).

Layout:

    +---------------------------+---------------------------+
    | LEFT camera               | RIGHT camera              |
    +---------------------------+---------------------------+
    | 3D trajectory / map       | SLAM state                |
    |                           | Pose                      |
    |                           | Debug                     |
    +---------------------------+---------------------------+
    | status bar                                            |
    +-------------------------------------------------------+

The GUI thread only ever reads the latest snapshot published by the
SLAM worker. It never calls into ORB-SLAM3 and never touches the
camera's capture thread, so a slow repaint cannot stall either.

Where a value is not available - because SLAM is not running, or
because ORB-SLAM3 has not initialised - the field shows "--" rather
than a stale or invented number.
"""

import os
import time

import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import QImage, QPainter, QPen, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QPushButton, QComboBox, QSplitter, QMainWindow, QStatusBar, QCheckBox,
    QPlainTextEdit, QSizePolicy,
)

from viewer3d import Viewer3D
from slam import STATE_HINTS


VIEW_RAW = 0
VIEW_RECTIFIED = 1
VIEW_FEATURES = 2

VIEW_NAMES = ["Raw", "Rectified", "ORB features"]

STATE_COLOURS = {
    "OK": "#3ddc84",
    "OK_KLT": "#3ddc84",
    "NOT_INITIALIZED": "#ffc107",
    "NO_IMAGES_YET": "#8a8f98",
    "SYSTEM_NOT_READY": "#8a8f98",
    "RECENTLY_LOST": "#ff9800",
    "LOST": "#f44336",
}

MONO = "monospace"


# ==============================================================
class ImagePanel(QWidget):
    """Displays one eye, with optional ORB keypoint overlay.

    Keypoints are drawn by QPainter on top of the image rather than
    burned into the pixels with cv2.drawKeypoints, which avoids a
    full-frame copy per repaint.
    """

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        self.setMinimumSize(320, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._image = None
        self._keypoints = None
        self._tracked = None
        self._src_size = (1, 1)
        self._subtitle = ""
        self._draw_scale = 1.0
        self._offset = (0.0, 0.0)
        self._buffer = None

    def set_image(self, bgr, keypoints=None, tracked=None, subtitle=""):
        if bgr is None:
            self._image = None
            self._subtitle = subtitle
            self.update()
            return

        h, w = bgr.shape[:2]
        self._src_size = (w, h)

        # Scale exactly once, straight to the size it will be drawn at.
        # cv2.resize is considerably cheaper than letting Qt rescale a
        # QImage with SmoothTransformation on every repaint, and doing
        # it here means the pixels are never resampled twice.
        pw = max(1, self.width())
        ph = max(1, self.height())
        scale = min(pw / w, ph / h)

        dw = max(1, int(w * scale))
        dh = max(1, int(h * scale))

        self._draw_scale = scale
        self._offset = ((pw - dw) / 2.0, (ph - dh) / 2.0)

        # INTER_AREA for downscaling, INTER_LINEAR when the panel is
        # larger than the source.
        small = cv2.resize(
            bgr,
            (dw, dh),
            interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR,
        )

        if small.ndim == 2:
            rgb = cv2.cvtColor(small, cv2.COLOR_GRAY2RGB)
        else:
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        rgb = np.ascontiguousarray(rgb)

        # Keep a reference: QImage does not copy the buffer, so letting
        # the array be collected would leave QImage pointing at freed
        # memory.
        self._buffer = rgb
        self._image = QImage(
            rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0], QImage.Format_RGB888
        )

        self._keypoints = keypoints
        self._tracked = tracked
        self._subtitle = subtitle
        self.update()

    def resizeEvent(self, event):  # noqa: N802
        # The cached image was built for the old size; the next frame
        # rebuilds it. Nothing to do but let it repaint.
        super().resizeEvent(event)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(12, 13, 16))

        if self._image is None:
            p.setPen(QPen(QColor(120, 125, 135)))
            p.drawText(self.rect(), Qt.AlignCenter, "no image")
            self._draw_title(p)
            p.end()
            return

        # Recentre in case the widget was resized since set_image.
        ox = (self.width() - self._image.width()) / 2.0
        oy = (self.height() - self._image.height()) / 2.0

        p.drawImage(QPointF(ox, oy), self._image)

        if self._keypoints is not None and len(self._keypoints):
            self._draw_keypoints(p, ox, oy, self._draw_scale)

        self._draw_title(p)
        p.end()

    def _draw_keypoints(self, p, ox, oy, scale):
        kp = self._keypoints
        tracked = self._tracked

        green = QPen(QColor(60, 230, 130), 1)
        grey = QPen(QColor(150, 150, 160, 160), 1)

        # Two passes so the pen is set twice instead of per point.
        if tracked is not None:
            untracked_idx = np.flatnonzero(~tracked)
            tracked_idx = np.flatnonzero(tracked)
        else:
            untracked_idx = np.arange(len(kp))
            tracked_idx = np.empty(0, dtype=int)

        p.setPen(grey)
        for i in untracked_idx:
            x = ox + kp[i, 0] * scale
            y = oy + kp[i, 1] * scale
            p.drawPoint(QPointF(x, y))

        p.setPen(green)
        for i in tracked_idx:
            x = ox + kp[i, 0] * scale
            y = oy + kp[i, 1] * scale
            # QRectF, not the int overload: PySide6 picks drawRect(int,...)
            # for plain floats and overflows on non-integral values.
            p.drawRect(QRectF(x - 2.0, y - 2.0, 4.0, 4.0))

    def _draw_title(self, p):
        p.setPen(QPen(QColor(230, 232, 236)))
        p.setFont(QFont(MONO, 9, QFont.Bold))
        p.drawText(8, 18, self.title)

        if self._subtitle:
            p.setPen(QPen(QColor(140, 145, 155)))
            p.setFont(QFont(MONO, 8))
            p.drawText(8, 33, self._subtitle)


# ==============================================================
class ValueGrid(QGroupBox):
    """A labelled grid of monospaced key/value rows."""

    def __init__(self, title, keys, parent=None):
        super().__init__(title, parent)
        self._labels = {}

        grid = QGridLayout()
        grid.setContentsMargins(8, 4, 8, 6)
        grid.setVerticalSpacing(2)

        for row, key in enumerate(keys):
            name = QLabel(key)
            name.setFont(QFont(MONO, 9))
            name.setStyleSheet("color:#8a8f98;")

            value = QLabel("--")
            value.setFont(QFont(MONO, 9, QFont.Bold))
            value.setStyleSheet("color:#e6e8ec;")
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)

            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            grid.setColumnStretch(1, 1)

            self._labels[key] = value

        self.setLayout(grid)

    def set(self, key, text, colour=None):
        label = self._labels.get(key)
        if label is None:
            return
        label.setText(str(text))
        if colour:
            label.setStyleSheet(f"color:{colour};")


# ==============================================================
class MainWindow(QMainWindow):
    def __init__(self, app_state):
        super().__init__()

        self.state = app_state

        self.setWindowTitle("NOVEX - ORB-SLAM3 STEREO TEST")
        self.resize(1500, 950)
        self._apply_theme()

        self.view_mode = VIEW_RAW if not app_state.slam_enabled else VIEW_FEATURES
        self.show_debug = False

        self._last_camera_frame_id = 0
        self._last_result_id = 0
        self._gui_ms = 0.0
        self._gui_fps = 0.0
        self._gui_times = []

        # Preview maps for the temporary lens model, built lazily and
        # only used when there is no real calibration.
        self._temp_maps = None

        self._build_ui()
        self._build_shortcuts()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(1000 / app_state.gui_fps))

    # ----------------------------------------------------------
    def _apply_theme(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #14161a; color: #e6e8ec; }
            QGroupBox {
                border: 1px solid #262a31; border-radius: 4px;
                margin-top: 14px; padding-top: 4px;
                font-family: monospace; font-size: 10px; color: #8a8f98;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
            QPushButton {
                background: #1e222a; border: 1px solid #2d323b; border-radius: 3px;
                padding: 5px 10px; font-family: monospace; font-size: 11px;
            }
            QPushButton:hover { background: #262b34; }
            QPushButton:checked { background: #2b4a63; border-color: #3d7ea6; }
            QComboBox {
                background: #1e222a; border: 1px solid #2d323b; border-radius: 3px;
                padding: 4px 8px; font-family: monospace;
            }
            QPlainTextEdit {
                background: #0f1114; border: 1px solid #262a31;
                font-family: monospace; font-size: 10px; color: #b8bcc4;
            }
            QStatusBar { background: #0f1114; font-family: monospace; }
            QCheckBox { font-family: monospace; font-size: 11px; }
            QSplitter::handle { background: #262a31; }
            """
        )

    # ----------------------------------------------------------
    def _build_ui(self):
        # ---- camera row ---------------------------------------
        self.left_panel = ImagePanel("LEFT CAMERA")
        self.right_panel = ImagePanel("RIGHT CAMERA")

        cameras = QWidget()
        cam_layout = QHBoxLayout(cameras)
        cam_layout.setContentsMargins(0, 0, 0, 0)
        cam_layout.setSpacing(2)
        cam_layout.addWidget(self.left_panel)
        cam_layout.addWidget(self.right_panel)

        # ---- 3D viewer ----------------------------------------
        self.viewer = Viewer3D()

        # ---- info column --------------------------------------
        info = QWidget()
        info_layout = QVBoxLayout(info)
        info_layout.setContentsMargins(6, 6, 6, 6)
        info_layout.setSpacing(6)

        self.banner = QLabel()
        self.banner.setWordWrap(True)
        self.banner.setFont(QFont(MONO, 10, QFont.Bold))
        self.banner.setAlignment(Qt.AlignCenter)
        self.banner.setVisible(False)
        info_layout.addWidget(self.banner)

        self.slam_box = ValueGrid(
            "SLAM",
            [
                "Tracking",
                "Camera FPS",
                "SLAM FPS",
                "GUI FPS",
                "Features L",
                "Features R",
                "Stereo pts",
                "Stereo %",
                "Tracked",
                "Depth m",
                "Map points",
                "Keyframes",
                "Maps",
            ],
        )
        info_layout.addWidget(self.slam_box)

        self.pose_box = ValueGrid(
            "POSE",
            ["X (m)", "Y (m)", "Z (m)", "Roll", "Pitch", "Yaw", "Path (m)"],
        )
        info_layout.addWidget(self.pose_box)

        self.plane_box = ValueGrid(
            "GEOMETRY", ["Planes", "Ground", "Height", "Tilt", "Fit ms"])
        info_layout.addWidget(self.plane_box)

        self.debug_box = QGroupBox("DEBUG")
        dbg_layout = QVBoxLayout(self.debug_box)
        dbg_layout.setContentsMargins(6, 4, 6, 6)
        self.debug_text = QPlainTextEdit()
        self.debug_text.setReadOnly(True)
        self.debug_text.setMinimumHeight(200)
        dbg_layout.addWidget(self.debug_text)
        self.debug_box.setVisible(False)
        info_layout.addWidget(self.debug_box)

        info_layout.addStretch(1)
        info_layout.addWidget(self._build_controls())

        info.setMinimumWidth(330)
        info.setMaximumWidth(430)

        # ---- assemble -----------------------------------------
        lower = QSplitter(Qt.Horizontal)
        lower.addWidget(self.viewer)
        lower.addWidget(info)
        lower.setStretchFactor(0, 1)
        lower.setSizes([1000, 380])

        main = QSplitter(Qt.Vertical)
        main.addWidget(cameras)
        main.addWidget(lower)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setSizes([380, 560])

        self.setCentralWidget(main)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

    def _build_controls(self):
        box = QGroupBox("CONTROLS")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        self.view_combo = QComboBox()
        self.view_combo.addItems(VIEW_NAMES)
        self.view_combo.setCurrentIndex(self.view_mode)
        self.view_combo.currentIndexChanged.connect(self._set_view_mode)
        layout.addWidget(self.view_combo)

        row1 = QHBoxLayout()
        self.btn_reset = QPushButton("R  Reset SLAM")
        self.btn_reset.clicked.connect(self.action_reset)
        row1.addWidget(self.btn_reset)

        self.btn_record = QPushButton("V  Record")
        self.btn_record.setCheckable(True)
        self.btn_record.clicked.connect(self.action_record)
        row1.addWidget(self.btn_record)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_points = QCheckBox("M points")
        self.chk_points.setChecked(True)
        self.chk_points.toggled.connect(
            lambda v: setattr(self.viewer, "show_points", v)
        )
        row2.addWidget(self.chk_points)

        self.chk_traj = QCheckBox("T traj")
        self.chk_traj.setChecked(True)
        self.chk_traj.toggled.connect(
            lambda v: setattr(self.viewer, "show_trajectory", v)
        )
        row2.addWidget(self.chk_traj)

        self.chk_planes = QCheckBox("P planes")
        self.chk_planes.setChecked(True)
        self.chk_planes.toggled.connect(
            lambda v: setattr(self.viewer, "show_planes", v))
        row2.addWidget(self.chk_planes)

        self.chk_debug = QCheckBox("D debug")
        self.chk_debug.toggled.connect(self._set_debug)
        row2.addWidget(self.chk_debug)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.btn_fpv = QPushButton("1  First person")
        self.btn_fpv.setCheckable(True)
        self.btn_fpv.toggled.connect(self._set_fpv)
        row3.addWidget(self.btn_fpv)

        self.btn_follow = QPushButton("Follow camera")
        self.btn_follow.setCheckable(True)
        self.btn_follow.setChecked(True)
        self.btn_follow.toggled.connect(lambda v: setattr(self.viewer, "follow", v))
        row3.addWidget(self.btn_follow)

        self.btn_reset_view = QPushButton("Reset view")
        self.btn_reset_view.clicked.connect(self.viewer.reset_view)
        row3.addWidget(self.btn_reset_view)
        layout.addLayout(row3)

        self.btn_save = QPushButton("Save trajectory (TUM)")
        self.btn_save.clicked.connect(self.action_save_trajectory)
        layout.addWidget(self.btn_save)

        return box

    # ----------------------------------------------------------
    def _build_shortcuts(self):
        def bind(key, fn):
            QShortcut(QKeySequence(key), self, activated=fn)

        bind("R", self.action_reset)
        bind("C", self.action_cycle_view)
        bind("F", lambda: self._set_view_mode(VIEW_FEATURES, sync=True))
        bind("M", lambda: self.chk_points.setChecked(not self.chk_points.isChecked()))
        bind("T", lambda: self.chk_traj.setChecked(not self.chk_traj.isChecked()))
        bind("D", lambda: self.chk_debug.setChecked(not self.chk_debug.isChecked()))
        bind("V", lambda: self.btn_record.click())
        bind("P", lambda: self.chk_planes.setChecked(not self.chk_planes.isChecked()))
        bind("1", lambda: self.btn_fpv.setChecked(not self.btn_fpv.isChecked()))
        bind("G", self.action_snap_to_ground)
        bind("Esc", self.close)

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------
    def _set_view_mode(self, index, sync=False):
        self.view_mode = index
        if sync:
            self.view_combo.setCurrentIndex(index)

    def action_cycle_view(self):
        self._set_view_mode((self.view_mode + 1) % len(VIEW_NAMES), sync=True)

    def _set_debug(self, on):
        self.show_debug = on
        self.debug_box.setVisible(on)

    def _set_fpv(self, on):
        self.viewer.first_person = on
        self.viewer.update()
        self.status.showMessage(
            "First person: riding the camera" if on else "Orbit view", 3000)

    def action_snap_to_ground(self):
        """Look down at the detected ground plane from above."""
        pw = getattr(self.state, "plane_worker", None)
        if pw is None:
            return
        _, ground = pw.latest()
        if ground is None:
            self.status.showMessage("No ground plane detected yet", 3000)
            return
        self.viewer.first_person = False
        self.btn_fpv.setChecked(False)
        self.viewer.follow = False
        self.btn_follow.setChecked(False)
        self.viewer.target = ground.centroid.copy()
        self.viewer.elevation = -1.2
        self.viewer.distance = max(2.0, max(ground.extent))
        self.viewer.update()
        self.status.showMessage(
            f"Ground: {ground.n_inliers} points, {abs(ground.d):.2f} m away", 5000)

    def action_reset(self):
        if self.state.worker is not None:
            self.state.worker.request_reset()
            self.viewer.reset_view()
            self.status.showMessage("SLAM reset requested", 3000)
        else:
            self.status.showMessage("SLAM is not running", 3000)

    def action_record(self):
        rec = self.state.recorder
        if rec is None:
            self.status.showMessage("Recording is not available", 3000)
            self.btn_record.setChecked(False)
            return

        if rec.is_recording:
            path = rec.stop()
            self.btn_record.setText("V  Record")
            self.status.showMessage(f"Recording saved: {path}", 8000)
        else:
            path = rec.start(self.state.camera)
            if path is None:
                self.btn_record.setChecked(False)
                self.status.showMessage(f"Recording failed: {rec.error}", 8000)
            else:
                self.btn_record.setText("V  STOP")
                self.status.showMessage(f"Recording to {path}", 5000)

    def action_save_trajectory(self):
        worker = self.state.worker
        if worker is None or worker.slam is None:
            self.status.showMessage("No SLAM session to save", 3000)
            return

        out = os.path.join(
            self.state.root,
            "recordings",
            f"trajectory_{time.strftime('%Y-%m-%d_%H-%M-%S')}.txt",
        )
        os.makedirs(os.path.dirname(out), exist_ok=True)
        try:
            worker.save_trajectory(out)
            self.status.showMessage(f"Keyframe trajectory written: {out}", 8000)
        except Exception as exc:  # noqa: BLE001
            self.status.showMessage(f"Save failed: {exc}", 8000)

    # ----------------------------------------------------------
    # Per-frame update
    # ----------------------------------------------------------
    def _tick(self):
        t0 = time.perf_counter()

        worker = self.state.worker
        result = worker.latest() if worker is not None else None

        self._update_images(result)
        self._update_slam_panel(result)
        self._update_pose_panel(result)
        self._update_viewer(result)

        if self.show_debug:
            self._update_debug(result)

        self._update_banner()

        t1 = time.perf_counter()
        self._gui_ms = (t1 - t0) * 1000.0

        self._gui_times.append(t1)
        if len(self._gui_times) >= 2:
            span = self._gui_times[-1] - self._gui_times[0]
            if span >= 1.0:
                self._gui_fps = (len(self._gui_times) - 1) / span
                self._gui_times = self._gui_times[-2:]
            elif len(self._gui_times) > 200:
                self._gui_times = self._gui_times[-2:]

    # ----------------------------------------------------------
    def _update_images(self, result):
        camera = self.state.camera

        if self.view_mode == VIEW_RAW:
            frame = camera.read_new(self._last_camera_frame_id)
            if frame is None:
                return
            self._last_camera_frame_id = frame.frame_id

            note = f"{frame.left.shape[1]}x{frame.left.shape[0]} raw"
            self.left_panel.set_image(frame.left, subtitle=note)
            self.right_panel.set_image(frame.right, subtitle=note)
            return

        # Rectified / features come from the SLAM worker so the same
        # rectification is not computed twice.
        if result is not None:
            if result.frame_id == self._last_result_id:
                return
            self._last_result_id = result.frame_id

            note = f"{result.left_rect.shape[1]}x{result.left_rect.shape[0]} rectified"

            if self.view_mode == VIEW_FEATURES:
                self.left_panel.set_image(
                    result.left_rect,
                    keypoints=result.keypoints,
                    tracked=result.kp_tracked,
                    subtitle=f"{note} | {result.num_tracked}/{result.num_keypoints} tracked",
                )
            else:
                self.left_panel.set_image(result.left_rect, subtitle=note)

            # The right eye gets its own overlay now: these are the
            # features ORB-SLAM3 extracted in the RIGHT image, which is
            # what stereo matching searches through.
            self.right_panel.set_image(
                result.right_rect,
                keypoints=result.keypoints_right,
                tracked=None,
                subtitle=f"{note} | {result.num_keypoints_right or 0} features",
            )
            return

        # No SLAM: fall back to the temporary lens preview so the
        # rectified view is not simply blank.
        self._update_temporary_preview()

    def _update_temporary_preview(self):
        camera = self.state.camera
        lens = self.state.temporary_lens

        frame = camera.read_new(self._last_camera_frame_id)
        if frame is None:
            return
        self._last_camera_frame_id = frame.frame_id

        if lens is None:
            self.left_panel.set_image(frame.left, subtitle="no lens model")
            self.right_panel.set_image(frame.right, subtitle="no lens model")
            return

        if self._temp_maps is None:
            h, w = frame.left.shape[:2]
            self._temp_maps = lens.build_maps(w, h, 640, int(640 * h / w))

        mx, my = self._temp_maps
        left = cv2.remap(frame.left, mx, my, cv2.INTER_LINEAR)
        right = cv2.remap(frame.right, mx, my, cv2.INTER_LINEAR)

        note = "TEMPORARY lens model - not a stereo calibration"
        self.left_panel.set_image(left, subtitle=note)
        self.right_panel.set_image(right, subtitle=note)

    # ----------------------------------------------------------
    def _update_slam_panel(self, result):
        camera = self.state.camera
        worker = self.state.worker

        self.slam_box.set("Camera FPS", f"{camera.measured_fps:5.1f}")
        self.slam_box.set("GUI FPS", f"{self._gui_fps:5.1f}")

        if worker is None:
            self.slam_box.set("Tracking", "DISABLED", "#f44336")
            self.slam_box.set("SLAM FPS", "--")
            for k in ("Features L", "Features R", "Stereo pts", "Stereo %",
                      "Tracked", "Depth m", "Map points", "Keyframes", "Maps"):
                self.slam_box.set(k, "--")
            return

        if worker.error:
            self.slam_box.set("Tracking", "ERROR", "#f44336")
            return

        if not worker.ready.is_set():
            self.slam_box.set("Tracking", "LOADING VOCAB", "#ffc107")
            return

        self.slam_box.set("SLAM FPS", f"{worker.slam_fps:5.1f}")

        if result is None:
            self.slam_box.set("Tracking", "STARTING", "#8a8f98")
            return

        colour = STATE_COLOURS.get(result.state_name, "#e6e8ec")
        self.slam_box.set("Tracking", result.state_name, colour)
        self.slam_box.set("Features L", result.num_keypoints)
        self.slam_box.set("Features R", result.num_keypoints_right or "--")

        # Stereo utilisation: what fraction of left features actually
        # matched in the right image. This is the honest measure of how
        # much the second camera is contributing - unmatched features
        # carry no depth and behave monocularly.
        n_st = result.num_stereo or 0
        self.slam_box.set("Stereo pts", n_st)
        if result.num_keypoints:
            pct = 100.0 * n_st / result.num_keypoints
            # The fisheye path matches stereo by descriptor + Lowe's
            # ratio with no epipolar constraint, so it legitimately
            # yields a lower fraction than the rectified row search.
            # Judging both against the same threshold would just paint
            # a working fisheye setup red.
            fisheye = getattr(self.state, "camera_model", None) == "fisheye"
            hi, mid = (15, 6) if fisheye else (40, 20)
            colour = ("#3ddc84" if pct >= hi else
                      "#ffc107" if pct >= mid else "#f44336")
            self.slam_box.set("Stereo %", f"{pct:5.1f}%", colour)
        else:
            self.slam_box.set("Stereo %", "--")

        self.slam_box.set("Tracked", result.num_tracked)

        if result.mean_depth:
            self.slam_box.set(
                "Depth m",
                f"{result.min_depth:.1f}-{result.max_depth:.1f} "
                f"(~{result.mean_depth:.1f})")
        else:
            self.slam_box.set("Depth m", "--")

        m = worker.latest_map()
        self.slam_box.set("Map points", m.num_points)
        self.slam_box.set("Keyframes", m.num_keyframes)
        self.slam_box.set("Maps", m.num_maps)

    def _update_pose_panel(self, result):
        pose = result.pose if result is not None else None

        if pose is None:
            for k in ("X (m)", "Y (m)", "Z (m)", "Roll", "Pitch", "Yaw"):
                self.pose_box.set(k, "--", "#8a8f98")
        else:
            # Amber means the metric scale was never verified: the
            # geometry is right, the units may not be.
            unverified = getattr(self.state, "scale_unverified", False)
            colour = "#ffc107" if unverified else "#e6e8ec"
            self.pose_box.set("X (m)", f"{pose.x:+8.3f}", colour)
            self.pose_box.set("Y (m)", f"{pose.y:+8.3f}", colour)
            self.pose_box.set("Z (m)", f"{pose.z:+8.3f}", colour)
            self.pose_box.set("Roll", f"{pose.roll:+7.1f}°", "#e6e8ec")
            self.pose_box.set("Pitch", f"{pose.pitch:+7.1f}°", "#e6e8ec")
            self.pose_box.set("Yaw", f"{pose.yaw:+7.1f}°", "#e6e8ec")

        worker = self.state.worker
        if worker is not None:
            self.pose_box.set("Path (m)", f"{worker.trajectory.total_distance:8.2f}")

    def _update_viewer(self, result):
        worker = self.state.worker
        if worker is None:
            return

        traj, breaks = worker.trajectory.snapshot()
        m = worker.latest_map()

        planes, ground = [], None
        pw = getattr(self.state, "plane_worker", None)
        if pw is not None:
            planes, ground = pw.latest()

        self.viewer.update_scene(
            trajectory=traj,
            breaks=breaks,
            map_points=m.points,
            keyframes=m.keyframes,
            pose=result.pose if result is not None else None,
            planes=planes,
            ground=ground,
        )

        self.plane_box.set("Planes", len(planes) if planes else "--")
        if ground is not None:
            self.plane_box.set("Ground", f"{ground.n_inliers} pts", "#3ddc84")
            self.plane_box.set("Height", f"{abs(ground.d):.2f} m")
            # Angle between the ground normal and the camera's own down
            # axis: near 0 means the camera is level with the surface.
            if result is not None and result.pose is not None:
                cam_down = result.pose.Twc[:3, 1]
                import numpy as _np
                tilt = _np.degrees(_np.arccos(
                    min(1.0, abs(float(ground.normal @ cam_down)))))
                self.plane_box.set("Tilt", f"{tilt:5.1f}°")
        else:
            self.plane_box.set("Ground", "none", "#8a8f98")
            self.plane_box.set("Height", "--")
            self.plane_box.set("Tilt", "--")
        if pw is not None:
            self.plane_box.set("Fit ms", f"{pw.last_ms:.0f}")

    # ----------------------------------------------------------
    def _update_debug(self, result):
        camera = self.state.camera
        worker = self.state.worker
        s = self.state

        a, r = camera.actual, camera.requested

        lines = []

        if getattr(s, "profile", None):
            lines += [f"PROFILE: {s.profile.upper()}", ""]

        model = getattr(s, "camera_model", None)
        if model:
            lines += [f"CAMERA MODEL: {model.upper()}"]
            if model == "fisheye":
                lines += [
                    "  raw fisheye straight into ORB-SLAM3 (KannalaBrandt8)",
                    "  full field of view, no undistort, no remap",
                    "  stereo depth only inside the lens overlap;",
                    "  features outside it are tracked monocularly",
                ]
            lines += [""]

        layout = getattr(s, "cpu_layout", None)
        if layout:
            lines += ["CPU CORES"]
            lines += [f"  requested   : camera {layout.get('camera')} "
                      f"slam {layout.get('slam')} gui {layout.get('gui')}"]
            for line in s.affinity.lines():
                lines.append(f"  {line}")
            if camera is not None:
                lines.append(f"  {getattr(camera, 'affinity_status', '')}")
            if worker is not None:
                lines.append(f"  {getattr(worker, 'affinity_status', '')}")
            lines.append("")

        lines += [
            "CAMERA",
            f"  requested   : {r.get('width')}x{r.get('height')} "
            f"{r.get('fourcc')} @ {r.get('fps')} fps",
            f"  actual      : {a.get('width')}x{a.get('height')} "
            f"{a.get('fourcc')} @ {a.get('fps')} fps",
            f"  measured    : {camera.measured_fps:.2f} fps",
            f"  read errors : {camera.read_failures}",
            "",
            "STEREO",
            f"  left        : {a.get('width', 0) // 2}x{a.get('height')}",
            f"  right       : {a.get('width', 0) // 2}x{a.get('height')}",
            f"  source      : one combined frame, split - always synchronized",
            "",
        ]

        if s.rectifier is not None:
            lines += ["RECTIFICATION"] + [
                "  " + ln for ln in s.rectifier.describe().splitlines()[1:]
            ] + [""]

        if worker is None:
            lines += ["SLAM", f"  disabled: {s.slam_disabled_reason}", ""]
        else:
            lines += [
                "SLAM",
                f"  vocab load  : {worker.startup_seconds:.1f} s",
                f"  processed   : {worker.frames_processed}",
                f"  skipped     : {worker.frames_skipped} "
                f"(camera faster than SLAM - expected)",
            ]
            if worker.error:
                lines += [f"  ERROR       : {worker.error}"]
            if result is not None:
                lines += [
                    f"  state       : {result.state_name} ({result.state})",
                    f"  hint        : {STATE_HINTS.get(result.state, '')}",
                ]
            lines += [""]

        if result is not None:
            lines += [
                "LATENCY (this frame)",
                f"  rectify     : {result.rectify_ms:6.2f} ms",
                f"  ORB-SLAM3   : {result.track_ms:6.2f} ms",
                f"  total       : {result.total_ms:6.2f} ms",
            ]

        lines += [f"  GUI repaint : {self._gui_ms:6.2f} ms", ""]

        if s.recorder is not None:
            lines += ["RECORDING", f"  {s.recorder.status()}"]

        text = "\n".join(lines)

        # Only touch the widget when the text really changed, so the
        # user can scroll it without it being yanked back.
        if text != self.debug_text.toPlainText():
            scroll = self.debug_text.verticalScrollBar().value()
            self.debug_text.setPlainText(text)
            self.debug_text.verticalScrollBar().setValue(scroll)

    # ----------------------------------------------------------
    def _update_banner(self):
        s = self.state
        worker = s.worker

        if worker is not None and worker.error:
            self._show_banner(worker.error.splitlines()[0], "#f44336")
            return

        if not s.slam_enabled:
            reason = (s.slam_disabled_reason or "").lower()
            if "rejected" in reason:
                self._show_banner("CALIBRATION REJECTED - SCALE IS WRONG", "#ff9800")
            else:
                self._show_banner("CALIBRATION REQUIRED", "#ff9800")
            return

        if worker is not None and not worker.ready.is_set():
            self._show_banner("LOADING ORB VOCABULARY...", "#ffc107")
            return

        result = worker.latest() if worker else None

        if (getattr(self.state, "scale_unverified", False)
                and result is not None and result.state in (2, 5)):
            self._show_banner("TRACKING OK - METRIC SCALE UNVERIFIED", "#ffc107")
            return

        if result is not None and result.state in (1, 0):
            self._show_banner("MOVE THE CAMERA SIDEWAYS TO INITIALISE", "#ffc107")
            return

        if result is not None and result.state in (3, 4):
            self._show_banner("TRACKING LOST", "#f44336")
            return

        self.banner.setVisible(False)

    def _show_banner(self, text, colour):
        self.banner.setText(text)
        self.banner.setStyleSheet(
            f"background:{colour}22; color:{colour}; "
            f"border:1px solid {colour}; border-radius:3px; padding:6px;"
        )
        self.banner.setVisible(True)

    # ----------------------------------------------------------
    def closeEvent(self, event):  # noqa: N802
        self.timer.stop()
        self.state.shutdown()
        event.accept()
