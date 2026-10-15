"""
Camera switching, as SocketClient.switchCamera() (lines 399-444).

There is ONE RTSP endpoint (rtsp://192.168.1.1:7070/webcam). Switching is a UDP
command on 7099 that makes the drone change which sensor feeds that stream:

    isSwitchCamera = !isSwitchCamera
    send  06 02  if isSwitchCamera else  06 01
    switchCameraReset (telemetry byte1):
        1 -> restart RTSP playback immediately
        2 -> stop playback first, restart after 600 ms
        other -> no playback restart
    isSwitchingCamera = true (for 1 and 2) until the player reports "prepared"

While isSwitchingCamera is set, a video error does NOT tear down the UDP task
(cancelUdpTask returns early) and "prepared" does NOT restart it.
The app never names the cameras; it only toggles between the two commands.
"""

import logging
import threading
from typing import Callable, Optional, Protocol

from controller.protocol import CMD_CAMERA_1, CMD_CAMERA_2

logger = logging.getLogger(__name__)

RESET_IMMEDIATE = 1
RESET_DELAYED = 2
RESET_DELAY_S = 0.6


class ReloadableStream(Protocol):
    def pause_and_reload(self, delay_sec: float = 0.0) -> None: ...


class CameraSwitcher:
    def __init__(self, send: Callable[[str, bytes], bool], reset_mode: Callable[[], int],
                 stream: Optional[ReloadableStream] = None):
        self._send = send
        self._reset_mode = reset_mode
        self._stream = stream
        self._lock = threading.Lock()
        self.is_switch_camera = False      # SocketClient.isSwitchCamera
        self.is_switching = False          # SocketClient.isSwitchingCamera
        self.commands_sent = 0

    @property
    def current_command(self) -> Optional[bytes]:
        """Last camera command sent, or None if never switched (drone's power-on camera)."""
        if self.commands_sent == 0:
            return None
        return CMD_CAMERA_2 if self.is_switch_camera else CMD_CAMERA_1

    def describe(self) -> str:
        cmd = self.current_command
        if cmd is None:
            return "power-on default (no switch sent)"
        return f"camera {cmd[1]} (sent {cmd.hex(' ').upper()})"

    def switch(self) -> str:
        with self._lock:
            if self.is_switching:
                return "camera switch already in progress"
            reset = self._reset_mode()
            self.is_switch_camera = not self.is_switch_camera
            cmd = CMD_CAMERA_2 if self.is_switch_camera else CMD_CAMERA_1
            if reset in (RESET_IMMEDIATE, RESET_DELAYED):
                self.is_switching = True
        ok = self._send("CAMERA SWITCH", cmd)
        self.commands_sent += 1
        if self._stream is not None:
            if reset == RESET_IMMEDIATE:
                self._stream.pause_and_reload(0.0)
            elif reset == RESET_DELAYED:
                self._stream.pause_and_reload(RESET_DELAY_S)
        logger.info("Camera switch: sent %s (reset mode %d, %s)", cmd.hex(" ").upper(), reset,
                    "ok" if ok else "link down")
        return f"camera switch {cmd.hex(' ').upper()} (reset mode {reset})"

    def on_video_prepared(self) -> bool:
        """Returns True if this 'prepared' completes a camera switch (onPrepared branch)."""
        with self._lock:
            was = self.is_switching
            self.is_switching = False
            return was
