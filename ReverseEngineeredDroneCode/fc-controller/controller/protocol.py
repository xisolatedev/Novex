"""
Flight-control packet construction, byte-for-byte from the decompiled app.

Source: cooingdv.rcufo/tools/FlyController.java, inner class FlyControlTask.run()
(lines 102-181). Every constant below cites where it comes from.

Two wire formats exist, selected by SocketClient.getDeviceType():

  deviceType == 10 (TC)  -> 9 bytes
      03 66 R P T Y F C 99
      C = R ^ P ^ T ^ Y ^ F

  deviceType != 10 (GL=2, or 0 before any telemetry) -> 21 bytes
      03 66 14 R P T Y F1 F2 00x10 C 99
      C = F1 ^ R ^ P ^ T ^ Y ^ F2      (0x14 is NOT in the checksum)

R = controlByte1 (roll), P = controlByte2 (pitch), T = controlAccelerator (throttle),
Y = controlTurn (yaw). The leading 0x03 is prepended by FlyController before
SocketClient.debugSend() (``bArr4[0] = 3``).
"""

from dataclasses import dataclass, field
from typing import Dict, Tuple

# --- Device types: SocketClient.java lines 26/31 (GL = 2, TC = 10), mDeviceType default 0 (line 49)
DEVICE_TYPE_UNKNOWN = 0
DEVICE_TYPE_GL = 2
DEVICE_TYPE_TC = 10
DEVICE_TYPE_NAMES = {DEVICE_TYPE_UNKNOWN: "UNKNOWN", DEVICE_TYPE_GL: "GL", DEVICE_TYPE_TC: "TC"}

# --- FlyController.java lines 20-27
SEND_COMMAND_INTERVAL_S = 0.050   # SEND_COMMAND_INTERVAL = 50; timer.schedule(task, 50, 50)
CONTROL_VALUES_MAX = 255
CONTROL_VALUES_DEFAULT = 128
CONTROL_VALUES_MIN = 1
CONTROL_VALUES_BYTE0 = 0x66       # 102
CONTROL_VALUES_BYTE7 = 0x99       # 153 (-103 as a Java byte)
FLIGHT_PREFIX = 0x03              # bArr4[0] = 3 / bArr2[0] = 3
GL_LENGTH_BYTE = 0x14             # Ascii.DC4 = 20, second byte of the GL body

TC_PACKET_LEN = 9
GL_PACKET_LEN = 21

# --- Other uplink datagrams (all on the same UDP socket to 192.168.1.1:7099)
CMD_HEARTBEAT = bytes([0x01, 0x01])      # SocketClient.HeartBeatTask.run(), every 1000 ms
CMD_CONTROL_OFF = bytes([0x08, 0x01])    # FlyController.setController(false)
CMD_CAMERA_1 = bytes([0x06, 0x01])       # SocketClient.switchCamera(), isSwitchCamera == false
CMD_CAMERA_2 = bytes([0x06, 0x02])       # SocketClient.switchCamera(), isSwitchCamera == true
CMD_ACK_PHOTO = bytes([0x09, 0x01])      # DeviceBLFragment onReceiver, photo counter advanced
CMD_ACK_VIDEO = bytes([0x09, 0x02])      # DeviceBLFragment onReceiver, video counter advanced


@dataclass(frozen=True)
class Axes:
    """Raw control bytes as FlyController stores them (not yet normalized)."""
    roll: int = CONTROL_VALUES_DEFAULT      # controlByte1
    pitch: int = CONTROL_VALUES_DEFAULT     # controlByte2
    throttle: int = CONTROL_VALUES_DEFAULT  # controlAccelerator
    yaw: int = CONTROL_VALUES_DEFAULT       # controlTurn


@dataclass(frozen=True)
class FlightFlags:
    """FlyController boolean state that reaches the wire."""
    fast_fly: bool = False          # TAKEOFF button (setFastFly)
    fast_drop: bool = False         # LAND button (setFastDrop)
    emergency_stop: bool = False    # EMERGENCY STOP button (setEmergencyStop)
    circle_turn_end: bool = False   # 360 flip end (setCircleTurnEnd)
    no_head: bool = False           # headless mode (setNoHeadMode)
    gyro_correction: bool = False   # gyro calibration (setGyroCorrection)
    gesture: bool = False           # gesture mode (GL flags byte only)
    fixed_height: bool = False      # altitude hold (GL second flags byte only)


@dataclass(frozen=True)
class FlightPacket:
    data: bytes
    device_type: int
    axes: Axes           # values after FlyControlTask normalization
    flags_bytes: Tuple[int, ...]
    checksum: int

    @property
    def length(self) -> int:
        return len(self.data)

    @property
    def format_name(self) -> str:
        return "TC-9" if self.length == TC_PACKET_LEN else "GL-21"

    def hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)


def normalize_axes(axes: Axes) -> Axes:
    """
    Clamping exactly as FlyControlTask.run() lines 130-147:
      controlTurn / controlByte1 / controlByte2 clamped to [1, 255]
      controlAccelerator: only ``== 1 -> 0``; no other clamp in the source.
    The source never produces a throttle outside [0, 255]; we clamp to a byte so a
    bad caller cannot raise here (Java's (byte) cast would silently wrap instead).
    """
    def clamp(v: int) -> int:
        return max(CONTROL_VALUES_MIN, min(CONTROL_VALUES_MAX, int(v)))

    throttle = int(axes.throttle)
    if throttle == 1:
        throttle = 0
    throttle = max(0, min(255, throttle))
    return Axes(roll=clamp(axes.roll), pitch=clamp(axes.pitch), throttle=throttle, yaw=clamp(axes.yaw))


def tc_flags_byte(flags: FlightFlags) -> int:
    """
    byte5 of the 9-byte packet (``r7`` in FlyControlTask.run, lines 104-129):
      bit0 fastFly, bit1 fastDrop, bit2 emergencyStop, bit3 circleTurnEnd,
      bit4 noHeadMode, bit7 gyroCorrection.
    bit5 (isFastReturn || isUnLock) is mangled by the decompiler, but neither field
    has a setter anywhere in the app, so it is always 0.
    """
    value = 0
    if flags.fast_fly:
        value += 1
    if flags.fast_drop:
        value += 2
    if flags.emergency_stop:
        value += 4
    if flags.circle_turn_end:
        value += 8
    if flags.no_head:
        value += 16
    if flags.gyro_correction:
        value += 128
    return value


def gl_flags_bytes(flags: FlightFlags) -> Tuple[int, int]:
    """
    ``i2`` and ``r9`` in FlyControlTask.run lines 150-167:
      F1: bit0 (fastFly OR fastDrop), bit1 emergencyStop, bit2 gyroCorrection,
          bit3 circleTurnEnd, bit6 gestureMode
      F2: bit0 noHeadMode, bit1 fixedHeightMode
    NOTE: takeoff and land share bit0 in this format.
    """
    f1 = 1 if (flags.fast_fly or flags.fast_drop) else 0
    if flags.emergency_stop:
        f1 += 2
    if flags.gyro_correction:
        f1 += 4
    if flags.circle_turn_end:
        f1 += 8
    if flags.gesture:
        f1 += 64
    f2 = 1 if flags.no_head else 0
    if flags.fixed_height:
        f2 += 2
    return f1, f2


def build_tc_packet(axes: Axes, flags: FlightFlags) -> FlightPacket:
    a = normalize_axes(axes)
    f = tc_flags_byte(flags)
    chk = (a.roll ^ a.pitch ^ a.throttle ^ a.yaw ^ f) & 0xFF
    body = bytes([CONTROL_VALUES_BYTE0, a.roll, a.pitch, a.throttle, a.yaw, f, chk, CONTROL_VALUES_BYTE7])
    return FlightPacket(bytes([FLIGHT_PREFIX]) + body, DEVICE_TYPE_TC, a, (f,), chk)


def build_gl_packet(axes: Axes, flags: FlightFlags, device_type: int = DEVICE_TYPE_GL) -> FlightPacket:
    a = normalize_axes(axes)
    f1, f2 = gl_flags_bytes(flags)
    chk = (f1 ^ a.pitch ^ a.roll ^ a.throttle ^ a.yaw ^ f2) & 0xFF
    body = bytes([CONTROL_VALUES_BYTE0, GL_LENGTH_BYTE, a.roll, a.pitch, a.throttle, a.yaw, f1, f2]) \
        + bytes(10) + bytes([chk, CONTROL_VALUES_BYTE7])
    return FlightPacket(bytes([FLIGHT_PREFIX]) + body, device_type, a, (f1, f2), chk)


def build_flight_packet(device_type: int, axes: Axes, flags: FlightFlags) -> FlightPacket:
    """``if (getDeviceType() != 10) -> 21-byte else -> 9-byte`` (FlyController.java line 149)."""
    if device_type == DEVICE_TYPE_TC:
        return build_tc_packet(axes, flags)
    return build_gl_packet(axes, flags, device_type)


def decode_flight_packet(data: bytes) -> Dict[str, object]:
    """Inverse of the builders, for logging and for checking captures from the Android app."""
    if len(data) == TC_PACKET_LEN and data[0] == FLIGHT_PREFIX and data[1] == CONTROL_VALUES_BYTE0:
        r, p, t, y, f, chk = data[2:8]
        return {
            "format": "TC-9", "roll": r, "pitch": p, "throttle": t, "yaw": y,
            "flags": (f,), "checksum": chk,
            "checksum_ok": chk == (r ^ p ^ t ^ y ^ f) & 0xFF,
            "terminator_ok": data[8] == CONTROL_VALUES_BYTE7,
        }
    if len(data) == GL_PACKET_LEN and data[0] == FLIGHT_PREFIX and data[1] == CONTROL_VALUES_BYTE0 \
            and data[2] == GL_LENGTH_BYTE:
        r, p, t, y, f1, f2 = data[3:9]
        chk = data[19]
        return {
            "format": "GL-21", "roll": r, "pitch": p, "throttle": t, "yaw": y,
            "flags": (f1, f2), "checksum": chk,
            "checksum_ok": chk == (f1 ^ r ^ p ^ t ^ y ^ f2) & 0xFF,
            "terminator_ok": data[20] == CONTROL_VALUES_BYTE7,
            "padding": data[9:19].hex(),
        }
    return {"format": "UNKNOWN", "length": len(data)}
