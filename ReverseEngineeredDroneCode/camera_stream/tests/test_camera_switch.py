"""
Unit tests for camera switching protocol commands and state handling.
"""

import unittest
from protocol.camera_switch import UdpCameraSwitcher
from protocol.constants import (
    CMD_SWITCH_CAMERA_PRIMARY,
    CMD_SWITCH_CAMERA_SECONDARY,
)


class MockReceiver:
    def __init__(self):
        self.sent_commands = []

    def is_running(self):
        return True

    def send_command(self, payload: bytes) -> bool:
        self.sent_commands.append(payload)
        return True

    def get_latest_packet(self):
        return None


class TestCameraSwitch(unittest.TestCase):

    def test_switch_primary_and_secondary_payloads(self):
        receiver = MockReceiver()
        switcher = UdpCameraSwitcher(telemetry_receiver=receiver)

        # 1. Switch to secondary (Bottom)
        success = switcher.switch_camera("secondary")
        self.assertTrue(success)
        self.assertEqual(len(receiver.sent_commands), 1)
        self.assertEqual(receiver.sent_commands[0], CMD_SWITCH_CAMERA_SECONDARY)
        self.assertEqual(receiver.sent_commands[0], bytes([0x06, 0x02]))

        # Wait for reload thread to complete
        import time
        time.sleep(0.7)

        # 2. Switch to primary (Front)
        success2 = switcher.switch_camera("primary")
        self.assertTrue(success2)
        self.assertEqual(len(receiver.sent_commands), 2)
        self.assertEqual(receiver.sent_commands[1], CMD_SWITCH_CAMERA_PRIMARY)
        self.assertEqual(receiver.sent_commands[1], bytes([0x06, 0x01]))


if __name__ == "__main__":
    unittest.main()
