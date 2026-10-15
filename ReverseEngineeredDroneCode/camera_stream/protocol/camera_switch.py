"""
Camera switching protocol handler.
Sends [0x06, 0x01] (Front) and [0x06, 0x02] (Bottom) over UDP port 7099.
Coordinates video pipeline settling and RTSP reconnections based on telemetry Byte 1.
"""

import logging
import threading
import time
from typing import Callable, Optional
from camera.stream import CameraStream
from protocol.constants import (
    DEFAULT_DRONE_IP,
    DEFAULT_UDP_PORT,
    CMD_SWITCH_CAMERA_PRIMARY,
    CMD_SWITCH_CAMERA_SECONDARY,
    CAMERA_RESET_MODE_IMMEDIATE,
    CAMERA_RESET_MODE_DELAYED_600MS,
)
from telemetry.receiver import TelemetryReceiver

logger = logging.getLogger(__name__)


class UdpCameraSwitcher:
    """
    Coordinates hardware camera switching:
    1. Transmits switch command datagram via UDP 7099.
    2. Coordinates RTSP pipeline restart (immediate or 600ms delayed settling time).
    3. Notifies state containers of active camera changes.
    """

    def __init__(
        self,
        telemetry_receiver: Optional[TelemetryReceiver] = None,
        camera_stream: Optional[CameraStream] = None,
        drone_ip: str = DEFAULT_DRONE_IP,
        drone_port: int = DEFAULT_UDP_PORT
    ):
        self.telemetry_receiver = telemetry_receiver
        self.camera_stream = camera_stream
        self.drone_ip = drone_ip
        self.drone_port = drone_port

        self._active_camera: str = "primary"  # "primary" (Front) or "secondary" (Bottom)
        self._switching = False
        self._lock = threading.Lock()
        self._on_switch_callback: Optional[Callable[[str], None]] = None

    def set_callback(self, callback: Callable[[str], None]) -> None:
        """Sets listener for camera switch completion."""
        self._on_switch_callback = callback

    def get_active_camera(self) -> str:
        with self._lock:
            return self._active_camera

    def get_active_camera_name(self) -> str:
        with self._lock:
            return "Front (Primary)" if self._active_camera == "primary" else "Bottom (Secondary)"

    def switch_camera(self, target: str) -> bool:
        """
        Switches to 'primary' (front) or 'secondary' (bottom).

        Args:
            target: 'primary' or 'secondary'.

        Returns:
            True if switch initiated.
        """
        if target not in ("primary", "secondary"):
            logger.warning(f"Invalid camera target: {target}")
            return False

        with self._lock:
            if self._switching:
                logger.info("Camera switch currently in progress, skipping request.")
                return False
            self._switching = True

        logger.info(f"Initiating camera switch to: {target.upper()}")
        cmd = CMD_SWITCH_CAMERA_SECONDARY if target == "secondary" else CMD_SWITCH_CAMERA_PRIMARY

        # 1. Send UDP switch datagram
        sent = False
        if self.telemetry_receiver and self.telemetry_receiver.is_running():
            sent = self.telemetry_receiver.send_command(cmd)
        else:
            # Standalone fallback socket
            try:
                import socket
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.sendto(cmd, (self.drone_ip, self.drone_port))
                sent = True
            except Exception as e:
                logger.error(f"Failed to send camera switch datagram: {e}")

        if not sent:
            with self._lock:
                self._switching = False
            return False

        # 2. Determine reload strategy from telemetry
        reset_mode = CAMERA_RESET_MODE_DELAYED_600MS
        if self.telemetry_receiver:
            latest_pkt = self.telemetry_receiver.get_latest_packet()
            if latest_pkt and latest_pkt.camera_reset_mode in (CAMERA_RESET_MODE_IMMEDIATE, CAMERA_RESET_MODE_DELAYED_600MS):
                reset_mode = latest_pkt.camera_reset_mode

        # 3. Asynchronously handle RTSP reload if a reload method is available
        def _reload_worker():
            try:
                if reset_mode == CAMERA_RESET_MODE_DELAYED_600MS:
                    logger.info("Camera switch mode 2: settling pipeline for 600ms...")
                    if self.camera_stream and hasattr(self.camera_stream, "pause_and_reload"):
                        self.camera_stream.pause_and_reload(delay_sec=0.6)
                    else:
                        time.sleep(0.6)
                elif reset_mode == CAMERA_RESET_MODE_IMMEDIATE:
                    logger.info("Camera switch mode 1: immediate RTSP reload...")
                    if self.camera_stream and hasattr(self.camera_stream, "pause_and_reload"):
                        self.camera_stream.pause_and_reload(delay_sec=0.0)

                with self._lock:
                    self._active_camera = target
                    self._switching = False

                logger.info(f"Camera switch completed -> Active: {self._active_camera.upper()}")
                if self._on_switch_callback:
                    self._on_switch_callback(self._active_camera)
            except Exception as e:
                logger.error(f"Error during camera switch reload: {e}")
                with self._lock:
                    self._switching = False

        threading.Thread(target=_reload_worker, name="CamSwitchReloadWorker", daemon=True).start()
        return True

    def toggle_camera(self) -> str:
        """Toggles between primary and secondary cameras."""
        with self._lock:
            next_target = "secondary" if self._active_camera == "primary" else "primary"
        self.switch_camera(next_target)
        return next_target
