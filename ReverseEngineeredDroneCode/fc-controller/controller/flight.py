"""
The 20 Hz flight-control loop (FlyController.setController + FlyControlTask).

keyboard state -> ControllerState -> map_keys_to_axes -> build_flight_packet -> sender

The sender is DroneLink.send, i.e. the same UDP socket that carries the heartbeat,
exactly like SocketClient.debugSend(). When the link is down the send is dropped,
as in the app where debugSend() is a no-op once udpComm is null.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from .keyboard import KeyboardState, map_inputs_to_axes
from .protocol import (
    CMD_CONTROL_OFF,
    CONTROL_VALUES_DEFAULT,
    DEVICE_TYPE_GL,
    SEND_COMMAND_INTERVAL_S,
    FlightPacket,
    build_flight_packet,
)
from .state import ControllerState

logger = logging.getLogger(__name__)

Sender = Callable[[bytes], bool]


@dataclass
class TxStats:
    sent: int = 0
    dropped: int = 0
    last_packet: Optional[FlightPacket] = None
    last_sent_ok: bool = False
    last_tx_time: float = 0.0


class FlightController:
    def __init__(
        self,
        sender: Sender,
        device_type: Callable[[], int],
        keyboard: Optional[KeyboardState] = None,
        state: Optional[ControllerState] = None,
        packet_logger=None,
        clock: Callable[[], float] = time.monotonic,
        interval_s: float = SEND_COMMAND_INTERVAL_S,
        gamepad=None,
        face_travel=None,
    ):
        self._send = sender
        self._device_type = device_type
        self.keyboard = keyboard or KeyboardState()
        self.gamepad = gamepad
        self.face_travel = face_travel
        self.state = state or ControllerState(clock)
        self._packet_logger = packet_logger
        self._clock = clock
        self._interval = interval_s
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._tick_lock = threading.Lock()
        self.stats = TxStats()

    # ---- control mode (FlyController.setController) -----------------------------

    def set_control_mode(self, enabled: bool) -> None:
        if enabled:
            if self._thread is not None:
                return
            # DeviceBLFragment.updateModeUI(): throttle 128 in fixed-height, else 0 (rocker at bottom).
            self.state.manual_throttle = CONTROL_VALUES_DEFAULT if self.state.fixed_height else 0
            self.state.control_mode = True
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="FlyControlTask", daemon=True)
            self._thread.start()
            logger.info("Control mode ON: flight packets every %.0f ms", self._interval * 1000)
            if self._packet_logger:
                self._packet_logger.log_event(
                    "CONTROL MODE ON",
                    f"fixed_height={self.state.fixed_height} throttle_init={self.state.manual_throttle} "
                    f"power={self.state.power}; first packet in {self._interval * 1000:.0f} ms")
            return

        self.state.control_mode = False
        thread, self._thread = self._thread, None
        if thread is None:
            return
        self._stop.set()
        thread.join(timeout=1.0)
        # setController(false): timer.cancel(); debugSend({8, 1})
        if self._packet_logger:
            self._packet_logger.log_event("CONTROL MODE OFF", "20 Hz loop stopped; sending 08 01")
        ok = self._send(CMD_CONTROL_OFF)
        if self._packet_logger:
            self._packet_logger.log_command("CONTROL OFF", CMD_CONTROL_OFF, ok)
        logger.info("Control mode OFF: sent 08 01 (%s)", "ok" if ok else "link down")

    def toggle_control_mode(self) -> bool:
        self.set_control_mode(not self.state.control_mode)
        return self.state.control_mode

    @property
    def running(self) -> bool:
        return self._thread is not None

    # ---- one-button actions -----------------------------------------------------

    def _action(self, name: str, fn: Callable[[], bool], needs_fixed_height: bool) -> str:
        def refuse(reason: str) -> str:
            msg = f"{name} ignored: {reason}"
            logger.warning(msg)
            if self._packet_logger:
                self._packet_logger.log_event("ACTION REFUSED", msg)
            return msg

        if not self.state.control_mode:
            return refuse("control mode is OFF (no flight packets are being sent)")
        if needs_fixed_height and not self.state.fixed_height:
            # updateFixHeightUI(false) hides takeoff/land/stop buttons in the app.
            return refuse("only available in fixed-height mode (as in the app)")
        if not fn():
            return refuse("already active")
        logger.warning("%s: flag pulse started", name)
        if self._packet_logger:
            self._packet_logger.log_event("ACTION", f"{name} flag pulse started")
        return f"{name} sent"

    def takeoff(self) -> str:
        """view_control_device_take_off -> FlyController.setFastFly (flag for 1000 ms)."""
        return self._action("TAKEOFF", self.state.fast_fly, needs_fixed_height=True)

    def land(self) -> str:
        """view_control_device_land -> FlyController.setFastDrop (flag for 1000 ms)."""
        return self._action("LAND", self.state.fast_drop, needs_fixed_height=True)

    def emergency_stop(self) -> str:
        """view_control_device_emergency_stop -> FlyController.setEmergencyStop (flag for 1000 ms).
        The app hides this button outside fixed-height mode; we keep it available (same packet)."""
        return self._action("EMERGENCY STOP", self.state.emergency_stop, needs_fixed_height=False)

    def gyro_calibrate(self) -> str:
        """view_device_mode_gyroscope -> FlyController.setGyroCorrection (flag for 2000 ms)."""
        return self._action("GYRO CALIBRATION", self.state.gyro_correction, needs_fixed_height=False)

    def set_fixed_height(self, enabled: bool) -> str:
        """DeviceBLFragment.onItemClick(tab_fixed_height): refused when deviceType == GL."""
        if self._device_type() == DEVICE_TYPE_GL and not enabled:
            return "Fixed-height cannot be turned off on GL devices (as in the app)"
        self.state.fixed_height = enabled
        self.state.manual_throttle = CONTROL_VALUES_DEFAULT if enabled else 0
        return f"Fixed-height {'ON' if enabled else 'OFF'}"

    # ---- the loop ----------------------------------------------------------------

    def gamepad_axes(self) -> Optional[dict]:
        """Deadzoned stick values, or None when no gamepad is connected."""
        if self.gamepad is None or not getattr(self.gamepad, "connected", False):
            return None
        return self.gamepad.axes()

    def build_current_packet(self, now: Optional[float] = None) -> FlightPacket:
        snap = self.state.snapshot(now)
        ft = self.face_travel
        # Disabled means not called at all: yaw behaves exactly as before.
        transform = ft.apply if ft is not None and ft.enabled else None
        mapping = map_inputs_to_axes(self.keyboard.held(), snap.half_len, snap.fixed_height,
                                     self.state.manual_throttle, self.gamepad_axes(), transform)
        self.state.manual_throttle = mapping.manual_throttle
        return build_flight_packet(self._device_type(), mapping.axes, snap.flags)

    def tick(self, now: Optional[float] = None) -> FlightPacket:
        with self._tick_lock:
            packet = self.build_current_packet(now)
            ok = self._send(packet.data)
            self.stats.last_packet = packet
            self.stats.last_sent_ok = ok
            self.stats.last_tx_time = time.time()
            if ok:
                self.stats.sent += 1
            else:
                self.stats.dropped += 1
            if self._packet_logger:
                self._packet_logger.log_flight(packet, ok)
            return packet

    def _run(self) -> None:
        # timer.schedule(new FlyControlTask(), 50L, 50L): first send after one interval.
        next_at = self._clock() + self._interval
        while not self._stop.wait(max(0.0, next_at - self._clock())):
            try:
                self.tick()
            except Exception:
                logger.exception("flight tick failed")
            next_at += self._interval
            if next_at < self._clock():   # fell behind (e.g. suspended): don't burst
                next_at = self._clock() + self._interval

    def shutdown(self) -> None:
        self.keyboard.release_all()
        self.set_control_mode(False)
