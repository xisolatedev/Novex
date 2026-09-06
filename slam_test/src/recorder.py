"""
Recording and replay of the raw stereo stream.

The point of this is repeatability: walk around the room once, then
replay that exact walk through ORB-SLAM3 as many times as you like
while changing parameters. Debugging SLAM against a live camera means
never running the same input twice.

What is recorded is the RAW combined 2560x720 frame, before any
rectification. That matters - if the calibration is later redone, an
old recording is still usable, because the pixels were never altered.

Layout of a recording:

    recordings/2026-09-05_14-31-02/
        stereo.avi        MJPG, the raw combined frames
        timestamps.txt    one capture timestamp per frame, seconds
        meta.yaml         resolution, requested/actual mode, fps

Encoding runs on its own thread behind a bounded queue. If the disk
cannot keep up, frames are DROPPED and counted, rather than stalling
the SLAM thread. The drop count is shown in the debug panel; a
recording with drops is still replayable, just sparser.
"""

import os
import queue
import threading
import time
import datetime

import cv2
import yaml


class StereoRecorder:
    def __init__(self, root, max_queue=8):
        self.root = root
        self.max_queue = max_queue

        self.is_recording = False
        self.path = None

        self._writer = None
        self._timestamps = None
        self._queue = None
        self._thread = None
        self._stop = threading.Event()

        self.frames_written = 0
        self.frames_dropped = 0
        self.error = None

    # ----------------------------------------------------------
    def start(self, camera):
        if self.is_recording:
            return self.path

        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.path = os.path.join(self.root, stamp)
        os.makedirs(self.path, exist_ok=True)

        w = camera.actual["width"]
        h = camera.actual["height"]
        fps = camera.measured_fps or camera.actual["fps"] or 30.0

        video = os.path.join(self.path, "stereo.avi")

        # MJPG, matching what the camera already delivers, so the
        # recording is a faithful copy rather than a re-encode into a
        # lossier codec.
        self._writer = cv2.VideoWriter(
            video,
            cv2.VideoWriter_fourcc(*"MJPG"),
            float(fps),
            (w, h),
        )

        if not self._writer.isOpened():
            self.error = f"Could not open {video} for writing"
            self._writer = None
            return None

        with open(os.path.join(self.path, "meta.yaml"), "w") as f:
            yaml.safe_dump(
                {
                    "created": stamp,
                    "width": w,
                    "height": h,
                    "eye_width": w // 2,
                    "eye_height": h,
                    "fps": float(fps),
                    "requested": camera.requested,
                    "actual": camera.actual,
                    "note": "Raw combined frames, no rectification applied.",
                },
                f,
                sort_keys=False,
            )

        self._timestamps = open(os.path.join(self.path, "timestamps.txt"), "w")
        self._queue = queue.Queue(maxsize=self.max_queue)
        self._stop.clear()

        self.frames_written = 0
        self.frames_dropped = 0

        self._thread = threading.Thread(
            target=self._writer_loop, name="novex-recorder", daemon=True
        )
        self._thread.start()

        self.is_recording = True
        return self.path

    # ----------------------------------------------------------
    def write(self, frame):
        """Called from the SLAM thread. Never blocks."""
        if not self.is_recording or self._queue is None:
            return

        try:
            self._queue.put_nowait((frame.combined, frame.timestamp))
        except queue.Full:
            self.frames_dropped += 1

    def _writer_loop(self):
        while not self._stop.is_set() or not self._queue.empty():
            try:
                image, ts = self._queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                self._writer.write(image)
                self._timestamps.write(f"{ts:.6f}\n")
                self.frames_written += 1
            except Exception as exc:  # noqa: BLE001
                self.error = f"Write failed: {exc}"
                break

    # ----------------------------------------------------------
    def stop(self):
        if not self.is_recording:
            return None

        self.is_recording = False
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None

        if self._writer is not None:
            self._writer.release()
            self._writer = None

        if self._timestamps is not None:
            self._timestamps.close()
            self._timestamps = None

        return self.path

    def status(self):
        if not self.is_recording:
            return "off"
        return f"REC {self.frames_written} frames ({self.frames_dropped} dropped)"


# ==============================================================
class ReplayCamera:
    """A recording, presented with the same interface as StereoCamera.

    Everything downstream - rectification, SLAM, the GUI - is unaware
    it is not looking at a live camera. That is the whole point: the
    replay path exercises the identical pipeline.
    """

    def __init__(self, path, realtime=True, loop=False):
        self.path = path
        self.realtime = realtime
        self.loop = loop

        meta_path = os.path.join(path, "meta.yaml")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(f"{path} is not a Novex recording (no meta.yaml)")

        with open(meta_path) as f:
            self.meta = yaml.safe_load(f)

        ts_path = os.path.join(path, "timestamps.txt")
        with open(ts_path) as f:
            self.timestamps = [float(line) for line in f if line.strip()]

        self.video_path = os.path.join(path, "stereo.avi")

        self.requested = self.meta.get("requested", {})
        self.actual = self.meta.get("actual", {})
        self.actual.setdefault("width", self.meta["width"])
        self.actual.setdefault("height", self.meta["height"])

        self._cap = None
        self._lock = threading.Lock()
        self._frame = None
        self._frame_id = 0
        self._running = False
        self._thread = None

        self.measured_fps = 0.0
        self.read_failures = 0
        self.error = None
        self.finished = False

    def open(self):
        self._cap = cv2.VideoCapture(self.video_path)
        if not self._cap.isOpened():
            self.error = f"Could not open {self.video_path}"
            return False
        return True

    def mode_warnings(self):
        return [f"REPLAY from {self.path} - this is not a live camera."]

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, name="novex-replay", daemon=True
        )
        self._thread.start()

    def _loop(self):
        from camera import StereoFrame

        index = 0
        t0_wall = time.perf_counter()
        t0_rec = self.timestamps[0] if self.timestamps else 0.0

        while self._running:
            ok, image = self._cap.read()

            if not ok:
                if self.loop:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    index = 0
                    t0_wall = time.perf_counter()
                    continue
                self.finished = True
                break

            if self.realtime and index < len(self.timestamps):
                # Reproduce the original inter-frame timing so SLAM
                # sees the same motion rate it would see live.
                target = self.timestamps[index] - t0_rec
                elapsed = time.perf_counter() - t0_wall
                if target > elapsed:
                    time.sleep(target - elapsed)

            now = time.perf_counter()

            with self._lock:
                self._frame_id += 1
                self._frame = StereoFrame(
                    combined=image,
                    frame_id=self._frame_id,
                    timestamp=self.timestamps[index]
                    if index < len(self.timestamps)
                    else now,
                    capture_ms=0.0,
                )

            index += 1

            if index > 1 and self.timestamps:
                span = now - t0_wall
                if span > 0:
                    self.measured_fps = index / span

    def read(self):
        with self._lock:
            return self._frame

    def read_new(self, last_frame_id):
        with self._lock:
            if self._frame is None or self._frame.frame_id <= last_frame_id:
                return None
            return self._frame

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
