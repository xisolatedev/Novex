#!/usr/bin/env python3
"""
Offline packet analysis and comparison.

Reads a packet stream from:
  * txlog  - an fc-controller --log-packets file
  * hex    - a text file with one datagram of hex per line ("03 66 80 ...")
  * pcap   - a classic tcpdump capture (for example of the Android app's traffic),
             filtered to the UDP payloads sent to/from the drone port

Commands:
  analyze  <file>            timing, flags, axis and link-state summary of one stream
  compare  <fileA> <fileB>   byte-for-byte comparison of two streams
  decode   <hex...>          decode a single packet given on the command line

Usage:
  python tools/packet_tools.py analyze logs/tx_packets.log
  python tools/packet_tools.py compare logs/pc.log android.pcap --port 7099
  python tools/packet_tools.py decode 03 66 80 A8 80 FF 00 57 99
"""

import argparse
import os
import re
import struct
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import _bootstrap  # noqa: E402,F401

from controller.protocol import decode_flight_packet  # noqa: E402

KNOWN_COMMANDS = {
    "01 01": "HEARTBEAT",
    "08 01": "CONTROL OFF",
    "06 01": "CAMERA 1",
    "06 02": "CAMERA 2",
    "09 01": "ACK PHOTO",
    "09 02": "ACK VIDEO",
}


@dataclass
class Datagram:
    index: int
    time: Optional[float]        # seconds relative to the first datagram
    data: bytes
    direction: str = "tx"
    note: str = ""

    @property
    def hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)

    @property
    def kind(self) -> str:
        h = self.hex
        if h in KNOWN_COMMANDS:
            return KNOWN_COMMANDS[h]
        if len(self.data) >= 2 and self.data[0] == 0x03 and self.data[1] == 0x66:
            return "FLIGHT"
        return "OTHER"


# --------------------------------------------------------------------------- readers

def read_txlog(path: str) -> List[Datagram]:
    """fc-controller TX log. Keeps events as notes so link-down shows up in the timeline."""
    out: List[Datagram] = []
    t0 = None
    pending_note = []
    line_re = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.]+) (TX|RX) ([A-Z ]+?) (?:dev=\S+ fmt=\S+ )?len=(\d+) (\S+)")
    event_re = re.compile(r"^(\d{4}-\d\d-\d\dT[\d:.]+) EVENT (.+)$")
    hdr = None
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.rstrip("\n")
        ev = event_re.match(line)
        if ev:
            pending_note.append(ev.group(2))
            continue
        m = line_re.match(line)
        if m:
            hdr = m
            continue
        if hdr and re.match(r"^\s+[0-9A-F]{2}( [0-9A-F]{2})*\s*$", line):
            ts = datetime.fromisoformat(hdr.group(1)).timestamp()
            if t0 is None:
                t0 = ts
            data = bytes.fromhex(line.strip().replace(" ", ""))
            note = hdr.group(5)
            if pending_note:
                note += " | " + "; ".join(pending_note)
                pending_note = []
            out.append(Datagram(len(out), ts - t0, data, hdr.group(2).lower(), note))
            hdr = None
    return out


def read_hex(path: str) -> List[Datagram]:
    out = []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.split("#")[0].strip()
        if not line:
            continue
        try:
            data = bytes.fromhex(line.replace(" ", ""))
        except ValueError:
            continue
        if data:
            out.append(Datagram(len(out), None, data))
    return out


def read_pcap(path: str, port: int = 7099) -> List[Datagram]:
    """
    Minimal classic-pcap reader for UDP payloads on `port`.
    Handles Ethernet, Linux cooked (SLL) and raw IP link types, IPv4 only.
    pcapng is not supported: save with `tcpdump -w file.pcap`.
    """
    out: List[Datagram] = []
    with open(path, "rb") as f:
        hdr = f.read(24)
        if len(hdr) < 24:
            return out
        magic = hdr[:4]
        if magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
            endian, nano = ">", magic == b"\xa1\xb2\x3c\x4d"
        elif magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
            endian, nano = "<", magic == b"\x4d\x3c\xb2\xa1"
        elif magic == b"\x0a\x0d\x0d\x0a":
            raise SystemExit("This is a pcapng file. Re-save as classic pcap: "
                             "`tcpdump -r in.pcapng -w out.pcap` or `editcap -F pcap in.pcapng out.pcap`")
        else:
            raise SystemExit(f"Not a pcap file: {path}")
        linktype = struct.unpack(endian + "I", hdr[20:24])[0]
        t0 = None
        while True:
            ph = f.read(16)
            if len(ph) < 16:
                break
            sec, usec, caplen, _ = struct.unpack(endian + "IIII", ph)
            pkt = f.read(caplen)
            if len(pkt) < caplen:
                break
            ts = sec + usec / (1e9 if nano else 1e6)
            offset = {1: 14, 113: 16, 101: 0, 12: 0, 0: 4}.get(linktype)
            if offset is None or len(pkt) < offset + 20:
                continue
            if linktype == 1:
                ethertype = struct.unpack(">H", pkt[12:14])[0]
                if ethertype != 0x0800:
                    continue
            ip = pkt[offset:]
            if (ip[0] >> 4) != 4 or ip[9] != 17:      # IPv4 + UDP
                continue
            ihl = (ip[0] & 0x0F) * 4
            udp = ip[ihl:]
            if len(udp) < 8:
                continue
            sport, dport, ulen = struct.unpack(">HHH", udp[:6])
            payload = udp[8:ulen] if 8 <= ulen <= len(udp) else udp[8:]
            if port not in (sport, dport) or not payload:
                continue
            if t0 is None:
                t0 = ts
            src = ".".join(str(b) for b in ip[12:16])
            dst = ".".join(str(b) for b in ip[16:20])
            out.append(Datagram(len(out), ts - t0, payload,
                                "tx" if dport == port else "rx", f"{src}->{dst}"))
    return out


def read_stream(path: str, fmt: str = "auto", port: int = 7099) -> List[Datagram]:
    if fmt == "auto":
        with open(path, "rb") as f:
            head = f.read(4)
        if head[:4] in (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1",
                        b"\xa1\xb2\x3c\x4d", b"\x0a\x0d\x0d\x0a"):
            fmt = "pcap"
        elif "TX " in open(path, encoding="utf-8", errors="replace").read(4096):
            fmt = "txlog"
        else:
            fmt = "hex"
    return {"txlog": read_txlog, "hex": read_hex,
            "pcap": lambda p: read_pcap(p, port)}[fmt](path)


# --------------------------------------------------------------------------- analysis

@dataclass
class Analysis:
    total: int = 0
    by_kind: Dict[str, int] = field(default_factory=dict)
    flight: List[Datagram] = field(default_factory=list)
    intervals_ms: List[float] = field(default_factory=list)
    flag_runs: List[str] = field(default_factory=list)
    axis_changes: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    bad_checksums: int = 0


def analyze(stream: List[Datagram]) -> Analysis:
    a = Analysis(total=len(stream))
    tx_flight = [d for d in stream if d.kind == "FLIGHT" and d.direction == "tx"]
    a.flight = tx_flight
    for d in stream:
        a.by_kind[d.kind] = a.by_kind.get(d.kind, 0) + 1
        if d.note and any(w in d.note for w in ("DROPPED", "|")):
            a.notes.append(f"#{d.index} t={d.time if d.time is None else round(d.time, 3)} {d.note}")
    for p, q in zip(tx_flight, tx_flight[1:]):
        if p.time is not None and q.time is not None:
            a.intervals_ms.append((q.time - p.time) * 1000)

    prev_flags = prev_axes = None
    for d in tx_flight:
        dec = decode_flight_packet(d.data)
        if dec.get("format") == "UNKNOWN":
            continue
        if not dec.get("checksum_ok", True):
            a.bad_checksums += 1
        flags = tuple(dec["flags"])
        axes = (dec["roll"], dec["pitch"], dec["throttle"], dec["yaw"])
        t = "?" if d.time is None else f"{d.time:7.3f}s"
        if flags != prev_flags:
            a.flag_runs.append(f"{t} #{d.index} flags={' '.join(f'0x{f:02X}' for f in flags)}")
            prev_flags = flags
        if axes != prev_axes:
            a.axis_changes.append(f"{t} #{d.index} R={axes[0]} P={axes[1]} T={axes[2]} Y={axes[3]}")
            prev_axes = axes
    return a


def print_analysis(path: str, stream: List[Datagram]) -> None:
    a = analyze(stream)
    print(f"=== {path}")
    print(f"datagrams: {a.total}   " + "  ".join(f"{k}={v}" for k, v in sorted(a.by_kind.items())))
    if a.intervals_ms:
        s = sorted(a.intervals_ms)
        n = len(s)
        print(f"flight interval ms: min={s[0]:.1f} p50={s[n // 2]:.1f} "
              f"p95={s[int(n * 0.95)]:.1f} max={s[-1]:.1f} mean={sum(s) / n:.2f}")
        gaps = [(i, v) for i, v in enumerate(a.intervals_ms) if v > 100]
        if gaps:
            print(f"  GAPS >100ms: {[(i, round(v, 1)) for i, v in gaps[:10]]}")
    print(f"bad checksums: {a.bad_checksums}")
    print(f"flag changes ({len(a.flag_runs)}):")
    for line in a.flag_runs[:40]:
        print("   " + line)
    print(f"axis changes ({len(a.axis_changes)}):")
    for line in a.axis_changes[:40]:
        print("   " + line)
    if a.notes:
        print(f"notes/events ({len(a.notes)}), first 20:")
        for line in a.notes[:20]:
            print("   " + line)


def compare(a: List[Datagram], b: List[Datagram], label_a: str, label_b: str, limit: int = 20) -> int:
    """Byte-for-byte comparison of two streams, aligned by index."""
    print(f"=== compare\n  A = {label_a} ({len(a)} datagrams)\n  B = {label_b} ({len(b)} datagrams)")
    diffs = 0
    for i in range(max(len(a), len(b))):
        da = a[i] if i < len(a) else None
        db = b[i] if i < len(b) else None
        if da is None or db is None:
            diffs += 1
            if diffs <= limit:
                missing = "B" if db is None else "A"
                have = da or db
                print(f"  #{i}: missing in {missing}: {have.hex} ({have.kind})")
            continue
        if da.data != db.data:
            diffs += 1
            if diffs <= limit:
                print(f"  #{i}: DIFFERS")
                print(f"      A: {da.hex}  ({da.kind})")
                print(f"      B: {db.hex}  ({db.kind})")
                if len(da.data) == len(db.data):
                    bad = [j for j in range(len(da.data)) if da.data[j] != db.data[j]]
                    print(f"      byte offsets differing: {bad}")
                else:
                    print(f"      lengths differ: {len(da.data)} vs {len(db.data)}")
    if diffs > limit:
        print(f"  ... and {diffs - limit} more")
    print(f"total differing positions: {diffs}")

    # A set comparison is often more useful than positional alignment.
    sa = {d.hex for d in a}
    sb = {d.hex for d in b}
    only_a, only_b = sorted(sa - sb), sorted(sb - sa)
    print(f"distinct datagrams only in A ({len(only_a)}):")
    for h in only_a[:15]:
        print("   " + h)
    print(f"distinct datagrams only in B ({len(only_b)}):")
    for h in only_b[:15]:
        print("   " + h)
    return diffs


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("analyze", "compare"):
        sp = sub.add_parser(name)
        sp.add_argument("files", nargs="+")
        sp.add_argument("--format", choices=["auto", "txlog", "hex", "pcap"], default="auto")
        sp.add_argument("--port", type=int, default=7099)
    sp = sub.add_parser("decode")
    sp.add_argument("bytes", nargs="+")

    args = p.parse_args(argv)
    if args.cmd == "decode":
        data = bytes.fromhex("".join(args.bytes).replace("0x", ""))
        print(" ".join(f"{b:02X}" for b in data))
        for k, v in decode_flight_packet(data).items():
            print(f"  {k}: {v}")
        return 0

    streams = [(f, read_stream(f, args.format, args.port)) for f in args.files]
    if args.cmd == "analyze":
        for path, s in streams:
            print_analysis(path, s)
            print()
        return 0
    if len(streams) != 2:
        p.error("compare needs exactly two files")
    (pa, sa), (pb, sb) = streams
    return 0 if compare(sa, sb, pa, pb) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
