"""
Offline packet-debug link: identical interface to DroneLink, but no socket and
no transmission. Everything is built and logged exactly as in flight, so the
packet stream can be inspected byte-for-byte without the drone hearing anything.

This is NOT a drone simulator: it never invents telemetry or protocol behaviour.
Telemetry can only come from a real capture replayed with feed_telemetry().
"""

import logging
import time
from typing import Callable, List, Optional

from telemetry.model import DroneTelemetryPacket   # camera_stream

from controller.protocol import DEVICE_TYPE_NAMES, DEVICE_TYPE_UNKNOWN
from .parser import classify_device_type, parse_telemetry_packet

logger = logging.getLogger(__name__)


class OfflineLink:
    def __init__(self, drone_ip: str = "(offline)", port: int = 7099,
                 forced_device_type: Optional[int] = None, tx_logger=None):
        self.drone_ip = drone_ip
        self.port = port
        self._forced_device_type = forced_device_type
        self._tx_logger = tx_logger
        self.device_type = DEVICE_TYPE_UNKNOWN
        self.first_device_id: Optional[int] = None
        self.last_device_id: Optional[int] = None
        self.switch_camera_reset = 0
        self.rx_count = 0
        self.last_rx_time = 0.0
        self.device_type_changes = 0
        self.sent: List[bytes] = []
        self._running = False
        self._packet_listeners: List[Callable[[DroneTelemetryPacket], None]] = []

    def start(self) -> bool:
        self._running = True
        if self._tx_logger:
            self._tx_logger.log_event("LINK", "offline dry-run: nothing is transmitted")
        logger.warning("DRY RUN: packets are built and logged but never transmitted")
        return True

    def stop(self) -> None:
        self._running = False
        if self._tx_logger:
            self._tx_logger.log_event("LINK", "offline dry-run stopped")

    @property
    def running(self) -> bool:
        return self._running

    def send(self, payload: bytes) -> bool:
        if not self._running:
            return False
        self.sent.append(bytes(payload))
        return True

    def send_logged(self, name: str, payload: bytes) -> bool:
        ok = self.send(payload)
        if self._tx_logger:
            self._tx_logger.log_command(name, payload, ok)
        return ok

    def add_packet_listener(self, fn) -> None:
        self._packet_listeners.append(fn)

    def feed_telemetry(self, data: bytes) -> None:
        """Inject a telemetry datagram captured from the real drone."""
        pkt = parse_telemetry_packet(bytes(data), source_ip="(replay)")
        if pkt is None:
            return
        self.rx_count += 1
        self.last_rx_time = time.time()
        new_type = classify_device_type(data[0])
        if new_type != self.device_type:
            if self.device_type != DEVICE_TYPE_UNKNOWN:
                self.device_type_changes += 1
            logger.info("Device type now %s (byte0=%d)", DEVICE_TYPE_NAMES[new_type], data[0])
            self.device_type = new_type
        self.last_device_id = data[0]
        if self.first_device_id is None:
            self.first_device_id = data[0]
        if len(data) >= 2:
            self.switch_camera_reset = data[1]
        for fn in list(self._packet_listeners):
            fn(pkt)

    def effective_device_type(self) -> int:
        return self._forced_device_type if self._forced_device_type is not None else self.device_type

    def telemetry_alive(self, now: Optional[float] = None) -> bool:
        return self.rx_count > 0

    def latest_packet(self):
        return None

    def rx_rate_hz(self) -> float:
        return 0.0
