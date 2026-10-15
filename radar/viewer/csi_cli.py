#!/usr/bin/env python3
"""Headless CSI monitor: prints a one-line summary per second.

    python csi_cli.py                       # monitor /dev/ttyACM0
    python csi_cli.py --cmd "ch 6" --cmd info
    python csi_cli.py --record ../captures/raw_test.log --seconds 30
"""
from __future__ import annotations

import argparse
import collections
import sys
import time

import numpy as np

from csiproto import LossTracker, SeqTracker, parse_line
from serial_link import LineReader, open_port


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--seconds", type=float, default=0, help="stop after N seconds (0 = forever)")
    ap.add_argument("--cmd", action="append", default=[], help="command to send after connect")
    ap.add_argument("--record", help="append raw timestamped lines to this file")
    ap.add_argument("--logs", action="store_true", help="also print ESP_LOG lines")
    args = ap.parse_args()

    rec = open(args.record, "ab") if args.record else None
    reader = LineReader(open_port(args.port), rec)
    time.sleep(0.2)
    for c in args.cmd:
        reader.send(c)

    transport = LossTracker(2**32)
    seq = collections.defaultdict(SeqTracker)
    win = collections.Counter()
    rssi = collections.defaultdict(list)
    amp = collections.defaultdict(list)
    lens = collections.Counter()
    bad = 0
    t0 = t_last = time.monotonic()
    while not args.seconds or time.monotonic() - t0 < args.seconds:
        for t, line in reader.read_lines():
            kind, p = parse_line(line, t)
            if kind == "CSI":
                transport.update(p.frame_id)
                seq[p.mac].update(p.rx_seq)
                win[p.mac] += 1
                rssi[p.mac].append(p.rssi)
                amp[p.mac].append(float(np.nanmean(np.abs(p.csi))))
                lens[(p.orig_len, p.sig_mode, p.cwb)] += 1
            elif kind == "STAT":
                print(f"  STAT cb={p['callbacks']} acc={p['accepted']} sent={p['sent']} "
                      f"qdrop={p['queue_drops']} txdrop={p['tx_drops']} ch={p['channel']} "
                      f"heap={p['heap_free']} psram={p['psram_free']}/{p['psram_total']}")
            elif kind == "BAD":
                bad += 1
                print("  BAD", p, file=sys.stderr)
            elif kind == "LOG":
                if args.logs and p.strip():
                    print("  LOG", p)
            else:
                print(f"  {kind}", p)
        now = time.monotonic()
        if now - t_last >= 1.0:
            total = sum(win.values())
            top = ", ".join(
                f"{m} {n}/s rssi={np.mean(rssi[m]):.0f} |H|={np.mean(amp[m]):.1f} "
                f"seqloss={seq[m].loss_ratio * 100:.0f}%"
                for m, n in win.most_common(3))
            print(f"[{now - t0:6.1f}s] {total / (now - t_last):6.1f} CSI/s  "
                  f"transport_loss={transport.missing} bad={bad}  {top}")
            if lens:
                print("         (len,sig_mode,cwb):", dict(lens.most_common(4)))
            win.clear(); rssi.clear(); amp.clear(); lens.clear()
            t_last = now
    if rec:
        rec.close()


if __name__ == "__main__":
    main()
