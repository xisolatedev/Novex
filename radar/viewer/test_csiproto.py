"""Unit tests for the wire-format parser: python -m unittest test_csiproto"""
import base64
import unittest

import numpy as np

from csiproto import LossTracker, SeqTracker, parse_line


def make_line(raw: bytes, fwi=0, cwb=0, frame_id=7):
    b64 = base64.b64encode(raw).decode()
    return (f"CSI,{frame_id},123456,999,aa:bb:cc:dd:ee:ff,ff:ff:ff:ff:ff:ff,-40,-95,6,0,1,7,{cwb},0,11,"
            f"321,{fwi},{len(raw)},{len(raw)},{b64}")


class ParseTest(unittest.TestCase):
    def test_imag_then_real(self):
        raw = np.array([3, 4, -1, 2], dtype=np.int8).tobytes()  # (imag=3, real=4), (imag=-1, real=2)
        kind, f = parse_line(make_line(raw))
        self.assertEqual(kind, "CSI")
        np.testing.assert_allclose(f.csi, [4 + 3j, 2 - 1j])
        self.assertEqual((f.rssi, f.noise_floor, f.channel, f.rx_seq, f.mac),
                         (-40, -95, 6, 321, "aa:bb:cc:dd:ee:ff"))

    def test_first_word_invalid_masks_two_subcarriers(self):
        raw = np.arange(128, dtype=np.int8).tobytes()
        _, f = parse_line(make_line(raw, fwi=1))
        self.assertTrue(np.isnan(f.csi[:2]).all())
        self.assertFalse(np.isnan(f.csi[2:]).any())

    def test_lltf_reorder(self):
        # subcarrier k in buffer order holds real=k (0..31, then -32..-1)
        order = list(range(32)) + list(range(-32, 0))
        raw = np.zeros(128, dtype=np.int8)
        raw[1::2] = order
        _, f = parse_line(make_line(raw.tobytes()))
        np.testing.assert_array_equal(f.lltf().real, np.arange(-32, 32))
        _, f40 = parse_line(make_line(raw.tobytes(), cwb=1))
        self.assertIsNone(f40.lltf())

    def test_bad_lines(self):
        self.assertEqual(parse_line("CSI,1,2,3")[0], "BAD")
        self.assertEqual(parse_line(make_line(b"\x01\x02")[:-2] + "!!")[0], "BAD")
        self.assertEqual(parse_line("I (123) wifi: hello")[0], "LOG")

    def test_stat_and_ap(self):
        k, s = parse_line("STAT,1000,5,0,5,0,0,5,0,6,200000,190000,8000000,8388608")
        self.assertEqual((k, s["channel"], s["psram_total"]), ("STAT", 6, 8388608))
        k, a = parse_line("AP,11:22:33:44:55:66,11,-50,wpa2,my,ssid")
        self.assertEqual((k, a["ssid"], a["channel"]), ("AP", "my,ssid", 11))


class LossTest(unittest.TestCase):
    def test_gaps_and_wrap(self):
        t = SeqTracker()
        for v in (4094, 4095, 0, 3, 3, 4):   # wrap, gap of 2, duplicate
            t.update(v)
        self.assertEqual((t.received, t.missing), (5, 2))

    def test_transport(self):
        t = LossTracker(2**32)
        for v in (0, 1, 2, 10):
            t.update(v)
        self.assertEqual(t.missing, 7)


if __name__ == "__main__":
    unittest.main()
