"""Live session on the binary link: decoding, clock sync and per-second metrics.

Shared by radar_cli.py and radar_viewer.py so both report identical numbers.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from radar_bin import SINKS, ClockSync, Decoder
from serial_link import open_port

PING_INTERVAL = 0.25


class Metrics:
    """One-second window of host-side and device-side measurements."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.rx_bytes = 0            # bytes read from the port
        self.csi = 0
        self.csi_bytes = 0           # full CSI packet bytes on the wire
        self.bench = 0
        self.bench_bytes = 0
        self.bench_bad = 0
        self.latency_ms: list[float] = []
        self.parse_s = 0.0


class Session:
    def __init__(self, port: str, record_file=None):
        self.ser = open_port(port)
        self.dec = Decoder(record_file)
        self.clock = ClockSync()
        self.win = Metrics()
        self.bench_seq = None        # BENCH loss tracking
        self.bench_missing = 0
        self.bench_received = 0
        self.stat: dict | None = None
        self.prev_stat: dict | None = None
        self.t_last_ping = 0.0
        self.t_win = time.monotonic()
        self.cpu_t0 = time.process_time()
        self._wlock = threading.Lock()
        self.send("")   # flush junk the device may have received while rebooting on open

    def send(self, cmd: str):
        with self._wlock:   # GUI thread and reader thread (pings) both write
            self.ser.write((cmd.strip() + "\n").encode())

    def poll(self) -> list:
        """Reads what is available, returns decoded (kind, obj) items."""
        now = time.monotonic()
        if now - self.t_last_ping > PING_INTERVAL:
            self.send(f"ping {ClockSync.token()}")
            self.t_last_ping = now
        data = self.ser.read(self.ser.in_waiting or 1)
        if not data:
            return []
        t = time.monotonic()
        self.win.rx_bytes += len(data)
        items = self.dec.feed(data, t)
        self.win.parse_s += time.monotonic() - t
        for kind, obj in items:
            if kind == "CSI":
                self.win.csi += 1
                self.win.csi_bytes += 20 + 36 + len(obj.raw) + 4
                pc = self.clock.esp_to_pc(obj.host_us)
                if pc is not None:
                    self.win.latency_ms.append((obj.t_pc - pc) * 1e3)
            elif kind == "BENCH":
                self.win.bench += 1
                self.win.bench_bytes += 20 + obj.size + 4
                if not obj.pattern_ok:
                    self.win.bench_bad += 1
                if self.bench_seq is not None and obj.seq > self.bench_seq + 1:
                    self.bench_missing += obj.seq - self.bench_seq - 1
                self.bench_seq = obj.seq
                self.bench_received += 1
            elif kind == "PONG":
                self.clock.on_pong(obj)
            elif kind == "STAT":
                self.prev_stat, self.stat = self.stat, obj
        return items

    def window_report(self) -> dict | None:
        """Returns a metrics dict once per second (else None) and starts a new window."""
        now = time.monotonic()
        dt = now - self.t_win
        if dt < 1.0:
            return None
        w = self.win
        r = {
            "dt": dt,
            "host_rx_Bps": w.rx_bytes / dt,
            "csi_fps": w.csi / dt,
            "csi_Bps": w.csi_bytes / dt,
            "bytes_per_frame": w.csi_bytes / w.csi if w.csi else 0,
            "bench_pps": w.bench / dt,
            "bench_Bps": w.bench_bytes / dt,
            "bench_bad": w.bench_bad,
            "bench_missing": self.bench_missing,
            "crc_errors": self.dec.crc_errors,
            "skipped_bytes": self.dec.skipped_bytes,
            "link_seq_missing": self.dec.link_seq.missing,
            "parse_MBps": (w.rx_bytes / w.parse_s / 1e6) if w.parse_s else 0,
            "host_cpu_pct": (time.process_time() - self.cpu_t0) / dt * 100,
        }
        if w.latency_ms:
            lat = np.array(w.latency_ms)
            r.update(lat_avg=float(lat.mean()), lat_p95=float(np.percentile(lat, 95)),
                     lat_max=float(lat.max()))
        b = self.clock.best
        if b:
            r["clock_rtt_ms"] = b[0] * 1e3
        s, p = self.stat, self.prev_stat
        if s:
            r.update(cpu0=s["cpu0_permille"] / 10, cpu1=s["cpu1_permille"] / 10,
                     ring_size=s["ring_size"], ring_free_min=s["ring_free_min"],
                     ring_psram=bool(s["ring_in_psram"]), sink=SINKS.get(s["data_sink"], "?"),
                     heap=s["heap_int_free"], heap_min=s["heap_int_min"],
                     psram_used=s["psram_total"] - s["psram_free"], psram_total=s["psram_total"],
                     ring_drops=s["csi_ring_drops"], ctrl_drops=s["ctrl_drops"],
                     bench_drops=s["bench_drops"], link_drops=s["link_drops"], cb_us_max=s["cb_us_max"],
                     wait_us_max=s["ring_wait_us_max"])
        if s and p:
            sdt = (s["t_us"] - p["t_us"]) / 1e6 or 1
            acc = s["csi_accepted"] - p["csi_accepted"]
            pk = s["tx_pkts"] - p["tx_pkts"]
            r.update(dev_tx_Bps=(s["tx_bytes"] - p["tx_bytes"]) / sdt,
                     dev_csi_fps=acc / sdt,
                     dev_cb_per_s=(s["csi_callbacks"] - p["csi_callbacks"]) / sdt,
                     dev_bench_gen_pps=(s["bench_generated"] - p["bench_generated"]) / sdt,
                     dev_ring_drops_d=s["csi_ring_drops"] - p["csi_ring_drops"],
                     dev_bench_drops_d=s["bench_drops"] - p["bench_drops"],
                     cb_us_avg=s["cb_us_sum"] / acc if acc else 0,
                     wait_us_avg=s["ring_wait_us_sum"],
                     write_busy_pct=s["tx_write_us"] / (sdt * 1e4))
            r["wait_us_avg"] = r["wait_us_avg"] / pk if pk else 0
        self.win.reset()
        self.t_win = now
        self.cpu_t0 = time.process_time()
        return r


def fmt_report(r: dict) -> str:
    def g(k, f="{:.0f}", d="-"):
        return f.format(r[k]) if k in r else d
    return (
        f"CSI {g('csi_fps', '{:.1f}')}/s x {g('bytes_per_frame')} B = {g('csi_Bps')} B/s "
        f"(dev {g('dev_csi_fps', '{:.1f}')}/s, cb {g('cb_us_avg', '{:.1f}')}/{g('cb_us_max')} us) | "
        f"BENCH {g('bench_pps')}/s {g('bench_Bps')} B/s bad={g('bench_bad')} miss={g('bench_missing')} | "
        f"link rx {g('host_rx_Bps')} B/s dev_tx {g('dev_tx_Bps')} B/s sink={g('sink', '{}')} "
        f"crc={g('crc_errors')} seqmiss={g('link_seq_missing')} | "
        f"drops ring={g('ring_drops')} bench={g('bench_drops')} ctrl={g('ctrl_drops')} link={g('link_drops')} | "
        f"cpu0 {g('cpu0', '{:.1f}')}% cpu1 {g('cpu1', '{:.1f}')}% | "
        f"ring {g('ring_free_min')}/{g('ring_size')} free-min psram={g('ring_psram', '{}')} "
        f"wait {g('wait_us_avg')}/{g('wait_us_max')} us | "
        f"lat {g('lat_avg', '{:.1f}')}/{g('lat_p95', '{:.1f}')}/{g('lat_max', '{:.1f}')} ms "
        f"(rtt {g('clock_rtt_ms', '{:.2f}')}) | heap {g('heap')} psram_used {g('psram_used')} | "
        f"host parse {g('parse_MBps', '{:.1f}')} MB/s cpu {g('host_cpu_pct', '{:.0f}')}%"
    )


def collect(sess: Session, seconds: float, on_item=None) -> list[dict]:
    reports = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        for item in sess.poll():
            if on_item:
                on_item(item)
        r = sess.window_report()
        if r:
            reports.append(r)
    return reports


def summarize(reports: list[dict], skip: int = 1) -> dict:
    rs = reports[skip:] or reports
    out = {}
    for k in rs[-1]:
        vals = [r[k] for r in rs if k in r and isinstance(r[k], (int, float)) and not isinstance(r[k], bool)]
        if vals:
            out[k] = float(np.mean(vals))
    for k in ("crc_errors", "link_seq_missing", "bench_missing", "ring_drops", "bench_drops",
              "ctrl_drops", "cb_us_max", "wait_us_max", "lat_max", "sink", "ring_psram"):
        if k in rs[-1]:
            out[k] = rs[-1][k]
    return out

