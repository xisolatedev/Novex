"""
Unit test for thread-safe pipeline reloading without segfaults.
"""

import time
import unittest
from camera.stream import RtspCameraStream
from mock.stream import MockCameraStream


class TestThreadSafeReload(unittest.TestCase):

    def test_mock_reload(self):
        stream = MockCameraStream(width=320, height=240)
        stream.connect()
        time.sleep(0.05)
        # Calling pause_and_reload concurrently must not raise exceptions or crash
        stream.pause_and_reload(delay_sec=0.01)
        time.sleep(0.05)
        ret, frame, _ = stream.read_frame()
        self.assertTrue(ret)
        stream.disconnect()

    def test_rtsp_pause_and_reload_flags(self):
        # Verify pause_and_reload sets reload flags without touching _cap on caller thread
        stream = RtspCameraStream("TestStream", "rtsp://127.0.0.1:9999/dummy")
        stream.pause_and_reload(delay_sec=0.5)
        self.assertTrue(stream._reload_event.is_set())
        self.assertEqual(stream._reload_delay, 0.5)
        self.assertIsNone(stream._cap)  # Never touched


if __name__ == "__main__":
    unittest.main()
