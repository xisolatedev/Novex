"""
Wires video, UDP link, flight loop and camera switching together with the
start/stop coupling of SocketClient:

  RTSP "prepared"  -> startUdpTask()   (UDP socket + receive thread + 1 Hz heartbeat)
                      unless it completes a camera switch
  RTSP error       -> cancelUdpTask()  (heartbeat stopped, socket closed), then the
                      player restarts after 500 ms; skipped while a switch is in progress

In the app the flight timer keeps running while the UDP task is down; its sends go
nowhere. That is reproduced here: the loop keeps ticking, packets show as DROPPED.

With ``link_follows_video=False`` the UDP link starts immediately and is independent of
video. That is a PC-side diagnostic option, not the app's behaviour.
"""

import enum
import logging
import threading
import time
from typing import Optional

from controller.flight import FlightController
from controller.protocol import DEVICE_TYPE_NAMES
from link.parser import is_gl_device
from link.udp_link import DroneLink
from video.switch import CameraSwitcher

logger = logging.getLogger(__name__)


class ConnectionState(enum.Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    VIDEO_CONNECTED = "VIDEO CONNECTED"
    TELEMETRY_CONNECTED = "TELEMETRY CONNECTED"
    CONNECTED = "CONNECTED"


def derive_connection_state(video_starting: bool, video_live: bool, telemetry_live: bool) -> ConnectionState:
    if video_live and telemetry_live:
        return ConnectionState.CONNECTED
    if video_live:
        return ConnectionState.VIDEO_CONNECTED
    if telemetry_live:
        return ConnectionState.TELEMETRY_CONNECTED
    return ConnectionState.CONNECTING if video_starting else ConnectionState.DISCONNECTED


class DroneSession:
    def __init__(self, video, link: DroneLink, flight: FlightController, switcher: CameraSwitcher,
                 link_follows_video: bool = True, packet_logger=None, telemetry_logger=None,
                 link_policy: str = "keepalive", vio_client=None):
        self.video = video
        self.link = link
        self.flight = flight
        self.switcher = switcher
        self.link_follows_video = link_follows_video
        # "keepalive": never drop the control link while control mode is ON (PC-side safety
        #              deviation; the app would call cancelUdpTask on a player error).
        # "app":       reproduce the app's teardown on every video loss.
        self.link_policy = link_policy
        self.vio_client = vio_client
        self.packet_logger = packet_logger
        self.telemetry_logger = telemetry_logger
        self._video_live = False
        self._last_video_status = None
        self._last_gap_report = 0.0
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.last_message = ""
        link.add_packet_listener(self._on_telemetry)

    def start(self) -> None:
        self._running = True
        if self.telemetry_logger:
            self.telemetry_logger.start()
        if self.flight.gamepad is not None:
            self.flight.gamepad.start()
        if self.vio_client is not None:
            self.vio_client.start()
        if self.video:
            self.video.start()
        if not self.link_follows_video or self.video is None:
            self.link.start()
        self._thread = threading.Thread(target=self._supervise, name="SessionSupervisor", daemon=True)
        self._thread.start()

    def _on_telemetry(self, pkt) -> None:
        if self.telemetry_logger:
            self.telemetry_logger.log_packet(pkt)
        if self.video is not None:
            self.video.device_id = self.link.first_device_id
        # DeviceBLFragment onReceiver: a GL ID forces fixed-height mode ON.
        if is_gl_device(pkt.device_id) and not self.flight.state.fixed_height:
            self.flight.set_fixed_height(True)
            logger.info("GL device ID %d: fixed-height forced ON (as in the app)", pkt.device_id)

    def _supervise(self) -> None:
        while self._running:
            live = self.video.has_live_frames() if self.video else False
            if live and not self._video_live:
                self._on_video_prepared()
            elif self._video_live and not live:
                self._on_video_error()
            self._video_live = live
            self._log_video_diagnostics()
            time.sleep(0.1)

    def _log_video_diagnostics(self) -> None:
        """Put RTSP state on the same timeline as the packets, so a video failure is diagnosable."""
        if not self.video:
            return
        status = self.video.status()
        if status != self._last_video_status:
            self._event("VIDEO STATUS", f"{self._last_video_status} -> {status} "
                                        f"(fps={self.video.fps():.1f})")
            self._last_video_status = status
        age = self.video.frame_age()
        now = time.time()
        if age is not None and age > 1.0 and now - self._last_gap_report > 1.0:
            self._event("VIDEO GAP", f"no new frame for {age:.1f}s (status={status})")
            self._last_gap_report = now

    def _on_video_prepared(self) -> None:
        if self.switcher.on_video_prepared():
            logger.info("Video prepared after camera switch (UDP task left running)")
            self._event("VIDEO", "prepared after camera switch; link untouched")
            return
        logger.info("Video prepared")
        self._event("VIDEO", "prepared")
        if self.link_follows_video:
            self.link.start()

    def _on_video_error(self) -> None:
        if self.switcher.is_switching:
            return   # cancelUdpTask(): if (isSwitchingCamera) return;
        logger.warning("Video lost (status=%s)", self.video.status() if self.video else "-")
        self._event("VIDEO", f"LOST (status={self.video.status() if self.video else '-'})")
        if not self.link_follows_video:
            return
        if self.link_policy == "keepalive" and self.flight.state.control_mode:
            # Deliberate deviation from the app: cancelUdpTask() here would stop the heartbeat
            # and close the socket mid-flight, leaving the drone with no uplink at all.
            logger.error("Video lost while control mode is ON: KEEPING the UDP link up "
                         "(PC-side safety policy; the app would close it). Video will keep retrying.")
            self._event("LINK", "video lost while control mode ON: link KEPT UP (policy=keepalive)")
            return
        logger.warning("Stopping UDP link as the app does on player error; "
                       "flight packets are dropped until video returns")
        self.link.stop()

    def _event(self, name: str, detail: str) -> None:
        if self.packet_logger:
            self.packet_logger.log_event(name, detail)

    # ---- status for the UI --------------------------------------------------------

    def connection_state(self) -> ConnectionState:
        video_starting = self.video is not None and self._running
        return derive_connection_state(video_starting, self._video_live, self.link.telemetry_alive())

    def device_summary(self) -> str:
        t = self.link.effective_device_type()
        forced = " (forced)" if self.link.effective_device_type() != self.link.device_type else ""
        return f"{DEVICE_TYPE_NAMES.get(t, '?')}({t}){forced}"

    # ---- shutdown -----------------------------------------------------------------

    def shutdown(self) -> None:
        logger.info("Shutting down...")
        self._running = False
        if self.flight.gamepad is not None:
            self.flight.gamepad.stop()         # release the joystick device
        if self.flight.face_travel is not None:
            self.flight.face_travel.set_enabled(False)
        if self.vio_client is not None:
            self.vio_client.stop()             # close the VIO socket, flush any recording
        self.flight.shutdown()                 # stop 20 Hz loop, send 08 01 if it was running
        if self._thread:
            self._thread.join(timeout=1.0)
        self.link.stop()                       # stop heartbeat, close UDP socket
        if self.video:
            self.video.stop()                  # stop RTSP playback, release capture
        if self.telemetry_logger:
            self.telemetry_logger.stop()
        if self.packet_logger:
            self.packet_logger.close()
        logger.info("Shutdown complete")
