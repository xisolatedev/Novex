"""Offline debug tooling: dry-run link, TX log parsing, pcap parsing, comparison."""

import os
import struct
import tempfile
import unittest

from controller.flight import FlightController
from controller.protocol import DEVICE_TYPE_GL, DEVICE_TYPE_TC
from diagnostics.logger import PacketLogger
from link.offline import OfflineLink
from tools.packet_tools import analyze, compare, read_hex, read_pcap, read_stream, read_txlog


class TestOfflineLink(unittest.TestCase):
    def test_nothing_is_transmitted_but_packets_are_built(self):
        link = OfflineLink()
        link.start()
        fc = FlightController(sender=link.send, device_type=link.effective_device_type)
        fc.state.control_mode = True
        fc.keyboard.press("w")
        pkt = fc.tick()
        self.assertEqual(link.sent, [pkt.data])
        self.assertEqual(fc.stats.dropped, 0)

    def test_replayed_telemetry_drives_device_type(self):
        link = OfflineLink()
        link.start()
        self.assertEqual(link.effective_device_type(), 0)          # before any telemetry
        link.feed_telemetry(bytes([90, 1] + [0] * 18))
        self.assertEqual(link.effective_device_type(), DEVICE_TYPE_GL)
        link.feed_telemetry(bytes([27, 2] + [0] * 18))
        self.assertEqual(link.effective_device_type(), DEVICE_TYPE_TC)
        self.assertEqual(link.device_type_changes, 1)
        self.assertEqual(link.first_device_id, 90)

    def test_packet_format_follows_replayed_telemetry(self):
        link = OfflineLink()
        link.start()
        fc = FlightController(sender=link.send, device_type=link.effective_device_type)
        fc.state.control_mode = True
        self.assertEqual(len(fc.tick().data), 21)                  # device type unknown -> GL format
        link.feed_telemetry(bytes([27, 2] + [0] * 18))
        self.assertEqual(len(fc.tick().data), 9)                   # TC


class TestLogParsing(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "tx.log")

    def test_roundtrip_through_packet_logger(self):
        log = PacketLogger(self.path)
        link = OfflineLink(tx_logger=log)
        link.start()
        fc = FlightController(sender=link.send, device_type=lambda: DEVICE_TYPE_TC, packet_logger=log)
        fc.state.control_mode = True
        fc.tick()
        fc.keyboard.press("w")
        fc.tick()
        log.log_heartbeat(b"\x01\x01", True)
        log.log_event("LINK DOWN", "socket closed")
        log.log_command("CONTROL OFF", b"\x08\x01", False)
        log.close()

        stream = read_txlog(self.path)
        kinds = [d.kind for d in stream]
        self.assertEqual(kinds, ["FLIGHT", "FLIGHT", "HEARTBEAT", "CONTROL OFF"])
        self.assertEqual(stream[1].hex, "03 66 80 A8 80 80 00 28 99")
        self.assertIn("DROPPED", stream[3].note)
        self.assertIn("LINK DOWN", stream[3].note)      # event attached to the following datagram

        a = analyze(stream)
        self.assertEqual(a.bad_checksums, 0)
        self.assertEqual(len(a.axis_changes), 2)

    def test_detects_bad_checksum(self):
        with open(self.path, "w") as f:
            f.write("2026-09-20T08:00:00.000 TX FLIGHT dev=TC(10) fmt=TC-9 len=9 ok\n")
            f.write("  03 66 80 A8 80 80 00 FF 99\n")
        self.assertEqual(analyze(read_txlog(self.path)).bad_checksums, 1)

    def test_hex_format(self):
        p = os.path.join(self.dir, "s.hex")
        with open(p, "w") as f:
            f.write("03 66 80 80 80 80 00 00 99\n# comment\n01 01\n")
        stream = read_stream(p)
        self.assertEqual([d.kind for d in stream], ["FLIGHT", "HEARTBEAT"])


def _make_pcap(path, payloads, port=7099):
    """Classic pcap, Ethernet, IPv4/UDP."""
    with open(path, "wb") as f:
        f.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for i, payload in enumerate(payloads):
            udp = struct.pack(">HHHH", 40000, port, 8 + len(payload), 0) + payload
            ip = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(udp), 0, 0, 64, 17, 0,
                             bytes([192, 168, 1, 50]), bytes([192, 168, 1, 1])) + udp
            eth = b"\x00" * 12 + b"\x08\x00" + ip
            f.write(struct.pack("<IIII", 100, i * 50000, len(eth), len(eth)))
            f.write(eth)


class TestPcap(unittest.TestCase):
    def test_reads_udp_payloads(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "c.pcap")
        _make_pcap(p, [bytes.fromhex("0366808080800000 99".replace(" ", "")), b"\x01\x01"])
        stream = read_stream(p)
        self.assertEqual([x.kind for x in stream], ["FLIGHT", "HEARTBEAT"])
        self.assertAlmostEqual(stream[1].time, 0.05, places=3)
        self.assertEqual(stream[0].direction, "tx")


class TestCompare(unittest.TestCase):
    def test_identical_and_differing_streams(self):
        d = tempfile.mkdtemp()
        a, b = os.path.join(d, "a.hex"), os.path.join(d, "b.hex")
        open(a, "w").write("03 66 80 80 80 80 00 00 99\n01 01\n")
        open(b, "w").write("03 66 80 80 80 80 00 00 99\n01 01\n")
        self.assertEqual(compare(read_hex(a), read_hex(b), "a", "b"), 0)
        open(b, "w").write("03 66 80 A8 80 80 00 28 99\n")
        self.assertEqual(compare(read_hex(a), read_hex(b), "a", "b"), 2)   # one differs, one missing


if __name__ == "__main__":
    unittest.main()
