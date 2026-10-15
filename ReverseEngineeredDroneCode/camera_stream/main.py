#!/usr/bin/env python3
"""
Main entry point for the Drone Camera Viewer application.
Provides CLI parameter overrides, initializes subsystems, and starts display loop.
Integrates live RTSP video, UDP telemetry reception (port 7099), and camera switching.
"""

import argparse
import logging
import os
import sys
from typing import Optional

# Ensure local packages can be imported cleanly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from camera.manager import CameraManager
from camera.stream import RtspCameraStream
from config import AppConfig
from drone.state import DroneState
from mock.stream import MockCameraStream
from mock.telemetry import MockTelemetryProvider
from protocol.camera_switch import UdpCameraSwitcher
from telemetry.logger import TelemetryLogger
from telemetry.receiver import TelemetryReceiver
from ui.viewer import DroneCameraViewer


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
        datefmt="%H:%M:%S"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Drone Camera Viewer & RTSP Receiver (CooingDV Architecture)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--url", "-u",
        type=str,
        default=None,
        help="Primary RTSP stream URL (e.g., rtsp://192.168.1.1:7070/webcam)"
    )
    parser.add_argument(
        "--camera2-url",
        type=str,
        default=None,
        help="Secondary camera RTSP stream URL for dual mode (if separate endpoint exists)"
    )
    parser.add_argument(
        "--rotation", "-r",
        type=int,
        choices=[0, 90, 180, 270],
        default=None,
        help="Camera rotation angle in degrees (0, 90, 180, 270). Default is 90° clockwise per drone physical mounting"
    )
    parser.add_argument(
        "--drone-ip",
        type=str,
        default=None,
        help="Drone IP address (default: 192.168.1.1)"
    )
    parser.add_argument(
        "--udp-port",
        type=int,
        default=None,
        help="Drone UDP telemetry & command port (default: 7099)"
    )
    parser.add_argument(
        "--telemetry-panel", "-t",
        action="store_true",
        help="Show raw UDP telemetry inspector overlay panel on startup"
    )
    parser.add_argument(
        "--record-telemetry",
        nargs="?",
        const="default",
        default=None,
        help="Record incoming 20-byte UDP telemetry datagrams to CSV. Optionally specify file path."
    )
    parser.add_argument(
        "--no-telemetry",
        action="store_true",
        help="Disable background UDP telemetry receiver and heartbeat"
    )
    parser.add_argument(
        "--mock", "-m",
        action="store_true",
        help="Run in mock/simulation mode with synthetic video test patterns and telemetry"
    )
    parser.add_argument(
        "--dual", "-d",
        action="store_true",
        help="Start in dual-camera split-screen mode (simulation / test)"
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Display window width"
    )
    parser.add_argument(
        "--height",
        type=int,
        default=None,
        help="Display window height"
    )
    parser.add_argument(
        "--aspect-mode", "-a",
        choices=["fit", "crop"],
        default=None,
        help="Aspect ratio behavior: 'fit' (letterbox) or 'crop' (fill window)"
    )
    parser.add_argument(
        "--no-hud",
        action="store_true",
        help="Hide telemetry and diagnostics HUD by default"
    )
    parser.add_argument(
        "--fullscreen", "-f",
        action="store_true",
        help="Start in fullscreen mode"
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Path to JSON configuration file"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging output"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    setup_logging(args.verbose)
    logger = logging.getLogger("main")

    # 1. Load configuration
    if args.config and os.path.exists(args.config):
        logger.info(f"Loading configuration from file: {args.config}")
        config = AppConfig.load_from_file(args.config)
    else:
        config = AppConfig()

    # 2. Apply CLI overrides
    if args.url:
        config.stream.primary_url = args.url
    if args.camera2_url:
        config.stream.secondary_url = args.camera2_url
    if args.rotation is not None:
        config.display.rotation = args.rotation
    if args.drone_ip:
        config.telemetry.drone_ip = args.drone_ip
    if args.udp_port:
        config.telemetry.udp_port = args.udp_port
    if args.telemetry_panel:
        config.telemetry.show_telemetry_panel = True
    if args.record_telemetry is not None:
        config.telemetry.enable_logging = True
        if args.record_telemetry != "default":
            config.telemetry.log_filepath = args.record_telemetry
    if args.no_telemetry:
        config.telemetry.enable_receiver = False
    if args.mock:
        config.mock.enabled = True
    if args.dual:
        config.dual_camera.enabled = True
    if args.width:
        config.display.window_width = args.width
    if args.height:
        config.display.window_height = args.height
    if args.aspect_mode:
        config.display.aspect_mode = args.aspect_mode
    if args.no_hud:
        config.hud.visible = False
    if args.fullscreen:
        config.display.fullscreen = True

    logger.info("Initializing Drone Camera Viewer...")
    logger.info(f"Stream URL (Primary)  : {config.stream.primary_url}")
    logger.info(f"Camera Rotation       : {config.display.rotation}° CW")
    logger.info(f"Mock Mode             : {'ENABLED' if config.mock.enabled else 'DISABLED'}")
    logger.info(f"Aspect Behavior       : {config.display.aspect_mode.upper()}")
    logger.info(f"UDP Telemetry (7099)  : {'ENABLED' if config.telemetry.enable_receiver else 'DISABLED'}")

    # 3. Initialize Drone State
    drone_state = DroneState(default_ip=config.telemetry.drone_ip)

    # 4. Build Camera Streams & Telemetry
    camera_manager = CameraManager()
    telemetry_receiver: Optional[TelemetryReceiver] = None
    telemetry_logger: Optional[TelemetryLogger] = None
    mock_telemetry: Optional[MockTelemetryProvider] = None

    if config.mock.enabled:
        logger.info("Setting up synthetic mock camera streams...")
        stream_primary = MockCameraStream(
            name="Front Camera (Mock)",
            width=config.mock.primary_resolution[0],
            height=config.mock.primary_resolution[1],
            target_fps=config.mock.mock_fps,
            style="color_bars",
            rotation=config.display.rotation
        )
        stream_secondary = MockCameraStream(
            name="Bottom Camera (Mock Optical Flow)",
            width=config.mock.secondary_resolution[0],
            height=config.mock.secondary_resolution[1],
            target_fps=config.mock.mock_fps,
            style="grid",
            rotation=config.display.rotation
        )
        camera_manager.register_stream("primary", stream_primary)
        camera_manager.register_stream("secondary", stream_secondary)

        mock_telemetry = MockTelemetryProvider(drone_state, update_rate_hz=2.0)
        mock_telemetry.start()
        camera_switcher = None
    else:
        logger.info("Setting up real RTSP camera stream pipelines...")
        stream_primary = RtspCameraStream(
            name="Front Camera (Primary)",
            url=config.stream.primary_url,
            rtsp_transport=config.stream.rtsp_transport,
            reconnect_interval=config.stream.reconnect_interval_sec,
            buffer_size=config.stream.buffer_size,
            rotation=config.display.rotation
        )
        camera_manager.register_stream("primary", stream_primary)

        if config.stream.secondary_url:
            stream_secondary = RtspCameraStream(
                name="Bottom Camera (Secondary)",
                url=config.stream.secondary_url,
                rtsp_transport=config.stream.rtsp_transport,
                reconnect_interval=config.stream.reconnect_interval_sec,
                buffer_size=config.stream.buffer_size,
                rotation=config.display.rotation
            )
            camera_manager.register_stream("secondary", stream_secondary)

        # Telemetry Receiver and Logger
        if config.telemetry.enable_receiver:
            telemetry_receiver = TelemetryReceiver(
                drone_ip=config.telemetry.drone_ip,
                drone_port=config.telemetry.udp_port,
                heartbeat_interval=config.telemetry.heartbeat_interval_sec,
                auto_ack_remote_buttons=config.telemetry.auto_ack_remote_buttons
            )

            if config.telemetry.enable_logging:
                telemetry_logger = TelemetryLogger(
                    filepath=config.telemetry.log_filepath,
                    format_type=config.telemetry.log_format
                )
                telemetry_logger.start()

            # Connect packet callback to drone state and logger
            def _on_packet_arrived(pkt):
                rate = telemetry_receiver.get_packet_rate_hz() if telemetry_receiver else 0.0
                drone_state.update_from_packet(pkt, rate_hz=rate)
                if telemetry_logger:
                    telemetry_logger.log_packet(pkt)

            telemetry_receiver.add_callback(_on_packet_arrived)
            telemetry_receiver.start()

        # Hardware UDP Camera Switcher (sends [0x06, 0x01] / [0x06, 0x02] to port 7099)
        camera_switcher = UdpCameraSwitcher(
            telemetry_receiver=telemetry_receiver,
            camera_stream=stream_primary,
            drone_ip=config.telemetry.drone_ip,
            drone_port=config.telemetry.udp_port
        )
        camera_switcher.set_callback(drone_state.set_active_camera)

    # Set dual mode state
    if config.dual_camera.enabled:
        camera_manager.set_dual_mode(True)

    # 5. Launch UI Viewer
    viewer = DroneCameraViewer(
        config=config,
        camera_manager=camera_manager,
        drone_state=drone_state,
        camera_switcher=camera_switcher
    )

    try:
        viewer.run()
    finally:
        if mock_telemetry:
            mock_telemetry.stop()
        if telemetry_receiver:
            telemetry_receiver.stop()
        if telemetry_logger:
            telemetry_logger.stop()


if __name__ == "__main__":
    main()
