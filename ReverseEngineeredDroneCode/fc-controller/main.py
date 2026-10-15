#!/usr/bin/env python3
"""
fc-controller: PC controller for the CooingDV "RC++ UFO" drone, built on the
protocol reverse-engineered from the Android app (see DISCOVERY.md).

Connect the PC to the drone's Wi-Fi first. Nothing is simulated: packets go to
192.168.1.1:7099 and video comes from rtsp://192.168.1.1:7070/webcam.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402,F401  (puts ../camera_stream on sys.path)

from controller.flight import FlightController  # noqa: E402
from controller.protocol import DEVICE_TYPE_GL, DEVICE_TYPE_TC  # noqa: E402
from controller.gamepad import DEFAULT_DEADZONE, Gamepad, GamepadConfig  # noqa: E402
from controller.state import POWER_LEVELS, ControllerState  # noqa: E402
from diagnostics.logger import PacketLogger, setup_logging  # noqa: E402
from link.udp_link import DroneLink  # noqa: E402
from session import DroneSession  # noqa: E402
from video.switch import CameraSwitcher  # noqa: E402

logger = logging.getLogger("fc-controller")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="PC flight controller (reverse-engineered CooingDV protocol)",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--drone-ip", default="192.168.1.1", help="Config.SERVER_IP")
    p.add_argument("--udp-port", type=int, default=7099, help="UdpComm.getInstance(\"192.168.1.1\", 7099)")
    p.add_argument("--rtsp-url", default="rtsp://192.168.1.1:7070/webcam", help="Config.PREVIEW_ADDRESS")
    p.add_argument("--rtsp-transport", choices=["udp", "tcp"], default="udp")
    p.add_argument("--no-video", action="store_true", help="Run without RTSP (implies --udp-independent)")
    p.add_argument("--udp-independent", action="store_true",
                   help="Start the UDP link immediately instead of after video is up (diagnostic; the app waits for video)")
    p.add_argument("--device-type", choices=["auto", "tc", "gl"], default="auto",
                   help="Force the flight packet format instead of detecting it from telemetry byte0")
    p.add_argument("--power", type=int, choices=POWER_LEVELS, default=4, help="Initial power level (app default 4)")
    p.add_argument("--no-fixed-height", action="store_true",
                   help="Start with fixed-height OFF (app default is ON; not allowed for GL devices)")
    p.add_argument("--log-packets", metavar="FILE", nargs="?", const="logs/tx_packets.log",
                   help="Log every transmitted datagram (hex + decoded) to FILE")
    p.add_argument("--log-changes-only", action="store_true", help="With --log-packets, skip repeated identical flight packets")
    p.add_argument("--record-telemetry", metavar="FILE", nargs="?", const="logs/telemetry.csv",
                   help="Record raw telemetry datagrams to CSV (camera_stream TelemetryLogger)")
    p.add_argument("--gamepad", metavar="DEVICE", nargs="?", const="auto", default="auto",
                   help="Joystick device (default: auto-detect /dev/input/js*)")
    p.add_argument("--no-gamepad", action="store_true", help="Ignore any joystick")
    p.add_argument("--deadzone", type=float, default=DEFAULT_DEADZONE,
                   help="Stick deadzone as a fraction of full travel (0 disables)")
    p.add_argument("--gamepad-map", metavar="FILE", help="JSON axis/button mapping (see README)")
    p.add_argument("--vio", metavar="ADDRESS",
                   help="Novex VIO daemon for measured motion: tcp://host:port (e.g. an SSH-forwarded "
                        "/tmp/novex-vio.sock) or unix:/path. Required for Face Direction of Travel")
    p.add_argument("--vio-record", metavar="FILE", help="Record every VIO reply for offline replay")
    p.add_argument("--face-travel", action="store_true",
                   help="Start with Face Direction of Travel enabled (default off; toggle with F)")
    p.add_argument("--face-travel-nose", metavar="X,Y,Z", default="0,0,1",
                   help="Drone nose direction in VIO camera coordinates (X right, Y down, Z forward). "
                        "0,0,1 = forward-facing camera; 0,-1,0 = downward camera, image top = nose")
    p.add_argument("--face-travel-yaw-sign", type=int, choices=[1, -1], default=1,
                   help="+1 if a yaw byte above 128 turns the drone clockwise from above (INFERRED; "
                        "a wrong value is detected in flight and faults the feature off)")
    p.add_argument("--face-travel-max-yaw", type=float, default=None,
                   help="Cap on the automatic yaw stick, 0..1 (default 0.5)")
    p.add_argument("--face-travel-min-speed", type=float, default=None,
                   help="Horizontal speed in m/s above which the nose starts following travel (default 0.20)")
    p.add_argument("--link-policy", choices=["keepalive", "app"], default="keepalive",
                   help="keepalive: never close the UDP link while control mode is ON (safety); "
                        "app: reproduce the app's cancelUdpTask on every video loss")
    p.add_argument("--dry-run", action="store_true",
                   help="OFFLINE packet debug: build and log every packet but transmit nothing (no socket)")
    p.add_argument("--log-rx", action="store_true", help="With --log-packets, also log received telemetry datagrams")
    p.add_argument("--log-file", help="Also write the application log to this file")
    p.add_argument("-v", "--verbose", action="store_true", help="DEBUG logging (includes every TX packet)")
    return p.parse_args(argv)


def build_session(args) -> DroneSession:
    forced = {"auto": None, "tc": DEVICE_TYPE_TC, "gl": DEVICE_TYPE_GL}[args.device_type]
    packet_logger = PacketLogger(args.log_packets, only_changes=args.log_changes_only) if args.log_packets else None

    telemetry_logger = None
    if args.record_telemetry:
        from telemetry.logger import TelemetryLogger   # camera_stream
        telemetry_logger = TelemetryLogger(args.record_telemetry, "csv")

    if args.dry_run:
        from link.offline import OfflineLink
        link = OfflineLink(args.drone_ip, args.udp_port, forced_device_type=forced, tx_logger=packet_logger)
    else:
        link = DroneLink(args.drone_ip, args.udp_port, forced_device_type=forced,
                         tx_logger=packet_logger, log_rx=args.log_rx)

    state = ControllerState()
    state.set_power(args.power)
    state.fixed_height = not args.no_fixed_height

    gamepad = None
    if not args.no_gamepad:
        cfg = GamepadConfig.load(args.gamepad_map) if args.gamepad_map else GamepadConfig()
        if args.gamepad != "auto":
            cfg.device = args.gamepad
        if args.deadzone != DEFAULT_DEADZONE or not args.gamepad_map:
            cfg.deadzone = args.deadzone
        gamepad = Gamepad(cfg)

    vio_client, face_travel = build_face_travel(args, packet_logger)

    flight = FlightController(sender=link.send, device_type=link.effective_device_type,
                              state=state, packet_logger=packet_logger, gamepad=gamepad,
                              face_travel=face_travel)

    video = None
    if args.dry_run:
        args.no_video = True
    if not args.no_video:
        from video.stream import DroneVideo   # imports OpenCV
        video = DroneVideo(args.rtsp_url, args.rtsp_transport)

    switcher = CameraSwitcher(send=link.send_logged, reset_mode=lambda: link.switch_camera_reset,
                              stream=video)
    return DroneSession(video, link, flight, switcher,
                        link_follows_video=not (args.udp_independent or args.no_video),
                        packet_logger=packet_logger, telemetry_logger=telemetry_logger,
                        link_policy=args.link_policy, vio_client=vio_client)


def build_face_travel(args, packet_logger):
    """Face Direction of Travel needs measured motion; without --vio it is unavailable."""
    if not args.vio:
        if args.face_travel:
            logger.warning("--face-travel ignored: it needs measured motion from --vio")
        return None, None
    from controller.face_travel import FaceTravel, FaceTravelConfig, with_overrides
    from link.vio_client import VioClient

    try:
        nose = tuple(float(v) for v in args.face_travel_nose.split(","))
        if len(nose) != 3:
            raise ValueError
    except ValueError:
        raise SystemExit(f"--face-travel-nose must be X,Y,Z, got {args.face_travel_nose!r}")
    stop_speed = None if args.face_travel_min_speed is None else args.face_travel_min_speed / 2.0
    cfg = with_overrides(FaceTravelConfig(), nose_axis_camera=nose, yaw_sign=args.face_travel_yaw_sign,
                         max_yaw=args.face_travel_max_yaw, start_speed=args.face_travel_min_speed,
                         stop_speed=stop_speed)

    def on_mode(mode, reason):
        if packet_logger:
            packet_logger.log_event("FACE TRAVEL", f"{mode.value}{': ' + reason if reason else ''}")

    client = VioClient(args.vio, record_path=args.vio_record)
    face_travel = FaceTravel(client.latest, cfg, on_mode_change=on_mode)
    face_travel.set_enabled(args.face_travel)
    return client, face_travel


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose, args.log_file)
    if args.dry_run:
        logger.warning("DRY RUN: no UDP socket is opened and nothing is transmitted to the drone")
    if args.device_type != "auto":
        logger.warning("Flight packet format forced to %s", args.device_type.upper())

    session = build_session(args)
    from gui.hud import ControllerWindow   # imports tkinter + OpenCV
    window = ControllerWindow(session)
    session.start()
    logger.info("Started. Control mode is OFF: press Enter to start sending flight packets.")
    try:
        window.run()
    finally:
        window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
