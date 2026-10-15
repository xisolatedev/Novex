"""
Drone camera viewer window and presentation loop.
Handles aspect-ratio preserving scaling (fit/crop), on-the-fly frame rotation,
UDP camera switching, telemetry overlay, and real-time HUD integration.
"""

import logging
import time
from typing import Optional, Tuple
import cv2
import numpy as np
from camera.manager import CameraManager
from camera.orientation import cycle_rotation
from config import AppConfig
from drone.state import DroneState
from .hud import HUDOverlay
from .telemetry_panel import TelemetryPanel

logger = logging.getLogger(__name__)


class DroneCameraViewer:
    """
    Main display controller managing window rendering and user interaction.
    """

    def __init__(
        self,
        config: AppConfig,
        camera_manager: CameraManager,
        drone_state: DroneState,
        camera_switcher: Optional[object] = None
    ):
        self.config = config
        self.camera_manager = camera_manager
        self.drone_state = drone_state
        self.camera_switcher = camera_switcher

        self.hud = HUDOverlay(config.hud)
        self.telemetry_panel = TelemetryPanel(visible=config.telemetry.show_telemetry_panel)

        self._window_name = config.display.window_title
        self._is_fullscreen = config.display.fullscreen
        self._aspect_mode = config.display.aspect_mode
        self._running = False

        # Rendering diagnostics
        self._render_fps = 0.0
        self._render_frames = 0
        self._last_fps_calc_time = time.time()

    def run(self) -> None:
        """Starts camera streams and executes the main GUI presentation loop."""
        logger.info("Starting camera streams...")
        self.camera_manager.start_all()
        self._running = True

        cv2.namedWindow(self._window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self._window_name, self.config.display.window_width, self.config.display.window_height)

        if self._is_fullscreen:
            cv2.setWindowProperty(self._window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        target_interval = 1.0 / max(self.config.display.target_fps, 10)

        try:
            while self._running:
                loop_start = time.time()

                # Get current window size (responsive resize)
                rect = cv2.getWindowImageRect(self._window_name)
                win_w = rect[2] if rect[2] > 100 else self.config.display.window_width
                win_h = rect[3] if rect[3] > 100 else self.config.display.window_height

                # Render frame based on active mode
                if self.camera_manager.is_dual_mode():
                    canvas = self._render_dual_view(win_w, win_h)
                else:
                    canvas = self._render_single_view(win_w, win_h)

                # Draw telemetry inspector overlay if toggled
                drone_info = self.drone_state.get_snapshot()
                canvas = self.telemetry_panel.draw(canvas, drone_info)

                cv2.imshow(self._window_name, canvas)

                # Measure render FPS
                self._render_frames += 1
                now = time.time()
                elapsed_fps = now - self._last_fps_calc_time
                if elapsed_fps >= 1.0:
                    self._render_fps = round(self._render_frames / elapsed_fps, 1)
                    self._render_frames = 0
                    self._last_fps_calc_time = now

                # Process user hotkeys (1 ms or remaining budget)
                compute_time = time.time() - loop_start
                delay_ms = max(1, int((target_interval - compute_time) * 1000))
                key = cv2.waitKey(delay_ms) & 0xFF

                if key != 255:
                    self._handle_key(key)

                # Check if window closed by user
                if cv2.getWindowProperty(self._window_name, cv2.WND_PROP_VISIBLE) < 1:
                    logger.info("Window closed by user.")
                    break

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received.")
        finally:
            self.close()

    def close(self) -> None:
        """Gracefully closes cameras and releases window surfaces."""
        self._running = False
        logger.info("Stopping camera streams...")
        self.camera_manager.stop_all()
        cv2.destroyAllWindows()
        logger.info("Viewer shutdown complete.")

    # -------------------------------------------------------------------------
    # Frame Rendering & Layout Logic
    # -------------------------------------------------------------------------

    def _render_single_view(self, target_w: int, target_h: int) -> np.ndarray:
        """Renders single active camera stream with aspect-ratio preservation."""
        stream = self.camera_manager.get_active_stream() or self.camera_manager.get_stream("primary")
        if not self.camera_switcher:
            active_id = self.camera_manager.get_active_camera_id()
            self.drone_state.set_active_camera(active_id)
        self.drone_state.set_camera_mode("Single View")

        canvas = np.full((target_h, target_w, 3), self.config.display.background_color, dtype=np.uint8)
        drone_info = self.drone_state.get_snapshot()

        if stream is None:
            return self.hud.draw_standby_screen(canvas, "Not Configured", "NO_STREAM", drone_info.active_camera_name)

        ret, frame, _ = stream.read_frame()

        if not ret or frame is None:
            status_msg = stream.get_status()
            cam_name = drone_info.active_camera_name
            url = getattr(stream, "_url", "Simulated")
            return self.hud.draw_standby_screen(canvas, url, status_msg, cam_name)

        # Scale frame preserving aspect ratio
        canvas = self._fit_or_crop_frame(frame, canvas, target_w, target_h, self._aspect_mode)

        # Draw HUD diagnostics
        res = stream.get_resolution()
        fps = stream.get_fps()
        latency = stream.get_latency_ms()
        status = stream.get_status()
        rotation_deg = stream.get_rotation() if hasattr(stream, "get_rotation") else self.config.display.rotation

        return self.hud.draw_hud(
            canvas=canvas,
            drone_info=drone_info,
            decode_fps=fps,
            render_fps=self._render_fps,
            latency_ms=latency,
            resolution=res,
            aspect_mode=self._aspect_mode,
            stream_status=status,
            camera_name=drone_info.active_camera_name,
            rotation_deg=rotation_deg
        )

    def _render_dual_view(self, target_w: int, target_h: int) -> np.ndarray:
        """Renders primary and secondary cameras side-by-side maintaining individual aspect ratios."""
        self.drone_state.set_camera_mode("Dual View (Side-by-Side)")
        canvas = np.full((target_h, target_w, 3), self.config.display.background_color, dtype=np.uint8)

        streams = self.camera_manager.get_all_streams()
        if len(streams) < 2:
            return self._render_single_view(target_w, target_h)

        mid_x = target_w // 2

        # Viewport 1 (Primary / Left)
        id1, stream1 = streams[0]
        vp1_canvas = np.full((target_h, mid_x, 3), self.config.display.background_color, dtype=np.uint8)
        ret1, frame1, _ = stream1.read_frame()
        if ret1 and frame1 is not None:
            vp1_canvas = self._fit_or_crop_frame(frame1, vp1_canvas, mid_x, target_h, "fit")
            res1 = stream1.get_resolution()
            fps1 = stream1.get_fps()
            cv2.putText(vp1_canvas, f"{stream1.get_name()} ({res1[0]}x{res1[1]} @ {fps1:.0f}Hz)", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 128), 1)
        else:
            vp1_canvas = self.hud.draw_standby_screen(vp1_canvas, getattr(stream1, "_url", "Simulated"), stream1.get_status(), stream1.get_name())

        # Viewport 2 (Secondary / Right)
        id2, stream2 = streams[1]
        vp2_w = target_w - mid_x
        vp2_canvas = np.full((target_h, vp2_w, 3), self.config.display.background_color, dtype=np.uint8)
        ret2, frame2, _ = stream2.read_frame()
        if ret2 and frame2 is not None:
            vp2_canvas = self._fit_or_crop_frame(frame2, vp2_canvas, vp2_w, target_h, "fit")
            res2 = stream2.get_resolution()
            fps2 = stream2.get_fps()
            cv2.putText(vp2_canvas, f"{stream2.get_name()} ({res2[0]}x{res2[1]} @ {fps2:.0f}Hz)", (15, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 215, 255), 1)
        else:
            vp2_canvas = self.hud.draw_standby_screen(vp2_canvas, getattr(stream2, "_url", "Simulated"), stream2.get_status(), stream2.get_name())

        # Compose viewports onto canvas
        canvas[:, :mid_x] = vp1_canvas
        canvas[:, mid_x:] = vp2_canvas

        # Vertical separator line
        cv2.line(canvas, (mid_x, 0), (mid_x, target_h), (50, 60, 80), 2)

        # Global HUD overlay
        drone_info = self.drone_state.get_snapshot()
        active_stream = self.camera_manager.get_active_stream() or stream1
        rotation_deg = active_stream.get_rotation() if hasattr(active_stream, "get_rotation") else self.config.display.rotation
        return self.hud.draw_hud(
            canvas=canvas,
            drone_info=drone_info,
            decode_fps=active_stream.get_fps(),
            render_fps=self._render_fps,
            latency_ms=active_stream.get_latency_ms(),
            resolution=(target_w, target_h),
            aspect_mode="DUAL_SPLIT",
            stream_status=active_stream.get_status(),
            camera_name="Dual Camera Mode",
            rotation_deg=rotation_deg
        )

    def _fit_or_crop_frame(self, frame: np.ndarray, canvas: np.ndarray, target_w: int, target_h: int, mode: str) -> np.ndarray:
        """Calculates scaling to preserve native aspect ratio without stretching."""
        src_h, src_w = frame.shape[:2]
        if src_w == 0 or src_h == 0 or target_w == 0 or target_h == 0:
            return canvas

        if mode == "crop":
            scale = max(target_w / src_w, target_h / src_h)
            scaled_w = int(src_w * scale)
            scaled_h = int(src_h * scale)
            resized = cv2.resize(frame, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)

            crop_x = max(0, (scaled_w - target_w) // 2)
            crop_y = max(0, (scaled_h - target_h) // 2)
            canvas[:] = resized[crop_y:crop_y + target_h, crop_x:crop_x + target_w]
            return canvas

        # Default: 'fit' (letterbox / pillarbox)
        scale = min(target_w / src_w, target_h / src_h)
        scaled_w = max(1, int(src_w * scale))
        scaled_h = max(1, int(src_h * scale))
        resized = cv2.resize(frame, (scaled_w, scaled_h), interpolation=cv2.INTER_LINEAR)

        pad_x = (target_w - scaled_w) // 2
        pad_y = (target_h - scaled_h) // 2

        canvas[pad_y:pad_y + scaled_h, pad_x:pad_x + scaled_w] = resized
        return canvas

    # -------------------------------------------------------------------------
    # Hotkey Event Dispatcher
    # -------------------------------------------------------------------------

    def _handle_key(self, key: int) -> None:
        """Handles keyboard controls."""
        if key in (ord('q'), ord('Q'), 27):  # 'q' or ESC
            logger.info("Quit command received.")
            self._running = False

        elif key in (ord('c'), ord('C')):  # Camera Switch
            if self.camera_switcher and hasattr(self.camera_switcher, "toggle_camera"):
                new_cam = self.camera_switcher.toggle_camera()
                self.drone_state.set_active_camera(new_cam)
                logger.info(f"UDP Camera Switch triggered -> {new_cam}")
            else:
                new_cam = self.camera_manager.toggle_active_camera()
                self.drone_state.set_active_camera(new_cam)
                logger.info(f"Active camera toggled to: {new_cam}")

        elif key in (ord('r'), ord('R')):  # Cycle frame rotation: 0° -> 90° -> 180° -> 270° -> 0°
            active_stream = self.camera_manager.get_active_stream()
            current_rot = active_stream.get_rotation() if (active_stream and hasattr(active_stream, "get_rotation")) else self.config.display.rotation
            next_rot = cycle_rotation(current_rot)
            self.config.display.rotation = next_rot

            # Update all registered streams
            for _, s in self.camera_manager.get_all_streams():
                if hasattr(s, "set_rotation"):
                    s.set_rotation(next_rot)

            logger.info(f"Frame rotation set to: {next_rot}°")

        elif key in (ord('t'), ord('T')):  # Toggle telemetry panel
            vis = self.telemetry_panel.toggle()
            logger.info(f"Telemetry debug panel visibility: {vis}")

        elif key in (ord('m'), ord('M')):  # Toggle dual camera mode
            dual = self.camera_manager.toggle_dual_mode()
            logger.info(f"Dual camera mode toggled: {dual}")

        elif key in (ord('a'), ord('A')):  # Toggle aspect ratio mode
            self._aspect_mode = "crop" if self._aspect_mode == "fit" else "fit"
            logger.info(f"Aspect mode set to: {self._aspect_mode}")

        elif key in (ord('h'), ord('H')):  # Toggle HUD overlay
            self.config.hud.visible = not self.config.hud.visible
            logger.info(f"HUD visibility: {self.config.hud.visible}")

        elif key in (ord('f'), ord('F')):  # Toggle fullscreen
            self._is_fullscreen = not self._is_fullscreen
            prop = cv2.WINDOW_FULLSCREEN if self._is_fullscreen else cv2.WINDOW_NORMAL
            cv2.setWindowProperty(self._window_name, cv2.WND_PROP_FULLSCREEN, prop)
            logger.info(f"Fullscreen set to: {self._is_fullscreen}")
