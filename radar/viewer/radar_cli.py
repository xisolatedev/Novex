#!/usr/bin/env python3
"""esp-radar headless tool for the binary link.

    radar_cli.py monitor [--seconds N] [--record capture.radar] [--logs]
    radar_cli.py bench --pps 0 --size 480 [--seconds 10] [--sink usb|uart|uart-text] [--ring int|psram]
    radar_cli.py sweep            # transport benchmark matrix, prints a table
    radar_cli.py cmd "ch 1"       # send one command and show replies for 2 s
    radar_cli.py c6 [--ch 11] [--mac aa:bb:..] [--rate 100] [--seconds 30]   # controlled C6 link test

BENCH packets are transport filler, typed separately from CSI and never shown as CSI.
"""
from __future__ import annotations

import argparse
import sys
import time

from radar_session import Session, collect, fmt_report, summarize


def print_item(item, logs: bool):
    kind, obj = item
    if kind in ("REPLY", "HELLO", "AP"):
        print(f"  {kind}: {obj}")
    elif kind == "LOG" and logs:
        print(f"  LOG {obj}")


def settle(sess: Session, seconds: float = 1.5):
    collect(sess, seconds, lambda it: print_item(it, False))


def run_bench(sess: Session, pps: int, size: int, seconds: float, sink: str, ring: str,
              verbose=True) -> dict:
    sess.send(f"sink {sink}")
    sess.send(f"ring {ring}")
    settle(sess, 1.0)
    sess.bench_seq = None
    sess.bench_missing = 0
    st0 = dict(sess.stat or {})
    sess.send(f"bench {pps} {size}")
    reports = collect(sess, seconds, lambda it: print_item(it, False))
    sess.send("bench off")
    settle(sess, 2.0)   # let the rings drain before reading the final counters
    st1 = sess.stat or {}
    if verbose:
        for r in reports:
            print(fmt_report(r))
    s = summarize(reports)
    for k in ("bench_generated", "bench_drops", "csi_ring_drops", "ctrl_drops"):
        s[k + "_run"] = st1.get(k, 0) - st0.get(k, 0)
    s["bench_missing_run"] = sess.bench_missing
    return s


def run_c6(sess: Session, a):
    """Controlled-transmitter test: fixed-rate ESP-NOW from the C6, CSI on the S3."""
    import collections

    import numpy as np

    from csiproto import SeqTracker

    collect(sess, 6)                      # boot after port open
    sess.send(f"ch {a.ch}")
    sess.send("mac any")
    mac = a.mac
    if not mac:
        seen = collections.defaultdict(list)
        collect(sess, 4, lambda it: seen[it[1].mac].append(it[1]) if it[0] == "CSI" else None)
        ht = {m: fs for m, fs in seen.items() if any(f.sig_mode == 1 for f in fs)}
        if not ht:
            print(f"no HT (OFDM) transmitter heard on channel {a.ch}; is the C6 powered and on this channel?")
            for m, fs in sorted(seen.items(), key=lambda kv: -len(kv[1]))[:5]:
                print(f"  heard {m}: {len(fs) / 4:.0f}/s sig_mode {fs[-1].sig_mode}")
            return
        mac = max(ht, key=lambda m: len(ht[m]))
        print(f"auto-selected C6 = {mac} ({len(ht[mac]) / 4:.0f} HT frames/s heard)")
    sess.send(f"mac {mac}")
    collect(sess, 1)
    seq_total = SeqTracker()
    st0 = None
    t0 = time.monotonic()
    while time.monotonic() - t0 < a.seconds:
        frames = []
        r = None
        t_w = time.monotonic()
        while r is None:
            for kind, obj in sess.poll():
                if kind == "CSI" and obj.mac == mac:
                    frames.append(obj)
            r = sess.window_report()
        if st0 is None and sess.stat:
            st0 = dict(sess.stat)
        win = SeqTracker()
        for f in frames:
            win.update(f.rx_seq)
            seq_total.update(f.rx_seq)
        if len(frames) > 1:
            rx = np.array([f.rx_us for f in frames], dtype=np.int64)
            ia = np.diff(rx) % (1 << 32) / 1000.0
            rssi = np.array([f.rssi for f in frames])
            lens = collections.Counter((f.orig_len, f.sig_mode) for f in frames)
            print(f"rx {len(frames) / r['dt']:6.1f}/s (expect {a.rate:.0f}) | air loss {win.missing:3d} "
                  f"({win.loss_ratio * 100:4.1f}%) | RSSI {rssi.mean():5.1f}±{rssi.std():3.1f} dBm | "
                  f"inter-arrival {ia.mean():5.2f}±{ia.std():4.2f} ms max {ia.max():6.2f} | "
                  f"CSI {dict(lens)} | dev drops {r.get('ring_drops', '-')} | "
                  f"lat {r.get('lat_avg', float('nan')):.2f} ms", flush=True)
        else:
            print(f"rx {len(frames)} frames from {mac} in the last second", flush=True)
    print(f"TOTAL {seq_total.received} received, {seq_total.missing} missing over the air "
          f"({seq_total.loss_ratio * 100:.2f}%), mac {mac}, channel {a.ch}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["monitor", "bench", "sweep", "cmd", "c6"])
    ap.add_argument("command", nargs="?")
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--pps", type=int, default=0)
    ap.add_argument("--size", type=int, default=480)
    ap.add_argument("--sink", default="usb")
    ap.add_argument("--ring", default="int")
    ap.add_argument("--record")
    ap.add_argument("--logs", action="store_true")
    ap.add_argument("--ch", type=int, default=11, help="c6 mode: channel the C6 transmits on")
    ap.add_argument("--mac", help="c6 mode: C6 MAC (auto-detected if omitted)")
    ap.add_argument("--rate", type=float, default=100, help="c6 mode: C6 configured packets/s")
    a = ap.parse_args()

    rec = open(a.record, "ab") if a.record else None
    sess = Session(a.port, rec)
    sess.send("info")

    if a.mode == "cmd":
        sess.send(a.command)
        collect(sess, 2.0, lambda it: print_item(it, True))
    elif a.mode == "monitor":
        t0 = time.monotonic()
        while not a.seconds or time.monotonic() - t0 < a.seconds:
            for it in sess.poll():
                print_item(it, a.logs)
            for ln in sess.dec.take_junk_lines():
                print("  RAW", ln)
            r = sess.window_report()
            if r:
                print(fmt_report(r))
    elif a.mode == "c6":
        run_c6(sess, a)
    elif a.mode == "bench":
        s = run_bench(sess, a.pps, a.size, a.seconds, a.sink, a.ring)
        print("SUMMARY", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in s.items()})
    elif a.mode == "sweep":
        rows = []
        hello = {}
        collect(sess, 6, lambda it: hello.update(it[1]) if it[0] == "HELLO" else None)
        on_uart = hello.get("sink") == "uart-bin"
        link = "uart" if on_uart else "usb"
        print(f"connected via {'COM/UART0' if on_uart else 'native USB'}; benchmarking that link only "
              "(the other link has no host attached)")
        sess.send("csi off")
        cases = ([(link, "int", 188, 0), (link, "int", 480, 0), (link, "int", 1024, 0),
                  (link, "psram", 480, 0), (link, "int", 480, 1400), (link, "int", 188, 3000)]
                 if not on_uart else
                 [(link, "int", 480, 0), (link, "int", 480, 350), (link, "psram", 480, 0)])
        for sink, ring, size, pps in cases:
            print(f"--- sink={sink} ring={ring} size={size} pps={pps or 'max'}", flush=True)
            s = run_bench(sess, pps, size, a.seconds, sink, ring, verbose=False)
            s["pps_cfg"] = pps
            rows.append((sink, ring, size, s))
            print(fmt_report(s), flush=True)
        sess.send(f"sink {link}")
        sess.send("ring int")
        sess.send("csi on")
        print()
        print(f"{'sink':5} {'ring':5} {'size':>5} {'pps':>5} {'host rx B/s':>11} {'dev tx B/s':>10} "
              f"{'gen':>6} {'drop@dev':>8} {'miss@pc':>7} {'bad':>3} {'crc':>3} {'ctrl_drop':>9} "
              f"{'cpu0%':>5} {'cpu1%':>5} {'wait avg/max ms':>15}")
        for sink, ring, size, s in rows:
            print(f"{sink:5} {ring:5} {size:5} {s.get('pps_cfg', 0) or 'max':>5} "
                  f"{s.get('bench_Bps', 0):11.0f} {s.get('dev_tx_Bps', 0):10.0f} "
                  f"{s['bench_generated_run']:6d} {s['bench_drops_run']:8d} {s['bench_missing_run']:7d} "
                  f"{s.get('bench_bad', 0):3.0f} {s.get('crc_errors', 0):3.0f} {s['ctrl_drops_run']:9d} "
                  f"{s.get('cpu0', 0):5.1f} {s.get('cpu1', 0):5.1f} "
                  f"{s.get('wait_us_avg', 0) / 1e3:7.1f}/{s.get('wait_us_max', 0) / 1e3:.1f}")
    if rec:
        rec.close()


if __name__ == "__main__":
    sys.exit(main())
