"""
Puts the existing ../camera_stream package on sys.path so fc-controller can reuse
its RTSP reader, telemetry parser, UDP receiver and protocol constants unchanged.

camera_stream imports its own modules absolutely (``from protocol.constants import ...``),
so its root must be importable as-is. fc-controller therefore avoids the package names
camera_stream already uses (camera, telemetry, ui, protocol, drone, mock, config).

Override the location with the FC_CAMERA_STREAM_DIR environment variable.
"""

import os
import sys

FC_ROOT = os.path.dirname(os.path.abspath(__file__))
CAMERA_STREAM_DIR = os.environ.get(
    "FC_CAMERA_STREAM_DIR",
    os.path.join(os.path.dirname(FC_ROOT), "camera_stream"),
)


def install() -> None:
    if FC_ROOT not in sys.path:
        sys.path.insert(0, FC_ROOT)
    if not os.path.isdir(CAMERA_STREAM_DIR):
        raise ImportError(f"camera_stream package not found at {CAMERA_STREAM_DIR} (set FC_CAMERA_STREAM_DIR)")
    if CAMERA_STREAM_DIR not in sys.path:
        # After FC_ROOT so fc-controller's own modules win any name clash.
        sys.path.insert(1, CAMERA_STREAM_DIR)


install()
