"""
Drone communication constants extracted from decompiled com.cooingdv.rcufo codebase.

Ground Truth References:
- socket/Config.java: PREVIEW_ADDRESS = "rtsp://192.168.1.1:7070/webcam"
- socket/SocketClient.java: UdpComm.getInstance("192.168.1.1", 7099)
- socket/SocketClient.java: debugSend(new byte[]{1, 1}) -> Heartbeat (1000ms)
- socket/SocketClient.java: switchCamera() -> {6, 2} (secondary) or {6, 1} (primary)
- fragment/DeviceBLFragment.java: Remote triggers: 0x4D ('M', photo) and 0x58 ('X', video)
"""

# Default Network Endpoints
DEFAULT_DRONE_IP: str = "192.168.1.1"
DEFAULT_RTSP_PORT: int = 7070
DEFAULT_RTSP_PATH: str = "/webcam"
DEFAULT_RTSP_URL: str = f"rtsp://{DEFAULT_DRONE_IP}:{DEFAULT_RTSP_PORT}{DEFAULT_RTSP_PATH}"
DEFAULT_UDP_PORT: int = 7099

# Commands sent to UDP Port 7099 (Client -> Drone)
# VERIFIED FROM SOURCE: SocketClient.java
CMD_HEARTBEAT: bytes = bytes([0x01, 0x01])                   # Sent every 1000ms
CMD_SWITCH_CAMERA_PRIMARY: bytes = bytes([0x06, 0x01])      # Front/Main camera
CMD_SWITCH_CAMERA_SECONDARY: bytes = bytes([0x06, 0x02])    # Bottom/Secondary camera
CMD_ACK_PHOTO: bytes = bytes([0x09, 0x01])                  # Photo trigger ACK
CMD_ACK_VIDEO: bytes = bytes([0x09, 0x02])                  # Video trigger ACK

# Telemetry Remote Trigger Bytes (Byte 2 of UDP telemetry from 7099)
# VERIFIED FROM SOURCE: DeviceBLFragment.java
REMOTE_TRIGGER_PHOTO: int = 0x4D      # ASCII 'M' (77)
REMOTE_TRIGGER_VIDEO: int = 0x58      # ASCII 'X' (88)
REMOTE_TRIGGER_GL_SYNC: int = 0x66    # Decimal 102 (GL Optical flow frame sync)

# Camera Switch Reset Modes (Byte 1 of UDP telemetry from 7099)
# VERIFIED FROM SOURCE: SocketClient.java lines 405-444
CAMERA_RESET_MODE_IMMEDIATE: int = 1      # Immediate reload of RTSP stream
CAMERA_RESET_MODE_DELAYED_600MS: int = 2  # Stop RTSP, wait 600ms, then restart RTSP
