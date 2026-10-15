"""
Telemetry file logger for recording raw drone datagrams.
Outputs clean CSV or JSONL files for reverse-engineering and packet analysis.
"""

import csv
from datetime import datetime
import json
import logging
import os
import threading
from typing import Optional
from .model import DroneTelemetryPacket

logger = logging.getLogger(__name__)


class TelemetryLogger:
    """
    Thread-safe datagram recorder for CooingDV drone telemetry.
    """

    def __init__(self, filepath: Optional[str] = None, format_type: str = "csv"):
        self.format_type = format_type.lower()
        if filepath is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = "jsonl" if self.format_type == "jsonl" else "csv"
            filepath = f"telemetry_log_{ts}.{ext}"

        self.filepath = filepath
        self._file = None
        self._csv_writer = None
        self._lock = threading.Lock()
        self._record_count = 0

    def start(self) -> None:
        """Opens log file and writes CSV header if needed."""
        with self._lock:
            if self._file is not None:
                return

            os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
            self._file = open(self.filepath, "w", newline="", encoding="utf-8")

            if self.format_type == "csv":
                self._csv_writer = csv.writer(self._file)
                self._csv_writer.writerow([
                    "timestamp_iso",
                    "epoch_time",
                    "source_ip",
                    "length",
                    "raw_hex",
                    "device_id",
                    "is_gl_model",
                    "camera_reset_mode",
                    "remote_trigger_raw_hex",
                    "remote_trigger_name",
                    "photo_seq",
                    "video_seq",
                    "wifi_password",
                    "unparsed_bytes_hex"
                ])
                self._file.flush()

            logger.info(f"Telemetry logging started -> {self.filepath}")

    def log_packet(self, packet: DroneTelemetryPacket) -> None:
        """Records a single telemetry packet."""
        with self._lock:
            if self._file is None:
                return

            try:
                dt_str = datetime.fromtimestamp(packet.timestamp).isoformat()
                unparsed_str = " ".join(f"{k}:{v}" for k, v in sorted(packet.unknown_bytes.items()))

                if self.format_type == "jsonl":
                    record = {
                        "timestamp_iso": dt_str,
                        "epoch_time": packet.timestamp,
                        "source_ip": packet.source_ip,
                        "length": packet.length,
                        "raw_hex": packet.raw_hex,
                        "device_id": packet.device_id,
                        "is_gl_model": packet.is_gl_model,
                        "camera_reset_mode": packet.camera_reset_mode,
                        "remote_trigger_raw_hex": f"{packet.remote_trigger_raw:02X}",
                        "remote_trigger_name": packet.remote_trigger_name,
                        "photo_seq": packet.photo_sequence,
                        "video_seq": packet.video_sequence,
                        "wifi_password": packet.wifi_password,
                        "unknown_bytes": packet.unknown_bytes,
                        "imu_transmitted_by_drone": False
                    }
                    self._file.write(json.dumps(record) + "\n")
                else:
                    self._csv_writer.writerow([
                        dt_str,
                        f"{packet.timestamp:.4f}",
                        packet.source_ip,
                        packet.length,
                        packet.raw_hex,
                        packet.device_id,
                        packet.is_gl_model,
                        packet.camera_reset_mode,
                        f"{packet.remote_trigger_raw:02X}",
                        packet.remote_trigger_name,
                        packet.photo_sequence if packet.photo_sequence is not None else "",
                        packet.video_sequence if packet.video_sequence is not None else "",
                        packet.wifi_password if packet.wifi_password else "",
                        unparsed_str
                    ])

                self._file.flush()
                self._record_count += 1
            except Exception as e:
                logger.error(f"Failed to write telemetry record: {e}")

    def stop(self) -> None:
        """Flushes and closes log file."""
        with self._lock:
            if self._file is not None:
                try:
                    self._file.flush()
                    self._file.close()
                except Exception:
                    pass
                self._file = None
                self._csv_writer = None
                logger.info(f"Telemetry logging stopped. Total records: {self._record_count}")

    @property
    def record_count(self) -> int:
        return self._record_count
