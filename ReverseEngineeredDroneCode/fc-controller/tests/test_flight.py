"""Takeoff / land / emergency stop pulses, control mode on/off, and the 20 Hz loop."""

import threading
import time
import unittest

from controller.flight import FlightController
from controller.protocol import CMD_CONTROL_OFF, DEVICE_TYPE_GL, DEVICE_TYPE_TC
from controller.state import ControllerState


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def make(device_type=DEVICE_TYPE_TC, clock=None):
    sent = []
    clock = clock or FakeClock()
    fc = FlightController(sender=lambda b: sent.append(bytes(b)) or True,
                          device_type=lambda: device_type,
                          state=ControllerState(clock), clock=clock)
    return fc, sent, clock


class TestActions(unittest.TestCase):
    def test_takeoff_pulse_lasts_1000ms(self):
        fc, _, clock = make()
        fc.state.control_mode = True
        self.assertEqual(fc.takeoff(), "TAKEOFF sent")
        clock.t += 0.99
        self.assertEqual(fc.tick().data, bytes.fromhex("03 66 80 80 80 80 01 01 99"))
        clock.t += 0.01
        self.assertEqual(fc.tick().data, bytes.fromhex("03 66 80 80 80 80 00 00 99"))

    def test_repress_does_not_extend(self):
        fc, _, clock = make()
        fc.state.control_mode = True
        fc.takeoff()
        clock.t += 0.5
        self.assertIn("already active", fc.takeoff())
        clock.t += 0.5
        self.assertFalse(fc.state.snapshot().flags.fast_fly)

    def test_land_command(self):
        fc, _, _ = make()
        fc.state.control_mode = True
        fc.land()
        self.assertEqual(fc.tick().data, bytes.fromhex("03 66 80 80 80 80 02 02 99"))

    def test_emergency_stop_command(self):
        fc, _, _ = make()
        fc.state.control_mode = True
        fc.emergency_stop()
        self.assertEqual(fc.tick().data, bytes.fromhex("03 66 80 80 80 80 04 04 99"))

    def test_emergency_stop_distinct_from_land(self):
        fc, _, _ = make()
        fc.state.control_mode = True
        fc.land()
        land = fc.tick().data
        fc2, _, _ = make()
        fc2.state.control_mode = True
        fc2.emergency_stop()
        self.assertNotEqual(land, fc2.tick().data)

    def test_gl_takeoff_and_land_share_bit(self):
        fc, _, _ = make(DEVICE_TYPE_GL)
        fc.state.control_mode = True
        fc.takeoff()
        takeoff = fc.tick().data
        fc2, _, _ = make(DEVICE_TYPE_GL)
        fc2.state.control_mode = True
        fc2.land()
        self.assertEqual(takeoff, fc2.tick().data)
        self.assertEqual(takeoff[7], 0x01)

    def test_actions_need_control_mode(self):
        fc, _, _ = make()
        self.assertIn("control mode is OFF", fc.takeoff())
        self.assertIn("control mode is OFF", fc.emergency_stop())

    def test_takeoff_land_need_fixed_height(self):
        fc, _, _ = make()
        fc.state.control_mode = True
        fc.set_fixed_height(False)
        self.assertIn("fixed-height", fc.takeoff())
        self.assertIn("fixed-height", fc.land())
        self.assertEqual(fc.emergency_stop(), "EMERGENCY STOP sent")

    def test_gl_cannot_disable_fixed_height(self):
        fc, _, _ = make(DEVICE_TYPE_GL)
        fc.set_fixed_height(False)
        self.assertTrue(fc.state.fixed_height)

    def test_keys_reach_packet(self):
        fc, _, _ = make()
        fc.state.control_mode = True
        fc.keyboard.press("w")
        fc.keyboard.press("Right")
        self.assertEqual(fc.tick().data, bytes.fromhex("03 66 80 A8 80 FF 00 57 99"))


class TestLoop(unittest.TestCase):
    def test_20hz_loop_and_control_off(self):
        sent = []
        lock = threading.Lock()

        def sender(b):
            with lock:
                sent.append((time.monotonic(), bytes(b)))
            return True

        fc = FlightController(sender=sender, device_type=lambda: DEVICE_TYPE_TC)
        fc.set_control_mode(True)
        time.sleep(0.525)
        fc.set_control_mode(False)
        with lock:
            flight = [t for t, b in sent if len(b) == 9]
            last = sent[-1][1]
        self.assertTrue(9 <= len(flight) <= 11, len(flight))
        gaps = [b - a for a, b in zip(flight, flight[1:])]
        self.assertAlmostEqual(sum(gaps) / len(gaps), 0.050, delta=0.01)
        self.assertEqual(last, CMD_CONTROL_OFF)

    def test_no_packets_when_control_off(self):
        sent = []
        fc = FlightController(sender=lambda b: sent.append(b) or True, device_type=lambda: DEVICE_TYPE_TC)
        time.sleep(0.12)
        fc.set_control_mode(False)   # never enabled: no 08 01 either (timer was null)
        self.assertEqual(sent, [])

    def test_dropped_when_link_down(self):
        fc = FlightController(sender=lambda b: False, device_type=lambda: DEVICE_TYPE_TC)
        fc.state.control_mode = True
        fc.tick()
        self.assertEqual((fc.stats.sent, fc.stats.dropped), (0, 1))


if __name__ == "__main__":
    unittest.main()
