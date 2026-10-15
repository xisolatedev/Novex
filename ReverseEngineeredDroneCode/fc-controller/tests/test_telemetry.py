"""
Telemetry parsing, device-type detection, heartbeat and the shared UDP socket.

The link tests talk to a UDP socket on 127.0.0.1 standing in for 192.168.1.1:7099:
a loopback test harness for the real DroneLink code, not a drone simulation.
"""

import socket
import time
import unittest

from controller.protocol import CMD_HEARTBEAT, DEVICE_TYPE_GL, DEVICE_TYPE_TC, DEVICE_TYPE_UNKNOWN
from link.parser import classify_device_type, parse_telemetry_packet
from link.udp_link import DroneLink
from session import ConnectionState, derive_connection_state


class TestParsing(unittest.TestCase):
    def test_device_type_rule(self):
        # WifiIdUtils.isGL: 90..101, 103, 82, 85, 88
        for gl_id in (90, 95, 101, 103, 82, 85, 88):
            self.assertEqual(classify_device_type(gl_id), DEVICE_TYPE_GL, gl_id)
        for tc_id in (5, 27, 29, 80, 81, 102, 104):
            self.assertEqual(classify_device_type(tc_id), DEVICE_TYPE_TC, tc_id)

    def test_parse_fields_and_unknown_bytes(self):
        data = bytes([27, 2, 0x4D, 7] + [0] * 16)
        pkt = parse_telemetry_packet(data)
        self.assertEqual(pkt.device_id, 27)
        self.assertEqual(pkt.camera_reset_mode, 2)
        self.assertEqual(pkt.photo_sequence, 7)
        self.assertFalse(pkt.is_gl_model)
        self.assertIn(19, pkt.unknown_bytes)
        self.assertFalse(pkt.imu_transmitted_by_drone)

    def test_connection_state(self):
        self.assertEqual(derive_connection_state(False, False, False), ConnectionState.DISCONNECTED)
        self.assertEqual(derive_connection_state(True, False, False), ConnectionState.CONNECTING)
        self.assertEqual(derive_connection_state(True, True, False), ConnectionState.VIDEO_CONNECTED)
        self.assertEqual(derive_connection_state(True, False, True), ConnectionState.TELEMETRY_CONNECTED)
        self.assertEqual(derive_connection_state(True, True, True), ConnectionState.CONNECTED)


class TestLinkOverLoopback(unittest.TestCase):
    def setUp(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.settimeout(2.0)
        self.link = DroneLink("127.0.0.1", self.server.getsockname()[1])

    def tearDown(self):
        self.link.stop()
        self.server.close()

    def test_heartbeat_immediate_then_1hz(self):
        t0 = time.monotonic()
        self.assertTrue(self.link.start())
        first, addr = self.server.recvfrom(64)
        t1 = time.monotonic()
        second, _ = self.server.recvfrom(64)
        t2 = time.monotonic()
        self.assertEqual(first, CMD_HEARTBEAT)
        self.assertEqual(second, CMD_HEARTBEAT)
        self.assertLess(t1 - t0, 0.3)                 # schedule(task, 0L, 1000L)
        self.assertAlmostEqual(t2 - t1, 1.0, delta=0.2)

    def test_no_send_when_stopped(self):
        self.assertFalse(self.link.send(b"\x03"))
        self.assertFalse(self.link.running)

    def test_telemetry_sets_device_type_and_flight_uses_same_socket(self):
        self.link.start()
        _, client = self.server.recvfrom(64)          # heartbeat tells us the client port
        self.assertEqual(self.link.device_type, DEVICE_TYPE_UNKNOWN)

        self.server.sendto(bytes([90, 1] + [0] * 18), client)
        self._wait(lambda: self.link.rx_count == 1)
        self.assertEqual(self.link.device_type, DEVICE_TYPE_GL)
        self.assertEqual(self.link.first_device_id, 90)
        self.assertEqual(self.link.switch_camera_reset, 1)
        self.assertTrue(self.link.telemetry_alive())

        self.server.sendto(bytes([27, 2] + [0] * 18), client)
        self._wait(lambda: self.link.rx_count == 2)
        self.assertEqual(self.link.device_type, DEVICE_TYPE_TC)   # re-evaluated every packet
        self.assertEqual(self.link.first_device_id, 90)
        self.assertEqual(self.link.device_type_changes, 1)

        self.assertTrue(self.link.send(bytes.fromhex("03 66 80 80 80 80 00 00 99")))
        while True:
            data, src = self.server.recvfrom(64)
            if data != CMD_HEARTBEAT:
                break
        self.assertEqual(src, client)
        self.assertEqual(data, bytes.fromhex("03 66 80 80 80 80 00 00 99"))

    def test_photo_ack_only_when_counter_advances(self):
        self.link.start()
        _, client = self.server.recvfrom(64)
        self.server.sendto(bytes([27, 1, 0]), client)             # classify as TC first
        self._wait(lambda: self.link.rx_count == 1)
        for _ in range(2):
            self.server.sendto(bytes([27, 1, 77, 3, 0] + [0] * 15), client)
        self._wait(lambda: self.link.rx_count == 3)
        acks = []
        self.server.settimeout(0.3)
        try:
            while True:
                data, _ = self.server.recvfrom(64)
                if data != CMD_HEARTBEAT:
                    acks.append(data)
        except socket.timeout:
            pass
        self.assertEqual(acks, [bytes([0x09, 0x01])])

    def test_heartbeat_continues_while_flight_packets_are_sent_on_same_port(self):
        """Audit point 3: one socket, heartbeat unaffected by the 20 Hz flight loop."""
        from controller.flight import FlightController
        from controller.protocol import DEVICE_TYPE_TC

        self.link.start()
        fc = FlightController(sender=self.link.send, device_type=lambda: DEVICE_TYPE_TC)
        fc.set_control_mode(True)
        try:
            seen = []
            end = time.monotonic() + 2.4
            ports = set()
            while time.monotonic() < end:
                try:
                    data, addr = self.server.recvfrom(64)
                except socket.timeout:
                    continue
                ports.add(addr[1])
                seen.append((time.monotonic(), data))
        finally:
            fc.set_control_mode(False)

        beats = [t for t, d in seen if d == CMD_HEARTBEAT]
        flights = [t for t, d in seen if len(d) == 9]
        self.assertGreaterEqual(len(beats), 2, "heartbeat stopped while flying")
        self.assertGreater(len(flights), 30)
        self.assertEqual(len(ports), 1, f"more than one source port used: {ports}")
        for a, b in zip(beats, beats[1:]):
            self.assertAlmostEqual(b - a, 1.0, delta=0.25)

    @staticmethod
    def _wait(cond, timeout=2.0):
        end = time.monotonic() + timeout
        while not cond():
            if time.monotonic() > end:
                raise AssertionError("condition not reached")
            time.sleep(0.01)


if __name__ == "__main__":
    unittest.main()
