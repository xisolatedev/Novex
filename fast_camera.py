import cv2
import numpy as np
import math
import threading
import time

# ============================================================
# NOVEX FAST FISHEYE CAMERA
# ============================================================

CAMERA_INDEX = 0

# Camera's advertised native mode
CAMERA_WIDTH = 2560
CAMERA_HEIGHT = 720
CAMERA_FPS = 30

# Preview size
PREVIEW_WIDTH = 960
PREVIEW_HEIGHT = 540

# ============================================================
# YOUR CALIBRATION
# ============================================================

SOURCE_FOV = 112.0

K1 = 0.141000
K2 = 0.013500
K3 = 0.000000
K4 = 0.003000

CENTER_X = 0.000000
CENTER_Y = 0.000000

VIRTUAL_FOV = 99.0

YAW = 0.0
PITCH = 0.0


# ============================================================
# CAMERA CAPTURE THREAD
#
# Important:
# We never allow frames to pile up.
# The processing loop always gets the newest frame.
# ============================================================

class Camera:

    def __init__(self, index):

        self.cap = cv2.VideoCapture(
            index,
            cv2.CAP_V4L2
        )

        if not self.cap.isOpened():

            # Fallback for Windows/macOS/etc.
            self.cap = cv2.VideoCapture(index)

        # Request MJPEG
        self.cap.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(*"MJPG")
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            CAMERA_WIDTH
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            CAMERA_HEIGHT
        )

        self.cap.set(
            cv2.CAP_PROP_FPS,
            CAMERA_FPS
        )

        # Try to minimize buffering.
        self.cap.set(
            cv2.CAP_PROP_BUFFERSIZE,
            1
        )

        self.frame = None
        self.lock = threading.Lock()

        self.running = True

        self.thread = threading.Thread(
            target=self._capture_loop,
            daemon=True
        )

        self.thread.start()

    def _capture_loop(self):

        while self.running:

            success, frame = self.cap.read()

            if not success:
                continue

            # Replace old frame.
            # Never queue frames.
            with self.lock:
                self.frame = frame

    def read(self):

        with self.lock:

            if self.frame is None:
                return None

            return self.frame.copy()

    def stop(self):

        self.running = False

        self.thread.join(
            timeout=1
        )

        self.cap.release()


# ============================================================
# ROTATION
# ============================================================

def rotation_matrix(yaw_deg, pitch_deg):

    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)

    cy = math.cos(yaw)
    sy = math.sin(yaw)

    cp = math.cos(pitch)
    sp = math.sin(pitch)

    Ry = np.array(
        [
            [cy, 0, sy],
            [0, 1, 0],
            [-sy, 0, cy]
        ],
        dtype=np.float32
    )

    Rx = np.array(
        [
            [1, 0, 0],
            [0, cp, -sp],
            [0, sp, cp]
        ],
        dtype=np.float32
    )

    return Rx @ Ry


# ============================================================
# CREATE FISHEYE MAP
#
# THIS RUNS ONLY ONCE.
# ============================================================

def create_fisheye_map(
    src_width,
    src_height,
    output_width,
    output_height
):

    print("Creating fisheye maps...")

    start = time.perf_counter()

    # --------------------------------------------------------
    # Perspective focal length
    # --------------------------------------------------------

    focal = (
        output_width / 2.0
        / math.tan(
            math.radians(VIRTUAL_FOV) / 2.0
        )
    )

    # --------------------------------------------------------
    # Output pixel grid
    # --------------------------------------------------------

    px, py = np.meshgrid(
        np.arange(output_width),
        np.arange(output_height)
    )

    cx = output_width / 2.0
    cy = output_height / 2.0

    x = (
        px.astype(np.float32) - cx
    ) / focal

    y = (
        py.astype(np.float32) - cy
    ) / focal

    z = np.ones_like(x)

    # Normalize ray vectors
    length = np.sqrt(
        x * x +
        y * y +
        z * z
    )

    x /= length
    y /= length
    z /= length

    # --------------------------------------------------------
    # Camera rotation
    # --------------------------------------------------------

    R = rotation_matrix(
        YAW,
        PITCH
    )

    rays = np.stack(
        [x, y, z],
        axis=-1
    )

    rays = rays @ R.T

    x = rays[..., 0]
    y = rays[..., 1]
    z = rays[..., 2]

    # --------------------------------------------------------
    # Fisheye angle
    # --------------------------------------------------------

    theta = np.arccos(
        np.clip(z, -1.0, 1.0)
    )

    theta2 = theta * theta
    theta4 = theta2 * theta2
    theta6 = theta4 * theta2
    theta8 = theta6 * theta2

    # --------------------------------------------------------
    # Fisheye distortion
    # --------------------------------------------------------

    distorted_theta = theta * (
        1.0
        + K1 * theta2
        + K2 * theta4
        + K3 * theta6
        + K4 * theta8
    )

    # --------------------------------------------------------
    # Fisheye focal length
    # --------------------------------------------------------

    fisheye_f = (
        min(src_width, src_height)
        / math.radians(SOURCE_FOV)
    )

    radius = (
        fisheye_f *
        distorted_theta
    )

    xy = np.sqrt(
        x * x +
        y * y
    )

    safe_xy = np.maximum(
        xy,
        1e-8
    )

    # --------------------------------------------------------
    # Optical center
    # --------------------------------------------------------

    source_cx = (
        src_width / 2.0
        + CENTER_X * src_width
    )

    source_cy = (
        src_height / 2.0
        + CENTER_Y * src_height
    )

    map_x = (
        source_cx
        + radius * x / safe_xy
    )

    map_y = (
        source_cy
        + radius * y / safe_xy
    )

    # Center ray
    center = xy < 1e-8

    map_x[center] = source_cx
    map_y[center] = source_cy

    # --------------------------------------------------------
    # Mask rays outside source FOV
    # --------------------------------------------------------

    valid = (
        theta <=
        math.radians(
            SOURCE_FOV / 2.0
        )
    )

    map_x[~valid] = -1
    map_y[~valid] = -1

    map_x = map_x.astype(
        np.float32
    )

    map_y = map_y.astype(
        np.float32
    )

    elapsed = (
        time.perf_counter()
        - start
    )

    print(
        f"Maps created in {elapsed:.3f}s"
    )

    return map_x, map_y


# ============================================================
# FAST REMAP
# ============================================================

def remap(image, map_x, map_y):

    return cv2.remap(
        image,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT
    )


# ============================================================
# FPS COUNTER
# ============================================================

class FPSCounter:

    def __init__(self):

        self.last = time.perf_counter()

        self.frames = 0

        self.fps = 0.0

    def update(self):

        self.frames += 1

        now = time.perf_counter()

        elapsed = now - self.last

        if elapsed >= 1.0:

            self.fps = (
                self.frames / elapsed
            )

            self.frames = 0

            self.last = now

        return self.fps


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("==============================================")
    print("          NOVEX FAST CAMERA")
    print("==============================================")
    print()
    print(
        f"Requested camera mode: "
        f"{CAMERA_WIDTH}x{CAMERA_HEIGHT} @ {CAMERA_FPS} FPS"
    )
    print("MJPEG enabled")
    print()

    camera = Camera(
        CAMERA_INDEX
    )

    # --------------------------------------------------------
    # Wait for camera
    # --------------------------------------------------------

    print("Waiting for camera...")

    frame = None

    for _ in range(100):

        frame = camera.read()

        if frame is not None:
            break

        time.sleep(0.01)

    if frame is None:

        print(
            "ERROR: No camera frames received."
        )

        camera.stop()

        return

    actual_height, actual_width = (
        frame.shape[:2]
    )

    print(
        f"Actual camera frame: "
        f"{actual_width}x{actual_height}"
    )

    # --------------------------------------------------------
    # Stereo dimensions
    # --------------------------------------------------------

    eye_width = actual_width // 2
    eye_height = actual_height

    print(
        f"Each eye: "
        f"{eye_width}x{eye_height}"
    )

    # --------------------------------------------------------
    # Create maps ONCE
    # --------------------------------------------------------

    left_map_x, left_map_y = (
        create_fisheye_map(
            eye_width,
            eye_height,
            PREVIEW_WIDTH,
            PREVIEW_HEIGHT
        )
    )

    right_map_x, right_map_y = (
        create_fisheye_map(
            eye_width,
            eye_height,
            PREVIEW_WIDTH,
            PREVIEW_HEIGHT
        )
    )

    # --------------------------------------------------------
    # Open display
    # --------------------------------------------------------

    cv2.namedWindow(
        "NOVEX",
        cv2.WINDOW_NORMAL
    )

    fps_counter = FPSCounter()

    frames_processed = 0

    last_frame_id = None

    # ========================================================
    # LOOP
    # ========================================================

    try:

        while True:

            frame = camera.read()

            if frame is None:
                continue

            # ------------------------------------------------
            # Split stereo image
            # ------------------------------------------------

            left = frame[
                :,
                :eye_width
            ]

            right = frame[
                :,
                eye_width:
            ]

            # ------------------------------------------------
            # FAST OpenCV remapping
            # ------------------------------------------------

            left_corrected = remap(
                left,
                left_map_x,
                left_map_y
            )

            right_corrected = remap(
                right,
                right_map_x,
                right_map_y
            )

            # ------------------------------------------------
            # Side-by-side
            # ------------------------------------------------

            display = np.hstack(
                (
                    left_corrected,
                    right_corrected
                )
            )

            # ------------------------------------------------
            # FPS
            # ------------------------------------------------

            fps = fps_counter.update()

            frames_processed += 1

            cv2.putText(
                display,
                f"PROCESS FPS: {fps:.1f}",
                (15, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA
            )

            cv2.putText(
                display,
                "LEFT",
                (15, 65),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2
            )

            cv2.putText(
                display,
                "RIGHT",
                (
                    PREVIEW_WIDTH + 15,
                    65
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2
            )

            cv2.imshow(
                "NOVEX",
                display
            )

            # ------------------------------------------------
            # Keyboard
            # ------------------------------------------------

            key = cv2.waitKey(1) & 0xFF

            if key in (
                27,
                ord("q"),
                ord("Q")
            ):
                break

    finally:

        camera.stop()

        cv2.destroyAllWindows()

    print()
    print("==============================================")
    print("NOVEX CAMERA STOPPED")
    print(
        f"Processed frames: {frames_processed}"
    )
    print("==============================================")


if __name__ == "__main__":
    main()