"""
Telemetry parsing. The byte-level parser is camera_stream's (reused unchanged);
this module only adds the device-type rule from SocketClient.
"""

from telemetry.parser import is_gl_device, is_no_rotate_device, parse_telemetry_packet  # camera_stream

from controller.protocol import DEVICE_TYPE_GL, DEVICE_TYPE_TC


def classify_device_type(byte0: int) -> int:
    """SocketClient lambda$startUdpTask$1: ``WifiIdUtils.isGL(bArr[0]) ? GL(2) : TC(10)``."""
    return DEVICE_TYPE_GL if is_gl_device(byte0) else DEVICE_TYPE_TC


__all__ = ["classify_device_type", "is_gl_device", "is_no_rotate_device", "parse_telemetry_packet"]
