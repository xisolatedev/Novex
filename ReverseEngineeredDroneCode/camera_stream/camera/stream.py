"""
Camera stream abstractions and RTSP network implementation.
Includes dynamic rotation transformation and pipeline reload controls.
"""

from abc import ABC, abstractmethod
import logging
import threading
import time
from typing import Optional, Tuple
import cv2
import numpy as np
from .orientation import rotate_frame, normalize_angle

logger = logging.getLogger(__name__)


class CameraStream(ABC):
    """
    Abstract interface for camera streams.
    Decouples UI and vision consumers from the physical transport layer.
    """

    @abstractmethod
    def connect(self) -> bool:
        """Establishes connection to the stream."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Terminates connection and cleans up resources."""
        pass

    @abstractmethod
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """
        Retrieves the latest available frame.
        Returns:
            (success: bool, frame: np.ndarray BGR or None, timestamp_seconds: float)
        """
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Returns True if stream is actively delivering frames."""
        pass

    @abstractmethod
    def get_resolution(self) -> Tuple[int, int]:
        """Returns (width, height) of native or rotated video frames."""
        pass

    @abstractmethod
    def get_fps(self) -> float:
        """Returns measured decode FPS."""
        pass

    @abstractmethod
    def get_status(self) -> str:
        """Returns human-readable stream status."""
        pass

    @abstractmethod
    def get_latency_ms(self) -> float:
        """Returns estimated frame acquisition interval in milliseconds."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Returns camera identifier name."""
        pass

    @abstractmethod
    def get_rotation(self) -> int:
        """Returns current frame rotation angle in degrees."""
        pass

    @abstractmethod
    def set_rotation(self, angle: int) -> None:
        """Sets frame rotation angle in degrees (0, 90, 180, 270)."""
        pass


class RtspCameraStream(CameraStream):
    """
    High-performance, non-blocking RTSP stream reader.
    Uses a dedicated background capture thread to ensure zero frame-buffering delay.
    Supports on-the-fly frame rotation and pipeline reloading for camera switching.
    """

    def __init__(
        self,
        name: str,
        url: str,
        rtsp_transport: str = "udp",
        reconnect_interval: float = 2.0,
        buffer_size: int = 1,
        rotation: int = 0
    ):
        self._name = name
        self._url = url
        self._rtsp_transport = rtsp_transport
        self._reconnect_interval = reconnect_interval
        self._buffer_size = buffer_size
        self._rotation = normalize_angle(rotation)

        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        self._status = "DISCONNECTED"

        # Frame slot (thread-safe, latest frame only)
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_timestamp = 0.0
        self._width = 0
        self._height = 0

        # Performance and diagnostics
        self._fps = 0.0
        self._frame_count = 0
        self._last_fps_time = time.time()
        self._latency_ms = 0.0
        self._last_frame_arrival = time.time()

        # Reload coordination
        self._reload_event = threading.Event()
        self._reload_delay = 0.0

    def connect(self) -> bool:
        """Starts the background capture and auto-reconnection thread."""
        if self._running:
            return True
        self._running = True
        self._status = "CONNECTING"
        self._thread = threading.Thread(target=self._capture_worker, name=f"RtspWorker-{self._name}", daemon=True)
        self._thread.start()
        return True

    def disconnect(self) -> None:
        """Stops the capture worker and closes the underlying socket/capture."""
        self._running = False
        self._reload_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._release_capture()
        self._status = "DISCONNECTED"
        self._connected = False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray], float]:
        with self._frame_lock:
            if self._latest_frame is None:
                return False, None, 0.0
            return True, self._latest_frame, self._latest_timestamp

    def is_connected(self) -> bool:
        return self._connected

    def get_resolution(self) -> Tuple[int, int]:
        with self._frame_lock:
            return self._width, self._height

    def get_fps(self) -> float:
        return self._fps

    def get_status(self) -> str:
        return self._status

    def get_latency_ms(self) -> float:
        return self._latency_ms

    def get_name(self) -> str:
        return self._name

    def get_rotation(self) -> int:
        return self._rotation

    def set_rotation(self, angle: int) -> None:
        """Dynamically updates rotation angle."""
        norm = normalize_angle(angle)
        if norm != self._rotation:
            self._rotation = norm
            logger.info(f"[{self._name}] Rotation set to: {self._rotation}°")

    def set_url(self, new_url: str) -> None:
        """Dynamically updates stream URL and triggers reconnect."""
        if self._url != new_url:
            self._url = new_url
            if self._running:
                self._reload_event.set()

    def pause_and_reload(self, delay_sec: float = 0.0) -> None:
        """
        Coordinates a brief pipeline pause and reconnect on the worker thread.
        Thread-safe: signals the capture thread to release and reconnect.
        Never calls release() directly from the caller thread.
        """
        logger.info(f"[{self._name}] Pipeline reload requested (delay={delay_sec:.2f}s)")
        self._reload_delay = delay_sec
        self._reload_event.set()

    # -------------------------------------------------------------------------
    # Internal Capture Worker
    # -------------------------------------------------------------------------

    def _open_capture(self) -> bool:
        self._release_capture()
        logger.info(f"[{self._name}] Opening RTSP stream: {self._url} (transport={self._rtsp_transport})")
        
        # Configure FFmpeg RTSP options (transport and socket read timeout 2.0s)
        import os
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = f"rtsp_transport;{self._rtsp_transport}|stimeout;2000000"

        backend = cv2.CAP_FFMPEG
        cap = cv2.VideoCapture(self._url, backend)
        
        if not cap.isOpened():
            logger.warning(f"[{self._name}] Failed to open RTSP stream: {self._url}")
            return False

        # Set low buffer size to discard stale backlog
        cap.set(cv2.CAP_PROP_BUFFERSIZE, self._buffer_size)
        
        raw_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        raw_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if raw_w <= 0:
            raw_w = 640
        if raw_h <= 0:
            raw_h = 480

        with self._frame_lock:
            if self._rotation in (90, 270):
                self._width, self._height = raw_h, raw_w
            else:
                self._width, self._height = raw_w, raw_h
        
        self._cap = cap
        return True

    def _release_capture(self) -> None:
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        self._connected = False

    def _capture_worker(self) -> None:
        """Daemon thread loop for continuous reading and automatic reconnection."""
        while self._running:
            # Check if reload delay was requested
            if self._reload_event.is_set():
                self._reload_event.clear()
                if self._reload_delay > 0:
                    time.sleep(self._reload_delay)

            if self._cap is None or not self._cap.isOpened():
                self._status = "CONNECTING"
                if not self._open_capture():
                    self._status = "RECONNECTING"
                    sleep_time = 0.0
                    while self._running and sleep_time < self._reconnect_interval:
                        if self._reload_event.is_set():
                            break
                        time.sleep(0.2)
                        sleep_time += 0.2
                    continue

            # Stream is open, begin frame grab loop
            self._status = "CONNECTED"
            self._connected = True
            self._last_fps_time = time.time()
            self._frame_count = 0

            consecutive_failures = 0
            while self._running and self._cap and self._cap.isOpened():
                if self._reload_event.is_set():
                    logger.info(f"[{self._name}] Pipeline reload event triggered, cycling stream...")
                    break

                ret, frame = self._cap.read()
                
                if self._reload_event.is_set():
                    logger.info(f"[{self._name}] Pipeline reload event triggered after read, cycling stream...")
                    break

                if not ret or frame is None:
                    consecutive_failures += 1
                    if consecutive_failures > 15:
                        logger.warning(f"[{self._name}] Lost stream signal from {self._url}")
                        break
                    time.sleep(0.01)
                    continue

                consecutive_failures = 0
                now_recv = time.time()
                
                # Apply rotation if active
                if self._rotation != 0:
                    frame = rotate_frame(frame, self._rotation)

                # Calculate inter-frame interval / latency indicator
                self._latency_ms = (now_recv - self._last_frame_arrival) * 1000.0
                self._last_frame_arrival = now_recv

                # Update latest frame
                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_timestamp = now_recv
                    self._width = frame.shape[1]
                    self._height = frame.shape[0]

                # Update FPS counter
                self._frame_count += 1
                elapsed = now_recv - self._last_fps_time
                if elapsed >= 1.0:
                    self._fps = round(self._frame_count / elapsed, 1)
                    self._frame_count = 0
                    self._last_fps_time = now_recv

            # Handle stream break / reload safely on the worker thread
            self._release_capture()
            if self._reload_event.is_set():
                self._reload_event.clear()
                if self._reload_delay > 0:
                    logger.info(f"[{self._name}] Settling pipeline for {self._reload_delay:.2f}s...")
                    time.sleep(self._reload_delay)
                self._reload_delay = 0.0
            elif self._running:
                self._status = "RECONNECTING"
                time.sleep(self._reconnect_interval)

        self._release_capture()
        self._status = "DISCONNECTED"
