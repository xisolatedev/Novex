"""
Client for the Novex VIO daemon (../c_prog), the only source of MEASURED motion.

Speaks the daemon's own line protocol (c_prog/include/StateServer.hpp): one command
per line, one JSON line back.

    GET_STATE -> {"velocity":[x,y,z], "orientation":[x,y,z,w], "tracking":..., "lost_frames":..., ...}
    GET_FLOOR -> {"valid":..., "confidence":..., "reported_plane":[nx,ny,nz,d], ...}

Both are in the VIO "reported" frame (StateEstimator.cpp L117-122 and
StateServer::formatFloor). The daemon listens on a Unix socket, /tmp/novex-vio.sock by
default (VIOConfig.hpp), which is local to the Pi. From the PC, forward it over SSH:

    ssh -N -L 7700:/tmp/novex-vio.sock pi@<pi-address>
    python main.py --vio tcp://127.0.0.1:7700

or, if the daemon runs on the same machine, --vio unix:/tmp/novex-vio.sock.
"""

import json
import logging
import socket
import threading
import time
from typing import Callable, Optional, Tuple

from controller.face_travel import MotionSample

logger = logging.getLogger(__name__)

DEFAULT_POLL_HZ = 20.0
FLOOR_EVERY_N = 4                 # the floor changes slowly: ~5 Hz at 20 Hz polling


def parse_address(address: str) -> Tuple[int, object]:
    """'tcp://host:port' | 'unix:/path' | '/path' -> (family, sockaddr)."""
    if address.startswith("tcp://"):
        host, _, port = address[len("tcp://"):].rpartition(":")
        if not host or not port.isdigit():
            raise ValueError(f"bad VIO address {address!r}, expected tcp://host:port")
        return socket.AF_INET, (host, int(port))
    if address.startswith("unix:"):
        return socket.AF_UNIX, address[len("unix:"):]
    if address.startswith("/"):
        return socket.AF_UNIX, address
    raise ValueError(f"bad VIO address {address!r}, expected tcp://host:port or unix:/path")


def sample_from_json(state: dict, floor: Optional[dict], received: float) -> MotionSample:
    """Build a MotionSample from GET_STATE (+ the latest GET_FLOOR) replies."""
    up = None
    confidence = 0.0
    if floor and floor.get("valid"):
        plane = floor.get("reported_plane") or []
        if len(plane) >= 3:
            up = (float(plane[0]), float(plane[1]), float(plane[2]))
            confidence = float(floor.get("confidence", 0.0))
    v = state["velocity"]
    q = state["orientation"]
    return MotionSample(
        received=received,
        velocity=(float(v[0]), float(v[1]), float(v[2])),
        orientation=(float(q[0]), float(q[1]), float(q[2]), float(q[3])),
        up=up,
        tracking=bool(state.get("tracking", False)),
        lost_frames=int(state.get("lost_frames", 0)),
        floor_confidence=confidence,
    )


class VioClient:
    def __init__(self, address: str, poll_hz: float = DEFAULT_POLL_HZ,
                 record_path: Optional[str] = None, reconnect_interval: float = 1.0,
                 clock: Callable[[], float] = time.monotonic, timeout: float = 0.5):
        self.address = address
        self._family, self._sockaddr = parse_address(address)
        self._interval = 1.0 / poll_hz
        self._reconnect_interval = reconnect_interval
        self._clock = clock
        self._timeout = timeout
        self._record = open(record_path, "a", encoding="utf-8") if record_path else None
        self._lock = threading.Lock()
        self._latest: Optional[MotionSample] = None
        self._floor: Optional[dict] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._sock: Optional[socket.socket] = None
        self.connected = False
        self.last_error = ""
        self.samples = 0

    # ---- lifecycle --------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="VioClient", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._close()
        if self._record:
            self._record.close()
            self._record = None

    def latest(self) -> Optional[MotionSample]:
        """The motion source for FaceTravel. None until a sample has arrived."""
        with self._lock:
            return self._latest

    def status(self) -> str:
        if not self.connected:
            return f"not connected ({self.last_error or 'connecting'}) {self.address}"
        s = self.latest()
        if s is None:
            return f"connected {self.address}, no sample yet"
        age = self._clock() - s.received
        floor = "floor ok" if s.up is not None else "NO FLOOR"
        return (f"{self.address}  tracking={'yes' if s.tracking else 'NO'}  "
                f"{floor}  age={age * 1000:.0f}ms  samples={self.samples}")

    # ---- worker -----------------------------------------------------------------

    def _connect(self) -> bool:
        try:
            sock = socket.socket(self._family, socket.SOCK_STREAM)
            sock.settimeout(self._timeout)
            sock.connect(self._sockaddr)
        except OSError as e:
            self.last_error = str(e)
            return False
        self._sock = sock
        self._rfile = sock.makefile("rb")
        self.connected = True
        self.last_error = ""
        logger.info("VIO connected: %s", self.address)
        return True

    def _close(self) -> None:
        was = self.connected
        self.connected = False
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        if was:
            logger.warning("VIO disconnected: %s", self.last_error or "closed")

    def _request(self, command: str) -> dict:
        assert self._sock is not None
        self._sock.sendall(command.encode("ascii") + b"\n")
        line = self._rfile.readline()
        if not line:
            raise ConnectionError("VIO daemon closed the connection")
        text = line.decode("utf-8", "replace").strip()
        if self._record:
            self._record.write(f"{self._clock():.6f}\t{command}\t{text}\n")
        reply = json.loads(text)
        if "error" in reply:
            raise ValueError(f"VIO replied error to {command}: {reply['error']}")
        return reply

    def _run(self) -> None:
        tick = 0
        while not self._stop.is_set():
            if self._sock is None and not self._connect():
                self._stop.wait(self._reconnect_interval)
                continue
            started = self._clock()
            try:
                if tick % FLOOR_EVERY_N == 0:
                    self._floor = self._request("GET_FLOOR")
                state = self._request("GET_STATE")
                sample = sample_from_json(state, self._floor, self._clock())
                with self._lock:
                    self._latest = sample
                self.samples += 1
                tick += 1
            except (OSError, ValueError, KeyError, IndexError, ConnectionError) as e:
                self.last_error = str(e)
                self._close()
                self._stop.wait(self._reconnect_interval)
                continue
            self._stop.wait(max(0.0, self._interval - (self._clock() - started)))
        self._close()
