"""Decoder for the esp-radar binary wire format (mirror of radar_proto.h).

    [hdr 20 B][payload][crc32 4 B]   little-endian, CRC-32 (zlib) over hdr+payload

Stream-safe: resynchronises on the A5 5A sync bytes, rejects bad CRCs, counts
every byte it had to skip. No GUI code here.
"""
from __future__ import annotations

import struct
import time
import zlib
from dataclasses import dataclass

import numpy as np

from csiproto import CsiFrame, LossTracker

SYNC = b"\xA5\x5A"
VERSION = 1
HDR = struct.Struct("<2sBBHHIQ")          # sync, version, type, payload_len, flags, seq, t_us
CSI_META = struct.Struct("<II6s6sbbBBBBBBBBHHH")
STAT_FIELDS = (
    "uptime_ms", "csi_callbacks", "csi_filtered", "csi_accepted", "csi_ring_drops",
    "csi_truncated", "cb_us_max", "cb_us_sum", "ring_size", "ring_free_min", "ring_in_psram",
    "data_sink", "channel", "promisc_data", "tx_bytes", "tx_pkts", "tx_write_us",
    "ring_wait_us_max", "ring_wait_us_sum", "ctrl_drops", "bench_generated", "bench_drops",
    "cpu0_permille", "cpu1_permille", "heap_int_free", "heap_int_min", "heap_int_largest",
    "psram_free", "psram_total", "link_drops",
)
STAT = struct.Struct("<" + "I" * 10 + "BBBB" + "I" * 8 + "HH" + "I" * 6)
PONG = struct.Struct("<QQ")
MAX_PAYLOAD = 4096

T_CSI, T_STAT, T_LOG, T_AP, T_HELLO, T_REPLY, T_BENCH, T_PONG = range(1, 9)
TYPE_NAMES = {T_CSI: "CSI", T_STAT: "STAT", T_LOG: "LOG", T_AP: "AP", T_HELLO: "HELLO",
              T_REPLY: "REPLY", T_BENCH: "BENCH", T_PONG: "PONG"}
SINKS = {0: "usb-jtag", 1: "uart-bin", 2: "uart-text", 3: "tinyusb-cdc"}
assert HDR.size == 20 and CSI_META.size == 36 and STAT.size == 104 and len(STAT_FIELDS) == 30


def mac_str(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


@dataclass
class Bench:
    seq: int
    size: int
    pattern_ok: bool


def check_bench(payload: bytes) -> Bench:
    seq = int.from_bytes(payload[:4], "little")
    n = len(payload)
    expect = ((seq + np.arange(4, n)) & 0xFF).astype(np.uint8)
    ok = bool(np.array_equal(np.frombuffer(payload, np.uint8, offset=4), expect))
    return Bench(seq, n, ok)


def decode_packet(ptype: int, t_us: int, payload: bytes, t_pc: float):
    if ptype == T_CSI:
        m = CSI_META.unpack_from(payload)
        (frame_id, rx_us, src, dst, rssi, nf, ch, sec, sig, mcs, cwb, stbc, rate, flags,
         rx_seq, orig_len, csi_len) = m
        raw = np.frombuffer(payload, np.int8, count=csi_len, offset=CSI_META.size)
        return "CSI", CsiFrame(frame_id=frame_id, host_us=t_us, rx_us=rx_us, mac=mac_str(src),
                               dmac=mac_str(dst), rssi=rssi, noise_floor=nf, channel=ch,
                               secondary=sec, sig_mode=sig, mcs=mcs, cwb=cwb, stbc=stbc,
                               rate=rate, rx_seq=rx_seq, first_word_invalid=bool(flags & 1),
                               orig_len=orig_len, raw=raw, t_pc=t_pc)
    if ptype == T_STAT:
        d = dict(zip(STAT_FIELDS, STAT.unpack_from(payload)))
        d["t_us"] = t_us
        return "STAT", d
    if ptype == T_BENCH:
        return "BENCH", check_bench(payload)
    if ptype == T_PONG:
        token, esp_us = PONG.unpack_from(payload)
        return "PONG", {"token": token, "esp_us": esp_us, "t_pc": t_pc}
    text = payload.decode("utf-8", errors="replace")
    if ptype == T_AP:
        bssid, ch, rssi, auth, ssid = text.split(",", 4)
        return "AP", {"bssid": bssid, "channel": int(ch), "rssi": int(rssi), "auth": auth,
                      "ssid": ssid}
    if ptype == T_HELLO:
        return "HELLO", dict(kv.partition("=")[::2] for kv in text.split(","))
    if ptype == T_REPLY:
        return "REPLY", text
    if ptype == T_LOG:
        return "LOG", text
    return "UNKNOWN", (ptype, payload)


class Decoder:
    """Feed raw link bytes; get decoded packets. Tracks integrity counters."""

    def __init__(self, record_file=None):
        self.buf = bytearray()
        self.link_seq = LossTracker(2**32)
        self.packets = 0
        self.bytes_ok = 0
        self.crc_errors = 0
        self.skipped_bytes = 0
        self.junk = bytearray()   # non-packet bytes (ROM boot text, etc.)
        self.record_file = record_file

    def feed(self, data: bytes, t_pc: float) -> list:
        self.buf += data
        out = []
        buf = self.buf
        i = 0
        n = len(buf)
        while True:
            j = buf.find(SYNC, i)
            if j < 0:
                keep = n - 1 if n and buf[-1] == 0xA5 else n
                self._skip(buf[i:keep])
                i = keep
                break
            if j > i:
                self._skip(buf[i:j])
            if n - j < HDR.size:
                i = j
                break
            _, ver, ptype, plen, _flags, seq, t_us = HDR.unpack_from(buf, j)
            if ver != VERSION or plen > MAX_PAYLOAD or ptype not in TYPE_NAMES:
                self._skip(buf[j:j + 1])
                i = j + 1
                continue
            end = j + HDR.size + plen + 4
            if n < end:
                i = j
                break
            crc = int.from_bytes(buf[end - 4:end], "little")
            if zlib.crc32(buf[j:end - 4]) != crc:
                self.crc_errors += 1
                self._skip(buf[j:j + 1])
                i = j + 1
                continue
            pkt = bytes(buf[j:end])
            if self.record_file is not None:
                self.record_file.write(struct.pack("<dI", t_pc, len(pkt)) + pkt)
            self.link_seq.update(seq)
            self.packets += 1
            self.bytes_ok += len(pkt)
            out.append(decode_packet(ptype, t_us, pkt[HDR.size:-4], t_pc))
            i = end
        del self.buf[:i]
        return out

    def _skip(self, b):
        if b:
            self.skipped_bytes += len(b)
            self.junk += b
            if len(self.junk) > 4096:
                del self.junk[:-4096]

    def take_junk_lines(self) -> list[str]:
        """Complete text lines found between packets (e.g. ROM boot messages)."""
        if b"\n" not in self.junk:
            return []
        *lines, rest = bytes(self.junk).split(b"\n")
        self.junk = bytearray(rest)
        return [ln.decode("ascii", errors="replace").strip() for ln in lines if ln.strip()]


class ClockSync:
    """ESP esp_timer -> PC monotonic offset from ping/pong round trips.

    Uses the minimum-RTT sample of the recent window; the uncertainty is RTT/2."""

    def __init__(self):
        self.samples: list[tuple[float, float]] = []   # (rtt_s, offset_s)

    @staticmethod
    def token() -> int:
        return int(time.monotonic() * 1e6)

    def on_pong(self, p: dict):
        t_send = p["token"] / 1e6
        rtt = p["t_pc"] - t_send
        offset = p["esp_us"] / 1e6 - (t_send + rtt / 2)
        self.samples.append((rtt, offset))
        self.samples = self.samples[-30:]

    @property
    def best(self) -> tuple[float, float] | None:
        return min(self.samples) if self.samples else None

    def esp_to_pc(self, esp_us: int) -> float | None:
        b = self.best
        return None if b is None else esp_us / 1e6 - b[1]


def read_capture(path: str):
    """Yields (t_pc, kind, obj) from a .radar capture written by Decoder(record_file)."""
    rec = struct.Struct("<dI")
    with open(path, "rb") as f:
        while True:
            h = f.read(rec.size)
            if len(h) < rec.size:
                return
            t_pc, n = rec.unpack(h)
            pkt = f.read(n)
            _, _, ptype, plen, _, _, t_us = HDR.unpack_from(pkt)
            yield (t_pc,) + decode_packet(ptype, t_us, pkt[HDR.size:HDR.size + plen], t_pc)
