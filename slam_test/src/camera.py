"""
Stereo camera capture for the Novex ORB-SLAM3 test.

The camera is a single UVC device that delivers ONE combined
2560x720 frame containing both eyes side by side. That is a genuine
hardware advantage: left and right are exposed and transported
together, so splitting one captured frame can never produce a
mismatched stereo pair. Nothing in this file ever holds a left image
from one grab and a right image from another.

Threading model:

    USB camera -> capture thread -> latest-frame slot -> consumers

The capture thread does nothing but read and store. There is no
queue, so a slow consumer can never build a backlog and add latency;
it just misses frames. Every stored frame carries a monotonically
increasing id so consumers can tell whether a frame is new and avoid
processing the same one twice.
"""

import glob
import os
import threading
import time
import subprocess

import cv2
import numpy as np


def fourcc_to_string(value):
    """Decode OpenCV's CAP_PROP_FOURCC float into e.g. 'MJPG'."""
    v = int(value)
    if v <= 0:
        return "????"
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4))


class StereoFrame:
    """One captured side-by-side frame, plus its metadata.

    `left` and `right` are views into `combined`, not copies, so
    splitting costs nothing. They are read-only by convention.
    """

    __slots__ = ("combined", "left", "right", "frame_id", "timestamp", "capture_ms")

    def __init__(self, combined, frame_id, timestamp, capture_ms):
        self.combined = combined
        self.frame_id = frame_id
        self.timestamp = timestamp
        self.capture_ms = capture_ms

        half = combined.shape[1] // 2

        # The SAME captured frame, split. Left = columns 0..half-1,
        # right = columns half..end.
        self.left = combined[:, :half]
        self.right = combined[:, half:]


class StereoCamera:
    """Threaded newest-frame-wins capture from a side-by-side USB stereo camera."""

    def __init__(
        self,
        index=0,
        width=2560,
        height=720,
        fps=30,
        fourcc="MJPG",
        use_v4l2=True,
    ):
        self.index = index

        self.requested = {
            "width": width,
            "height": height,
            "fps": fps,
            "fourcc": fourcc,
        }

        self.actual = {
            "width": None,
            "height": None,
            "fps": None,
            "fourcc": None,
        }

        self._cap = None
        self._use_v4l2 = use_v4l2

        self._lock = threading.Lock()
        self._frame = None
        self._frame_id = 0

        self._running = False
        self._thread = None

        self._read_failures = 0
        self._fps_times = []
        self.measured_fps = 0.0

        self.error = None
        self.controls_applied = {}
        self.controls_failed = {}
        self.cpu_cores = None
        self.affinity_status = "camera: not pinned"
        self.capture_tid = None

    # ----------------------------------------------------------
    def open(self):
        """Open the device and negotiate the mode.

        Returns True on success. On failure `self.error` explains why.
        The requested mode is never assumed to have been accepted -
        `self.actual` always reports what the driver really gave us.
        """
        device = f"/dev/video{self.index}"

        # Check the device node first. Without this, OpenCV works its
        # way down to the FFMPEG backend and spends ~20 s failing at a
        # camera that was never there.
        if not os.path.exists(device):
            existing = sorted(glob.glob("/dev/video*"))
            self.error = (
                f"{device} does not exist. "
                + (f"Available: {', '.join(existing)}" if existing
                   else "No video devices found at all - is the camera plugged in?")
            )
            return False

        backend = cv2.CAP_V4L2 if self._use_v4l2 else cv2.CAP_ANY

        cap = cv2.VideoCapture(self.index, backend)

        if not cap.isOpened() and self._use_v4l2:
            # Fall back to whatever backend OpenCV picks.
            cap = cv2.VideoCapture(self.index)

        if not cap.isOpened():
            self.error = (
                f"Could not open camera index {self.index}. "
                f"Check that /dev/video{self.index} exists and that your user "
                f"is in the 'video' group."
            )
            return False

        # Order matters: set the pixel format BEFORE the resolution.
        # If MJPEG is not selected first, many UVC cameras silently fall
        # back to uncompressed YUYV, which cannot sustain 2560x720@30
        # over USB 2.0 and quietly drops to ~5 fps.
        r = self.requested
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*r["fourcc"]))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, r["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, r["height"])
        cap.set(cv2.CAP_PROP_FPS, r["fps"])

        # Ask the driver for the shallowest possible buffer. Not all
        # drivers honour this; the capture thread is the real defence
        # against latency.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            self.error = (
                f"Camera {self.index} opened but returned no frame. "
                f"Another program may be holding the device."
            )
            return False

        self.actual["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.actual["fps"] = float(cap.get(cv2.CAP_PROP_FPS))
        self.actual["fourcc"] = fourcc_to_string(cap.get(cv2.CAP_PROP_FOURCC))

        # Trust the delivered frame over the property, which some
        # drivers report incorrectly.
        h, w = frame.shape[:2]
        self.actual["width"] = w
        self.actual["height"] = h

        self._cap = cap
        return True

    # ----------------------------------------------------------
    def mode_warnings(self):
        """Concrete complaints about what the driver actually gave us."""
        warn = []
        r, a = self.requested, self.actual

        if a["width"] != r["width"] or a["height"] != r["height"]:
            warn.append(
                f"Resolution: requested {r['width']}x{r['height']}, "
                f"got {a['width']}x{a['height']}"
            )

        if a["fourcc"] != r["fourcc"]:
            warn.append(
                f"Format: requested {r['fourcc']}, got {a['fourcc']}. "
                f"Uncompressed formats usually cannot sustain the full frame rate."
            )

        if a["fps"] and abs(a["fps"] - r["fps"]) > 1.0:
            warn.append(f"FPS: requested {r['fps']}, driver reports {a['fps']:.1f}")

        if a["width"] % 2 != 0:
            warn.append(f"Odd frame width {a['width']}, cannot split into equal halves")

        return warn

    # ----------------------------------------------------------
    def list_controls(self):
        """Every V4L2 control the driver exposes, as raw text."""
        try:
            out = subprocess.run(
                ["v4l2-ctl", "-d", f"/dev/video{self.index}", "--list-ctrls"],
                capture_output=True, text=True, timeout=5,
            )
            return out.stdout
        except FileNotFoundError:
            return "v4l2-ctl not installed (sudo apt install v4l-utils)"
        except Exception as exc:  # noqa: BLE001
            return f"v4l2-ctl failed: {exc}"

    def apply_controls(self, controls):
        """Set V4L2 controls, e.g. to pin exposure and white balance.

        This matters more than it looks for stereo. The sensor runs
        AGC/AEC/AWB automatically by default, and if the two eyes drift
        to different exposures the same surface has different intensity
        in each image, which is precisely what ORB's descriptor
        matching relies on being stable. Auto exposure also lengthens
        the shutter in dim rooms, and with a ROLLING shutter that turns
        camera motion into a sheared, blurred frame - the single most
        common cause of ORB-SLAM3 losing tracking.

        Controls are applied one at a time so that one unsupported
        name does not silently discard the rest. Returns
        (applied, failed) so the caller can report honestly.
        """
        applied, failed = {}, {}

        if not controls:
            return applied, failed

        device = f"/dev/video{self.index}"

        # auto_exposure must be switched to manual BEFORE
        # exposure_time_absolute will accept a value - the driver marks
        # it inactive while auto exposure owns it.
        ordered = sorted(
            controls.items(),
            key=lambda kv: 0 if kv[0] in ("auto_exposure", "white_balance_automatic") else 1,
        )

        for name, value in ordered:
            if value is None:
                continue
            try:
                out = subprocess.run(
                    ["v4l2-ctl", "-d", device, "-c", f"{name}={value}"],
                    capture_output=True, text=True, timeout=5,
                )
                if out.returncode == 0 and not out.stderr.strip():
                    applied[name] = value
                else:
                    failed[name] = (out.stderr or out.stdout).strip() or "rejected"
            except FileNotFoundError:
                failed[name] = "v4l2-ctl not installed"
            except Exception as exc:  # noqa: BLE001
                failed[name] = str(exc)

        self.controls_applied = applied
        self.controls_failed = failed
        return applied, failed

    # ----------------------------------------------------------
    def start(self):
        if self._cap is None:
            raise RuntimeError("open() must succeed before start()")

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="novex-capture",
            daemon=True,
        )
        self._thread.start()

    def _capture_loop(self):
        # Pin before the first read. The capture thread is the one that
        # must never be starved: a descheduled reader misses frames at
        # the USB layer, and those frames are gone for good.
        if self.cpu_cores:
            import threading as _th
            from affinity import pin_current_thread
            self.capture_tid = _th.get_native_id()
            self.affinity_status = pin_current_thread(self.cpu_cores, "camera")

        while self._running:
            t0 = time.perf_counter()
            ok, frame = self._cap.read()
            t1 = time.perf_counter()

            if not ok or frame is None:
                self._read_failures += 1
                # Do not spin at 100% CPU on a dead device.
                time.sleep(0.005)
                continue

            with self._lock:
                self._frame_id += 1
                self._frame = StereoFrame(
                    combined=frame,
                    frame_id=self._frame_id,
                    timestamp=t1,
                    capture_ms=(t1 - t0) * 1000.0,
                )

            # Measured capture rate over a 1 s sliding window.
            self._fps_times.append(t1)
            if len(self._fps_times) > 2:
                span = self._fps_times[-1] - self._fps_times[0]
                if span >= 1.0:
                    self.measured_fps = (len(self._fps_times) - 1) / span
                    self._fps_times = self._fps_times[-2:]
                elif len(self._fps_times) > 120:
                    self._fps_times = self._fps_times[-2:]

    # ----------------------------------------------------------
    def read(self):
        """Newest frame, or None if nothing has been captured yet."""
        with self._lock:
            return self._frame

    def read_new(self, last_frame_id):
        """Newest frame only if it is newer than `last_frame_id`.

        This is how consumers avoid burning CPU re-processing a frame
        they have already seen when they run faster than the camera.
        """
        with self._lock:
            if self._frame is None:
                return None
            if self._frame.frame_id <= last_frame_id:
                return None
            return self._frame

    @property
    def read_failures(self):
        return self._read_failures

    # ----------------------------------------------------------
    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None


# --------------------------------------------------------------
def v4l2_device_info(index):
    """Ask v4l2-ctl what the device really is.

    Optional: returns a note if v4l-utils is not installed rather than
    failing, since it is only used for the debug panel.
    """
    dev = f"/dev/video{index}"
    try:
        out = subprocess.run(
            ["v4l2-ctl", "-d", dev, "--all"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout
    except FileNotFoundError:
        return "v4l2-ctl not installed (sudo apt install v4l-utils)"
    except Exception as exc:  # noqa: BLE001
        return f"v4l2-ctl failed: {exc}"


def probe_camera(index=0, width=2560, height=720, fps=30, fourcc="MJPG"):
    """Step 1 of the bring-up: open the camera and report the truth.

    Used by main.py at startup and runnable on its own:

        python src/camera.py
    """
    cam = StereoCamera(index=index, width=width, height=height, fps=fps, fourcc=fourcc)

    if not cam.open():
        return None, cam.error

    return cam, None


if __name__ == "__main__":
    import sys

    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    print()
    print("=" * 60)
    print(" NOVEX CAMERA PROBE")
    print("=" * 60)

    cam, err = probe_camera(idx)

    if cam is None:
        print(f"ERROR: {err}")
        sys.exit(1)

    r, a = cam.requested, cam.actual
    print(f"Requested : {r['width']}x{r['height']} {r['fourcc']} @ {r['fps']} fps")
    print(f"ACTUAL    : {a['width']}x{a['height']} {a['fourcc']} @ {a['fps']} fps")
    print(f"Left eye  : {a['width'] // 2}x{a['height']}")
    print(f"Right eye : {a['width'] // 2}x{a['height']}")

    for w in cam.mode_warnings():
        print(f"WARNING   : {w}")

    cam.start()

    print()
    print("Measuring actual capture rate for 3 seconds...")
    time.sleep(3.0)
    print(f"Measured  : {cam.measured_fps:.1f} fps  ({cam.read_failures} read failures)")

    frame = cam.read()
    if frame is not None:
        print(f"Split OK  : left {frame.left.shape}  right {frame.right.shape}")

        cv2.imshow("left", cv2.resize(frame.left, (640, 360)))
        cv2.imshow("right", cv2.resize(frame.right, (640, 360)))
        print()
        print("Showing left/right. Press any key in the image window to quit.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    cam.stop()
