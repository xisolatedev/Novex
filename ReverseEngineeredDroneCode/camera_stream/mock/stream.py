"""
Mock camera stream simulator.
Generates synthetic video test patterns with moving markers, timestamps,
and artificial horizon for offline development and testing without physical drone hardware.
"""

import math
import threading
import time
from typing import Optional, Tuple
import cv2
import numpy as np
from camera.orientation import rotate_frame, normalize_angle
from camera.stream import CameraStream


class MockCameraStream(CameraStream):
    """
    Synthetic camera feed generator implementing the CameraStream interface.
    Provides test patterns, moving targets, and configurable frame rates.
    """

    def __init__(
        self,
        name: str = "Mock Camera",
        width: int = 1280,
        height: int = 720,
        target_fps: float = 20.0,
        style: str = "color_bars",
        rotation: int = 0
    ):
        self._name = name
        self._width = width
        self._height = height
        self._target_fps = target_fps
        self._frame_interval = 1.0 / max(target_fps, 1.0)
        self._style = style
        self._rotation = normalize_angle(rotation)

        self._running = False
        self._connected = False
        self._thread: Optional[threading.Thread] = None

        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_timestamp = 0.0

        self._frame_idx = 0
        self._fps = target_fps
        self._latency_ms = 15.0

    def connect(self) -> bool:
        if self._running:
            return True
        self._running = True
        self._connected = True
        self._thread = threading.Thread(target=self._generator_worker, name=f"MockWorker-{self._name}", daemon=True)
        self._thread.start()
        return True

    def disconnect(self) -> None:
        self._running = False
        self._connected = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._latest_frame = None

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray], float]:
        with self._frame_lock:
            if self._latest_frame is None:
                return False, None, 0.0
            return True, self._latest_frame, self._latest_timestamp

    def is_connected(self) -> bool:
        return self._connected

    def get_resolution(self) -> Tuple[int, int]:
        with self._frame_lock:
            if self._rotation in (90, 270):
                return self._height, self._width
            return self._width, self._height

    def get_fps(self) -> float:
        return self._fps

    def get_status(self) -> str:
        return "CONNECTED (MOCK)" if self._connected else "DISCONNECTED"

    def get_latency_ms(self) -> float:
        return self._latency_ms

    def get_name(self) -> str:
        return self._name

    def get_rotation(self) -> int:
        return self._rotation

    def set_rotation(self, angle: int) -> None:
        self._rotation = normalize_angle(angle)

    def pause_and_reload(self, delay_sec: float = 0.0) -> None:
        """Simulates camera switch reload with optional settling delay."""
        if delay_sec > 0:
            time.sleep(delay_sec)

    # -------------------------------------------------------------------------
    # Generator Loop
    # -------------------------------------------------------------------------

    def _generator_worker(self) -> None:
        last_time = time.time()
        fps_timer = time.time()
        frames_in_second = 0

        while self._running:
            start_loop = time.time()
            frame = self._render_test_pattern(self._frame_idx)
            if self._rotation != 0:
                frame = rotate_frame(frame, self._rotation)
            now = time.time()

            with self._frame_lock:
                self._latest_frame = frame
                self._latest_timestamp = now

            self._frame_idx += 1
            frames_in_second += 1

            if now - fps_timer >= 1.0:
                self._fps = round(frames_in_second / (now - fps_timer), 1)
                frames_in_second = 0
                fps_timer = now

            # Throttle to simulate exact frame rate
            elapsed = time.time() - start_loop
            sleep_needed = self._frame_interval - elapsed
            if sleep_needed > 0:
                time.sleep(sleep_needed)

    def _render_test_pattern(self, frame_num: int) -> np.ndarray:
        w, h = self._width, self._height
        canvas = np.zeros((h, w, 3), dtype=np.uint8)

        # 1. Dark gradient background
        for y in range(h):
            val = int(25 + 20 * (y / h))
            canvas[y, :] = (val, val + 5, val + 10)

        # 2. Grid lines
        grid_step = 60
        for x in range(0, w, grid_step):
            cv2.line(canvas, (x, 0), (x, h), (40, 45, 55), 1)
        for y in range(0, h, grid_step):
            cv2.line(canvas, (0, y), (w, y), (40, 45, 55), 1)

        # 3. Top color bars (SMPTE-style reference)
        bar_height = max(int(h * 0.12), 24)
        colors = [
            (255, 255, 255),  # White
            (0, 255, 255),    # Yellow
            (255, 255, 0),    # Cyan
            (0, 255, 0),      # Green
            (255, 0, 255),    # Magenta
            (0, 0, 255),      # Red
            (255, 0, 0),      # Blue
            (50, 50, 50)      # Gray
        ]
        bar_width = w // len(colors)
        for i, col in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < len(colors) - 1 else w
            cv2.rectangle(canvas, (x1, 0), (x2, bar_height), col, -1)

        # 4. Animated moving target / synthetic flight horizon
        cx, cy = w // 2, h // 2
        t = frame_num * 0.05
        offset_x = int(math.sin(t) * (w * 0.28))
        offset_y = int(math.cos(t * 1.3) * (h * 0.2))
        target_x = cx + offset_x
        target_y = cy + offset_y

        # Artificial Horizon Pitch / Roll lines
        pitch_offset = int(math.sin(t * 0.5) * 40)
        roll_angle = math.sin(t * 0.7) * 15.0  # degrees
        rad = math.radians(roll_angle)
        dx = int(math.cos(rad) * 120)
        dy = int(math.sin(rad) * 120)
        horizon_y = cy + pitch_offset
        cv2.line(canvas, (cx - dx, horizon_y - dy), (cx + dx, horizon_y + dy), (0, 215, 255), 2)
        cv2.circle(canvas, (cx, horizon_y), 4, (0, 215, 255), -1)

        # Moving Target Reticle (represents motion to verify pipeline smoothness)
        cv2.circle(canvas, (target_x, target_y), 24, (0, 255, 128), 2)
        cv2.line(canvas, (target_x - 30, target_y), (target_x + 30, target_y), (0, 255, 128), 1)
        cv2.line(canvas, (target_x, target_y - 30), (target_x, target_y + 30), (0, 255, 128), 1)

        # Center crosshairs
        cv2.drawMarker(canvas, (cx, cy), (120, 120, 140), cv2.MARKER_CROSS, 20, 1)

        # 5. On-canvas diagnostic watermark
        cv2.rectangle(canvas, (20, h - 90), (380, h - 20), (20, 24, 30), -1)
        cv2.rectangle(canvas, (20, h - 90), (380, h - 20), (60, 70, 85), 1)
        
        cv2.putText(canvas, f"STREAM: {self._name.upper()}", (35, h - 68), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 128), 1)
        cv2.putText(canvas, f"RES: {w}x{h} @ {self._target_fps:.0f} FPS", (35, h - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
        cv2.putText(canvas, f"FRAME: {frame_num:06d} | TS: {time.time():.3f}", (35, h - 32), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 180, 200), 1)

        return canvas
