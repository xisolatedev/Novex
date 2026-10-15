"""
The single UDP socket to 192.168.1.1:7099 (SocketClient + UdpComm).

Reuses camera_stream's TelemetryReceiver for the socket, the 1 Hz heartbeat
(``01 01``, HeartBeatTask scheduled at 0 ms / 1000 ms) and the receive thread.
Everything is sent on that one socket (flight packets, camera switch, control-off),
as SocketClient.debugSend() does.

Added on top, from SocketClient.startUdpTask's receive lambda (lines 198-229):
  * device type:  isGL(byte0) -> GL (2), otherwise -> TC (10), re-evaluated on EVERY packet
  * device ID:    first byte0 after each (re)start ("fake resolution number")
  * switchCameraReset = byte1
and from DeviceBLFragment onReceiver (TC path, lines 1425-1458):
  * photo/video remote-button ACKs ``09 01`` / ``09 02`` when the counter advances.
"""

import logging
import threading
import time
from typing import Callable, List, Optional

from telemetry.model import DroneTelemetryPacket   # camera_stream
from telemetry.receiver import TelemetryReceiver   # camera_stream

from controller.protocol import (
    CMD_ACK_PHOTO,
    CMD_ACK_VIDEO,
    CMD_HEARTBEAT,
    DEVICE_TYPE_GL,
    DEVICE_TYPE_NAMES,
    DEVICE_TYPE_TC,
    DEVICE_TYPE_UNKNOWN,
)
from .parser import classify_device_type

logger = logging.getLogger(__name__)

# PC-side threshold (INFERRED): the app has no telemetry timeout of its own.
TELEMETRY_TIMEOUT_S = 2.0


class _LoggingReceiver(TelemetryReceiver):
    """
    camera_stream's receiver, with every datagram it sends by itself (the 1 Hz
    heartbeat) reported to the TX log. Timing and socket behaviour are unchanged.
    """

    def __init__(self, *args, tx_hook=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._tx_hook = tx_hook

    def send_command(self, payload: bytes) -> bool:
        ok = super().send_command(payload)
        if self._tx_hook:
            self._tx_hook(payload, ok)
        return ok


class DroneLink:
    def __init__(self, drone_ip: str = "192.168.1.1", port: int = 7099,
                 heartbeat_interval: float = 1.0, forced_device_type: Optional[int] = None,
                 tx_logger=None, log_rx: bool = False):
        self.drone_ip = drone_ip
        self.port = port
        self._heartbeat_interval = heartbeat_interval
        self._forced_device_type = forced_device_type
        self._tx_logger = tx_logger
        self._log_rx = log_rx
        self._receiver: Optional[TelemetryReceiver] = None
        self._lock = threading.Lock()   # SocketClient.sendLock
        self._packet_listeners: List[Callable[[DroneTelemetryPacket], None]] = []

        self.device_type = DEVICE_TYPE_UNKNOWN   # SocketClient.mDeviceType = 0 (singleton: survives restarts)
        self.first_device_id: Optional[int] = None
        self.last_device_id: Optional[int] = None
        self.switch_camera_reset = 0
        self.rx_count = 0
        self.last_rx_time = 0.0
        self.device_type_changes = 0
        self._num_photo = 0
        self._num_video = 0

    # ---- lifecycle (startUdpTask / cancelUdpTask) -------------------------------

    def start(self) -> bool:
        with self._lock:
            if self._receiver and self._receiver.is_running():
                return True
            rx = _LoggingReceiver(self.drone_ip, self.port, heartbeat_interval=self._heartbeat_interval,
                                  auto_ack_remote_buttons=False, tx_hook=self._on_receiver_tx)
            rx.add_callback(self._on_packet)
            if not rx.start():
                if self._tx_logger:
                    self._tx_logger.log_event("LINK", "FAILED to open UDP socket")
                return False
            self._receiver = rx
            # onPrepared: MainApplication.setFakeResolutionNumber(0)
            self.first_device_id = None
            self._num_photo = self._num_video = 0
        local_port = None
        try:
            local_port = rx._socket.getsockname()[1]
        except Exception:
            pass
        logger.info("UDP link started -> %s:%d from local port %s (heartbeat 01 01 every %.1fs)",
                    self.drone_ip, self.port, local_port, self._heartbeat_interval)
        if self._tx_logger:
            self._tx_logger.log_event("LINK UP", f"socket {local_port} -> {self.drone_ip}:{self.port}, "
                                                 f"heartbeat every {self._heartbeat_interval}s")
        return True

    def stop(self) -> None:
        with self._lock:
            rx, self._receiver = self._receiver, None
        if rx:
            rx.remove_callback(self._on_packet)
            rx.stop()
            logger.warning("UDP link stopped (heartbeat stopped, socket closed)")
            if self._tx_logger:
                self._tx_logger.log_event("LINK DOWN", "heartbeat stopped and socket closed; "
                                                       "the drone now receives nothing from us")

    def _on_receiver_tx(self, payload: bytes, ok: bool) -> None:
        # The receiver sends the heartbeat itself; log it on the same timeline as everything else.
        if self._tx_logger and payload == CMD_HEARTBEAT:
            self._tx_logger.log_heartbeat(payload, ok)

    @property
    def running(self) -> bool:
        rx = self._receiver
        return bool(rx and rx.is_running())

    # ---- tx ------------------------------------------------------------------------

    def send(self, payload: bytes) -> bool:
        """SocketClient.debugSend(): silently dropped when the UDP task is not running."""
        with self._lock:
            rx = self._receiver
            if rx is None or not rx.is_running():
                return False
            return rx.send_command(payload)

    def send_logged(self, name: str, payload: bytes) -> bool:
        ok = self.send(payload)
        if self._tx_logger:
            self._tx_logger.log_command(name, payload, ok)
        return ok

    # ---- rx ------------------------------------------------------------------------

    def add_packet_listener(self, fn: Callable[[DroneTelemetryPacket], None]) -> None:
        self._packet_listeners.append(fn)

    def _on_packet(self, pkt: DroneTelemetryPacket) -> None:
        data = pkt.raw_bytes
        self.rx_count += 1
        self.last_rx_time = time.time()
        if self._log_rx and self._tx_logger:
            self._tx_logger.log_rx(data)

        # DeviceBLFragment.onReceiver runs BEFORE the type update, with the previous type.
        self._handle_remote_buttons(data)

        new_type = classify_device_type(data[0])
        if new_type != self.device_type:
            if self.device_type != DEVICE_TYPE_UNKNOWN:
                self.device_type_changes += 1
                logger.warning("Device type changed %s -> %s on byte0=0x%02X (source re-classifies every packet)",
                               DEVICE_TYPE_NAMES[self.device_type], DEVICE_TYPE_NAMES[new_type], data[0])
            else:
                logger.info("Device type detected: %s (byte0=%d)", DEVICE_TYPE_NAMES[new_type], data[0])
            self.device_type = new_type
        self.last_device_id = data[0]
        if self.first_device_id is None:
            self.first_device_id = data[0]
        if len(data) >= 2:
            self.switch_camera_reset = data[1]

        for fn in list(self._packet_listeners):
            try:
                fn(pkt)
            except Exception:
                logger.exception("telemetry listener failed")

    def _handle_remote_buttons(self, data: bytes) -> None:
        # Only on the non-GL path, packets longer than 4 bytes (DeviceBLFragment lines 1425-1458).
        if self.device_type == DEVICE_TYPE_GL or len(data) <= 4:
            return
        if data[2] == 77:
            n = data[3]
            if n > self._num_photo or (self._num_photo == 255 and n < self._num_photo):
                self._num_photo = n
                self.send_logged("ACK PHOTO", CMD_ACK_PHOTO)
        elif data[2] == 88:
            n = data[4]
            if n > self._num_video or (self._num_video == 255 and n < self._num_video):
                self._num_video = n
                self.send_logged("ACK VIDEO", CMD_ACK_VIDEO)

    # ---- state for the flight loop / UI --------------------------------------------

    def effective_device_type(self) -> int:
        return self._forced_device_type if self._forced_device_type is not None else self.device_type

    def telemetry_alive(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return self.running and self.last_rx_time > 0 and now - self.last_rx_time < TELEMETRY_TIMEOUT_S

    def latest_packet(self) -> Optional[DroneTelemetryPacket]:
        rx = self._receiver
        return rx.get_latest_packet() if rx else None

    def rx_rate_hz(self) -> float:
        rx = self._receiver
        return rx.get_packet_rate_hz() if rx else 0.0


__all__ = ["DroneLink", "DEVICE_TYPE_TC", "DEVICE_TYPE_GL"]
