"""
Packet construction vs FlyController.FlyControlTask.run().
Expected bytes are written out by hand from the Java XOR formulas, not produced by the builder.
Power level 4 (app default) -> right-stick half range 40: 128 +/- 40 = 0xA8 / 0x58.
"""

import unittest

from controller.keyboard import map_keys_to_axes
from controller.protocol import (
    CMD_CONTROL_OFF,
    CMD_HEARTBEAT,
    DEVICE_TYPE_GL,
    DEVICE_TYPE_TC,
    DEVICE_TYPE_UNKNOWN,
    Axes,
    FlightFlags,
    build_flight_packet,
    decode_flight_packet,
)


def tc(keys, power_half=40, fixed=True, flags=FlightFlags(fixed_height=True)):
    axes = map_keys_to_axes(frozenset(keys), power_half, fixed).axes
    return build_flight_packet(DEVICE_TYPE_TC, axes, flags).data


def gl(keys, flags=FlightFlags(fixed_height=True)):
    axes = map_keys_to_axes(frozenset(keys), 40, True).axes
    return build_flight_packet(DEVICE_TYPE_GL, axes, flags).data


H = bytes.fromhex


class TestTcPackets(unittest.TestCase):
    def test_neutral(self):
        self.assertEqual(tc([]), H("03 66 80 80 80 80 00 00 99"))

    def test_length_header_terminator(self):
        pkt = tc([])
        self.assertEqual(len(pkt), 9)
        self.assertEqual(pkt[:2], H("03 66"))
        self.assertEqual(pkt[-1], 0x99)

    def test_w_forward(self):
        self.assertEqual(tc(["w"]), H("03 66 80 A8 80 80 00 28 99"))

    def test_s_backward(self):
        self.assertEqual(tc(["s"]), H("03 66 80 58 80 80 00 D8 99"))

    def test_a_left(self):
        self.assertEqual(tc(["a"]), H("03 66 58 80 80 80 00 D8 99"))

    def test_d_right(self):
        self.assertEqual(tc(["d"]), H("03 66 A8 80 80 80 00 28 99"))

    def test_yaw_left(self):
        self.assertEqual(tc(["Left"]), H("03 66 80 80 80 01 00 81 99"))

    def test_yaw_right(self):
        self.assertEqual(tc(["Right"]), H("03 66 80 80 80 FF 00 7F 99"))

    def test_ascend(self):
        self.assertEqual(tc(["Up"]), H("03 66 80 80 FF 80 00 7F 99"))

    def test_descend_throttle_1_becomes_0(self):
        # FlyControlTask: if (controlAccelerator == 1) controlAccelerator = 0;
        self.assertEqual(tc(["Down"]), H("03 66 80 80 00 80 00 80 99"))

    def test_simultaneous_w_d(self):
        self.assertEqual(tc(["w", "d"]), H("03 66 A8 A8 80 80 00 00 99"))

    def test_simultaneous_w_left(self):
        self.assertEqual(tc(["w", "Left"]), H("03 66 80 A8 80 01 00 A9 99"))

    def test_simultaneous_s_a(self):
        self.assertEqual(tc(["s", "a"]), H("03 66 58 58 80 80 00 00 99"))

    def test_simultaneous_up_right(self):
        self.assertEqual(tc(["Up", "Right"]), H("03 66 80 80 FF FF 00 00 99"))

    def test_opposite_keys_cancel(self):
        self.assertEqual(tc(["w", "s", "a", "d"]), tc([]))

    def test_power_14_full_range(self):
        self.assertEqual(tc(["w"], power_half=127), H("03 66 80 FF 80 80 00 7F 99"))

    def test_takeoff_flag(self):
        self.assertEqual(tc([], flags=FlightFlags(fast_fly=True, fixed_height=True)), H("03 66 80 80 80 80 01 01 99"))

    def test_land_flag(self):
        self.assertEqual(tc([], flags=FlightFlags(fast_drop=True, fixed_height=True)), H("03 66 80 80 80 80 02 02 99"))

    def test_emergency_stop_flag(self):
        self.assertEqual(tc([], flags=FlightFlags(emergency_stop=True, fixed_height=True)),
                         H("03 66 80 80 80 80 04 04 99"))

    def test_gyro_and_headless_bits(self):
        self.assertEqual(tc([], flags=FlightFlags(gyro_correction=True, no_head=True)),
                         H("03 66 80 80 80 80 90 90 99"))

    def test_fixed_height_not_encoded_in_tc(self):
        self.assertEqual(tc([], flags=FlightFlags(fixed_height=False)), tc([], flags=FlightFlags(fixed_height=True)))


class TestGlPackets(unittest.TestCase):
    PAD = "00 " * 10

    def test_neutral(self):
        self.assertEqual(gl([]), H("03 66 14 80 80 80 80 00 02 " + self.PAD + "02 99"))

    def test_length(self):
        self.assertEqual(len(gl([])), 21)

    def test_forward(self):
        self.assertEqual(gl(["w"]), H("03 66 14 80 A8 80 80 00 02 " + self.PAD + "2A 99"))

    def test_takeoff(self):
        self.assertEqual(gl([], FlightFlags(fast_fly=True, fixed_height=True)),
                         H("03 66 14 80 80 80 80 01 02 " + self.PAD + "03 99"))

    def test_land_uses_same_bit_as_takeoff(self):
        # i2 = (isFastFly || isFastDrop) ? 1 : 0
        self.assertEqual(gl([], FlightFlags(fast_drop=True, fixed_height=True)),
                         gl([], FlightFlags(fast_fly=True, fixed_height=True)))

    def test_emergency_stop(self):
        self.assertEqual(gl([], FlightFlags(emergency_stop=True, fixed_height=True)),
                         H("03 66 14 80 80 80 80 02 02 " + self.PAD + "00 99"))

    def test_unknown_device_type_uses_21_byte_format(self):
        # mDeviceType starts at 0 and the source tests "!= 10".
        pkt = build_flight_packet(DEVICE_TYPE_UNKNOWN, Axes(), FlightFlags())
        self.assertEqual(len(pkt.data), 21)


class TestChecksumAndDecode(unittest.TestCase):
    def test_decode_roundtrip_tc(self):
        d = decode_flight_packet(H("03 66 80 A8 80 01 00 A9 99"))
        self.assertEqual((d["roll"], d["pitch"], d["throttle"], d["yaw"]), (128, 168, 128, 1))
        self.assertTrue(d["checksum_ok"])

    def test_decode_detects_bad_checksum(self):
        self.assertFalse(decode_flight_packet(H("03 66 80 A8 80 01 00 00 99"))["checksum_ok"])

    def test_gl_checksum_excludes_length_byte(self):
        pkt = build_flight_packet(DEVICE_TYPE_GL, Axes(roll=10, pitch=20, throttle=30, yaw=40), FlightFlags())
        self.assertEqual(pkt.checksum, 10 ^ 20 ^ 30 ^ 40)
        self.assertTrue(decode_flight_packet(pkt.data)["checksum_ok"])

    def test_clamping(self):
        pkt = build_flight_packet(DEVICE_TYPE_TC, Axes(roll=400, pitch=-5, throttle=1, yaw=0), FlightFlags())
        self.assertEqual(pkt.data[2:6], bytes([255, 1, 0, 1]))

    def test_other_commands(self):
        self.assertEqual(CMD_HEARTBEAT, H("01 01"))
        self.assertEqual(CMD_CONTROL_OFF, H("08 01"))


if __name__ == "__main__":
    unittest.main()
