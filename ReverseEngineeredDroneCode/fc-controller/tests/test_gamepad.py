"""
Proportional stick input: deadzone, scaling, packet values, button edges.

No hardware needed: Gamepad.feed() takes raw 8-byte joystick events, so a real
Gamepad object is driven with synthetic events in exactly the format the kernel
emits (struct js_event: __u32 time, __s16 value, __u8 type, __u8 number).
"""

import json
import os
import struct
import tempfile
import time
import unittest

from controller.axis_math import apply_deadzone, byte_to_normalized, raw_to_normalized, stick_to_byte
from controller.flight import FlightController
from controller.gamepad import (
    JS_EVENT_AXIS,
    JS_EVENT_BUTTON,
    JS_EVENT_INIT,
    Gamepad,
    GamepadConfig,
    parse_event,
)
from controller.keyboard import map_inputs_to_axes
from controller.protocol import DEVICE_TYPE_TC
from controller.state import POWER_HALF_LEN


def axis_event(number: int, value: int, init: bool = False) -> bytes:
    return struct.pack("=IhBB", 0, value, JS_EVENT_AXIS | (JS_EVENT_INIT if init else 0), number)


def button_event(number: int, pressed: bool, init: bool = False) -> bytes:
    return struct.pack("=IhBB", 0, 1 if pressed else 0,
                       JS_EVENT_BUTTON | (JS_EVENT_INIT if init else 0), number)


def connected_pad(**kw) -> Gamepad:
    pad = Gamepad(GamepadConfig(**kw))
    pad.connected = True          # no device; events are fed directly
    return pad


class TestDeadzone(unittest.TestCase):
    def test_centre_band_is_zero(self):
        for v in (0.0, 0.05, -0.05, 0.08, -0.08):
            self.assertEqual(apply_deadzone(v, 0.08), 0.0)

    def test_just_outside_deadzone_is_small_not_a_jump(self):
        value = apply_deadzone(0.10, 0.08)
        self.assertGreater(value, 0.0)
        self.assertLess(value, 0.03)

    def test_rescales_to_full_range(self):
        self.assertAlmostEqual(apply_deadzone(1.0, 0.08), 1.0)
        self.assertAlmostEqual(apply_deadzone(-1.0, 0.08), -1.0)
        self.assertAlmostEqual(apply_deadzone(0.54, 0.08), (0.54 - 0.08) / 0.92)

    def test_zero_deadzone_is_identity(self):
        self.assertAlmostEqual(apply_deadzone(0.01, 0.0), 0.01)

    def test_clamps_out_of_range_input(self):
        self.assertAlmostEqual(apply_deadzone(1.7, 0.08), 1.0)


class TestProportionalScaling(unittest.TestCase):
    def test_centre_is_128(self):
        self.assertEqual(stick_to_byte(0.0, 127), 128)
        self.assertEqual(stick_to_byte(0.0, 40), 128)

    def test_full_deflection(self):
        self.assertEqual(stick_to_byte(1.0, 127), 255)
        self.assertEqual(stick_to_byte(-1.0, 127), 1)

    def test_proportional_midpoints(self):
        self.assertEqual(stick_to_byte(0.5, 127), 191)
        self.assertEqual(stick_to_byte(-0.5, 127), 65)
        self.assertEqual(stick_to_byte(0.25, 127), 159)

    def test_small_movement_small_value(self):
        self.assertEqual(stick_to_byte(0.02, 127), 130)
        self.assertEqual(stick_to_byte(-0.02, 127), 126)

    def test_truncates_towards_zero_like_javas_int_cast(self):
        # Java: (int)((x / r) * 127.0f) + 128
        self.assertEqual(stick_to_byte(0.999, 127), 254)
        self.assertEqual(stick_to_byte(-0.999, 127), 2)

    def test_roll_pitch_use_power_dependent_half_range(self):
        self.assertEqual(stick_to_byte(1.0, POWER_HALF_LEN[4]), 168)
        self.assertEqual(stick_to_byte(1.0, POWER_HALF_LEN[9]), 188)
        self.assertEqual(stick_to_byte(1.0, POWER_HALF_LEN[14]), 255)

    def test_raw_conversion_and_inversion(self):
        self.assertAlmostEqual(raw_to_normalized(32767), 1.0)
        self.assertAlmostEqual(raw_to_normalized(-32767), -1.0)
        self.assertAlmostEqual(raw_to_normalized(0), 0.0)
        self.assertAlmostEqual(raw_to_normalized(-32767, invert=True), 1.0)

    def test_round_trip(self):
        self.assertAlmostEqual(byte_to_normalized(stick_to_byte(0.5, 127), 127), 0.5, places=2)


class TestEventParsing(unittest.TestCase):
    def test_axis_and_button_events(self):
        self.assertEqual(parse_event(axis_event(3, -16000)), (JS_EVENT_AXIS, 3, -16000, False))
        self.assertEqual(parse_event(button_event(1, True)), (JS_EVENT_BUTTON, 1, 1, False))

    def test_init_flag_is_separated(self):
        ev_type, number, value, is_init = parse_event(axis_event(0, 100, init=True))
        self.assertEqual((ev_type, number, value), (JS_EVENT_AXIS, 0, 100))
        self.assertTrue(is_init)


class TestGamepadAxes(unittest.TestCase):
    def test_default_layout_matches_the_apps_two_rockers(self):
        pad = connected_pad()
        pad.feed(axis_event(0, 32767))     # left X  -> yaw right
        pad.feed(axis_event(1, -32767))    # left Y  -> throttle up (inverted)
        pad.feed(axis_event(3, -32767))    # right X -> roll left
        pad.feed(axis_event(4, 32767))     # right Y -> pitch back (inverted)
        ax = pad.axes()
        self.assertAlmostEqual(ax["yaw"], 1.0)
        self.assertAlmostEqual(ax["throttle"], 1.0)
        self.assertAlmostEqual(ax["roll"], -1.0)
        self.assertAlmostEqual(ax["pitch"], -1.0)

    def test_deadzone_applied_to_axes(self):
        pad = connected_pad(deadzone=0.2)
        pad.feed(axis_event(3, 3000))                  # ~9% travel, inside deadzone
        self.assertEqual(pad.axes()["roll"], 0.0)
        self.assertFalse(pad.active())
        pad.feed(axis_event(3, 32767))
        self.assertTrue(pad.active())

    def test_disconnect_returns_axes_to_neutral(self):
        pad = connected_pad()
        pad.feed(axis_event(3, 32767))
        self.assertNotEqual(pad.axes()["roll"], 0.0)
        pad._close()
        self.assertEqual(pad.axes(), {"roll": 0.0, "pitch": 0.0, "yaw": 0.0, "throttle": 0.0})
        self.assertFalse(pad.connected)

    def test_button_press_edge_fires_once_and_init_is_ignored(self):
        actions = []
        pad = Gamepad(GamepadConfig(), on_button=actions.append)
        pad.connected = True
        # The kernel's initial-state burst must never trigger an action, and a button
        # reported as already held has to be released before it can fire.
        pad.feed(button_event(0, True, init=True))
        self.assertEqual(actions, [])
        pad.feed(button_event(0, True))
        self.assertEqual(actions, [])
        pad.feed(button_event(0, False))
        pad.feed(button_event(0, True))                # first genuine press edge
        pad.feed(button_event(0, True))                # repeats while held do nothing
        self.assertEqual(actions, ["takeoff"])
        pad.feed(button_event(0, False))
        pad.feed(button_event(0, True))
        self.assertEqual(actions, ["takeoff", "takeoff"])

    def test_emergency_stop_is_not_on_a_face_button(self):
        cfg = GamepadConfig()
        self.assertNotIn(cfg.buttons["estop"], (0, 1, 2, 3))

    def test_disconnect_callback(self):
        called = []
        pad = Gamepad(GamepadConfig(), on_disconnect=lambda: called.append(True))
        pad.connected = True
        pad.feed(axis_event(0, 0, init=True))    # the kernel's initial-state burst
        pad._close()
        self.assertEqual(called, [True])

    def test_no_disconnect_noise_for_a_device_that_never_delivered_events(self):
        called = []
        pad = Gamepad(GamepadConfig(), on_disconnect=lambda: called.append(True))
        pad.connected = True
        pad._close()
        self.assertEqual(called, [])


class TestRealDevicePath(unittest.TestCase):
    """
    Exercises the actual reader thread and /dev/input-style device handling, using a
    FIFO as a stand-in joystick node (the kernel's interface is just a byte stream).
    """

    def setUp(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("no mkfifo on this platform")
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "js_fake")
        os.mkfifo(self.path)
        self.wfd = os.open(self.path, os.O_RDWR)     # keep a writer so there is no EOF
        self.pad = None

    def tearDown(self):
        if self.pad:
            self.pad.stop()
        try:
            os.close(self.wfd)
        except OSError:
            pass

    def _write(self, data: bytes):
        os.write(self.wfd, data)

    def _wait(self, cond, timeout=3.0):
        end = time.monotonic() + timeout
        while not cond():
            if time.monotonic() > end:
                self.fail("condition not reached")
            time.sleep(0.02)

    def test_reads_events_from_device_and_neutralises_on_unplug(self):
        self.pad = Gamepad(GamepadConfig(device=self.path, deadzone=0.0))
        self.pad.start()
        self._wait(lambda: self.pad.connected)

        self._write(axis_event(3, 32767) + axis_event(4, -32767) + button_event(1, True))
        self._wait(lambda: self.pad.events_seen >= 3)
        self.assertAlmostEqual(self.pad.axes()["roll"], 1.0)
        self.assertAlmostEqual(self.pad.axes()["pitch"], 1.0)
        self.assertEqual(self.pad.pressed_buttons(), [1])

        os.close(self.wfd)                            # unplug
        self._wait(lambda: not self.pad.connected)
        self.assertEqual(self.pad.axes(), {"roll": 0.0, "pitch": 0.0, "yaw": 0.0, "throttle": 0.0})

    def test_missing_device_is_not_fatal(self):
        self.pad = Gamepad(GamepadConfig(device=os.path.join(self.dir, "nope")), reconnect_interval=0.05)
        self.pad.start()
        time.sleep(0.2)
        self.assertFalse(self.pad.connected)
        self.assertEqual(self.pad.axes()["roll"], 0.0)   # keyboard-only operation continues


class TestConfigFile(unittest.TestCase):
    def test_load_and_save(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "pad.json")
        with open(path, "w") as f:
            json.dump({"deadzone": 0.15, "axes": {"roll": [2, True]}, "buttons": {"takeoff": 9}}, f)
        cfg = GamepadConfig.load(path)
        self.assertEqual(cfg.deadzone, 0.15)
        self.assertEqual(cfg.axes["roll"], (2, True))
        self.assertEqual(cfg.axes["yaw"], (0, False))      # untouched default
        self.assertEqual(cfg.buttons["takeoff"], 9)

        out = os.path.join(d, "out.json")
        cfg.save(out)
        self.assertEqual(GamepadConfig.load(out).axes["roll"], (2, True))

    def test_rejects_unknown_axis(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "bad.json")
        with open(path, "w") as f:
            json.dump({"axes": {"altitude": [1, False]}}, f)
        with self.assertRaises(ValueError):
            GamepadConfig.load(path)


class TestFlightIntegration(unittest.TestCase):
    def build(self, pad, fixed_height=True, power_half=40):
        return map_inputs_to_axes(frozenset(), power_half, fixed_height, 128,
                                  pad.axes() if pad and pad.connected else None)

    def test_half_stick_gives_half_deflection_in_the_packet(self):
        pad = connected_pad(deadzone=0.0)
        pad.feed(axis_event(4, -16384))            # right Y half forward
        axes = self.build(pad).axes
        self.assertEqual(axes.pitch, 148)          # 128 + int(0.5*40)
        self.assertEqual(axes.roll, 128)

    def test_full_range_at_power_14(self):
        pad = connected_pad(deadzone=0.0)
        pad.feed(axis_event(3, 32767))
        pad.feed(axis_event(4, -32767))
        axes = self.build(pad, power_half=POWER_HALF_LEN[14]).axes
        self.assertEqual((axes.roll, axes.pitch), (255, 255))

    def test_centred_sticks_produce_the_neutral_packet(self):
        pad = connected_pad()
        for i in (0, 1, 3, 4):
            pad.feed(axis_event(i, 0))
        fc = FlightController(sender=lambda b: True, device_type=lambda: DEVICE_TYPE_TC, gamepad=pad)
        fc.state.control_mode = True
        self.assertEqual(fc.tick().data, bytes.fromhex("03 66 80 80 80 80 00 00 99"))

    def test_gamepad_overrides_keyboard_only_outside_deadzone(self):
        pad = connected_pad(deadzone=0.1)
        fc = FlightController(sender=lambda b: True, device_type=lambda: DEVICE_TYPE_TC, gamepad=pad)
        fc.state.control_mode = True
        fc.keyboard.press("w")                               # keyboard full forward
        self.assertEqual(fc.build_current_packet().axes.pitch, 168)
        pad.feed(axis_event(4, 32767))                       # stick full back wins
        self.assertEqual(fc.build_current_packet().axes.pitch, 88)
        pad.feed(axis_event(4, 0))                           # centred again -> keyboard again
        self.assertEqual(fc.build_current_packet().axes.pitch, 168)

    def test_packet_format_is_unchanged_by_analog_input(self):
        pad = connected_pad(deadzone=0.0)
        pad.feed(axis_event(3, 12000))
        fc = FlightController(sender=lambda b: True, device_type=lambda: DEVICE_TYPE_TC, gamepad=pad)
        fc.state.control_mode = True
        pkt = fc.tick()
        self.assertEqual(len(pkt.data), 9)
        self.assertEqual(pkt.data[0:2], bytes.fromhex("03 66"))
        self.assertEqual(pkt.data[-1], 0x99)
        a = pkt.axes
        self.assertEqual(pkt.data[7], (a.roll ^ a.pitch ^ a.throttle ^ a.yaw) & 0xFF)

    def test_throttle_is_a_rate_when_fixed_height_is_off(self):
        pad = connected_pad(deadzone=0.0)
        pad.feed(axis_event(1, -32767))                      # full up
        m1 = self.build(pad, fixed_height=False)
        self.assertEqual(m1.axes.throttle, 141)              # 128 + 13
        m2 = map_inputs_to_axes(frozenset(), 40, False, m1.manual_throttle, pad.axes())
        self.assertEqual(m2.axes.throttle, 154)              # keeps integrating
        pad.feed(axis_event(1, 0))                           # released -> holds
        m3 = map_inputs_to_axes(frozenset(), 40, False, m2.manual_throttle, pad.axes())
        self.assertEqual(m3.axes.throttle, 154)

    def test_no_gamepad_means_keyboard_only(self):
        fc = FlightController(sender=lambda b: True, device_type=lambda: DEVICE_TYPE_TC)
        self.assertIsNone(fc.gamepad_axes())
        fc.state.control_mode = True
        fc.keyboard.press("d")
        self.assertEqual(fc.tick().axes.roll, 168)


if __name__ == "__main__":
    unittest.main()
