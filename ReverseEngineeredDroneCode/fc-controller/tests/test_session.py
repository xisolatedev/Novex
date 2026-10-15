"""
Regression tests for the failure seen on 2026-09-20: video loss closed the UDP link
mid-flight, so the drone received neither control packets nor heartbeat.
See DEBUG_REPORT.md, definite bug 1.
"""

import unittest

from controller.flight import FlightController
from controller.protocol import DEVICE_TYPE_TC
from session import ConnectionState, DroneSession, derive_connection_state
from video.switch import CameraSwitcher


class FakeLink:
    def __init__(self):
        self.running = False
        self.stops = 0
        self.starts = 0
        self.device_type = DEVICE_TYPE_TC
        self.first_device_id = 27
        self.switch_camera_reset = 0
        self.last_rx_time = 0.0
        self.rx_count = 0
        self._listeners = []

    def start(self):
        self.running = True
        self.starts += 1
        return True

    def stop(self):
        self.running = False
        self.stops += 1

    def send(self, payload):
        return self.running

    def send_logged(self, name, payload):
        return self.send(payload)

    def add_packet_listener(self, fn):
        self._listeners.append(fn)

    def effective_device_type(self):
        return self.device_type

    def telemetry_alive(self, now=None):
        return self.running


class FakeVideo:
    def __init__(self):
        self.live = True
        self.device_id = None
        self.turn_180 = False
        self.url = "rtsp://test/webcam"

    def start(self):
        pass

    def stop(self):
        pass

    def has_live_frames(self, max_age_s=None):
        return self.live

    def frame_age(self):
        return 0.0 if self.live else 9.9

    def status(self):
        return "CONNECTED" if self.live else "RECONNECTING"

    def fps(self):
        return 30.0

    def pause_and_reload(self, delay_sec=0.0):
        pass


def make(policy="keepalive"):
    link, video = FakeLink(), FakeVideo()
    flight = FlightController(sender=link.send, device_type=link.effective_device_type)
    switcher = CameraSwitcher(send=link.send_logged, reset_mode=lambda: 0, stream=video)
    session = DroneSession(video, link, flight, switcher, link_policy=policy)
    return session, link, video, flight


class TestVideoLossPolicy(unittest.TestCase):
    def test_keepalive_does_not_close_link_during_control_mode(self):
        session, link, video, flight = make("keepalive")
        link.start()
        flight.state.control_mode = True
        video.live = False
        session._video_live = True
        session._on_video_error()
        self.assertTrue(link.running, "link was closed mid-flight")
        self.assertEqual(link.stops, 0)
        self.assertTrue(flight.tick().data, "packets must still be sendable")
        self.assertEqual(flight.stats.dropped, 0)

    def test_keepalive_still_follows_app_when_control_mode_is_off(self):
        session, link, video, flight = make("keepalive")
        link.start()
        flight.state.control_mode = False
        session._on_video_error()
        self.assertFalse(link.running)
        self.assertEqual(link.stops, 1)

    def test_app_policy_reproduces_original_teardown(self):
        session, link, video, flight = make("app")
        link.start()
        flight.state.control_mode = True
        session._on_video_error()
        self.assertFalse(link.running)
        self.assertEqual(flight.tick().data and flight.stats.dropped, 1)

    def test_switching_camera_never_tears_down_link(self):
        session, link, video, flight = make("app")
        link.start()
        session.switcher.is_switching = True
        session._on_video_error()
        self.assertTrue(link.running)

    def test_video_staleness_threshold_matches_android_readtimeout(self):
        from video.stream import DroneVideo
        self.assertEqual(DroneVideo.VIDEO_STALE_S, 5.0)   # SocketClient readtimeout = 5_000_000 us


class TestConnectionState(unittest.TestCase):
    def test_states(self):
        self.assertEqual(derive_connection_state(True, True, True), ConnectionState.CONNECTED)
        self.assertEqual(derive_connection_state(True, False, True), ConnectionState.TELEMETRY_CONNECTED)


if __name__ == "__main__":
    unittest.main()
