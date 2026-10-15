"""
Parser for 20-byte CooingDV UDP telemetry packets.
Implements the exact byte-level logic extracted from SocketClient.java and DeviceBLFragment.java.
"""

import time
from typing import Dict, Optional
from protocol.constants import (
    REMOTE_TRIGGER_PHOTO,
    REMOTE_TRIGGER_VIDEO,
    REMOTE_TRIGGER_GL_SYNC,
)
from .model import DroneTelemetryPacket


def is_gl_device(device_id: int) -> bool:
    """
    Evaluates whether device is a GL-series optical flow drone.
    Ground truth: WifiIdUtils.isGL(int i) in com.cooingdv.rcufo.utils.WifiIdUtils.
    """
    return (90 <= device_id <= 101) or device_id in (103, 82, 85, 88)


def is_no_rotate_device(device_id: int) -> bool:
    """
    Evaluates whether drone camera does NOT require 90-degree clockwise rotation.
    Ground truth: WifiIdUtils.isNoRotate(int i) in com.cooingdv.rcufo.utils.WifiIdUtils.
    Only devices 94 and 99 do not require rotation.
    """
    return device_id in (94, 99)


def parse_telemetry_packet(data: bytes, source_ip: str = "192.168.1.1", timestamp: Optional[float] = None) -> Optional[DroneTelemetryPacket]:
    """
    Parses a raw UDP packet received from the drone (typically 20 bytes).

    Args:
        data: Raw datagram payload bytes.
        source_ip: Sender IP address.
        timestamp: Packet arrival epoch timestamp (defaults to time.time()).

    Returns:
        Populated DroneTelemetryPacket, or None if data is empty.
    """
    if not data or len(data) == 0:
        return None

    if timestamp is None:
        timestamp = time.time()

    pkt_len = len(data)
    parsed_byte_indices = set()

    # Byte 0: Hardware / Fake Resolution Number
    device_id = data[0]
    parsed_byte_indices.add(0)
    is_gl = is_gl_device(device_id)
    requires_rotation = not is_no_rotate_device(device_id)

    # Byte 1: Camera Switch Reset Mode
    camera_reset_mode = 0
    if pkt_len >= 2:
        camera_reset_mode = data[1]
        parsed_byte_indices.add(1)

    # Byte 2: Remote Trigger / Sync Header
    remote_trigger_raw = 0
    remote_trigger_name = "Idle"
    photo_seq = None
    video_seq = None

    if pkt_len >= 3:
        remote_trigger_raw = data[2]
        parsed_byte_indices.add(2)
        if remote_trigger_raw == REMOTE_TRIGGER_PHOTO:  # 0x4D ('M')
            remote_trigger_name = "Photo Shutter"
            if pkt_len >= 4:
                photo_seq = data[3]
                parsed_byte_indices.add(3)
        elif remote_trigger_raw == REMOTE_TRIGGER_VIDEO:  # 0x58 ('X')
            remote_trigger_name = "Video Record"
            if pkt_len >= 5:
                video_seq = data[4]
                parsed_byte_indices.add(4)
        elif remote_trigger_raw == REMOTE_TRIGGER_GL_SYNC:  # 0x66 (102)
            remote_trigger_name = "GL Frame Sync"
        elif remote_trigger_raw == 0x00:
            remote_trigger_name = "Standby"
        else:
            remote_trigger_name = f"Trigger 0x{remote_trigger_raw:02X}"

    # Password extraction logic from SocketClient.java
    password_status = None
    password_valid = None
    wifi_password = None

    if is_gl and pkt_len >= 19:
        password_status = data[8]
        parsed_byte_indices.add(8)
        password_valid = (data[9] == 1)
        parsed_byte_indices.add(9)
        if password_valid:
            # Low nibbles of bytes 11..18
            nibbles = [f"{data[i] & 0x0F:X}" for i in range(11, 19)]
            wifi_password = "".join(nibbles)
            for i in range(11, 19):
                parsed_byte_indices.add(i)
    elif not is_gl and pkt_len >= 15:
        password_status = data[5]
        parsed_byte_indices.add(5)
        password_valid = (data[6] == 1)
        parsed_byte_indices.add(6)
        if password_valid:
            # Reassembly order from SocketClient.java:
            # cCharAt=B7, cCharAt4=B8, cCharAt7=B9, cCharAt3=B10,
            # cCharAt5=B11, cCharAt8=B12, cCharAt6=B13, cCharAt2=B14
            b = data
            ordered_nibbles = [
                f"{b[7] & 0x0F:X}",
                f"{b[8] & 0x0F:X}",
                f"{b[9] & 0x0F:X}",
                f"{b[10] & 0x0F:X}",
                f"{b[11] & 0x0F:X}",
                f"{b[12] & 0x0F:X}",
                f"{b[13] & 0x0F:X}",
                f"{b[14] & 0x0F:X}",
            ]
            wifi_password = "".join(ordered_nibbles)
            for i in range(7, 15):
                parsed_byte_indices.add(i)

    # Collect all bytes NOT parsed by decompiled source code
    unknown_bytes: Dict[int, str] = {}
    for idx in range(pkt_len):
        if idx not in parsed_byte_indices:
            unknown_bytes[idx] = f"{data[idx]:02X}"

    return DroneTelemetryPacket(
        timestamp=timestamp,
        source_ip=source_ip,
        raw_bytes=data,
        length=pkt_len,
        device_id=device_id,
        is_gl_model=is_gl,
        requires_rotation=requires_rotation,
        camera_reset_mode=camera_reset_mode,
        remote_trigger_raw=remote_trigger_raw,
        remote_trigger_name=remote_trigger_name,
        photo_sequence=photo_seq,
        video_sequence=video_seq,
        password_status=password_status,
        password_valid=password_valid,
        wifi_password=wifi_password,
        unknown_bytes=unknown_bytes,
        imu_transmitted_by_drone=False  # Source code verifies drone transmits no gyro/accel data
    )
