#!/usr/bin/env python3
"""
NOVEX - Stereo Configuration & Calibration Workbench.

A STANDALONE tool for finding the best rectified stereo configuration
for a very wide fisheye pair, and exporting it for ORB-SLAM3.

    python src/workbench.py

It does not touch the SLAM system. It reads your measured calibration,
never writes to config/stereo_calibration.yaml or
config/orbslam3_stereo.yaml, and exports only where you tell it to.

The quality signal to steer by is EPIPOLAR ERROR. After rectification a
real 3D point must land on the same image ROW in both eyes, so the
median vertical offset of feature matches, and the fraction of matches
within 1.5 px, say directly whether the geometry is right. Measured
here: correct geometry gives a median of 0.000 px and ~80% inliers,
while one degree of induced rotation error gives 7.2 px and 0.5%.
ORB-SLAM3's rectified stereo matching searches along rows, so this is
the same property it depends on.

Everything you change is tracked against the measured value, shown in
amber, and written into the exported file so an experimental setup can
never be mistaken for a measured one.
"""

import os
import sys
import threading
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (QImage, QPainter, QPen, QColor, QFont, QKeySequence,
                           QShortcut, QBrush)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QPushButton, QComboBox, QDoubleSpinBox, QSlider,
    QScrollArea, QSplitter, QStatusBar, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QFileDialog, QSizePolicy, QCheckBox, QSpinBox,
    QMessageBox, QHeaderView,
)

from camera import StereoCamera
from calibration import calibration_status, measured_fov
from workbench_core import (
    StereoParams, OutputConfig, WorkbenchProcessor, validate,
    export_orbslam3, FOV_PRESETS, RESOLUTION_PRESETS,
)


MONO = "monospace"

VIEW_RAW = 0
VIEW_RECTIFIED = 1
VIEW_MATCHES = 2
VIEW_EPIPOLAR = 3
VIEW_DISPARITY = 4
VIEW_OVERLAP = 5

VIEW_NAMES = [
    "Raw fisheye",
    "Rectified pair",
    "Feature matches",
    "Epipolar check",
    "Disparity / depth",
    "Stereo overlap",
]


# ==============================================================
class ProcessThread(threading.Thread):
    """Rectifies and measures off the GUI thread.

    Rebuilding the remap tables costs ~100 ms, so it happens here and
    only when a parameter actually changed.
    """

    def __init__(self, camera, params, output):
        super().__init__(name="workbench-process", daemon=True)
        self.camera = camera
        self.params = params
        self.output = output

        self._lock = threading.Lock()
        self._result = None
        self._dirty = True
        self._running = False
        self.processor = None
        self.want_disparity = False
        self.build_error = None
        self.fps = 0.0
        self._times = []

    def mark_dirty(self):
        self._dirty = True

    def latest(self):
        with self._lock:
            return self._result

    def run(self):
        self._running = True
        last_id = 0

        while self._running:
            if self._dirty or self.processor is None:
                self._dirty = False
                try:
                    self.processor = WorkbenchProcessor(self.params, self.output)
                    self.build_error = self.processor.error
                except Exception as exc:  # noqa: BLE001
                    self.processor = None
                    self.build_error = str(exc)

            frame = self.camera.read_new(last_id)
            if frame is None or self.processor is None:
                time.sleep(0.005)
                continue
            last_id = frame.frame_id

            gl = cv2.cvtColor(frame.left, cv2.COLOR_BGR2GRAY)
            gr = cv2.cvtColor(frame.right, cv2.COLOR_BGR2GRAY)

            try:
                rl, rr, disp, metrics, matches = self.processor.process(
                    gl, gr, want_disparity=self.want_disparity)
            except Exception as exc:  # noqa: BLE001
                self.build_error = f"processing failed: {exc}"
                time.sleep(0.1)
                continue

            with self._lock:
                self._result = {
                    "raw_l": gl, "raw_r": gr,
                    "rect_l": rl, "rect_r": rr,
                    "disparity": disp, "metrics": metrics,
                    "matches": matches, "frame_id": frame.frame_id,
                }

            now = time.perf_counter()
            self._times.append(now)
            if len(self._times) >= 2:
                span = self._times[-1] - self._times[0]
                if span >= 1.0:
                    self.fps = (len(self._times) - 1) / span
                    self._times = self._times[-2:]
                elif len(self._times) > 90:
                    self._times = self._times[-2:]

    def stop(self):
        self._running = False
        # Join, or Qt tears the interpreter down while this thread is
        # still inside OpenCV and the process aborts on exit.
        if self.is_alive():
            self.join(timeout=3.0)


# ==============================================================
class ParamRow(QWidget):
    """One parameter: spinbox, slider, and its measured value."""

    def __init__(self, param, on_change, parent=None):
        super().__init__(parent)
        self.param = param
        self.on_change = on_change
        self._updating = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.name = QLabel(param.label)
        self.name.setFont(QFont(MONO, 9))
        self.name.setFixedWidth(52)
        layout.addWidget(self.name)

        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(param.decimals)
        self.spin.setRange(param.lo, param.hi)
        self.spin.setSingleStep(param.step)
        self.spin.setValue(param.value)
        self.spin.setFont(QFont(MONO, 9))
        self.spin.setFixedWidth(112)
        self.spin.valueChanged.connect(self._from_spin)
        layout.addWidget(self.spin)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.slider.setValue(self._to_slider(param.value))
        self.slider.valueChanged.connect(self._from_slider)
        layout.addWidget(self.slider, 1)

        self.reset_btn = QPushButton("↺")
        self.reset_btn.setFixedWidth(24)
        self.reset_btn.setToolTip(
            f"Reset to the measured value: {param.measured:.6f} {param.unit}")
        self.reset_btn.clicked.connect(self._reset)
        layout.addWidget(self.reset_btn)

        self._refresh_style()

    def _to_slider(self, value):
        span = self.param.hi - self.param.lo
        if span <= 0:
            return 0
        return int(round((value - self.param.lo) / span * 1000))

    def _from_slider(self, pos):
        if self._updating:
            return
        span = self.param.hi - self.param.lo
        value = self.param.lo + (pos / 1000.0) * span
        self._updating = True
        self.spin.setValue(value)
        self._updating = False
        self._apply(value)

    def _from_spin(self, value):
        if self._updating:
            return
        self._updating = True
        self.slider.setValue(self._to_slider(value))
        self._updating = False
        self._apply(value)

    def _apply(self, value):
        self.param.value = float(value)
        self._refresh_style()
        self.on_change()

    def _reset(self):
        self._updating = True
        self.spin.setValue(self.param.measured)
        self.slider.setValue(self._to_slider(self.param.measured))
        self._updating = False
        self._apply(self.param.measured)

    def refresh(self):
        self._updating = True
        self.spin.setValue(self.param.value)
        self.slider.setValue(self._to_slider(self.param.value))
        self._updating = False
        self._refresh_style()

    def _refresh_style(self):
        if self.param.modified:
            # Amber: this number is now experimental, not measured.
            self.name.setStyleSheet("color:#ffc107; font-weight:bold;")
            self.spin.setStyleSheet("color:#ffc107;")
            self.reset_btn.setEnabled(True)
        else:
            self.name.setStyleSheet("color:#8a8f98;")
            self.spin.setStyleSheet("color:#e6e8ec;")
            self.reset_btn.setEnabled(False)


# ==============================================================
class ImageView(QWidget):
    """Draws whichever visualisation is selected."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._image = None
        self._buffer = None
        self.caption = ""

    def show_bgr(self, bgr, caption=""):
        if bgr is None:
            self._image = None
            self.caption = caption
            self.update()
            return

        h, w = bgr.shape[:2]
        pw, ph = max(1, self.width()), max(1, self.height() - 18)
        scale = min(pw / w, ph / h)
        dw, dh = max(1, int(w * scale)), max(1, int(h * scale))

        small = cv2.resize(bgr, (dw, dh),
                           interpolation=cv2.INTER_AREA if scale < 1
                           else cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(small, cv2.COLOR_GRAY2RGB) if small.ndim == 2 \
            else cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb = np.ascontiguousarray(rgb)

        self._buffer = rgb
        self._image = QImage(rgb.data, rgb.shape[1], rgb.shape[0],
                             rgb.strides[0], QImage.Format_RGB888)
        self.caption = caption
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(12, 13, 16))

        if self._image is None:
            p.setPen(QPen(QColor(120, 125, 135)))
            p.drawText(self.rect(), Qt.AlignCenter, self.caption or "no image")
            p.end()
            return

        ox = (self.width() - self._image.width()) / 2.0
        p.drawImage(QPointF(ox, 0), self._image)

        p.setPen(QPen(QColor(190, 195, 205)))
        p.setFont(QFont(MONO, 8))
        p.drawText(6, self.height() - 5, self.caption)
        p.end()


# ==============================================================
class Workbench(QMainWindow):
    def __init__(self, calib, camera, calib_status):
        super().__init__()

        self.calib = calib
        self.camera = camera
        self.calib_status = calib_status

        self.params = StereoParams(calib)
        self.output = OutputConfig(1280, 720, 120.0, "rectified")
        self.view_mode = VIEW_RECTIFIED
        self.snapshots = []

        self.setWindowTitle("NOVEX - Stereo Configuration Workbench")
        self.resize(1680, 1000)
        self._theme()

        self.worker = ProcessThread(camera, self.params, self.output)

        self._build_ui()
        self.worker.start()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(40)

        self._revalidate()

    # ----------------------------------------------------------
    def _theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#14161a; color:#e6e8ec; }
            QGroupBox { border:1px solid #262a31; border-radius:4px;
                margin-top:14px; padding-top:6px; font-family:monospace;
                font-size:10px; color:#8a8f98; }
            QGroupBox::title { subcontrol-origin:margin; left:8px; padding:0 4px; }
            QPushButton { background:#1e222a; border:1px solid #2d323b;
                border-radius:3px; padding:5px 9px; font-family:monospace;
                font-size:11px; }
            QPushButton:hover { background:#262b34; }
            QPushButton:checked { background:#2b4a63; border-color:#3d7ea6; }
            QPushButton:disabled { color:#4a4f58; }
            QComboBox, QDoubleSpinBox, QSpinBox { background:#1e222a;
                border:1px solid #2d323b; border-radius:3px; padding:3px 6px;
                font-family:monospace; }
            QPlainTextEdit, QTableWidget { background:#0f1114;
                border:1px solid #262a31; font-family:monospace; font-size:10px; }
            QHeaderView::section { background:#1e222a; color:#8a8f98;
                border:0; padding:3px; font-family:monospace; font-size:10px; }
            QStatusBar { background:#0f1114; font-family:monospace; }
            QCheckBox { font-family:monospace; font-size:11px; }
            QSplitter::handle { background:#262a31; }
            QScrollArea { border:0; }
            QSlider::groove:horizontal { height:4px; background:#262a31; }
            QSlider::handle:horizontal { width:10px; background:#4a86b8;
                margin:-4px 0; border-radius:2px; }
        """)

    # ----------------------------------------------------------
    def _build_ui(self):
        self.view = ImageView()

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(6, 6, 6, 6)
        lv.setSpacing(6)
        lv.addWidget(self._build_view_bar())
        lv.addWidget(self.view, 1)
        lv.addWidget(self._build_metrics())
        lv.addWidget(self._build_warnings())

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(6, 6, 6, 6)
        rv.setSpacing(6)
        rv.addWidget(self._build_output_box())
        rv.addWidget(self._build_params_box(), 1)
        rv.addWidget(self._build_compare_box())
        rv.addWidget(self._build_export_box())
        right.setMinimumWidth(470)
        right.setMaximumWidth(560)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setSizes([1100, 520])
        self.setCentralWidget(split)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

        src = self.calib.path
        note = ("MEASURED calibration" if self.calib_status == "OK"
                else f"calibration status: {self.calib_status}")
        self.status.showMessage(f"{note} - {src}")

        for i, name in enumerate(VIEW_NAMES):
            QShortcut(QKeySequence(str(i + 1)), self,
                      activated=lambda n=i: self._set_view(n))
        QShortcut(QKeySequence("Esc"), self, activated=self.close)

    # ----------------------------------------------------------
    def _build_view_bar(self):
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)

        self.view_combo = QComboBox()
        for i, n in enumerate(VIEW_NAMES):
            self.view_combo.addItem(f"{i + 1}  {n}")
        self.view_combo.setCurrentIndex(self.view_mode)
        self.view_combo.currentIndexChanged.connect(self._set_view)
        row.addWidget(self.view_combo)

        row.addStretch(1)

        self.chk_epilines = QCheckBox("epipolar lines")
        self.chk_epilines.setChecked(True)
        row.addWidget(self.chk_epilines)

        self.lbl_procfps = QLabel("--")
        self.lbl_procfps.setFont(QFont(MONO, 9))
        row.addWidget(self.lbl_procfps)
        return box

    def _build_output_box(self):
        box = QGroupBox("OUTPUT GEOMETRY")
        g = QGridLayout(box)
        g.setContentsMargins(8, 6, 8, 8)
        g.setSpacing(4)

        g.addWidget(QLabel("model"), 0, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["rectified (pinhole)", "fisheye (KB8, no rectify)"])
        self.model_combo.currentIndexChanged.connect(self._model_changed)
        g.addWidget(self.model_combo, 0, 1, 1, 4)

        g.addWidget(QLabel("FOV preset"), 1, 0)
        self.preset_btns = []
        for i, fov in enumerate(FOV_PRESETS):
            b = QPushButton(f"{fov:.0f}°")
            b.setCheckable(True)
            b.setChecked(abs(fov - self.output.hfov) < 0.01)
            b.clicked.connect(lambda _=False, f=fov: self._set_fov(f))
            g.addWidget(b, 1, 1 + i)
            self.preset_btns.append((fov, b))

        g.addWidget(QLabel("FOV °"), 2, 0)
        self.fov_spin = QDoubleSpinBox()
        self.fov_spin.setRange(20.0, 175.0)
        self.fov_spin.setDecimals(2)
        self.fov_spin.setSingleStep(1.0)
        self.fov_spin.setValue(self.output.hfov)
        self.fov_spin.valueChanged.connect(self._fov_spin_changed)
        g.addWidget(self.fov_spin, 2, 1, 1, 2)

        self.fov_slider = QSlider(Qt.Horizontal)
        self.fov_slider.setRange(2000, 17500)
        self.fov_slider.setValue(int(self.output.hfov * 100))
        self.fov_slider.valueChanged.connect(
            lambda v: self.fov_spin.setValue(v / 100.0))
        g.addWidget(self.fov_slider, 2, 3, 1, 3)

        g.addWidget(QLabel("resolution"), 3, 0)
        self.res_combo = QComboBox()
        for label, w, h in RESOLUTION_PRESETS:
            self.res_combo.addItem(label, (w, h))
        self.res_combo.addItem("custom", None)
        self.res_combo.currentIndexChanged.connect(self._res_changed)
        g.addWidget(self.res_combo, 3, 1, 1, 2)

        self.w_spin = QSpinBox()
        self.w_spin.setRange(160, 4096)
        self.w_spin.setValue(self.output.width)
        self.w_spin.valueChanged.connect(self._custom_res)
        g.addWidget(self.w_spin, 3, 3, 1, 1)
        self.h_spin = QSpinBox()
        self.h_spin.setRange(120, 4096)
        self.h_spin.setValue(self.output.height)
        self.h_spin.valueChanged.connect(self._custom_res)
        g.addWidget(self.h_spin, 3, 4, 1, 2)

        g.addWidget(QLabel("zoom"), 4, 0)
        self.zoom_spin = QDoubleSpinBox()
        self.zoom_spin.setRange(0.3, 3.0)
        self.zoom_spin.setSingleStep(0.02)
        self.zoom_spin.setDecimals(3)
        self.zoom_spin.setValue(1.0)
        self.zoom_spin.valueChanged.connect(self._zoom_changed)
        g.addWidget(self.zoom_spin, 4, 1, 1, 2)

        g.addWidget(QLabel("centre dx/dy"), 5, 0)
        self.cxs = QDoubleSpinBox(); self.cxs.setRange(-500, 500)
        self.cxs.setValue(0.0); self.cxs.valueChanged.connect(self._shift_changed)
        g.addWidget(self.cxs, 5, 1, 1, 2)
        self.cys = QDoubleSpinBox(); self.cys.setRange(-500, 500)
        self.cys.setValue(0.0); self.cys.valueChanged.connect(self._shift_changed)
        g.addWidget(self.cys, 5, 3, 1, 3)

        g.addWidget(QLabel("fps"), 6, 0)
        self.fps_spin = QSpinBox(); self.fps_spin.setRange(1, 240)
        self.fps_spin.setValue(30)
        self.fps_spin.valueChanged.connect(
            lambda v: setattr(self.output, "fps", int(v)))
        g.addWidget(self.fps_spin, 6, 1, 1, 2)
        return box

    def _build_params_box(self):
        box = QGroupBox("CAMERA PARAMETERS   (amber = changed from measured)")
        outer = QVBoxLayout(box)
        outer.setContentsMargins(6, 4, 6, 6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(2, 2, 2, 2)
        v.setSpacing(2)

        self.rows = []
        for group, params in self.params.groups().items():
            head = QLabel(group)
            head.setFont(QFont(MONO, 9, QFont.Bold))
            head.setStyleSheet("color:#5a9fd4; padding-top:6px;")
            v.addWidget(head)
            for p in params:
                row = ParamRow(p, self._params_changed)
                v.addWidget(row)
                self.rows.append(row)

        v.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        btns = QHBoxLayout()
        b = QPushButton("Reset all to measured")
        b.clicked.connect(self._reset_all)
        btns.addWidget(b)
        outer.addLayout(btns)
        return box

    def _build_metrics(self):
        box = QGroupBox("MEASUREMENTS")
        g = QGridLayout(box)
        g.setContentsMargins(8, 4, 8, 6)
        g.setVerticalSpacing(2)

        self.metric_labels = {}
        keys = [
            ("features", "Features L/R"), ("matches", "Stereo matches"),
            ("inlier", "Epipolar inliers"), ("epi", "Epipolar median"),
            ("p95", "Epipolar p95"), ("coverage", "Valid pixels"),
            ("fov", "Usable FOV"), ("fx", "Rectified fx"),
            ("baseline", "Baseline"), ("disp", "Disparity valid"),
            ("depth", "Median depth"), ("ms", "Process time"),
        ]
        for i, (key, label) in enumerate(keys):
            r, c = i % 6, i // 6
            name = QLabel(label)
            name.setFont(QFont(MONO, 9))
            name.setStyleSheet("color:#8a8f98;")
            val = QLabel("--")
            val.setFont(QFont(MONO, 9, QFont.Bold))
            g.addWidget(name, r, c * 2)
            g.addWidget(val, r, c * 2 + 1)
            g.setColumnStretch(c * 2 + 1, 1)
            self.metric_labels[key] = val
        return box

    def _build_warnings(self):
        box = QGroupBox("VALIDATION")
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 4, 6, 6)
        self.warn_text = QPlainTextEdit()
        self.warn_text.setReadOnly(True)
        self.warn_text.setMaximumHeight(96)
        v.addWidget(self.warn_text)
        return box

    def _build_compare_box(self):
        box = QGroupBox("COMPARE CONFIGURATIONS")
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 4, 6, 6)
        v.setSpacing(4)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["name", "FOV", "res", "matches", "inlier%", "epi med"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setMaximumHeight(130)
        self.table.verticalHeader().setVisible(False)
        v.addWidget(self.table)

        row = QHBoxLayout()
        b1 = QPushButton("Snapshot current")
        b1.clicked.connect(self._snapshot)
        row.addWidget(b1)
        b2 = QPushButton("Restore selected")
        b2.clicked.connect(self._restore)
        row.addWidget(b2)
        b3 = QPushButton("Motion test (10 s)")
        b3.setToolTip("Move the camera while this runs; it reports how the "
                      "configuration holds up under motion.")
        b3.clicked.connect(self._motion_test)
        row.addWidget(b3)
        v.addLayout(row)
        return box

    def _build_export_box(self):
        box = QGroupBox("EXPORT")
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 4, 6, 6)

        self.export_btn = QPushButton("Export for ORB-SLAM3")
        self.export_btn.setStyleSheet(
            "background:#2b5a3a; border-color:#3d8a5a; padding:8px; "
            "font-weight:bold;")
        self.export_btn.clicked.connect(self._export)
        v.addWidget(self.export_btn)

        self.export_note = QLabel(
            "Writes a complete ORB-SLAM3 YAML. Your existing config is "
            "never modified.")
        self.export_note.setWordWrap(True)
        self.export_note.setFont(QFont(MONO, 8))
        self.export_note.setStyleSheet("color:#8a8f98;")
        v.addWidget(self.export_note)
        return box

    # ----------------------------------------------------------
    # Changes
    # ----------------------------------------------------------
    def _params_changed(self):
        self.worker.mark_dirty()
        self._revalidate()

    def _set_view(self, index):
        self.view_mode = index
        self.view_combo.setCurrentIndex(index)
        self.worker.want_disparity = (index == VIEW_DISPARITY)

    def _set_fov(self, fov):
        self.fov_spin.setValue(fov)

    def _fov_spin_changed(self, value):
        self.output.hfov = float(value)
        self.fov_slider.blockSignals(True)
        self.fov_slider.setValue(int(value * 100))
        self.fov_slider.blockSignals(False)
        for fov, b in self.preset_btns:
            b.setChecked(abs(fov - value) < 0.01)
        self._params_changed()

    def _model_changed(self, index):
        self.output.model = "rectified" if index == 0 else "fisheye"
        wide = self.output.model == "rectified"
        for w in (self.fov_spin, self.fov_slider, self.zoom_spin,
                  self.cxs, self.cys):
            w.setEnabled(wide)
        for _, b in self.preset_btns:
            b.setEnabled(wide)
        self._params_changed()

    def _res_changed(self, index):
        data = self.res_combo.itemData(index)
        if data is None:
            return
        w, h = data
        self.w_spin.blockSignals(True); self.h_spin.blockSignals(True)
        self.w_spin.setValue(w); self.h_spin.setValue(h)
        self.w_spin.blockSignals(False); self.h_spin.blockSignals(False)
        self.output.width, self.output.height = w, h
        self._params_changed()

    def _custom_res(self):
        self.output.width = int(self.w_spin.value())
        self.output.height = int(self.h_spin.value())
        self.res_combo.blockSignals(True)
        self.res_combo.setCurrentIndex(self.res_combo.count() - 1)
        self.res_combo.blockSignals(False)
        self._params_changed()

    def _zoom_changed(self, value):
        self.output.zoom = float(value)
        self._params_changed()

    def _shift_changed(self):
        self.output.cx_shift = float(self.cxs.value())
        self.output.cy_shift = float(self.cys.value())
        self._params_changed()

    def _reset_all(self):
        self.params.reset_all()
        for row in self.rows:
            row.refresh()
        self._params_changed()
        self.status.showMessage("All camera parameters reset to measured", 4000)

    # ----------------------------------------------------------
    def _revalidate(self):
        issues = validate(self.params, self.output)
        lines = []
        worst = "ok"
        for sev, msg in issues:
            tag = {"error": "ERROR", "warn": "WARN ", "info": "info "}[sev]
            lines.append(f"[{tag}] {msg}")
            if sev == "error":
                worst = "error"
            elif sev == "warn" and worst != "error":
                worst = "warn"

        modified = self.params.modified_keys()
        if modified:
            lines.insert(0, f"[EDIT ] {len(modified)} parameter(s) changed from "
                            f"the measured calibration: "
                            f"{', '.join(sorted(modified))}")

        if not lines:
            lines = ["[ ok  ] No issues. All values as measured."]

        self.warn_text.setPlainText("\n".join(lines))
        colour = {"ok": "#3ddc84", "warn": "#ffc107", "error": "#f44336"}[worst]
        self.warn_text.setStyleSheet(
            f"border:1px solid {colour}; color:#b8bcc4;")
        return worst

    # ----------------------------------------------------------
    def _tick(self):
        result = self.worker.latest()
        self.lbl_procfps.setText(f"{self.worker.fps:4.1f} proc fps")

        if self.worker.build_error:
            self.view.show_bgr(None, f"configuration invalid: {self.worker.build_error}")
            return
        if result is None:
            self.view.show_bgr(None, "waiting for frames...")
            return

        self._render(result)
        self._update_metrics(result["metrics"])

    def _render(self, r):
        mode = self.view_mode
        if mode == VIEW_RAW:
            self.view.show_bgr(np.hstack([r["raw_l"], r["raw_r"]]),
                               "RAW fisheye - left | right (unmodified sensor data)")
        elif mode == VIEW_RECTIFIED:
            eff = getattr(self.worker.processor, "effective_size",
                          self.output.size)
            label = (f"RECTIFIED - left | right   {eff[0]}x{eff[1]} @ "
                     f"{self.output.effective_hfov():.1f}°"
                     if self.output.model == "rectified" else
                     f"RAW FISHEYE (no rectification) - left | right   "
                     f"{eff[0]}x{eff[1]}, full FOV")
            self.view.show_bgr(np.hstack([r["rect_l"], r["rect_r"]]), label)
        elif mode == VIEW_MATCHES:
            self.view.show_bgr(self._draw_matches(r), "stereo feature matches")
        elif mode == VIEW_EPIPOLAR:
            self.view.show_bgr(self._draw_epipolar(r),
                               "epipolar check - matches must sit on the SAME row")
        elif mode == VIEW_DISPARITY:
            self.view.show_bgr(self._draw_disparity(r),
                               "disparity (diagnostic only - ORB-SLAM3 does not use it)")
        elif mode == VIEW_OVERLAP:
            self.view.show_bgr(self._draw_overlap(r),
                               "stereo overlap - green = both eyes see it")

    def _draw_matches(self, r):
        canvas = cv2.cvtColor(np.hstack([r["rect_l"], r["rect_r"]]),
                              cv2.COLOR_GRAY2BGR)
        w = r["rect_l"].shape[1]
        for (p1, p2) in r["matches"][:400]:
            dy = abs(p1[1] - p2[1])
            colour = (80, 230, 120) if dy < 1.5 else (60, 90, 240)
            a = (int(p1[0]), int(p1[1]))
            b = (int(p2[0]) + w, int(p2[1]))
            cv2.line(canvas, a, b, colour, 1)
            cv2.circle(canvas, a, 2, colour, -1)
        return canvas

    def _draw_epipolar(self, r):
        canvas = cv2.cvtColor(np.hstack([r["rect_l"], r["rect_r"]]),
                              cv2.COLOR_GRAY2BGR)
        h, w = r["rect_l"].shape[:2]
        if self.chk_epilines.isChecked():
            for y in range(0, h, max(24, h // 24)):
                cv2.line(canvas, (0, y), (canvas.shape[1], y), (55, 60, 70), 1)
        for (p1, p2) in r["matches"][:400]:
            dy = abs(p1[1] - p2[1])
            colour = (80, 230, 120) if dy < 1.5 else (60, 90, 240)
            cv2.circle(canvas, (int(p1[0]), int(p1[1])), 3, colour, 1)
            cv2.circle(canvas, (int(p2[0]) + w, int(p2[1])), 3, colour, 1)
            if dy >= 1.5:
                cv2.line(canvas, (int(p2[0]) + w, int(p1[1])),
                         (int(p2[0]) + w, int(p2[1])), (60, 90, 240), 1)
        return canvas

    def _draw_disparity(self, r):
        disp = r["disparity"]
        if disp is None:
            return r["rect_l"]
        d = disp.copy()
        d[d < 0] = 0
        if d.max() > 0:
            d = (d / d.max() * 255).astype(np.uint8)
        else:
            d = d.astype(np.uint8)
        colour = cv2.applyColorMap(d, cv2.COLORMAP_TURBO)
        colour[disp <= 0.5] = (25, 25, 28)
        return cv2.resize(colour, (r["rect_l"].shape[1], r["rect_l"].shape[0]),
                          interpolation=cv2.INTER_NEAREST)

    def _draw_overlap(self, r):
        """Where the two rectified images both contain real pixels."""
        l, rr = r["rect_l"], r["rect_r"]
        canvas = cv2.cvtColor(l, cv2.COLOR_GRAY2BGR)
        both = (l > 0) & (rr > 0)
        only_left = (l > 0) & (rr == 0)
        canvas[both] = (canvas[both] * 0.6 + np.array([0, 90, 0]) * 0.4).astype(np.uint8)
        canvas[only_left] = (canvas[only_left] * 0.6
                             + np.array([0, 0, 110]) * 0.4).astype(np.uint8)
        pct = 100.0 * both.mean()
        cv2.putText(canvas, f"both eyes: {pct:.1f}% of frame", (12, 26),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        return canvas

    # ----------------------------------------------------------
    def _update_metrics(self, m):
        def col(widget_key, text, colour="#e6e8ec"):
            self.metric_labels[widget_key].setText(text)
            self.metric_labels[widget_key].setStyleSheet(f"color:{colour};")

        col("features", f"{m.features_left} / {m.features_right}")
        col("matches", f"{m.matches}")

        inl = ("#3ddc84" if m.inlier_pct >= 70 else
               "#ffc107" if m.inlier_pct >= 40 else "#f44336")
        col("inlier", f"{m.inliers}  ({m.inlier_pct:.1f}%)", inl)

        epi = ("#3ddc84" if m.epipolar_median < 1.0 else
               "#ffc107" if m.epipolar_median < 3.0 else "#f44336")
        col("epi", f"{m.epipolar_median:.2f} px", epi)
        col("p95", f"{m.epipolar_p95:.1f} px")

        cov = ("#3ddc84" if m.coverage >= 98 else
               "#ffc107" if m.coverage >= 85 else "#f44336")
        col("coverage", f"{m.coverage:.1f}%", cov)

        col("fov", f"{m.hfov:.1f}° x {m.vfov:.1f}°")
        col("fx", f"{m.fx:.1f} px")
        col("baseline", f"{m.baseline_mm:.2f} mm")
        col("disp", f"{m.disparity_pct:.1f}%" if m.disparity_pct else "--")
        col("depth", f"{m.median_depth:.2f} m" if m.median_depth else "--")
        col("ms", f"{m.process_ms:.0f} ms")

    # ----------------------------------------------------------
    def _snapshot(self):
        r = self.worker.latest()
        if r is None:
            return
        m = r["metrics"]
        name = f"cfg{len(self.snapshots) + 1}"

        snap = {
            "name": name,
            "values": {k: p.value for k, p in self.params.params.items()},
            "output": (self.output.width, self.output.height, self.output.hfov,
                       self.output.model, self.output.zoom,
                       self.output.cx_shift, self.output.cy_shift),
            "metrics": m,
        }
        self.snapshots.append(snap)

        row = self.table.rowCount()
        self.table.insertRow(row)
        for c, text in enumerate([
            name, f"{self.output.effective_hfov():.0f}",
            f"{self.output.width}x{self.output.height}",
            f"{m.matches}", f"{m.inlier_pct:.0f}", f"{m.epipolar_median:.2f}",
        ]):
            item = QTableWidgetItem(text)
            item.setFont(QFont(MONO, 9))
            self.table.setItem(row, c, item)
        self.status.showMessage(f"Snapshot {name} taken", 3000)

    def _restore(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.snapshots):
            self.status.showMessage("Select a row first", 3000)
            return
        snap = self.snapshots[row]
        for k, v in snap["values"].items():
            self.params.set(k, v)
        (self.output.width, self.output.height, self.output.hfov,
         self.output.model, self.output.zoom,
         self.output.cx_shift, self.output.cy_shift) = snap["output"]

        for r in self.rows:
            r.refresh()
        self.fov_spin.setValue(self.output.hfov)
        self.w_spin.setValue(self.output.width)
        self.h_spin.setValue(self.output.height)
        self.zoom_spin.setValue(self.output.zoom)
        self._params_changed()
        self.status.showMessage(f"Restored {snap['name']}", 3000)

    # ----------------------------------------------------------
    def _motion_test(self):
        """Sample the metrics for 10 s while you move the camera.

        A configuration that looks fine on a static scene can still fall
        apart under motion, which is when it actually matters.
        """
        self.status.showMessage(
            "MOTION TEST: move the camera around for 10 seconds...", 11000)
        samples = []
        start = time.perf_counter()

        def sample():
            r = self.worker.latest()
            if r is not None:
                m = r["metrics"]
                samples.append((m.matches, m.inlier_pct, m.epipolar_median,
                                m.features_left))
            if time.perf_counter() - start < 10.0:
                QTimer.singleShot(100, sample)
            else:
                self._motion_report(samples)

        QTimer.singleShot(100, sample)

    def _motion_report(self, samples):
        if not samples:
            self.status.showMessage("Motion test: no samples", 5000)
            return
        a = np.array(samples, dtype=float)
        msg = (
            f"MOTION TEST over {len(samples)} samples\n\n"
            f"  stereo matches   mean {a[:, 0].mean():6.0f}   min {a[:, 0].min():5.0f}\n"
            f"  epipolar inlier% mean {a[:, 1].mean():6.1f}   min {a[:, 1].min():5.1f}\n"
            f"  epipolar median  mean {a[:, 2].mean():6.2f}   max {a[:, 2].max():5.2f} px\n"
            f"  features (left)  mean {a[:, 3].mean():6.0f}   min {a[:, 3].min():5.0f}\n\n"
            f"A configuration that holds its inlier rate and keeps the median\n"
            f"low while moving is one ORB-SLAM3 can actually track with.\n"
            f"Sharp drops usually mean motion blur (shorten the exposure) or\n"
            f"a geometry that only works at one depth."
        )
        QMessageBox.information(self, "Motion test", msg)

    # ----------------------------------------------------------
    def _export(self):
        worst = self._revalidate()
        if worst == "error":
            QMessageBox.critical(
                self, "Cannot export",
                "The configuration has errors that make it physically "
                "impossible. Fix the items marked ERROR first.")
            return

        default = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config",
            f"workbench_{self.output.model}_"
            f"{self.output.effective_hfov():.0f}deg_"
            f"{self.output.width}x{self.output.height}.yaml")

        path, _ = QFileDialog.getSaveFileName(
            self, "Export ORB-SLAM3 settings", default, "YAML (*.yaml)")
        if not path:
            return

        modified = self.params.modified_keys()
        if modified:
            answer = QMessageBox.question(
                self, "Experimental values",
                f"{len(modified)} parameter(s) differ from the measured "
                f"calibration:\n\n  " + "\n  ".join(sorted(modified)) +
                "\n\nThese are experimental, not measured. The exported file "
                "will say so in its header.\n\nExport anyway?",
                QMessageBox.Yes | QMessageBox.No)
            if answer != QMessageBox.Yes:
                return

        r = self.worker.latest()
        notes = ""
        if r is not None:
            m = r["metrics"]
            notes = (f"Measured live at export: {m.matches} stereo matches, "
                     f"{m.inlier_pct:.1f}% epipolar inliers, "
                     f"median epipolar error {m.epipolar_median:.2f} px, "
                     f"{m.coverage:.1f}% valid pixels.")

        try:
            export_orbslam3(path, self.params, self.output, notes=notes)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Export failed", str(exc))
            return

        QMessageBox.information(
            self, "Exported",
            f"Written:\n{path}\n\nUse it with:\n"
            f"  python src/main.py --settings {path}\n\n"
            f"Your existing configuration was not modified.")
        self.status.showMessage(f"Exported {path}", 8000)

    # ----------------------------------------------------------
    def closeEvent(self, event):  # noqa: N802
        self.timer.stop()
        self.worker.stop()
        self.camera.stop()
        event.accept()


# ==============================================================
def main():
    import argparse

    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)

    ap = argparse.ArgumentParser(description="Novex stereo configuration workbench")
    ap.add_argument("--calibration",
                    default=os.path.join(root, "config", "stereo_calibration.yaml"))
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=2560)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--lock-exposure", type=float, default=None, metavar="MS")
    args = ap.parse_args()

    print()
    print("=" * 62)
    print(" NOVEX STEREO CONFIGURATION WORKBENCH")
    print("=" * 62)
    print("Standalone tool. It reads your calibration and never modifies")
    print("config/stereo_calibration.yaml or config/orbslam3_stereo.yaml.")
    print()

    status, message, calib = calibration_status(args.calibration,
                                                max_baseline_m=None)
    if calib is None:
        print(f"Calibration: {status}")
        print(message)
        return 1

    print(f"Calibration: {status}")
    print(calib.describe())
    print()

    cam = StereoCamera(index=args.camera, width=args.width,
                       height=args.height, fps=args.fps)
    if not cam.open():
        print(f"Camera: FAILED - {cam.error}")
        return 1

    for w in cam.mode_warnings():
        print(f"WARNING: {w}")

    if args.lock_exposure is not None:
        applied, failed = cam.apply_controls({
            "auto_exposure": 1,
            "white_balance_automatic": 0,
            "exposure_time_absolute": max(1, int(round(args.lock_exposure * 10))),
        })
        print(f"Exposure locked: {applied}")
        if failed:
            print(f"  rejected: {failed}")

    cam.start()
    print(f"Camera: {cam.actual['width']}x{cam.actual['height']} "
          f"{cam.actual['fourcc']}")
    print()
    print("Keys 1-6 switch views. ESC quits.")
    print()

    app = QApplication(sys.argv)
    win = Workbench(calib, cam, status)
    win.show()
    code = app.exec()
    cam.stop()
    return code


if __name__ == "__main__":
    sys.exit(main())
