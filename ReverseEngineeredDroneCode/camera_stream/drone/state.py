"""
Drone state data model.
Maintains live operational telemetry and identification metrics.
Bridges real UDP (port 7099) telemetry packets and simulation state.
"""

from dataclasses import dataclass, field
import threading
import time
from typing import Dict, Optional
from telemetry.model import DroneTelemetryPacket
from telemetry.parser import is_gl_device, is_no_rotate_device


@dataclass
class DroneInfo:
    """Read-only snapshot of drone telemetry and metadata."""
    connected: bool = False
    ip_address: str = "192.168.1.1"
    wifi_ssid: str = "Not Connected"
    device_id: int = 0
    device_model: str = "Unknown Drone"
    optical_flow_enabled: bool = False
    requires_rotation: bool = True
    active_camera_id: str = "primary"
    active_camera_name: str = "Front (Primary)"
    camera_mode: str = "Single Camera"
    
    # Telemetry properties
    battery_percent: Optional[int] = None
    battery_voltage: Optional[float] = None
    signal_rssi_dbm: Optional[int] = None
    telemetry_source: str = "Offline"
    last_update_time: float = 0.0
    shutter_status: str = "Standby"

    # Raw datagram & decoded packet fields (UDP 7099)
    camera_reset_mode: int = 0
    remote_trigger_raw: int = 0
    remote_trigger_name: str = "Idle"
    photo_sequence: Optional[int] = None
    video_sequence: Optional[int] = None
    wifi_password: Optional[str] = None
    raw_hex: str = ""
    packet_rate_hz: float = 0.0
    unknown_bytes: Dict[int, str] = field(default_factory=dict)
    imu_transmitted_by_drone: bool = False


class DroneState:
    """
    Thread-safe drone state container.
    Decouples camera rendering from network telemetry collection.
    """
    def __init__(self, default_ip: str = "192.168.1.1"):
        self._lock = threading.Lock()
        self._connected = False
        self._ip_address = default_ip
        self._wifi_ssid = "WIFIPD_DISCONNECTED"
        self._device_id = 0
        self._device_model = "Standby"
        self._optical_flow = False
        self._requires_rotation = True
        self._active_camera_id = "primary"
        self._camera_mode = "Single"
        self._battery_percent = None
        self._battery_voltage = None
        self._signal_rssi = None
        self._telemetry_source = "Standby"
        self._last_update = time.time()
        self._shutter_status = "Standby"

        # Packet fields
        self._latest_packet: Optional[DroneTelemetryPacket] = None
        self._camera_reset_mode = 0
        self._remote_trigger_raw = 0
        self._remote_trigger_name = "Idle"
        self._photo_sequence: Optional[int] = None
        self._video_sequence: Optional[int] = None
        self._wifi_password: Optional[str] = None
        self._raw_hex = ""
        self._packet_rate_hz = 0.0
        self._unknown_bytes: Dict[int, str] = {}

    def update_connection(self, connected: bool, ssid: Optional[str] = None) -> None:
        with self._lock:
            self._connected = connected
            if ssid:
                self._wifi_ssid = ssid
            self._last_update = time.time()

    def update_from_packet(self, packet: DroneTelemetryPacket, rate_hz: float = 0.0) -> None:
        """Updates internal state from a freshly received UDP telemetry packet."""
        with self._lock:
            self._connected = True
            self._latest_packet = packet
            self._telemetry_source = f"UDP {packet.source_ip}:7099"
            self._raw_hex = packet.raw_hex
            self._packet_rate_hz = rate_hz
            self._last_update = packet.timestamp

            # Byte 0
            self._device_id = packet.device_id
            self._optical_flow = packet.is_gl_model
            self._requires_rotation = packet.requires_rotation
            if packet.is_gl_model:
                self._device_model = f"GL Optical Flow (ID {packet.device_id})"
            elif packet.device_id > 0:
                self._device_model = f"Standard Drone (ID {packet.device_id})"

            # Byte 1
            self._camera_reset_mode = packet.camera_reset_mode

            # Byte 2
            self._remote_trigger_raw = packet.remote_trigger_raw
            self._remote_trigger_name = packet.remote_trigger_name
            self._shutter_status = packet.remote_trigger_name

            # Bytes 3 & 4
            if packet.photo_sequence is not None:
                self._photo_sequence = packet.photo_sequence
            if packet.video_sequence is not None:
                self._video_sequence = packet.video_sequence

            # Passwords & unknowns
            if packet.wifi_password:
                self._wifi_password = packet.wifi_password
            self._unknown_bytes = dict(packet.unknown_bytes)

    def set_active_camera(self, camera_id: str) -> None:
        with self._lock:
            self._active_camera_id = camera_id
            self._last_update = time.time()

    def set_camera_mode(self, mode: str) -> None:
        with self._lock:
            self._camera_mode = mode
            self._last_update = time.time()

    def update_mock_telemetry(self, battery_pct: int, voltage: float, rssi: int, source: str = "Mock Simulated") -> None:
        with self._lock:
            self._battery_percent = battery_pct
            self._battery_voltage = voltage
            self._signal_rssi = rssi
            self._telemetry_source = source
            self._last_update = time.time()

    def set_shutter_status(self, status: str) -> None:
        with self._lock:
            self._shutter_status = status
            self._last_update = time.time()

    def get_snapshot(self) -> DroneInfo:
        """Returns an immutable snapshot of current drone state."""
        with self._lock:
            cam_name = "Front (Primary)" if self._active_camera_id == "primary" else "Bottom (Secondary)"
            return DroneInfo(
                connected=self._connected,
                ip_address=self._ip_address,
                wifi_ssid=self._wifi_ssid,
                device_id=self._device_id,
                device_model=self._device_model,
                optical_flow_enabled=self._optical_flow,
                requires_rotation=self._requires_rotation,
                active_camera_id=self._active_camera_id,
                active_camera_name=cam_name,
                camera_mode=self._camera_mode,
                battery_percent=self._battery_percent,
                battery_voltage=self._battery_voltage,
                signal_rssi_dbm=self._signal_rssi,
                telemetry_source=self._telemetry_source,
                last_update_time=self._last_update,
                shutter_status=self._shutter_status,
                camera_reset_mode=self._camera_reset_mode,
                remote_trigger_raw=self._remote_trigger_raw,
                remote_trigger_name=self._remote_trigger_name,
                photo_sequence=self._photo_sequence,
                video_sequence=self._video_sequence,
                wifi_password=self._wifi_password,
                raw_hex=self._raw_hex,
                packet_rate_hz=self._packet_rate_hz,
                unknown_bytes=dict(self._unknown_bytes),
                imu_transmitted_by_drone=False
            )
