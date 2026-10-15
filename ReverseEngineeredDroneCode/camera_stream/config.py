"""
Configuration module for the Drone Camera Viewer.
Provides comprehensive, strongly-typed settings with default values
extracted directly from reverse-engineered specifications.
"""

from dataclasses import dataclass, field
import json
import os
from typing import Optional, Tuple


@dataclass
class StreamConfig:
    """RTSP and network stream parameters."""
    # Default RTSP endpoint reverse-engineered from com.cooingdv.rcufo.socket.Config.PREVIEW_ADDRESS
    primary_url: str = "rtsp://192.168.1.1:7070/webcam"
    
    # Secondary URL note: Physical drone does not support /webcam_bottom (returns 461).
    # Camera switching is multiplexed on /webcam via UDP commands to port 7099.
    secondary_url: Optional[str] = None
    
    # Transport protocol: 'udp' (lower latency, standard for drone) or 'tcp' (interleaved)
    rtsp_transport: str = "udp"
    
    # Internal frame buffer size. Keep at 1 for lowest live piloting latency
    buffer_size: int = 1
    
    # Reconnection parameters
    reconnect_interval_sec: float = 2.0
    open_timeout_ms: int = 3000
    read_timeout_ms: int = 3000
    max_reconnect_attempts: int = -1  # -1 for indefinite reconnection


@dataclass
class DisplayConfig:
    """Window, canvas, and rendering layout settings."""
    window_title: str = "Drone Camera Viewer (CooingDV Protocol)"
    window_width: int = 1280
    window_height: int = 720
    resizable: bool = True
    fullscreen: bool = False
    
    # Physical sensor orientation correction in degrees (0, 90, 180, 270)
    # Default 90 degrees based on decompiled MjpegThread.java (AppUtils.rotateBitmap(90, bitmap))
    rotation: int = 90
    flip_horizontal: bool = False
    flip_vertical: bool = False

    # Aspect Ratio behavior:
    # 'fit'  : Scales while maintaining native aspect ratio, adds letterbox/pillarbox bars.
    # 'crop' : Scales to fill the entire window, center-cropping excess frame boundaries.
    aspect_mode: str = "fit"
    
    # Target frame presentation rate
    target_fps: int = 30
    
    # Background color for letterbox padding (B, G, R)
    background_color: Tuple[int, int, int] = (15, 18, 22)


@dataclass
class DualCameraConfig:
    """Settings for simultaneous multi-camera display (e.g. simulation or dual receiver)."""
    enabled: bool = False
    layout: str = "side_by_side"
    active_camera: str = "primary"


@dataclass
class TelemetryConfig:
    """UDP telemetry and command channel settings (Port 7099)."""
    drone_ip: str = "192.168.1.1"
    udp_port: int = 7099
    heartbeat_interval_sec: float = 1.0
    enable_receiver: bool = True
    auto_ack_remote_buttons: bool = True
    
    # Recording / Logging options
    enable_logging: bool = False
    log_filepath: Optional[str] = None
    log_format: str = "csv"  # "csv" or "jsonl"
    
    # UI Overlay
    show_telemetry_panel: bool = False


@dataclass
class HUDConfig:
    """Heads-Up Display overlay configuration."""
    visible: bool = True
    show_diagnostics: bool = True
    show_telemetry: bool = True
    show_hotkey_help: bool = True
    
    # Colors (B, G, R)
    primary_color: Tuple[int, int, int] = (0, 255, 128)      # Mint green
    accent_color: Tuple[int, int, int] = (0, 215, 255)       # Amber / Yellow
    alert_color: Tuple[int, int, int] = (50, 50, 255)        # Red
    overlay_bg: Tuple[int, int, int] = (10, 14, 20)          # Translucent dark
    font_scale: float = 0.55
    font_thickness: int = 1


@dataclass
class MockConfig:
    """Configuration for synthetic / simulation mode when offline."""
    enabled: bool = False
    mock_fps: float = 20.0
    primary_resolution: Tuple[int, int] = (1280, 720)
    secondary_resolution: Tuple[int, int] = (640, 480)
    simulated_device_id: int = 90       # Optical Flow GL Drone (0x5A)
    simulated_wifi_ssid: str = "WIFIPD_4K_FLOW_8830"


@dataclass
class AppConfig:
    """Master application configuration container."""
    stream: StreamConfig = field(default_factory=StreamConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    dual_camera: DualCameraConfig = field(default_factory=DualCameraConfig)
    telemetry: TelemetryConfig = field(default_factory=TelemetryConfig)
    hud: HUDConfig = field(default_factory=HUDConfig)
    mock: MockConfig = field(default_factory=MockConfig)

    def save_to_file(self, filepath: str) -> None:
        """Serializes current configuration to a JSON file."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self._to_dict(), f, indent=4)

    @classmethod
    def load_from_file(cls, filepath: str) -> "AppConfig":
        """Loads configuration from JSON file, falling back to defaults for missing keys."""
        if not os.path.exists(filepath):
            return cls()
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls._from_dict(data)

    def _to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)

    @classmethod
    def _from_dict(cls, d: dict) -> "AppConfig":
        config = cls()
        if "stream" in d:
            for k, v in d["stream"].items():
                if hasattr(config.stream, k):
                    setattr(config.stream, k, v)
        if "display" in d:
            for k, v in d["display"].items():
                if hasattr(config.display, k):
                    setattr(config.display, k, v if not isinstance(v, list) else tuple(v))
        if "dual_camera" in d:
            for k, v in d["dual_camera"].items():
                if hasattr(config.dual_camera, k):
                    setattr(config.dual_camera, k, v)
        if "telemetry" in d:
            for k, v in d["telemetry"].items():
                if hasattr(config.telemetry, k):
                    setattr(config.telemetry, k, v)
        if "hud" in d:
            for k, v in d["hud"].items():
                if hasattr(config.hud, k):
                    setattr(config.hud, k, v if not isinstance(v, list) else tuple(v))
        if "mock" in d:
            for k, v in d["mock"].items():
                if hasattr(config.mock, k):
                    setattr(config.mock, k, v if not isinstance(v, list) else tuple(v))
        return config
