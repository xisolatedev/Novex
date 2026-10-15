"""Parser for the esp-radar USB line protocol.

Keep in sync with esp-radar/components/csi/csi.c (CSI line) and
esp-radar/main/main.c (STAT / HELLO lines). No GUI code in here so it can be
reused by the recorder, the DSP stages and tests.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field

import numpy as np

CSI_FIELDS = (
    "frame_id", "host_us", "rx_us", "mac", "dmac", "rssi", "noise_floor", "channel",
    "secondary", "sig_mode", "mcs", "cwb", "stbc", "rate", "rx_seq",
    "first_word_invalid", "orig_len", "len",
)
STAT_FIELDS = (
    "uptime_ms", "callbacks", "filtered", "accepted", "queue_drops", "truncated", "sent",
    "tx_drops", "channel", "heap_free", "heap_min", "psram_free", "psram_total",
)
SIG_MODE = {0: "non-HT (11bg)", 1: "HT (11n)", 3: "VHT (11ac)"}


@dataclass
class CsiFrame:
    frame_id: int
    host_us: int          # ESP esp_timer at callback
    rx_us: int            # radio RX timestamp (32-bit, wraps)
    mac: str
    dmac: str
    rssi: int
    noise_floor: int
    channel: int
    secondary: int
    sig_mode: int
    mcs: int
    cwb: int
    stbc: int
    rate: int
    rx_seq: int
    first_word_invalid: bool
    orig_len: int
    raw: np.ndarray       # int8, as delivered by the Wi-Fi driver
    t_pc: float = 0.0     # PC monotonic time the line was received
    csi: np.ndarray = field(init=False)  # complex64 per subcarrier (buffer order)

    def __post_init__(self):
        # ESP-IDF: each subcarrier is 2 signed bytes, imaginary first, then real.
        pairs = self.raw[: len(self.raw) // 2 * 2].astype(np.float32).reshape(-1, 2)
        self.csi = (pairs[:, 1] + 1j * pairs[:, 0]).astype(np.complex64)
        if self.first_word_invalid and len(self.csi) >= 2:
            # First 4 bytes are invalid due to a hardware limitation.
            self.csi[:2] = np.nan

    @property
    def n_subcarriers(self) -> int:
        return len(self.csi)

    def lltf(self) -> np.ndarray | None:
        """64 L-LTF subcarriers reordered to -32..31 (buffer order is 0..31, -32..-1).

        Only valid for 20 MHz frames, where the L-LTF is the first 128 bytes.
        """
        if self.cwb != 0 or len(self.csi) < 64:
            return None
        return np.fft.fftshift(self.csi[:64])


def parse_csi(parts: list[str], t_pc: float) -> CsiFrame:
    if len(parts) != len(CSI_FIELDS) + 2:
        raise ValueError(f"CSI line has {len(parts)} fields, expected {len(CSI_FIELDS) + 2}")
    v = dict(zip(CSI_FIELDS, parts[1:-1]))
    raw = np.frombuffer(base64.b64decode(parts[-1], validate=True), dtype=np.int8)
    if len(raw) != int(v["len"]):
        raise ValueError(f"payload {len(raw)} B != declared {v['len']} B")
    return CsiFrame(
        frame_id=int(v["frame_id"]), host_us=int(v["host_us"]), rx_us=int(v["rx_us"]),
        mac=v["mac"], dmac=v["dmac"], rssi=int(v["rssi"]), noise_floor=int(v["noise_floor"]),
        channel=int(v["channel"]), secondary=int(v["secondary"]), sig_mode=int(v["sig_mode"]),
        mcs=int(v["mcs"]), cwb=int(v["cwb"]), stbc=int(v["stbc"]), rate=int(v["rate"]),
        rx_seq=int(v["rx_seq"]), first_word_invalid=v["first_word_invalid"] == "1",
        orig_len=int(v["orig_len"]), raw=raw, t_pc=t_pc,
    )


def parse_line(line: bytes | str, t_pc: float = 0.0):
    """Returns (kind, payload). kind is one of CSI, STAT, AP, APEND, HELLO, ACK, ERR,
    LOG (ordinary ESP_LOG text) or BAD (a tagged line that failed to parse)."""
    if isinstance(line, bytes):
        line = line.decode("ascii", errors="replace")
    line = line.rstrip("\r\n")
    tag = line.split(",", 1)[0]
    try:
        if tag == "CSI":
            return "CSI", parse_csi(line.split(","), t_pc)
        if tag == "STAT":
            vals = [int(x) for x in line.split(",")[1:]]
            return "STAT", dict(zip(STAT_FIELDS, vals))
        if tag == "AP":
            _, bssid, ch, rssi, auth, ssid = line.split(",", 5)
            return "AP", {"bssid": bssid, "channel": int(ch), "rssi": int(rssi),
                          "auth": auth, "ssid": ssid}
        if tag == "HELLO":
            parts = line.split(",")
            info = {"fw": parts[1], "version": parts[2], "target": parts[3], "rev": parts[4]}
            for p in parts[5:]:
                k, _, val = p.partition("=")
                info[k] = val
            return "HELLO", info
        if tag in ("APEND", "ACK", "ERR"):
            return tag, line
    except (ValueError, IndexError) as e:
        return "BAD", f"{e}: {line[:120]}"
    return "LOG", line


class LossTracker:
    """Counts gaps in a monotonically increasing counter with wrap-around."""

    def __init__(self, modulo: int):
        self.modulo = modulo
        self.last: int | None = None
        self.received = 0
        self.missing = 0

    def update(self, value: int) -> int:
        gap = 0
        if self.last is not None:
            step = (value - self.last) % self.modulo
            if step == 0:
                return 0  # duplicate / retransmission
            if step < self.modulo // 2:
                gap = step - 1
            # else: reordering or a reset, treat as a new start
        self.last = value
        self.received += 1
        self.missing += gap
        return gap

    @property
    def loss_ratio(self) -> float:
        total = self.received + self.missing
        return self.missing / total if total else 0.0


class SeqTracker(LossTracker):
    """802.11 sequence-number loss for one transmitter (12-bit counter).

    Only meaningful for a single sender transmitting continuously (e.g. the C6);
    ambient APs skip sequence numbers for frames sent to other stations."""

    def __init__(self):
        super().__init__(4096)

    def update(self, value: int) -> int:
        return super().update(value & 0xFFF)
