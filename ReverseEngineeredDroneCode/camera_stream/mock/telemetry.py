"""
Mock telemetry generator.
Simulates drone sensor and status data for offline testing.
"""

import math
import random
import threading
import time
from drone.state import DroneState


class MockTelemetryProvider:
    """
    Background worker simulating drone telemetry updates into DroneState.
    """

    def __init__(self, drone_state: DroneState, update_rate_hz: float = 2.0):
        self._drone_state = drone_state
        self._interval = 1.0 / max(update_rate_hz, 0.5)
        self._running = False
        self._thread = None
        self._start_time = time.time()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, name="MockTelemetryWorker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _worker(self) -> None:
        battery = 92
        self._drone_state.update_connection(True, ssid="WIFIPD_4K_FLOW_8830")
        self._drone_state.update_device_id(90)  # GL Drone model 90

        while self._running:
            t = time.time() - self._start_time

            # Slow realistic battery discharge
            voltage = round(3.7 + 0.5 * (battery / 100.0) + random.uniform(-0.02, 0.02), 2)
            if int(t) % 60 == 0 and battery > 20:
                battery -= 1

            # Realistic Wi-Fi RSSI jitter (-45 to -65 dBm)
            rssi = int(-52 + 8 * math.sin(t * 0.1) + random.randint(-3, 3))

            self._drone_state.update_mock_telemetry(
                battery_pct=battery,
                voltage=voltage,
                rssi=rssi,
                source="Simulated Drone Engine"
            )

            time.sleep(self._interval)
