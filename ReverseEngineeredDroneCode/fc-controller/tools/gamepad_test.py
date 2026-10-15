#!/usr/bin/env python3
"""
Live joystick readout: find out which axis and button numbers your pad reports,
and what the drone would receive for each stick position. Transmits nothing.

    python tools/gamepad_test.py
    python tools/gamepad_test.py --device /dev/input/js1 --deadzone 0.10 --power 14
    python tools/gamepad_test.py --save my_pad.json        # write a mapping file

Move one stick at a time and note the axis numbers, then put them in a mapping file:

    {"deadzone": 0.08,
     "axes": {"yaw": [0, false], "throttle": [1, true], "roll": [3, false], "pitch": [4, true]},
     "buttons": {"takeoff": 0, "land": 1, "gyro": 3, "camera": 4, "power": 5, "estop": 6, "control": 7}}

and run the controller with --gamepad-map my_pad.json.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bootstrap  # noqa: E402,F401

from controller.gamepad import DEFAULT_DEADZONE, Gamepad, GamepadConfig, find_device  # noqa: E402
from controller.keyboard import map_inputs_to_axes  # noqa: E402
from controller.protocol import DEVICE_TYPE_TC, FlightFlags, build_flight_packet  # noqa: E402
from controller.state import POWER_HALF_LEN  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Joystick axis/button discovery and packet preview")
    p.add_argument("--device", help="Joystick device (default: first /dev/input/js*)")
    p.add_argument("--deadzone", type=float, default=DEFAULT_DEADZONE)
    p.add_argument("--power", type=int, choices=sorted(POWER_HALF_LEN), default=4,
                   help="Power level: roll/pitch half range 40/60/127")
    p.add_argument("--map", help="Load an existing mapping file")
    p.add_argument("--save", metavar="FILE", help="Write the current mapping to FILE and exit")
    p.add_argument("--fixed-height", action="store_true", default=True)
    p.add_argument("--no-fixed-height", dest="fixed_height", action="store_false")
    args = p.parse_args(argv)

    cfg = GamepadConfig.load(args.map) if args.map else GamepadConfig()
    if args.device:
        cfg.device = args.device
    cfg.deadzone = args.deadzone
    if args.save:
        cfg.save(args.save)
        print(f"wrote {args.save}")
        return 0

    if not (cfg.device or find_device()):
        print("No joystick found at /dev/input/js*.\n"
              "Plug in a pad (the joydev kernel module handles it) and try again.\n"
              "If the device exists but cannot be opened, add yourself to the 'input' group.")
        return 1

    half = POWER_HALF_LEN[args.power]
    pad = Gamepad(cfg, on_button=lambda action: print(f"\n  button -> {action.upper()}"))
    pad.start()
    print(f"Reading {cfg.device or find_device()}  deadzone={cfg.deadzone:.2f}  "
          f"power={args.power} (roll/pitch half range {half})   Ctrl-C to stop")
    print("Nothing is transmitted.\n")
    try:
        while True:
            ax = pad.axes()
            mapping = map_inputs_to_axes(frozenset(), half, args.fixed_height, 128, ax if pad.connected else None)
            pkt = build_flight_packet(DEVICE_TYPE_TC, mapping.axes,
                                      FlightFlags(fixed_height=args.fixed_height))
            seen = pad.raw_axes()
            mapped = {v[0] for v in pad.config.axes.values()}
            raw = " ".join(f"{'*' if i in mapped else ''}a{i}={seen[i]:6d}" for i in sorted(seen)) or "no axis events yet"
            status = pad.status() if pad.connected else "NOT CONNECTED"
            sys.stdout.write(
                f"\r{status:28.28s} | {raw} | "
                f"R={pkt.axes.roll:3d} P={pkt.axes.pitch:3d} T={pkt.axes.throttle:3d} Y={pkt.axes.yaw:3d} | "
                f"{pkt.hex()}   ")
            sys.stdout.flush()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print()
    finally:
        pad.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
