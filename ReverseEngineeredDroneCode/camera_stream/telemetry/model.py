"""
Data models for CooingDV drone telemetry packets.
Maintains clear demarcation between VERIFIED FROM SOURCE, INFERRED, and UNKNOWN data.
"""

from dataclasses import dataclass, field
import time
from typing import Dict, Optional


@dataclass
class DroneTelemetryPacket:
    """
    Representation of a single 20-byte UDP telemetry datagram received from 192.168.1.1:7099.

    Confidence Levels:
    - [VERIFIED FROM SOURCE]: Confirmed by decompiled Java logic in SocketClient & DeviceBLFragment.
    - [INFERRED]: Deduced from enum naming or device ID mappings.
    - [UNKNOWN]: Bytes never accessed or parsed by the original application.
    """
    timestamp: float
    source_ip: str
    raw_bytes: bytes
    length: int

    # [VERIFIED FROM SOURCE: Byte 0]
    device_id: int
    is_gl_model: bool
    requires_rotation: bool  # False only for IDs 94 and 99 (WifiIdUtils.isNoRotate)

    # [VERIFIED FROM SOURCE: Byte 1]
    camera_reset_mode: int   # 1 = immediate reload, 2 = delayed 600ms reload

    # [VERIFIED FROM SOURCE: Byte 2]
    remote_trigger_raw: int
    remote_trigger_name: str  # "Photo Trigger", "Video Trigger", "GL Sync Frame", "Idle", "Unknown"

    # [VERIFIED FROM SOURCE: Bytes 3 & 4]
    photo_sequence: Optional[int] = None
    video_sequence: Optional[int] = None

    # [VERIFIED FROM SOURCE: Bytes 5-18 (Standard) / Bytes 8-18 (GL)]
    password_status: Optional[int] = None  # 0 = initial/default, 1 = changed
    password_valid: Optional[bool] = None
    wifi_password: Optional[str] = None    # 8-character hex password

    # [UNKNOWN / UNPARSED BY SOURCE CODE]
    # Mapping of byte index (0..19) -> 2-digit hex string for all unparsed bytes
    unknown_bytes: Dict[int, str] = field(default_factory=dict)

    # [VERIFIED FROM SOURCE: Gyro / Accelerometer Reality]
    imu_transmitted_by_drone: bool = False  # NEVER transmitted by this drone protocol

    @property
    def raw_hex(self) -> str:
        """Returns space-separated hex representation of packet."""
        return " ".join(f"{b:02X}" for b in self.raw_bytes)

    @property
    def reset_mode_description(self) -> str:
        if self.camera_reset_mode == 1:
            return "Mode 1 (Immediate RTSP Reload)"
        elif self.camera_reset_mode == 2:
            return "Mode 2 (600ms Settling Delay RTSP Reload)"
        return f"Unknown ({self.camera_reset_mode})"

    def format_summary(self) -> str:
        """Produces a multi-line formatted summary for diagnostics."""
        lines = [
            f"--- Drone Telemetry [{time.strftime('%H:%M:%S', time.localtime(self.timestamp))}] ---",
            f"Source         : {self.source_ip}:{7099} ({self.length} bytes)",
            f"Raw Hex        : {self.raw_hex}",
            f"Device ID      : {self.device_id} (0x{self.device_id:02X}) {'[GL Model]' if self.is_gl_model else '[Standard]'}",
            f"Camera Reset   : {self.reset_mode_description}",
            f"Remote Trigger : {self.remote_trigger_name} (0x{self.remote_trigger_raw:02X})",
        ]
        if self.photo_sequence is not None:
            lines.append(f"Photo Counter  : #{self.photo_sequence}")
        if self.video_sequence is not None:
            lines.append(f"Video Counter  : #{self.video_sequence}")
        if self.wifi_password:
            lines.append(f"Wi-Fi Password : {self.wifi_password} (Valid={self.password_valid})")
        if self.unknown_bytes:
            unparsed_str = ", ".join(f"B{k}:0x{v}" for k, v in sorted(self.unknown_bytes.items()))
            lines.append(f"Unparsed Bytes : {unparsed_str}")
        lines.append(f"IMU Transmitted: {self.imu_transmitted_by_drone} [VERIFIED: Drone does not send IMU data]")
        return "\n".join(lines)
