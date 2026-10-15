import unittest

from video.switch import CameraSwitcher


class FakeStream:
    def __init__(self):
        self.reloads = []

    def pause_and_reload(self, delay_sec=0.0):
        self.reloads.append(delay_sec)


def make(reset):
    sent = []
    stream = FakeStream()
    sw = CameraSwitcher(send=lambda name, b: sent.append(b) or True, reset_mode=lambda: reset, stream=stream)
    return sw, sent, stream


class TestCameraSwitch(unittest.TestCase):
    def test_toggles_between_06_02_and_06_01(self):
        sw, sent, _ = make(0)
        sw.switch()
        sw.switch()
        sw.switch()
        self.assertEqual(sent, [b"\x06\x02", b"\x06\x01", b"\x06\x02"])

    def test_reset_mode_2_reloads_after_600ms(self):
        sw, _, stream = make(2)
        sw.switch()
        self.assertEqual(stream.reloads, [0.6])
        self.assertTrue(sw.is_switching)

    def test_reset_mode_1_reloads_immediately(self):
        sw, _, stream = make(1)
        sw.switch()
        self.assertEqual(stream.reloads, [0.0])

    def test_other_reset_mode_no_reload(self):
        sw, _, stream = make(0)
        sw.switch()
        self.assertEqual(stream.reloads, [])
        self.assertFalse(sw.is_switching)

    def test_blocked_while_switching_until_prepared(self):
        sw, sent, _ = make(2)
        sw.switch()
        self.assertIn("in progress", sw.switch())
        self.assertEqual(len(sent), 1)
        self.assertTrue(sw.on_video_prepared())
        self.assertFalse(sw.on_video_prepared())
        sw.switch()
        self.assertEqual(sent, [b"\x06\x02", b"\x06\x01"])

    def test_describe(self):
        sw, _, _ = make(0)
        self.assertIn("power-on", sw.describe())
        sw.switch()
        self.assertIn("06 02", sw.describe())


class TestRotation(unittest.TestCase):
    def setUp(self):
        try:
            from video.stream import source_rotation
        except ImportError as e:   # OpenCV missing
            self.skipTest(str(e))
        self.rot = source_rotation

    def test_rotation_rule(self):
        self.assertEqual(self.rot(240, 320, 27), 90)
        self.assertEqual(self.rot(240, 320, 94), 0)      # isNoRotate
        self.assertEqual(self.rot(1280, 720, 27), 0)
        self.assertEqual(self.rot(1280, 720, 27, turn_180=True), 180)
        self.assertEqual(self.rot(160, 272, None, turn_180=True), 270)


if __name__ == "__main__":
    unittest.main()
