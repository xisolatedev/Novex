"""
Live video: camera_stream's RtspCameraStream (reused unchanged) plus the
display rules from the app.

Endpoint: Config.PREVIEW_ADDRESS = rtsp://192.168.1.1:7070/webcam.
Reconnect: SocketClient.stopAndRestartPlayback() restarts after 500 ms
(Config.RECONNECTION_INTERVAL = 500).

Rotation (MjpegThread.java ~line 262): rotate 90 degrees only when the decoded frame
is 240x320, 120x160 or 160x272 and the device ID is not "no rotate" (94, 99);
rotate 180 degrees when the user enables "turn 180" (isTurnBitmap).
"""

import time
from typing import Optional, Tuple

import numpy as np

from camera.orientation import rotate_frame   # camera_stream
from camera.stream import RtspCameraStream    # camera_stream

from link.parser import is_no_rotate_device

PREVIEW_ADDRESS = "rtsp://192.168.1.1:7070/webcam"
RECONNECTION_INTERVAL_S = 0.5
PORTRAIT_SIZES = {(240, 320), (120, 160), (160, 272)}


def source_rotation(width: int, height: int, device_id: Optional[int], turn_180: bool = False) -> int:
    """Total rotation the app applies to a decoded frame of this size."""
    angle = 180 if turn_180 else 0
    # MjpegThread checks the size AFTER the optional 180 turn, which does not change the size.
    if (width, height) in PORTRAIT_SIZES and not (device_id is not None and is_no_rotate_device(device_id)):
        angle = (angle + 90) % 360
    return angle


class DroneVideo:
    """Owns the RTSP reader; exposes frames with the app's rotation applied."""

    def __init__(self, url: str = PREVIEW_ADDRESS, rtsp_transport: str = "udp"):
        self.url = url
        # Rotation handled here (per frame size), so the reader's own rotation is 0.
        self.stream = RtspCameraStream("drone", url, rtsp_transport=rtsp_transport,
                                       reconnect_interval=RECONNECTION_INTERVAL_S, rotation=0)
        self.turn_180 = False
        self.device_id: Optional[int] = None
        self._last_ts = 0.0

    def start(self) -> None:
        self.stream.connect()

    def stop(self) -> None:
        self.stream.disconnect()

    def pause_and_reload(self, delay_sec: float = 0.0) -> None:
        self.stream.pause_and_reload(delay_sec)

    # Matches the app's player tolerance: applyOptionsToVideoView sets
    # readtimeout = 5 000 000 us (SocketClient.java L154), so the Android player does not
    # report an error until ~5 s of silence. A 2 s threshold here used to declare video
    # lost long before the app would, which tore down the control link mid-flight.
    VIDEO_STALE_S = 5.0

    def has_live_frames(self, max_age_s: Optional[float] = None) -> bool:
        max_age_s = self.VIDEO_STALE_S if max_age_s is None else max_age_s
        ok, _, ts = self.stream.read_frame()
        return ok and self.stream.is_connected() and time.time() - ts < max_age_s

    def frame_age(self) -> Optional[float]:
        ok, _, ts = self.stream.read_frame()
        return None if not ok else time.time() - ts

    def read(self) -> Tuple[bool, Optional[np.ndarray], float]:
        ok, frame, ts = self.stream.read_frame()
        if not ok or frame is None:
            return False, None, 0.0
        h, w = frame.shape[:2]
        angle = source_rotation(w, h, self.device_id, self.turn_180)
        if angle:
            frame = rotate_frame(frame, angle)
        return True, frame, ts

    def status(self) -> str:
        return self.stream.get_status()

    def fps(self) -> float:
        return self.stream.get_fps()

    def resolution(self) -> Tuple[int, int]:
        return self.stream.get_resolution()
