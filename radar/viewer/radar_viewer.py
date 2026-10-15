#!/usr/bin/env python3
"""esp-radar live CSI viewer.

Decodes the binary USB stream (radar_bin.py), plots raw CSI and shows live
transport/CPU/latency benchmarks. Everything shown comes from real frames;
BENCH filler packets are counted separately and never plotted as CSI.

    .venv/bin/python radar_viewer.py [--port /dev/ttyACM0]
"""
from __future__ import annotations

import argparse
import collections
import os
import sys
import threading
import time

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from csiproto import SIG_MODE, LossTracker, SeqTracker
from radar_session import Session

HISTORY = 400            # frames kept per source for waterfall / time series
CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "captures")
SUBC_X = np.arange(-32, 32)


class SerialWorker(QtCore.QObject):
    """Background reader thread: owns the Session, hands batches to the GUI."""

    batch = QtCore.Signal(list)
    metrics = QtCore.Signal(dict)
    status = QtCore.Signal(str)

    def __init__(self, port: str):
        super().__init__()
        self.port = port
        self.sess: Session | None = None
        self.record_file = None
        self._stop = False
        self._lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self._stop = True

    def send(self, cmd: str):
        sess = self.sess
        if sess:
            try:
                sess.send(cmd)
            except OSError as e:
                self.status.emit(f"send failed: {e}")

    def set_record(self, path: str | None):
        with self._lock:
            if self.record_file:
                self.record_file.close()
            self.record_file = open(path, "ab") if path else None
            if self.sess:
                self.sess.dec.record_file = self.record_file

    def _run(self):
        while not self._stop:
            try:
                sess = Session(self.port, self.record_file)
            except OSError as e:
                self.status.emit(f"{self.port}: {e.strerror or e} (retrying)")
                time.sleep(1.0)
                continue
            self.sess = sess
            self.status.emit(f"connected {self.port}")
            sess.send("info")
            pending: list = []
            t_flush = time.monotonic()
            try:
                while not self._stop:
                    pending += sess.poll()
                    for ln in sess.dec.take_junk_lines():
                        pending.append(("RAW", ln))
                    r = sess.window_report()
                    if r:
                        self.metrics.emit(r)
                    if pending and time.monotonic() - t_flush > 0.03:
                        self.batch.emit(pending)
                        pending = []
                        t_flush = time.monotonic()
            except Exception as e:  # device unplugged / reset
                self.status.emit(f"disconnected: {e}")
            self.sess = None
            try:
                sess.ser.close()
            except Exception:
                pass
            time.sleep(0.5)


class SourceState:
    """Per-transmitter rolling history."""

    def __init__(self):
        self.count = 0
        self.t = collections.deque(maxlen=HISTORY)
        self.rssi = collections.deque(maxlen=HISTORY)
        self.amp_mean = collections.deque(maxlen=HISTORY)
        self.lltf_amp = collections.deque(maxlen=HISTORY)
        self.arrivals = collections.deque(maxlen=5000)
        self.seq = SeqTracker()
        self.last = None

    def rate(self, now: float) -> float:
        while self.arrivals and now - self.arrivals[0] > 1.0:
            self.arrivals.popleft()
        return float(len(self.arrivals))


def grid_box(title: str, rows: list[tuple[str, str]], labels: dict) -> QtWidgets.QGroupBox:
    grid = QtWidgets.QGridLayout()
    for i, (k, name) in enumerate(rows):
        grid.addWidget(QtWidgets.QLabel(name + ":"), i, 0, QtCore.Qt.AlignTop)
        lab = QtWidgets.QLabel("—")
        lab.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        lab.setWordWrap(True)
        lab.setMinimumWidth(280)
        grid.addWidget(lab, i, 1)
        labels[k] = lab
    box = QtWidgets.QGroupBox(title)
    box.setLayout(grid)
    return box


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, port: str):
        super().__init__()
        self.setWindowTitle(f"esp-radar CSI viewer — {port}")
        self.resize(1600, 1000)
        pg.setConfigOptions(antialias=False, imageAxisOrder="row-major")

        self.sources: dict[str, SourceState] = collections.defaultdict(SourceState)
        self.frame_ids = LossTracker(2**32)
        self.total_frames = 0
        self.all_arrivals = collections.deque(maxlen=20000)
        self.rate_hist = collections.deque(maxlen=HISTORY)
        self.stat: dict = {}
        self.hello: dict = {}
        self.aps: list[dict] = []
        self.selected: str | None = None  # None = auto (busiest source)
        self.gui_frames = 0
        self.gui_fps = 0.0
        self.t_gui = time.monotonic()

        self._build_ui()

        self.worker = SerialWorker(port)
        self.worker.batch.connect(self.on_batch)
        self.worker.metrics.connect(self.on_metrics)
        self.worker.status.connect(self.on_status)
        self.worker.start()

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(50)

    # ---------------- UI ----------------
    def _build_ui(self):
        split = QtWidgets.QSplitter()
        self.setCentralWidget(split)

        side = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(side)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(side)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(520)
        split.addWidget(scroll)

        self.conn_label = QtWidgets.QLabel("connecting…")
        self.conn_label.setStyleSheet("font-weight: bold")
        sl.addWidget(self.conn_label)

        self.L: dict[str, QtWidgets.QLabel] = {}
        sl.addWidget(grid_box("Selected CSI source", [
            ("device", "Device"), ("rate", "CSI rate (selected)"),
            ("rssi", "RSSI / noise floor"), ("channel", "Channel / BW"),
            ("subc", "Subcarriers (bytes)"), ("mode", "PHY mode"),
            ("seq", "Air loss (802.11 seq)"), ("ts", "Timestamps"),
        ], self.L))
        sl.addWidget(grid_box("Benchmark (live)", [
            ("b_csi", "CSI"), ("b_link", "Transport"), ("b_integrity", "Integrity"),
            ("b_drops", "Dropped on device"), ("b_cpu", "CPU"), ("b_ring", "Ring buffer"),
            ("b_mem", "Memory"), ("b_lat", "Latency acq→PC"), ("b_host", "Host"),
        ], self.L))

        src_box = QtWidgets.QGroupBox("Transmitter (source MAC)")
        sv = QtWidgets.QVBoxLayout(src_box)
        self.src_combo = QtWidgets.QComboBox()
        self.src_combo.addItem("auto (busiest)", None)
        self.src_combo.currentIndexChanged.connect(self.on_source_changed)
        sv.addWidget(self.src_combo)
        hb = QtWidgets.QHBoxLayout()
        lock = QtWidgets.QPushButton("Filter on ESP")
        lock.setToolTip("Tell the ESP to forward only this MAC")
        lock.clicked.connect(self.on_lock_mac)
        unlock = QtWidgets.QPushButton("Accept all")
        unlock.clicked.connect(lambda: self.worker.send("mac any"))
        hb.addWidget(lock)
        hb.addWidget(unlock)
        sv.addLayout(hb)
        sl.addWidget(src_box)

        ctl = QtWidgets.QGroupBox("Radio / transport")
        cg = QtWidgets.QGridLayout(ctl)
        self.ch_spin = QtWidgets.QSpinBox()
        self.ch_spin.setRange(1, 13)
        cg.addWidget(self.ch_spin, 0, 0)
        cg.addWidget(self._button("Set channel", lambda: self.worker.send(f"ch {self.ch_spin.value()}")), 0, 1)
        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.addItems(["all", "mgmt"])
        cg.addWidget(self.filter_combo, 1, 0)
        cg.addWidget(self._button("Set frame filter",
                                  lambda: self.worker.send(f"filter {self.filter_combo.currentText()}")), 1, 1)
        self.sink_combo = QtWidgets.QComboBox()
        self.sink_combo.addItems(["usb", "uart", "uart-text"])
        self.sink_combo.setToolTip("Data sink for CSI/BENCH. Stats always stay on USB.")
        cg.addWidget(self.sink_combo, 2, 0)
        cg.addWidget(self._button("Set data sink",
                                  lambda: self.worker.send(f"sink {self.sink_combo.currentText()}")), 2, 1)
        self.ring_combo = QtWidgets.QComboBox()
        self.ring_combo.addItems(["int", "psram"])
        cg.addWidget(self.ring_combo, 3, 0)
        cg.addWidget(self._button("Set ring", lambda: self.worker.send(f"ring {self.ring_combo.currentText()}")), 3, 1)
        cg.addWidget(self._button("Scan APs", self.on_scan), 4, 0)
        cg.addWidget(self._button("Info", lambda: self.worker.send("info")), 4, 1)
        self.csi_btn = QtWidgets.QPushButton("CSI on")
        self.csi_btn.setCheckable(True)
        self.csi_btn.setChecked(True)
        self.csi_btn.toggled.connect(lambda on: (self.worker.send(f"csi {'on' if on else 'off'}"),
                                                 self.csi_btn.setText("CSI on" if on else "CSI off")))
        cg.addWidget(self.csi_btn, 5, 0)
        self.rec_btn = QtWidgets.QPushButton("● Record")
        self.rec_btn.setCheckable(True)
        self.rec_btn.toggled.connect(self.on_record)
        cg.addWidget(self.rec_btn, 5, 1)
        self.phase_unwrap = QtWidgets.QCheckBox("Unwrap phase")
        self.phase_unwrap.setChecked(True)
        cg.addWidget(self.phase_unwrap, 6, 0, 1, 2)
        sl.addWidget(ctl)

        bench = QtWidgets.QGroupBox("Transport benchmark (BENCH filler, not CSI)")
        bg = QtWidgets.QGridLayout(bench)
        self.bench_pps = QtWidgets.QSpinBox()
        self.bench_pps.setRange(0, 20000)
        self.bench_pps.setSpecialValueText("max")
        self.bench_pps.setSuffix(" pkt/s")
        self.bench_size = QtWidgets.QSpinBox()
        self.bench_size.setRange(4, 2048)
        self.bench_size.setValue(480)
        self.bench_size.setSuffix(" B")
        bg.addWidget(self.bench_pps, 0, 0)
        bg.addWidget(self.bench_size, 0, 1)
        bg.addWidget(self._button("Start", lambda: self.worker.send(
            f"bench {self.bench_pps.value()} {self.bench_size.value()}")), 1, 0)
        bg.addWidget(self._button("Stop", lambda: self.worker.send("bench off")), 1, 1)
        sl.addWidget(bench)

        self.ap_table = QtWidgets.QTableWidget(0, 4)
        self.ap_table.setHorizontalHeaderLabels(["SSID", "BSSID", "Ch", "RSSI"])
        self.ap_table.horizontalHeader().setStretchLastSection(True)
        self.ap_table.verticalHeader().setVisible(False)
        self.ap_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.ap_table.cellDoubleClicked.connect(self.on_ap_clicked)
        self.ap_table.setToolTip("Double-click: tune to this AP's channel and follow its BSSID")
        self.ap_table.setMinimumHeight(140)
        sl.addWidget(self.ap_table)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setMinimumHeight(150)
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        sl.addWidget(self.log)

        # Plots
        glw = pg.GraphicsLayoutWidget()
        split.addWidget(glw)
        split.setStretchFactor(1, 1)

        self.p_amp = glw.addPlot(0, 0, title="Amplitude |H| per subcarrier (L-LTF, 20 MHz)")
        self.p_amp.setLabel("bottom", "subcarrier index")
        self.p_amp.showGrid(x=True, y=True, alpha=0.3)
        self.c_amp_mean = self.p_amp.plot(pen=pg.mkPen((120, 120, 120), width=2))
        self.c_amp = self.p_amp.plot(pen=pg.mkPen((80, 180, 255), width=2))

        self.p_phase = glw.addPlot(0, 1, title="Phase ∠H per subcarrier")
        self.p_phase.setLabel("bottom", "subcarrier index")
        self.p_phase.setLabel("left", "rad")
        self.p_phase.showGrid(x=True, y=True, alpha=0.3)
        self.c_phase = self.p_phase.plot(pen=None, symbol="o", symbolSize=4, symbolBrush=(255, 170, 60))

        self.p_wf = glw.addPlot(1, 0, title="Amplitude waterfall (time ↓ × subcarrier)")
        self.p_wf.setLabel("bottom", "subcarrier index")
        self.p_wf.setLabel("left", "frames ago")
        self.img = pg.ImageItem()
        self.img.setColorMap(pg.colormap.get("viridis"))
        self.p_wf.addItem(self.img)
        self.p_wf.invertY(True)

        self.p_iq = glw.addPlot(1, 1, title="Raw I/Q (current frame, full buffer)")
        self.p_iq.setLabel("bottom", "I (real)")
        self.p_iq.setLabel("left", "Q (imag)")
        self.p_iq.setAspectLocked(True)
        self.p_iq.showGrid(x=True, y=True, alpha=0.3)
        self.c_iq = self.p_iq.plot(pen=None, symbol="o", symbolSize=4, symbolBrush=(120, 220, 120, 180))

        self.p_ts = glw.addPlot(2, 0, title="Mean |H| over time (motion shows up here)")
        self.p_ts.setLabel("bottom", "seconds")
        self.p_ts.showGrid(x=True, y=True, alpha=0.3)
        self.c_ts = self.p_ts.plot(pen=pg.mkPen((80, 180, 255), width=1.5))

        self.p_rssi = glw.addPlot(2, 1, title="RSSI (dBm) and CSI rate (frames/s)")
        self.p_rssi.setLabel("bottom", "seconds")
        self.p_rssi.showGrid(x=True, y=True, alpha=0.3)
        self.p_rssi.addLegend(offset=(5, 5))
        self.c_rssi = self.p_rssi.plot(pen=pg.mkPen((255, 120, 120), width=1.5), name="RSSI")
        self.c_rate = self.p_rssi.plot(pen=pg.mkPen((200, 200, 80), width=1.5), name="rate (all)")

    def _button(self, text, slot):
        b = QtWidgets.QPushButton(text)
        b.clicked.connect(slot)
        return b

    # ---------------- events ----------------
    def on_status(self, msg: str):
        self.conn_label.setText(msg)
        self.append_log(f"[viewer] {msg}")

    def append_log(self, text: str):
        self.log.appendPlainText(text)

    def on_source_changed(self, _):
        self.selected = self.src_combo.currentData()

    def on_lock_mac(self):
        mac = self.current_mac()
        if mac:
            self.worker.send(f"mac {mac}")

    def on_scan(self):
        self.aps = []
        self.ap_table.setRowCount(0)
        self.worker.send("scan")

    def on_ap_clicked(self, row, _col):
        ap = self.aps[row]
        self.worker.send(f"ch {ap['channel']}")
        self.ch_spin.setValue(ap["channel"])
        idx = self.src_combo.findData(ap["bssid"])
        if idx < 0:
            self.src_combo.addItem(f"{ap['bssid']} ({ap['ssid'] or 'hidden'})", ap["bssid"])
            idx = self.src_combo.count() - 1
        self.src_combo.setCurrentIndex(idx)

    def on_record(self, on: bool):
        if on:
            os.makedirs(CAPTURE_DIR, exist_ok=True)
            path = os.path.abspath(os.path.join(CAPTURE_DIR, time.strftime("cap_%Y%m%d_%H%M%S.radar")))
            self.worker.set_record(path)
            self.rec_btn.setText("■ Recording…")
            self.append_log(f"[viewer] recording packets to {path}")
        else:
            self.worker.set_record(None)
            self.rec_btn.setText("● Record")
            self.append_log("[viewer] recording stopped")

    def on_batch(self, items: list):
        for kind, p in items:
            if kind == "CSI":
                self.total_frames += 1
                self.frame_ids.update(p.frame_id)
                self.all_arrivals.append(p.t_pc)
                s = self.sources[p.mac]
                if s.count == 0:
                    self.src_combo.addItem(p.mac, p.mac)
                s.count += 1
                s.arrivals.append(p.t_pc)
                s.seq.update(p.rx_seq)
                s.last = p
                s.t.append(p.t_pc)
                s.rssi.append(p.rssi)
                s.amp_mean.append(float(np.nanmean(np.abs(p.csi))))
                lltf = p.lltf()
                s.lltf_amp.append(np.abs(lltf) if lltf is not None else np.full(64, np.nan))
            elif kind == "STAT":
                self.stat = p
            elif kind == "HELLO":
                self.hello = p
                self.append_log(f"HELLO {p}")
                try:
                    self.ch_spin.setValue(int(p.get("ch", 1)))
                except ValueError:
                    pass
                sink = {"usb-jtag": "usb", "tinyusb-cdc": "usb", "uart-bin": "uart"}.get(p.get("sink"), p.get("sink"))
                i = self.sink_combo.findText(sink or "")
                if i >= 0:
                    self.sink_combo.setCurrentIndex(i)
            elif kind == "AP":
                self.aps.append(p)
                r = self.ap_table.rowCount()
                self.ap_table.insertRow(r)
                for c, v in enumerate((p["ssid"] or "(hidden)", p["bssid"], p["channel"], p["rssi"])):
                    self.ap_table.setItem(r, c, QtWidgets.QTableWidgetItem(str(v)))
            elif kind in ("LOG", "REPLY", "RAW"):
                if p.strip() and p.isprintable():
                    self.append_log(p if kind == "LOG" else f"{kind}: {p}")
            # BENCH / PONG: accounted in the Session metrics only

    def on_metrics(self, r: dict):
        L = self.L

        def g(k, f="{:.0f}", d="—"):
            return f.format(r[k]) if k in r else d

        L["b_csi"].setText(f"{g('csi_fps', '{:.1f}')} frames/s × {g('bytes_per_frame')} B = "
                           f"{g('csi_Bps', '{:.0f}')} B/s  (device accepted {g('dev_csi_fps', '{:.1f}')}/s, "
                           f"callback avg {g('cb_us_avg', '{:.1f}')} µs / max {g('cb_us_max')} µs)")
        L["b_link"].setText(f"host rx {r['host_rx_Bps'] / 1024:.1f} KiB/s  device tx {g('dev_tx_Bps', '{:.0f}')} B/s  "
                            f"sink {g('sink', '{}')}  write busy {g('write_busy_pct', '{:.0f}')}%\n"
                            f"BENCH {g('bench_pps')}/s = {r['bench_Bps'] / 1024:.1f} KiB/s")
        L["b_integrity"].setText(f"CRC errors {r['crc_errors']}  link seq missing {r['link_seq_missing']}  "
                                 f"skipped bytes {r['skipped_bytes']}  BENCH pattern errors {r['bench_bad']}")
        L["b_drops"].setText(f"CSI ring {g('ring_drops')}  control {g('ctrl_drops')}  no-host {g('link_drops')}  BENCH {g('bench_drops')}  "
                             f"(frame_id gaps seen on PC: {self.frame_ids.missing})")
        L["b_cpu"].setText(f"core 0 {g('cpu0', '{:.1f}')}%   core 1 {g('cpu1', '{:.1f}')}%")
        L["b_ring"].setText(f"{'PSRAM' if r.get('ring_psram') else 'internal'} {g('ring_size')} B, "
                            f"headroom min {g('ring_free_min')} B, queue wait avg {g('wait_us_avg')} µs / "
                            f"max {g('wait_us_max')} µs")
        if "heap" in r:
            L["b_mem"].setText(f"internal free {r['heap'] / 1024:.0f} KiB (min {r['heap_min'] / 1024:.0f})  "
                               f"PSRAM used {r['psram_used'] / 1024:.0f} / {r['psram_total'] / 1024:.0f} KiB")
        L["b_lat"].setText(f"avg {g('lat_avg', '{:.2f}')} ms  p95 {g('lat_p95', '{:.2f}')}  max {g('lat_max', '{:.2f}')} ms"
                           f"  (clock sync RTT {g('clock_rtt_ms', '{:.2f}')} ms)")
        L["b_host"].setText(f"parser {g('parse_MBps', '{:.1f}')} MB/s  viewer process CPU {g('host_cpu_pct')}% (all threads)  "
                            f"GUI {self.gui_fps:.0f} fps")

    def current_mac(self) -> str | None:
        if self.selected:
            return self.selected
        if not self.sources:
            return None
        now = time.monotonic()
        return max(self.sources, key=lambda m: self.sources[m].rate(now))

    # ---------------- drawing ----------------
    def refresh(self):
        now = time.monotonic()
        self.gui_frames += 1
        if now - self.t_gui >= 1.0:
            self.gui_fps = self.gui_frames / (now - self.t_gui)
            self.gui_frames = 0
            self.t_gui = now
        while self.all_arrivals and now - self.all_arrivals[0] > 1.0:
            self.all_arrivals.popleft()
        self.rate_hist.append((now, len(self.all_arrivals)))
        L = self.L

        if self.hello:
            h = self.hello
            L["device"].setText(f"{h.get('target')} rev{h.get('rev')} fw {h.get('version')} mac {h.get('mac')}\n"
                                f"filter={h.get('filter')} promisc={h.get('promisc')} sink={h.get('sink')}")

        mac = self.current_mac()
        if not mac or mac not in self.sources or self.sources[mac].last is None:
            return
        s = self.sources[mac]
        f = s.last
        L["rate"].setText(f"{s.rate(now):.0f} frames/s from {mac}  ({len(self.sources)} sources)")
        L["rssi"].setText(f"{f.rssi} dBm / {f.noise_floor} dBm  (SNR≈{f.rssi - f.noise_floor} dB)")
        L["channel"].setText(f"{f.channel}  {'40' if f.cwb else '20'} MHz  secondary={f.secondary}")
        L["subc"].setText(f"{f.n_subcarriers}  ({f.orig_len} B)  first_word_invalid={int(f.first_word_invalid)}")
        L["mode"].setText(f"{SIG_MODE.get(f.sig_mode, f.sig_mode)}  mcs={f.mcs}  rate={f.rate}  stbc={f.stbc}")
        L["seq"].setText(f"{s.seq.missing} missing ({s.seq.loss_ratio * 100:.1f} %)  seq={f.rx_seq}\n"
                         "(meaningful only for a dedicated TX)")
        L["ts"].setText(f"esp {f.host_us / 1e6:.3f} s  radio {f.rx_us} µs  frame #{f.frame_id}")

        lltf = f.lltf()
        if lltf is not None:
            self.c_amp.setData(SUBC_X, np.abs(lltf))
            hist = np.array(s.lltf_amp)
            with np.errstate(all="ignore"):
                self.c_amp_mean.setData(SUBC_X, np.nanmean(hist[-50:], axis=0))
            ph = np.angle(lltf)
            if self.phase_unwrap.isChecked():
                ok = np.isfinite(lltf) & (np.abs(lltf) > 0)
                ph = np.full(64, np.nan)
                ph[ok] = np.unwrap(np.angle(lltf[ok]))
            self.c_phase.setData(SUBC_X, ph)
            if len(hist):
                wf = hist[::-1]
                self.img.setImage(np.nan_to_num(wf), autoLevels=True)
                self.img.setRect(QtCore.QRectF(-32, 0, 64, len(wf)))
        else:
            self.c_amp.setData([], [])
            self.c_phase.setData([], [])
        iq = f.csi[np.isfinite(f.csi)]
        self.c_iq.setData(iq.real, iq.imag)

        t = np.array(s.t) - now
        self.c_ts.setData(t, np.array(s.amp_mean))
        self.c_rssi.setData(t, np.array(s.rssi))
        rh = np.array(self.rate_hist)
        self.c_rate.setData(rh[:, 0] - now, rh[:, 1])

    def closeEvent(self, e):
        self.worker.stop()
        self.worker.set_record(None)
        super().closeEvent(e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    args = ap.parse_args()
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow(args.port)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
