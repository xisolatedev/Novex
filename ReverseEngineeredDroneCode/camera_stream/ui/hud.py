"""
Heads-Up Display (HUD) overlay renderer.
Renders real-time camera diagnostics, drone state, and hotkey tips directly
onto the video canvas with high contrast and zero external UI dependencies.
"""

import time
from typing import Optional, Tuple
import cv2
import numpy as np
from config import HUDConfig
from drone.state import DroneInfo


class HUDOverlay:
    """
    Renders diagnostic telemetry overlays and standby cards onto OpenCV frames.
    """

    def __init__(self, config: HUDConfig):
        self.config = config

    def draw_hud(
        self,
        canvas: np.ndarray,
        drone_info: DroneInfo,
        decode_fps: float,
        render_fps: float,
        latency_ms: float,
        resolution: Tuple[int, int],
        aspect_mode: str,
        stream_status: str,
        camera_name: str,
        rotation_deg: int = 0
    ) -> np.ndarray:
        """Draws top status bar, diagnostics block, and bottom hotkey legend."""
        if not self.config.visible:
            return canvas

        h, w = canvas.shape[:2]

        # 1. Top status bar background (semi-translucent dark band)
        top_bar_height = 42
        self._draw_translucent_rect(canvas, 0, 0, w, top_bar_height, (12, 16, 22), 0.75)

        # Connection status badge
        is_conn = (stream_status == "CONNECTED" or stream_status == "CONNECTED (MOCK)")
        status_color = (0, 255, 128) if is_conn else ((0, 165, 255) if "RECONNECT" in stream_status else (60, 60, 255))
        status_text = "LIVE" if is_conn else stream_status

        # Status indicator circle
        cv2.circle(canvas, (20, top_bar_height // 2), 6, status_color, -1)
        cv2.putText(canvas, status_text, (34, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.52, status_color, 2)

        # Drone Model / Device ID
        model_str = f"MODEL: {drone_info.device_model}"
        cv2.putText(canvas, model_str, (160, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (220, 220, 220), 1)

        # Active Camera pill in center
        cam_pill = f"CAM: {camera_name.upper()} [{drone_info.camera_mode.upper()}]"
        (pill_w, _), _ = cv2.getTextSize(cam_pill, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        pill_x = max((w - pill_w) // 2, 400)
        cv2.putText(canvas, cam_pill, (pill_x, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 215, 255), 1)

        # Right side: Battery & Wi-Fi
        right_offset = w - 20
        if drone_info.signal_rssi_dbm is not None:
            wifi_str = f"RSSI: {drone_info.signal_rssi_dbm} dBm"
            (ww, _), _ = cv2.getTextSize(wifi_str, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            right_offset -= ww + 15
            cv2.putText(canvas, wifi_str, (right_offset, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 200, 210), 1)

        if drone_info.battery_percent is not None:
            bat_color = (0, 255, 128) if drone_info.battery_percent > 30 else (0, 140, 255)
            bat_str = f"BAT: {drone_info.battery_percent}% ({drone_info.battery_voltage:.2f}V)"
            (bw, _), _ = cv2.getTextSize(bat_str, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1)
            right_offset -= bw + 15
            cv2.putText(canvas, bat_str, (right_offset, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.48, bat_color, 1)

        # 2. Left Diagnostics Block
        if self.config.show_diagnostics:
            diag_y = top_bar_height + 20
            diag_w = 260
            diag_h = 125
            self._draw_translucent_rect(canvas, 12, diag_y, diag_w, diag_h, (15, 20, 28), 0.65)
            cv2.rectangle(canvas, (12, diag_y), (12 + diag_w, diag_y + diag_h), (50, 60, 75), 1)

            res_w, res_h = resolution
            cv2.putText(canvas, f"RESOLUTION: {res_w}x{res_h}", (22, diag_y + 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1)
            cv2.putText(canvas, f"STREAM FPS : {decode_fps:.1f} Hz", (22, diag_y + 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 128), 1)
            cv2.putText(canvas, f"RENDER FPS : {render_fps:.1f} Hz", (22, diag_y + 64), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1)
            cv2.putText(canvas, f"LATENCY    : {latency_ms:.1f} ms", (22, diag_y + 84), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
            cv2.putText(canvas, f"ROTATION   : {rotation_deg} DEG", (22, diag_y + 104), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 215, 255), 1)
            cv2.putText(canvas, f"ASPECT     : {aspect_mode.upper()}", (22, diag_y + 124), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (160, 180, 200), 1)

        # 3. Bottom Hotkey Help Bar
        if self.config.show_hotkey_help:
            bot_bar_height = 28
            bot_y = h - bot_bar_height
            self._draw_translucent_rect(canvas, 0, bot_y, w, bot_bar_height, (12, 16, 22), 0.75)
            
            help_text = "[C] Switch Cam | [R] Rotate | [T] Telemetry | [A] Aspect | [H] HUD | [F] Fullscreen | [Q] Exit"
            (hw, _), _ = cv2.getTextSize(help_text, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
            hx = (w - hw) // 2
            cv2.putText(canvas, help_text, (max(hx, 10), bot_y + 19), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 190, 200), 1)

        return canvas

    def draw_standby_screen(self, canvas: np.ndarray, stream_url: str, status_msg: str, camera_name: str) -> np.ndarray:
        """
        Renders an informative standby card when the camera stream is disconnected or reconnecting.
        Prevents crashes and provides real-time guidance.
        """
        h, w = canvas.shape[:2]
        canvas.fill(16)  # Dark charcoal slate

        # Outer frame grid accent
        cv2.rectangle(canvas, (40, 40), (w - 40, h - 40), (35, 42, 55), 1)

        # Center Card
        card_w = min(620, w - 80)
        card_h = min(280, h - 80)
        cx1 = (w - card_w) // 2
        cy1 = (h - card_h) // 2

        self._draw_translucent_rect(canvas, cx1, cy1, card_w, card_h, (22, 28, 38), 0.9)
        cv2.rectangle(canvas, (cx1, cy1), (cx1 + card_w, cy1 + card_h), (70, 85, 110), 1)

        # Warning Symbol / Title
        cv2.circle(canvas, (cx1 + 45, cy1 + 50), 18, (0, 165, 255), 2)
        cv2.putText(canvas, "!", (cx1 + 40, cy1 + 57), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)
        cv2.putText(canvas, "CAMERA STREAM OFFLINE", (cx1 + 75, cy1 + 56), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)

        # Status Details
        cv2.putText(canvas, f"Target Camera : {camera_name}", (cx1 + 40, cy1 + 105), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 220, 230), 1)
        cv2.putText(canvas, f"Endpoint      : {stream_url}", (cx1 + 40, cy1 + 135), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 215, 255), 1)
        cv2.putText(canvas, f"Current Status: {status_msg}", (cx1 + 40, cy1 + 165), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 165, 255), 1)

        # Instructions / Reconnect indicator
        dots = "." * (int(time.time() * 2.5) % 4)
        cv2.putText(canvas, f"Waiting for drone Wi-Fi / retrying connection{dots}", (cx1 + 40, cy1 + 205), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (160, 170, 185), 1)

        # Key action hint
        cv2.putText(canvas, "Press [M] to launch Mock Test Pattern | [C] Switch Cam | [Q] Exit", (cx1 + 40, cy1 + 245), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 128), 1)

        return canvas

    @staticmethod
    def _draw_translucent_rect(img: np.ndarray, x: int, y: int, width: int, height: int, color: Tuple[int, int, int], alpha: float) -> None:
        """Fast in-place alpha blending for HUD rectangles."""
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(img.shape[1], x + width)
        y2 = min(img.shape[0], y + height)
        if x1 >= x2 or y1 >= y2:
            return
        
        sub_region = img[y1:y2, x1:x2]
        color_rect = np.full_like(sub_region, color, dtype=np.uint8)
        cv2.addWeighted(color_rect, alpha, sub_region, 1.0 - alpha, 0, sub_region)
