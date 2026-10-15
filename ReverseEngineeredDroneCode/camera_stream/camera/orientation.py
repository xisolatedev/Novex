"""
Frame orientation, rotation, and mirror transformation utilities.
Designed to correct drone camera physical mounting angles (e.g. 90-degree sensor tilt).
"""

from typing import Optional
import cv2
import numpy as np


VALID_ROTATION_ANGLES = (0, 90, 180, 270)


def normalize_angle(angle: int) -> int:
    """Normalizes any integer angle to one of: 0, 90, 180, 270."""
    normalized = angle % 360
    # Map to nearest 90-degree multiple
    if normalized < 45 or normalized >= 315:
        return 0
    elif normalized < 135:
        return 90
    elif normalized < 225:
        return 180
    else:
        return 270


def rotate_frame(frame: np.ndarray, angle: int) -> np.ndarray:
    """
    Rotates frame clockwise by 0, 90, 180, or 270 degrees.
    Notice that 90 and 270-degree rotations will swap frame height and width.

    Args:
        frame: Source BGR/RGB numpy image array.
        angle: Rotation in degrees (0, 90, 180, 270).

    Returns:
        Rotated numpy image array.
    """
    if frame is None or frame.size == 0:
        return frame

    norm_angle = normalize_angle(angle)

    if norm_angle == 0:
        return frame
    elif norm_angle == 90:
        return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
    elif norm_angle == 180:
        return cv2.rotate(frame, cv2.ROTATE_180)
    elif norm_angle == 270:
        return cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return frame


def flip_frame(frame: np.ndarray, horizontal: bool = False, vertical: bool = False) -> np.ndarray:
    """
    Applies horizontal or vertical mirroring to frame.

    Args:
        frame: Source numpy image array.
        horizontal: If True, flips across Y axis (left-to-right).
        vertical: If True, flips across X axis (top-to-bottom).

    Returns:
        Flipped image array.
    """
    if frame is None or frame.size == 0:
        return frame

    if horizontal and vertical:
        return cv2.flip(frame, -1)
    elif horizontal:
        return cv2.flip(frame, 1)
    elif vertical:
        return cv2.flip(frame, 0)

    return frame


def cycle_rotation(current_angle: int) -> int:
    """
    Cycles rotation to the next 90-degree clockwise step:
    0° -> 90° -> 180° -> 270° -> 0°
    """
    current_norm = normalize_angle(current_angle)
    idx = VALID_ROTATION_ANGLES.index(current_norm)
    return VALID_ROTATION_ANGLES[(idx + 1) % len(VALID_ROTATION_ANGLES)]
