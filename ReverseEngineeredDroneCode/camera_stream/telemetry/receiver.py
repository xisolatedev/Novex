"""
UDP telemetry receiver and command transmission channel.
Replicates the UDP communication pipeline from com.cooingdv.rcufo.socket.UdpComm and SocketClient.
"""

import logging
import socket
import threading
import time
from typing import Callable, List, Optional
from protocol.constants import (
    DEFAULT_DRONE_IP,
    DEFAULT_UDP_PORT,
    CMD_HEARTBEAT,
    CMD_ACK_PHOTO,
    CMD_ACK_VIDEO,
    REMOTE_TRIGGER_PHOTO,
    REMOTE_TRIGGER_VIDEO,
)
from .model import DroneTelemetryPacket
from .parser import parse_telemetry_packet

logger = logging.getLogger(__name__)

TelemetryCallback = Callable[[DroneTelemetryPacket], None]


class TelemetryReceiver:
    """
    Manages non-blocking bidirectional UDP communication on port 7099:
    1. Sends periodic registration/heartbeat datagrams [0x01, 0x01] to 192.168.1.1:7099.
    2. Receives 20-byte incoming telemetry datagrams.
    3. Transmits camera-switching datagrams [0x06, 0x01] / [0x06, 0x02].

    STRICT SAFETY CONSTRAINT:
    This class strictly excludes any flight-control or motor-speed packet handling.
    """

    def __init__(
        self,
        drone_ip: str = DEFAULT_DRONE_IP,
        drone_port: int = DEFAULT_UDP_PORT,
        heartbeat_interval: float = 1.0,
        auto_ack_remote_buttons: bool = True
    ):
        self.drone_ip = drone_ip
        self.drone_port = drone_port
        self.heartbeat_interval = heartbeat_interval
        self.auto_ack_remote_buttons = auto_ack_remote_buttons

        self._socket: Optional[socket.socket] = None
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Telemetry metrics and latest snapshot
        self._callbacks: List[TelemetryCallback] = []
        self._latest_packet: Optional[DroneTelemetryPacket] = None
        self._packet_count = 0
        self._packet_rate_hz = 0.0
        self._last_rate_calc = time.time()
        self._rate_packet_count = 0
        self._last_packet_time = 0.0

    def add_callback(self, callback: TelemetryCallback) -> None:
        """Registers a listener for newly parsed telemetry packets."""
        with self._lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def remove_callback(self, callback: TelemetryCallback) -> None:
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def start(self) -> bool:
        """Initializes UDP socket and starts background receiver and heartbeat workers."""
        if self._running:
            return True

        try:
            # Ephemeral UDP socket for client
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(1.0)
            # Bind to all interfaces with OS-assigned ephemeral port
            s.bind(("", 0))
            self._socket = s
            local_port = s.getsockname()[1]
            logger.info(f"Telemetry UDP socket opened on local port {local_port}, target: {self.drone_ip}:{self.drone_port}")
        except Exception as e:
            logger.error(f"Failed to open UDP socket: {e}")
            return False

        self._running = True

        # 1. Receiver worker
        self._recv_thread = threading.Thread(
            target=self._receive_loop,
            name="UdpTelemetryRecv",
            daemon=True
        )
        self._recv_thread.start()

        # 2. Heartbeat worker (replicates SocketClient HeartBeatTask)
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="UdpTelemetryHeartbeat",
            daemon=True
        )
        self._heartbeat_thread.start()

        return True

    def stop(self) -> None:
        """Gracefully stops threads and closes UDP socket."""
        self._running = False

        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=1.0)
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=1.0)

        logger.info("TelemetryReceiver stopped.")

    def is_running(self) -> bool:
        return self._running

    def send_command(self, payload: bytes) -> bool:
        """
        Transmits a raw datagram to drone UDP port 7099.
        Used strictly for camera switching and registration heartbeats.
        """
        if not self._running or self._socket is None:
            logger.warning("Cannot send UDP command: TelemetryReceiver not running.")
            return False

        try:
            self._socket.sendto(payload, (self.drone_ip, self.drone_port))
            logger.debug(f"Sent UDP command to {self.drone_ip}:{self.drone_port}: {payload.hex().upper()}")
            return True
        except Exception as e:
            logger.error(f"Failed to send UDP datagram to {self.drone_ip}:{self.drone_port}: {e}")
            return False

    def get_latest_packet(self) -> Optional[DroneTelemetryPacket]:
        """Returns the most recently received telemetry packet."""
        with self._lock:
            return self._latest_packet

    def get_packet_rate_hz(self) -> float:
        """Returns measured incoming telemetry packet rate."""
        with self._lock:
            return self._packet_rate_hz

    def get_last_packet_time(self) -> float:
        """Returns epoch timestamp of last received packet."""
        with self._lock:
            return self._last_packet_time

    # -------------------------------------------------------------------------
    # Internal Workers
    # -------------------------------------------------------------------------

    def _heartbeat_loop(self) -> None:
        """
        Periodic worker sending heartbeat [0x01, 0x01] to 192.168.1.1:7099.
        Ensures the drone registers the client's IP and ephemeral port for downlink telemetry.
        """
        logger.info(f"Heartbeat loop started (interval={self.heartbeat_interval}s)")
        while self._running:
            self.send_command(CMD_HEARTBEAT)

            # Sleep in small increments for responsive shutdown
            slept = 0.0
            while self._running and slept < self.heartbeat_interval:
                time.sleep(0.1)
                slept += 0.1

    def _receive_loop(self) -> None:
        """Continuous socket receive loop for incoming telemetry packets."""
        logger.info("Telemetry receive loop started.")
        while self._running and self._socket:
            try:
                data, addr = self._socket.recvfrom(1024)
                if not data:
                    continue

                recv_time = time.time()
                packet = parse_telemetry_packet(data, source_ip=addr[0], timestamp=recv_time)
                if packet is None:
                    continue

                # Auto-ACK remote buttons if configured (matches DeviceBLFragment behavior)
                if self.auto_ack_remote_buttons:
                    if packet.remote_trigger_raw == REMOTE_TRIGGER_PHOTO:
                        self.send_command(CMD_ACK_PHOTO)
                    elif packet.remote_trigger_raw == REMOTE_TRIGGER_VIDEO:
                        self.send_command(CMD_ACK_VIDEO)

                # Update metrics
                with self._lock:
                    self._latest_packet = packet
                    self._last_packet_time = recv_time
                    self._packet_count += 1
                    self._rate_packet_count += 1

                    now = time.time()
                    elapsed = now - self._last_rate_calc
                    if elapsed >= 1.0:
                        self._packet_rate_hz = round(self._rate_packet_count / elapsed, 1)
                        self._rate_packet_count = 0
                        self._last_rate_calc = now

                    callbacks = list(self._callbacks)

                # Dispatch callbacks outside lock
                for cb in callbacks:
                    try:
                        cb(packet)
                    except Exception as err:
                        logger.error(f"Error in telemetry callback: {err}")

            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                if self._running:
                    logger.debug(f"Telemetry socket receive error: {e}")
                time.sleep(0.05)
