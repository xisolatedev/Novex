"""
Unit tests for 20-byte UDP telemetry packet parsing and model behavior.
"""

import unittest
from telemetry.parser import (
    parse_telemetry_packet,
    is_gl_device,
    is_no_rotate_device
)
from protocol.constants import (
    REMOTE_TRIGGER_PHOTO,
    REMOTE_TRIGGER_VIDEO,
    CAMERA_RESET_MODE_DELAYED_600MS,
    CAMERA_RESET_MODE_IMMEDIATE,
)


class TestTelemetry(unittest.TestCase):

    def test_device_classification(self):
        # GL Devices: 90..101, 103, 82, 85, 88
        self.assertTrue(is_gl_device(90))
        self.assertTrue(is_gl_device(95))
        self.assertTrue(is_gl_device(101))
        self.assertTrue(is_gl_device(85))
        self.assertFalse(is_gl_device(50))
        self.assertFalse(is_gl_device(12))

        # No-Rotate Devices: 94 and 99
        self.assertTrue(is_no_rotate_device(94))
        self.assertTrue(is_no_rotate_device(99))
        self.assertFalse(is_no_rotate_device(90))
        self.assertFalse(is_no_rotate_device(85))

    def test_standard_telemetry_packet(self):
        # Construct synthetic 20-byte packet for standard device
        # Byte 0: Device ID 40 (Standard)
        # Byte 1: Reset mode 2 (Delayed 600ms)
        # Byte 2: Photo Shutter 0x4D
        # Byte 3: Photo seq 7
        # Byte 4: Video seq 0
        raw = bytearray([40, 2, 0x4D, 7, 0] + [0] * 15)
        pkt = parse_telemetry_packet(bytes(raw), source_ip="192.168.1.1")

        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.device_id, 40)
        self.assertFalse(pkt.is_gl_model)
        self.assertTrue(pkt.requires_rotation)
        self.assertEqual(pkt.camera_reset_mode, CAMERA_RESET_MODE_DELAYED_600MS)
        self.assertEqual(pkt.remote_trigger_raw, REMOTE_TRIGGER_PHOTO)
        self.assertEqual(pkt.remote_trigger_name, "Photo Shutter")
        self.assertEqual(pkt.photo_sequence, 7)
        self.assertFalse(pkt.imu_transmitted_by_drone)

    def test_gl_telemetry_packet(self):
        # Byte 0: 95 (GL Optical Flow)
        # Byte 1: 1 (Immediate reload)
        # Byte 2: 0x58 (Video Shutter)
        # Byte 4: Video seq 12
        raw = bytearray([95, 1, 0x58, 0, 12] + [0] * 15)
        pkt = parse_telemetry_packet(bytes(raw), source_ip="192.168.1.1")

        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.device_id, 95)
        self.assertTrue(pkt.is_gl_model)
        self.assertEqual(pkt.camera_reset_mode, CAMERA_RESET_MODE_IMMEDIATE)
        self.assertEqual(pkt.remote_trigger_raw, REMOTE_TRIGGER_VIDEO)
        self.assertEqual(pkt.remote_trigger_name, "Video Record")
        self.assertEqual(pkt.video_sequence, 12)

    def test_unknown_bytes_isolation(self):
        # Verify unparsed bytes are recorded in unknown_bytes dictionary
        raw = bytearray(20)
        raw[0] = 50
        raw[1] = 2
        raw[19] = 0xAB  # Mystery byte at end
        pkt = parse_telemetry_packet(bytes(raw))

        self.assertIn(19, pkt.unknown_bytes)
        self.assertEqual(pkt.unknown_bytes[19], "AB")


if __name__ == "__main__":
    unittest.main()
