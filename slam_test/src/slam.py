"""
The ORB-SLAM3 worker thread.

This is where real ORB-SLAM3 runs. Every pose, tracking state, feature
count, map point and keyframe the GUI displays originates in the
native ORB-SLAM3 library through the pybind11 module built in
native/. Nothing here simulates, smooths or invents motion. If
ORB-SLAM3 does not know where the camera is, this module reports that
rather than filling the gap.

Pipeline, all inside this one thread:

    newest synchronized frame from the capture thread
        -> split into left / right (same frame, always)
        -> fisheye rectification with precomputed maps
        -> grayscale
        -> ORB_SLAM3::System::TrackStereo
        -> pose + state + keypoints published as an immutable snapshot

The GUI never calls into ORB-SLAM3 itself; it only reads the latest
published snapshot. That keeps rendering off the SLAM thread and SLAM
off the GUI thread.
"""

import os
import sys
import threading
import time
import traceback

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trajectory import Pose, Trajectory  # noqa: E402


# --------------------------------------------------------------
# Import the native module, and if it is missing say exactly why.
# --------------------------------------------------------------
NATIVE_IMPORT_ERROR = None

try:
    import novex_orbslam3
except ImportError as exc:  # pragma: no cover
    novex_orbslam3 = None
    NATIVE_IMPORT_ERROR = str(exc)


# ORB_SLAM3::Tracking::eTrackingState
STATE_NAMES = {
    -1: "SYSTEM_NOT_READY",
    0: "NO_IMAGES_YET",
    1: "NOT_INITIALIZED",
    2: "OK",
    3: "RECENTLY_LOST",
    4: "LOST",
    5: "OK_KLT",
}

STATE_HINTS = {
    -1: "ORB-SLAM3 has not finished starting up.",
    0: "Waiting for the first images.",
    1: "Waiting for motion. Move the camera sideways, not by rotating on the spot.",
    2: "Tracking.",
    3: "Lost recently - ORB-SLAM3 is trying to relocalise. Return the camera "
       "towards a view it has already seen.",
    4: "Tracking lost. Point at a textured, well-lit area, or press R to reset.",
    5: "Tracking (KLT).",
}


class SlamResult:
    """One immutable snapshot published by the worker."""

    __slots__ = (
        "frame_id", "timestamp",
        "left_rect", "right_rect",
        "keypoints", "keypoints_right", "kp_tracked", "kp_stereo", "kp_depth",
        "state", "state_name",
        "pose",
        "num_keypoints", "num_keypoints_right", "num_tracked", "num_stereo",
        "mean_depth", "min_depth", "max_depth",
        "rectify_ms", "track_ms", "total_ms",
    )

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


class MapSnapshot:
    __slots__ = ("points", "keyframes", "num_points", "num_keyframes", "num_maps")

    def __init__(self, points, keyframes, stats):
        self.points = points
        self.keyframes = keyframes
        self.num_points = stats.get("map_points", 0)
        self.num_keyframes = stats.get("keyframes", 0)
        self.num_maps = stats.get("num_maps", 0)


class PlaneWorker(threading.Thread):
    """Fits planes to the map cloud on its own thread.

    Kept off the SLAM thread deliberately: a RANSAC pass over a few
    thousand points costs tens of milliseconds, which would show up as
    a periodic stall in tracking. Here it just runs whenever it can and
    publishes whatever it last found.
    """

    def __init__(self, worker, cfg):
        super().__init__(name="novex-planes", daemon=True)

        self.worker = worker
        self.cfg = cfg or {}
        self.interval = float(self.cfg.get("interval_s", 1.5))

        self._lock = threading.Lock()
        self._planes = []
        self._ground = None
        self._running = False
        self.last_ms = 0.0
        self.error = None

    def run(self):
        from planes import detect_planes, classify_ground, down_from_poses

        self._running = True
        while self._running:
            time.sleep(self.interval)

            snapshot = self.worker.latest_map()
            pts = snapshot.points

            if pts is None or len(pts) < self.cfg.get("min_inliers", 60):
                continue

            try:
                t0 = time.perf_counter()
                planes = detect_planes(
                    pts,
                    max_planes=int(self.cfg.get("max_planes", 3)),
                    threshold=float(self.cfg.get("threshold_m", 0.04)),
                    iterations=int(self.cfg.get("iterations", 150)),
                    min_inliers=int(self.cfg.get("min_inliers", 60)),
                    max_points=int(self.cfg.get("max_points", 3000)),
                )

                # "Down" is assumed from the cameras' own +Y axes; there
                # is no IMU, so this is an assumption, not gravity.
                recent = self.worker.recent_poses()
                down = down_from_poses([p.Twc for p in recent]) if recent else None
                positions = [p.position for p in recent] if recent else None

                ground = classify_ground(planes, down, positions)
                self.last_ms = (time.perf_counter() - t0) * 1000.0

                with self._lock:
                    self._planes = planes
                    self._ground = ground
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)

    def latest(self):
        with self._lock:
            return self._planes, self._ground

    def stop(self):
        self._running = False


class SlamWorker(threading.Thread):
    """Runs ORB-SLAM3 over the live stereo stream."""

    def __init__(
        self,
        camera,
        rectifier,
        vocabulary_path,
        settings_path,
        use_orbslam_viewer=False,
        map_update_every=10,
        recorder=None,
        verbosity=1,
    ):
        super().__init__(name="novex-slam", daemon=True)

        self.camera = camera
        self.rectifier = rectifier
        self.vocabulary_path = vocabulary_path
        self.settings_path = settings_path
        self.use_orbslam_viewer = use_orbslam_viewer
        self.map_update_every = map_update_every
        self.recorder = recorder
        self.verbosity = verbosity

        self.slam = None
        self.trajectory = Trajectory()

        self._lock = threading.Lock()
        self._result = None
        self._map = MapSnapshot(
            np.zeros((0, 3), np.float32),
            np.zeros((0, 3), np.float32),
            {},
        )

        self._running = False
        self._reset_requested = False

        self.ready = threading.Event()
        self.error = None
        self.startup_seconds = 0.0

        self.cpu_cores = None
        self.affinity_status = "slam: not pinned"
        self.affinity_changes = []
        self.slam_fps = 0.0
        self._fps_window = []

        self._last_state = -1
        self._recent_poses = []
        self.frames_processed = 0
        self.frames_skipped = 0

    # ----------------------------------------------------------
    @staticmethod
    def native_available():
        return novex_orbslam3 is not None

    @staticmethod
    def native_error():
        return NATIVE_IMPORT_ERROR

    # ----------------------------------------------------------
    def run(self):
        # Pin BEFORE constructing the System. ORB-SLAM3's LocalMapping
        # and LoopClosing threads are created inside that constructor,
        # and the per-frame ORB extractor threads are spawned during
        # tracking - all of them inherit this mask, so pinning here
        # confines the whole SLAM system to the chosen cores.
        if self.cpu_cores:
            from affinity import pin_current_thread
            self.affinity_status = pin_current_thread(self.cpu_cores, "slam")

        if novex_orbslam3 is None:
            self.error = (
                "The ORB-SLAM3 Python module is not built.\n"
                f"Import error: {NATIVE_IMPORT_ERROR}\n\n"
                "Build it with:\n"
                "    bash scripts/01_build_orbslam3.sh\n"
                "    bash scripts/02_build_binding.sh"
            )
            self.ready.set()
            return

        for path, what in (
            (self.vocabulary_path, "ORB vocabulary"),
            (self.settings_path, "ORB-SLAM3 settings"),
        ):
            if not os.path.exists(path):
                self.error = f"{what} not found at {path}"
                self.ready.set()
                return

        try:
            t0 = time.perf_counter()
            # Blocks for 10-20 s loading the vocabulary. The GIL is
            # released inside the binding so the camera keeps running.
            self.slam = novex_orbslam3.StereoSlam(
                vocabulary=self.vocabulary_path,
                settings=self.settings_path,
                use_viewer=self.use_orbslam_viewer,
                verbosity=self.verbosity,
            )
            self.startup_seconds = time.perf_counter() - t0
        except Exception as exc:  # noqa: BLE001
            self.error = (
                f"ORB-SLAM3 failed to start: {exc}\n\n"
                f"{traceback.format_exc()}"
            )
            self.ready.set()
            return

        self._running = True
        self.ready.set()

        self._loop()

    def confine_helpers(self, exempt_tids):
        """Sweep OpenCV's worker pool onto the SLAM cores.

        Called once after the pipeline is warm, because the pool does
        not exist until parallel work has actually run.
        """
        if not self.cpu_cores:
            return []
        from affinity import confine_stray_threads
        changes = confine_stray_threads(self.cpu_cores, exempt_tids)
        self.affinity_changes = changes
        return changes

    # ----------------------------------------------------------
    def _loop(self):
        last_frame_id = 0
        map_counter = 0

        while self._running:
            if self._reset_requested:
                self._do_reset()

            frame = self.camera.read_new(last_frame_id)

            if frame is None:
                # No new frame. Never re-track a frame we have already
                # processed - that would burn CPU and, worse, feed
                # ORB-SLAM3 a duplicate observation.
                time.sleep(0.001)
                continue

            if frame.frame_id > last_frame_id + 1:
                self.frames_skipped += frame.frame_id - last_frame_id - 1

            last_frame_id = frame.frame_id
            t_start = time.perf_counter()

            # --- rectify -------------------------------------------
            # left and right come from the SAME captured buffer, so
            # they are synchronized by construction.
            #
            # Grayscale conversion happens BEFORE rectification, not
            # after. ORB-SLAM3 only ever works on grayscale, and
            # remapping one channel instead of three measures about
            # 35% faster on this pipeline (16 ms vs 24 ms per pair at
            # 1280x720). The GUI then displays exactly the images
            # ORB-SLAM3 was given, which is what you want from a
            # debugging tool.
            if frame.left.ndim == 3:
                gray_l_raw = cv2.cvtColor(frame.left, cv2.COLOR_BGR2GRAY)
                gray_r_raw = cv2.cvtColor(frame.right, cv2.COLOR_BGR2GRAY)
            else:
                gray_l_raw, gray_r_raw = frame.left, frame.right

            gray_l, gray_r = self.rectifier.rectify(gray_l_raw, gray_r_raw)

            left_rect, right_rect = gray_l, gray_r

            t_rect = time.perf_counter()

            if self.recorder is not None and self.recorder.is_recording:
                self.recorder.write(frame)

            # --- track ---------------------------------------------
            try:
                out = self.slam.track_stereo(gray_l, gray_r, frame.timestamp)
            except Exception as exc:  # noqa: BLE001
                self.error = f"TrackStereo raised: {exc}"
                self._running = False
                break

            t_track = time.perf_counter()

            state = int(out["state"])

            # A pose is only meaningful when ORB-SLAM3 says it is
            # tracking. In every other state the returned matrix is
            # stale or undefined, so it is discarded rather than drawn.
            pose = None
            if state in (2, 5):
                pose = Pose(np.asarray(out["Tcw"], dtype=np.float64), frame.timestamp)
                self.trajectory.append(pose)
                with self._lock:
                    self._recent_poses.append(pose)
                    if len(self._recent_poses) > 120:
                        self._recent_poses = self._recent_poses[-120:]
            elif self._last_state in (2, 5):
                self.trajectory.mark_break()

            self._last_state = state

            result = SlamResult(
                frame_id=frame.frame_id,
                timestamp=frame.timestamp,
                left_rect=left_rect,
                right_rect=right_rect,
                keypoints=out["keypoints"],
                keypoints_right=out.get("keypoints_right"),
                kp_tracked=out["kp_tracked"],
                kp_stereo=out.get("kp_stereo"),
                kp_depth=out.get("kp_depth"),
                state=state,
                state_name=STATE_NAMES.get(state, f"UNKNOWN({state})"),
                pose=pose,
                num_keypoints=int(out["num_keypoints"]),
                num_keypoints_right=int(out.get("num_keypoints_right", 0)),
                num_tracked=int(out["num_tracked"]),
                num_stereo=int(out.get("num_stereo", 0)),
                mean_depth=float(out.get("mean_depth", 0.0)),
                min_depth=float(out.get("min_depth", 0.0)),
                max_depth=float(out.get("max_depth", 0.0)),
                rectify_ms=(t_rect - t_start) * 1000.0,
                track_ms=(t_track - t_rect) * 1000.0,
                total_ms=(t_track - t_start) * 1000.0,
            )

            with self._lock:
                self._result = result

            self.frames_processed += 1

            # --- map, refreshed less often than every frame ---------
            map_counter += 1
            if map_counter >= self.map_update_every:
                map_counter = 0
                try:
                    snapshot = MapSnapshot(
                        self.slam.get_map_points(),
                        self.slam.get_keyframe_positions(),
                        self.slam.get_map_stats(),
                    )
                    with self._lock:
                        self._map = snapshot
                except Exception:  # noqa: BLE001
                    # A map read failing is not worth killing SLAM for.
                    pass

            self._tick_fps(t_track)

    # ----------------------------------------------------------
    def _tick_fps(self, now):
        self._fps_window.append(now)
        if len(self._fps_window) >= 2:
            span = self._fps_window[-1] - self._fps_window[0]
            if span >= 1.0:
                self.slam_fps = (len(self._fps_window) - 1) / span
                self._fps_window = self._fps_window[-2:]
            elif len(self._fps_window) > 120:
                self._fps_window = self._fps_window[-2:]

    # ----------------------------------------------------------
    def latest(self):
        with self._lock:
            return self._result

    def latest_map(self):
        with self._lock:
            return self._map

    def recent_poses(self):
        with self._lock:
            return list(self._recent_poses)

    # ----------------------------------------------------------
    def request_reset(self):
        """Ask for a reset. Performed on the SLAM thread, because
        ORB-SLAM3's Reset() is not safe to call concurrently with
        TrackStereo."""
        self._reset_requested = True

    def _do_reset(self):
        self._reset_requested = False
        try:
            self.slam.reset()
        except Exception as exc:  # noqa: BLE001
            self.error = f"Reset failed: {exc}"
            return

        self.trajectory.clear()
        self._last_state = -1
        self.frames_processed = 0
        self.frames_skipped = 0
        with self._lock:
            self._result = None
            self._map = MapSnapshot(
                np.zeros((0, 3), np.float32),
                np.zeros((0, 3), np.float32),
                {},
            )

    # ----------------------------------------------------------
    def save_trajectory(self, path):
        """Write the keyframe trajectory in TUM format.

        Uses the keyframe trajectory rather than the full one because
        SaveTrajectoryTUM requires the system to be shut down first,
        while keyframe poses can be written at any time.
        """
        if self.slam is None:
            return None
        self.slam.save_keyframe_trajectory(path)
        return path

    def stop(self):
        self._running = False
        self.join(timeout=5.0)

        if self.slam is not None:
            try:
                self.slam.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self.slam = None
