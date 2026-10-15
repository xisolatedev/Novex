"""
Camera manager orchestrating single and dual camera pipelines.
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
from .stream import CameraStream

logger = logging.getLogger(__name__)


class CameraManager:
    """
    Manages one or more CameraStream instances.
    Provides uniform interfaces for Single Camera Mode (Mode A) and Dual Camera Mode (Mode B).
    """

    def __init__(self):
        self._streams: Dict[str, CameraStream] = {}
        self._active_camera_id: str = "primary"
        self._dual_mode: bool = False

    def register_stream(self, camera_id: str, stream: CameraStream) -> None:
        """Registers a camera stream instance."""
        self._streams[camera_id] = stream
        logger.info(f"Registered camera stream: {camera_id} ({stream.get_name()})")

    def unregister_stream(self, camera_id: str) -> None:
        """Stops and removes a registered camera stream."""
        if camera_id in self._streams:
            self._streams[camera_id].disconnect()
            del self._streams[camera_id]

    def start_all(self) -> None:
        """Connects all registered camera streams."""
        for cam_id, stream in self._streams.items():
            stream.connect()

    def stop_all(self) -> None:
        """Disconnects all camera streams."""
        for cam_id, stream in self._streams.items():
            stream.disconnect()

    def set_active_camera(self, camera_id: str) -> bool:
        """Switches active camera for Single Camera Mode."""
        if camera_id in self._streams:
            self._active_camera_id = camera_id
            logger.info(f"Switched active camera to: {camera_id}")
            return True
        logger.warning(f"Cannot switch to unregistered camera: {camera_id}")
        return False

    def toggle_active_camera(self) -> str:
        """Toggles active camera between primary and secondary."""
        keys = list(self._streams.keys())
        if len(keys) <= 1:
            return self._active_camera_id
        
        try:
            curr_idx = keys.index(self._active_camera_id)
            next_idx = (curr_idx + 1) % len(keys)
            self._active_camera_id = keys[next_idx]
        except ValueError:
            self._active_camera_id = keys[0]
            
        logger.info(f"Toggled active camera to: {self._active_camera_id}")
        return self._active_camera_id

    def is_dual_mode(self) -> bool:
        return self._dual_mode and len(self._streams) > 1

    def set_dual_mode(self, enabled: bool) -> None:
        self._dual_mode = enabled
        logger.info(f"Dual camera display mode set to: {enabled}")

    def toggle_dual_mode(self) -> bool:
        self.set_dual_mode(not self._dual_mode)
        return self._dual_mode

    def get_active_camera_id(self) -> str:
        return self._active_camera_id

    def get_active_stream(self) -> Optional[CameraStream]:
        return self._streams.get(self._active_camera_id)

    def get_stream(self, camera_id: str) -> Optional[CameraStream]:
        return self._streams.get(camera_id)

    def get_all_streams(self) -> List[Tuple[str, CameraStream]]:
        return list(self._streams.items())

    def read_active_frame(self) -> Tuple[bool, Optional[np.ndarray], float]:
        """Reads frame from currently selected active camera."""
        stream = self.get_active_stream()
        if stream:
            return stream.read_frame()
        return False, None, 0.0

    def read_all_frames(self) -> Dict[str, Tuple[bool, Optional[np.ndarray], float]]:
        """Reads latest frame from every registered camera."""
        results = {}
        for cam_id, stream in self._streams.items():
            results[cam_id] = stream.read_frame()
        return results
