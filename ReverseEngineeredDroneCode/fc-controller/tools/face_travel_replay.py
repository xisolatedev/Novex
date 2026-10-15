#!/usr/bin/env python3
"""
Replay a recorded VIO session through Face Direction of Travel, offline.

Record while flying (or while carrying the rig by hand) with:

    python main.py --vio tcp://127.0.0.1:7700 --vio-record logs/vio.tsv

then see exactly what the feature would have commanded, tick by tick:

    python tools/face_travel_replay.py logs/vio.tsv
    python tools/face_travel_replay.py logs/vio.tsv --pitch 1.0 --nose 0,0,1 --csv out.csv

Nothing is transmitted. The recording holds the daemon's real GET_STATE / GET_FLOOR
replies with their receive times, so the replay sees the same data, gaps and all.
Note that a replay cannot show the drone's *response* to the commands: the recorded
motion is what happened, not what would happen with the feature steering.
"""

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bootstrap  # noqa: E402,F401

from controller.face_travel import FaceTravel, FaceTravelConfig  # noqa: E402
from link.vio_client import sample_from_json  # noqa: E402


def read_recording(path):
    """Yields (time, MotionSample) for each GET_STATE, using the latest GET_FLOOR before it."""
    floor = None
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t", 2)
            if len(parts) != 3:
                continue
            t, command, text = float(parts[0]), parts[1], parts[2]
            try:
                reply = json.loads(text)
            except json.JSONDecodeError:
                continue
            if command == "GET_FLOOR":
                floor = reply
            elif command == "GET_STATE" and "velocity" in reply:
                yield t, sample_from_json(reply, floor, t)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("recording")
    p.add_argument("--nose", default="0,0,1", help="Nose axis in camera coordinates")
    p.add_argument("--yaw-sign", type=int, choices=[1, -1], default=1)
    p.add_argument("--roll", type=float, default=0.0, help="Constant pilot roll input to apply")
    p.add_argument("--pitch", type=float, default=0.0, help="Constant pilot pitch input to apply")
    p.add_argument("--csv", help="Also write every tick to this CSV")
    args = p.parse_args(argv)

    samples = list(read_recording(args.recording))
    if not samples:
        print("no GET_STATE samples in recording")
        return 1

    current = {"s": None}
    cfg = FaceTravelConfig(nose_axis_camera=tuple(float(v) for v in args.nose.split(",")),
                           yaw_sign=args.yaw_sign)
    clock = {"t": samples[0][0]}
    ft = FaceTravel(lambda: current["s"], cfg, clock=lambda: clock["t"])
    ft.set_enabled(True)

    writer = None
    if args.csv:
        out = open(args.csv, "w", newline="", encoding="utf-8")
        writer = csv.writer(out)
        writer.writerow(["t", "mode", "reason", "heading_deg", "travel_deg", "error_deg",
                         "speed", "yaw", "roll", "pitch"])

    t0 = samples[0][0]
    last_mode = None
    modes = {}
    for t, sample in samples:
        clock["t"] = t
        current["s"] = sample
        result = ft.apply({"roll": args.roll, "pitch": args.pitch, "yaw": 0.0, "throttle": 0.0}, t)
        st = ft.status()
        modes[st.mode.value] = modes.get(st.mode.value, 0) + 1
        if writer:
            writer.writerow([f"{t - t0:.3f}", st.mode.value, st.reason, st.heading_deg, st.travel_deg,
                             st.error_deg, f"{st.speed:.3f}", f"{result['yaw']:.3f}",
                             f"{result['roll']:.3f}", f"{result['pitch']:.3f}"])
        if st.mode != last_mode:
            print(f"{t - t0:8.2f}s  {st.mode.value}{' - ' + st.reason if st.reason else ''}")
            last_mode = st.mode

    print(f"\n{len(samples)} samples over {samples[-1][0] - t0:.1f}s")
    for mode, n in sorted(modes.items(), key=lambda kv: -kv[1]):
        print(f"  {mode:18s} {n:6d}  ({100.0 * n / len(samples):.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
