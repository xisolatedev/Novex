"""
Logging setup and the TX packet log used to compare against Android captures.

Flight packet entry:
    2026-09-19T12:00:00.050 TX FLIGHT dev=TC(10) fmt=TC-9 len=9 ok
      03 66 80 80 80 80 00 00 99
      roll=128 pitch=128 throttle=128 yaw=128 flags=[0x00] checksum=0x00
"""

import logging
import os
import threading
from datetime import datetime
from typing import Optional

from controller.protocol import DEVICE_TYPE_NAMES, FlightPacket


def setup_logging(verbose: bool = False, log_file: Optional[str] = None) -> None:
    handlers = [logging.StreamHandler()]
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def format_flight(packet: FlightPacket, ok: bool, when: Optional[datetime] = None) -> str:
    ts = (when or datetime.now()).isoformat(timespec="milliseconds")
    a = packet.axes
    flags = " ".join(f"0x{f:02X}" for f in packet.flags_bytes)
    dev = f"{DEVICE_TYPE_NAMES.get(packet.device_type, '?')}({packet.device_type})"
    return (f"{ts} TX FLIGHT dev={dev} fmt={packet.format_name} len={packet.length} "
            f"{'ok' if ok else 'DROPPED(link down)'}\n"
            f"  {packet.hex()}\n"
            f"  roll={a.roll} pitch={a.pitch} throttle={a.throttle} yaw={a.yaw} "
            f"flags=[{flags}] checksum=0x{packet.checksum:02X}")


class PacketLogger:
    """Writes every TX datagram to a file (and optionally to the DEBUG log)."""

    def __init__(self, path: Optional[str] = None, only_changes: bool = False):
        self.path = path
        self.only_changes = only_changes
        self._file = None
        self._lock = threading.Lock()
        self._last_flight: Optional[bytes] = None
        self._log = logging.getLogger("tx")
        if path:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            self._file = open(path, "a", encoding="utf-8")
            self._write(f"# fc-controller TX log opened {datetime.now().isoformat()}")

    def _write(self, text: str) -> None:
        with self._lock:
            if self._file:
                self._file.write(text + "\n")
                self._file.flush()

    def log_flight(self, packet: FlightPacket, ok: bool) -> None:
        if self.only_changes and packet.data == self._last_flight:
            return
        self._last_flight = packet.data
        text = format_flight(packet, ok)
        self._log.debug(text)
        self._write(text)

    def log_command(self, name: str, payload: bytes, ok: bool) -> None:
        ts = datetime.now().isoformat(timespec="milliseconds")
        text = f"{ts} TX {name} len={len(payload)} {'ok' if ok else 'DROPPED(link down)'}\n  {payload.hex(' ').upper()}"
        self._log.info(text.replace("\n", " |"))
        self._write(text)

    def log_heartbeat(self, payload: bytes, ok: bool) -> None:
        """Heartbeats are frequent, so they go to the file and to DEBUG only."""
        ts = datetime.now().isoformat(timespec="milliseconds")
        text = f"{ts} TX HEARTBEAT len={len(payload)} {'ok' if ok else 'DROPPED(link down)'}\n  {payload.hex(' ').upper()}"
        self._log.debug(text.replace("\n", " |"))
        self._write(text)

    def log_event(self, name: str, detail: str) -> None:
        """Non-transmitting events (link up/down, video, refused actions) on the same timeline."""
        ts = datetime.now().isoformat(timespec="milliseconds")
        text = f"{ts} EVENT {name}: {detail}"
        self._log.info("EVENT %s: %s", name, detail)
        self._write(text)

    def log_rx(self, data: bytes) -> None:
        ts = datetime.now().isoformat(timespec="milliseconds")
        self._write(f"{ts} RX TELEMETRY len={len(data)}\n  {data.hex(' ').upper()}")

    def close(self) -> None:
        with self._lock:
            if self._file:
                self._file.close()
                self._file = None
