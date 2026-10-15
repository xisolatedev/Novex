"""
Interactive telemetry debug overlay panel.
Renders raw hex packets, decoded verified fields, and unknown byte indicators
directly onto the video frame canvas.
"""

import time
from typing import Tuple
import cv2
import numpy as np
from drone.state import DroneInfo


class TelemetryPanel:
    """
    Renders an on-screen semi-transparent debug panel displaying
    real-time 20-byte UDP datagrams and field breakdowns.
    """

    def __init__(self, visible: bool = False):
        self.visible = visible

    def toggle(self) -> bool:
        self.visible = not self.visible
        return self.visible

    def draw(self, canvas: np.ndarray, info: DroneInfo) -> np.ndarray:
        """Draws the telemetry inspector panel onto the provided canvas."""
        if not self.visible:
            return canvas

        h, w = canvas.shape[:2]
        panel_w = min(420, w - 20)
        panel_h = min(360, h - 80)
        x = w - panel_w - 15
        y = 55

        # 1. Background box with border
        self._draw_translucent_rect(canvas, x, y, panel_w, panel_h, (12, 16, 24), 0.85)
        cv2.rectangle(canvas, (x, y), (x + panel_w, y + panel_h), (65, 80, 105), 1)

        # 2. Panel Title
        cv2.rectangle(canvas, (x, y), (x + panel_w, y + 28), (24, 32, 45), -1)
        cv2.putText(canvas, "TELEMETRY INSPECTOR (UDP 7099)", (x + 12, y + 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 215, 255), 1)

        # Close hint
        cv2.putText(canvas, "[T] CLOSE", (x + panel_w - 75, y + 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160, 175, 190), 1)

        curr_y = y + 48
        line_spacing = 20

        # 3. Connection & Packet Rate
        has_packets = bool(info.raw_hex)
        time_since_last = time.time() - info.last_update_time if has_packets else 999.0

        if has_packets and time_since_last < 3.0:
            rate_str = f"RATE: {info.packet_rate_hz:.1f} Hz | AGE: {time_since_last * 1000.0:.0f} ms"
            rate_color = (0, 255, 128)
        else:
            rate_str = "STATUS: NO TELEMETRY RECEIVED (7099)"
            rate_color = (0, 140, 255)

        cv2.putText(canvas, rate_str, (x + 12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.42, rate_color, 1)
        curr_y += line_spacing

        # 4. Raw Datagram Hex
        cv2.putText(canvas, "RAW HEX (20 BYTES):", (x + 12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 190, 200), 1)
        curr_y += 18

        hex_text = info.raw_hex if info.raw_hex else "WAITING FOR UDP HEARTBEAT / RESPONSE..."
        # Split hex into 2 lines if long
        if len(hex_text) > 30:
            first_line = hex_text[:30]
            second_line = hex_text[30:]
            cv2.putText(canvas, first_line, (x + 16, curr_y), cv2.FONT_HERSHEY_MONO_COMPLEX if hasattr(cv2, "FONT_HERSHEY_MONO_COMPLEX") else cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 200), 1)
            curr_y += 16
            cv2.putText(canvas, second_line, (x + 16, curr_y), cv2.FONT_HERSHEY_MONO_COMPLEX if hasattr(cv2, "FONT_HERSHEY_MONO_COMPLEX") else cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 200), 1)
        else:
            cv2.putText(canvas, hex_text, (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 200), 1)
        curr_y += line_spacing

        # 5. Verified Fields
        cv2.putText(canvas, "DECODED FIELDS [VERIFIED]:", (x + 12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (255, 215, 0), 1)
        curr_y += 18

        # Device ID
        dev_str = f"B0 Hardware ID : {info.device_id} (0x{info.device_id:02X}) {'[GL]' if info.optical_flow_enabled else ''}"
        cv2.putText(canvas, dev_str, (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1)
        curr_y += 16

        # Reset Mode
        reset_desc = "Mode 2 (600ms delay)" if info.camera_reset_mode == 2 else ("Mode 1 (Immediate)" if info.camera_reset_mode == 1 else f"0x{info.camera_reset_mode:02X}")
        reset_str = f"B1 Cam Reset   : {reset_desc}"
        cv2.putText(canvas, reset_str, (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1)
        curr_y += 16

        # Remote Trigger
        trig_str = f"B2 Trigger     : 0x{info.remote_trigger_raw:02X} ({info.remote_trigger_name})"
        cv2.putText(canvas, trig_str, (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1)
        curr_y += 16

        # Counters
        cnt_str = f"B3-4 Counters  : Photo #{info.photo_sequence or 0} | Video #{info.video_sequence or 0}"
        cv2.putText(canvas, cnt_str, (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (220, 220, 220), 1)
        curr_y += 16

        if info.wifi_password:
            pwd_str = f"Wi-Fi Password : {info.wifi_password}"
            cv2.putText(canvas, pwd_str, (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 255, 128), 1)
            curr_y += 16

        # 6. IMU Reality Notice
        curr_y += 4
        cv2.putText(canvas, "IMU / GYRO REALITY:", (x + 12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (140, 160, 255), 1)
        curr_y += 16
        cv2.putText(canvas, "NOT SENT BY DRONE (VERIFIED)", (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (100, 140, 255), 1)
        curr_y += 14
        cv2.putText(canvas, "Phone's internal accelerometer used", (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (140, 150, 170), 1)
        curr_y += 18

        # 7. Unparsed Bytes
        if info.unknown_bytes:
            cv2.putText(canvas, "UNPARSED BYTES [RAW]:", (x + 12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1)
            curr_y += 16
            items = [f"B{k}:{v}" for k, v in sorted(info.unknown_bytes.items())]
            unparsed_txt = " ".join(items[:8])
            cv2.putText(canvas, unparsed_txt, (x + 16, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.36, (180, 190, 200), 1)

        return canvas

    @staticmethod
    def _draw_translucent_rect(img: np.ndarray, x: int, y: int, width: int, height: int, color: Tuple[int, int, int], alpha: float) -> None:
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(img.shape[1], x + width)
        y2 = min(img.shape[0], y + height)
        if x1 >= x2 or y1 >= y2:
            return
        sub = img[y1:y2, x1:x2]
        c_rect = np.full_like(sub, color, dtype=np.uint8)
        cv2.addWeighted(c_rect, alpha, sub, 1.0 - alpha, 0, sub)
