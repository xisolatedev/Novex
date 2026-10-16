"""Binary decoder tests: python -m unittest test_radar_bin"""
import struct
import unittest
import zlib

import numpy as np

import radar_bin as rb


def pkt(ptype, payload, seq=0, t_us=1000):
    h = rb.HDR.pack(rb.SYNC, 1, ptype, len(payload), 0, seq, t_us)
    body = h + payload
    return body + struct.pack("<I", zlib.crc32(body))


def csi_payload(frame_id=5, csi=b"\x03\x04\xff\x02"):
    meta = rb.CSI_META.pack(frame_id, 77, b"\xaa\xbb\xcc\xdd\xee\xff", b"\xff" * 6, -40, -92, 6,
                            0, 1, 7, 0, 0, 11, 0, 321, len(csi), len(csi))
    return meta + csi


class DecoderTest(unittest.TestCase):
    def test_csi_roundtrip(self):
        d = rb.Decoder()
        (kind, f), = d.feed(pkt(rb.T_CSI, csi_payload(), t_us=123456), 1.0)
        self.assertEqual(kind, "CSI")
        np.testing.assert_allclose(f.csi, [4 + 3j, 2 - 1j])
        self.assertEqual((f.frame_id, f.host_us, f.mac, f.rssi, f.rx_seq), (5, 123456, "aa:bb:cc:dd:ee:ff", -40, 321))

    def test_resync_split_and_crc(self):
        good = [pkt(rb.T_LOG, b"hello %d" % i, seq=i) for i in range(5)]
        bad = bytearray(pkt(rb.T_LOG, b"corrupt", seq=5))
        bad[25] ^= 0xFF
        stream = b"ESP-ROM boot\n" + good[0] + good[1] + bytes(bad) + b"\xA5\x5Ajunk" + good[2] + good[3] + good[4]
        d = rb.Decoder()
        out = []
        for i in range(0, len(stream), 3):          # tiny chunks exercise partial headers
            out += d.feed(stream[i:i + 3], 0.0)
        self.assertEqual([p for _, p in out], [f"hello {i}" for i in range(5)])
        self.assertEqual(d.crc_errors, 1)
        self.assertEqual(d.link_seq.missing, 0)
        self.assertIn("ESP-ROM boot", d.take_junk_lines())

    def test_seq_gap(self):
        d = rb.Decoder()
        d.feed(pkt(rb.T_LOG, b"a", seq=10) + pkt(rb.T_LOG, b"b", seq=13), 0.0)
        self.assertEqual(d.link_seq.missing, 2)

    def test_stat_and_bench(self):
        vals = list(range(10)) + [1, 0, 6, 1] + list(range(8)) + [250, 500] + list(range(6))
        d = rb.Decoder()
        (k, s), = d.feed(pkt(rb.T_STAT, rb.STAT.pack(*vals)), 0.0)
        self.assertEqual((s["channel"], s["cpu1_permille"], s["psram_total"]), (6, 500, 4))
        payload = struct.pack("<I", 7) + bytes((7 + i) & 0xFF for i in range(4, 100))
        (k, b), = d.feed(pkt(rb.T_BENCH, payload), 0.0)
        self.assertTrue(b.pattern_ok)
        (k, b), = d.feed(pkt(rb.T_BENCH, payload[:-1] + b"\x00"), 0.0)
        self.assertFalse(b.pattern_ok)


if __name__ == "__main__":
    unittest.main()
