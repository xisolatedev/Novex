"""Serial port handling shared by the CLI and the GUI."""
from __future__ import annotations

import time

import serial


BAUD = 2_000_000  # set by esp-radar telemetry after boot (ROM/bootloader use 115200)


def open_port(port: str, baud: int = BAUD) -> serial.Serial:
    """Open the board's CH343 USB-UART port without resetting the chip.

    DTR/RTS drive the auto-reset circuit (EN / GPIO0). Linux raises both when a
    tty is opened, so they are forced low before opening."""
    s = serial.Serial()
    s.port = port
    s.baudrate = baud
    s.timeout = 0.05
    s.dtr = False
    s.rts = False
    s.open()
    return s


class LineReader:
    """Splits a byte stream into lines and stamps each with PC monotonic time."""

    def __init__(self, ser: serial.Serial, record_file=None):
        self.ser = ser
        self.buf = b""
        self.record_file = record_file

    def read_lines(self) -> list[tuple[float, bytes]]:
        data = self.ser.read(self.ser.in_waiting or 1)
        if not data:
            return []
        now = time.monotonic()
        self.buf += data
        *lines, self.buf = self.buf.split(b"\n")
        if self.record_file is not None:
            wall = time.time()
            for ln in lines:
                self.record_file.write(f"{wall:.6f} ".encode() + ln + b"\n")
        return [(now, ln) for ln in lines]

    def send(self, cmd: str):
        self.ser.write((cmd.strip() + "\n").encode())
