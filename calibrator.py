import cv2
import numpy as np
import json
import math

# ============================================================
# NOVEX FISHEYE CALIBRATION TOOL
# ============================================================

CAMERA_INDEX = 0

CAMERA_WIDTH = 2560
CAMERA_HEIGHT = 720

DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 480


# ============================================================
# Slider ranges
# ============================================================

# Approximate source FOV.
SOURCE_FOV_MIN = 120
SOURCE_FOV_MAX = 200

# Distortion coefficients.
K_MIN = -1.5
K_MAX = 1.5

# Optical center movement.
CENTER_OFFSET = 0.50


# ============================================================
# Global state
# ============================================================

source_fov = 180.0

k1 = 0.0
k2 = 0.0
k3 = 0.0
k4 = 0.0

center_x = 0.0
center_y = 0.0

virtual_fov = 60.0

yaw = 0.0
pitch = 0.0


# ============================================================
# Slider conversion helpers
# ============================================================

def slider_value(name):
    return cv2.getTrackbarPos(name, "CALIBRATION")


def signed_slider(name, minimum, maximum):
    value = slider_value(name)

    maximum_slider = 2000

    normalized = value / maximum_slider

    return minimum + normalized * (maximum - minimum)


def update_parameters():
    global source_fov
    global k1, k2, k3, k4
    global center_x, center_y
    global virtual_fov

    source_fov = slider_value("Source FOV")

    k1 = signed_slider("K1", K_MIN, K_MAX)
    k2 = signed_slider("K2", K_MIN, K_MAX)
    k3 = signed_slider("K3", K_MIN, K_MAX)
    k4 = signed_slider("K4", K_MIN, K_MAX)

    center_x = signed_slider(
        "Center X",
        -CENTER_OFFSET,
        CENTER_OFFSET
    )

    center_y = signed_slider(
        "Center Y",
        -CENTER_OFFSET,
        CENTER_OFFSET
    )

    virtual_fov = slider_value("Virtual FOV")


# ============================================================
# Rotation matrix
# ============================================================

def rotation_matrix(yaw_deg, pitch_deg):

    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)

    cy = math.cos(yaw)
    sy = math.sin(yaw)

    cp = math.cos(pitch)
    sp = math.sin(pitch)

    Ry = np.array([
        [cy, 0, sy],
        [0,  1, 0],
        [-sy, 0, cy]
    ], dtype=np.float32)

    Rx = np.array([
        [1, 0, 0],
        [0, cp, -sp],
        [0, sp, cp]
    ], dtype=np.float32)

    return Rx @ Ry


# ============================================================
# Fisheye correction
# ============================================================

def create_map(
    width,
    height,
    yaw_deg=0,
    pitch_deg=0
):

    output_w = DISPLAY_WIDTH
    output_h = DISPLAY_HEIGHT

    # --------------------------------------------------------
    # Perspective camera focal length
    # --------------------------------------------------------

    f = (
        output_w / 2
        / math.tan(math.radians(virtual_fov) / 2)
    )

    px, py = np.meshgrid(
        np.arange(output_w),
        np.arange(output_h)
    )

    cx = output_w / 2
    cy = output_h / 2

    x = (px - cx) / f
    y = (py - cy) / f

    z = np.ones_like(x)

    length = np.sqrt(
        x * x +
        y * y +
        z * z
    )

    x /= length
    y /= length
    z /= length

    # --------------------------------------------------------
    # Rotate virtual camera
    # --------------------------------------------------------

    R = rotation_matrix(
        yaw_deg,
        pitch_deg
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

    # Equidistant fisheye focal length.
    fisheye_f = (
        min(width, height)
        / math.radians(source_fov)
    )

    # --------------------------------------------------------
    # Polynomial fisheye distortion
    #
    # r = theta * (
    #       1 +
    #       k1 theta² +
    #       k2 theta⁴ +
    #       k3 theta⁶ +
    #       k4 theta⁸
    #     )
    # --------------------------------------------------------

    theta2 = theta * theta

    distorted_theta = theta * (
        1
        + k1 * theta2
        + k2 * theta2 * theta2
        + k3 * theta2 * theta2 * theta2
        + k4 * theta2 * theta2 * theta2 * theta2
    )

    radius = fisheye_f * distorted_theta

    xy = np.sqrt(
        x * x +
        y * y
    )

    safe_xy = np.where(
        xy < 1e-8,
        1,
        xy
    )

    # --------------------------------------------------------
    # Optical center
    # --------------------------------------------------------

    image_cx = (
        width / 2
        + center_x * width
    )

    image_cy = (
        height / 2
        + center_y * height
    )

    map_x = (
        image_cx
        + radius * x / safe_xy
    )

    map_y = (
        image_cy
        + radius * y / safe_xy
    )

    # Center ray
    center_mask = xy < 1e-8

    map_x[center_mask] = image_cx
    map_y[center_mask] = image_cy

    # Don't sample outside source fisheye.
    valid = (
        theta <=
        math.radians(source_fov / 2)
    )

    map_x[~valid] = -1
    map_y[~valid] = -1

    return (
        map_x.astype(np.float32),
        map_y.astype(np.float32)
    )


# ============================================================
# Correct image
# ============================================================

def correct_image(image):

    h, w = image.shape[:2]

    map_x, map_y = create_map(
        w,
        h,
        yaw,
        pitch
    )

    return cv2.remap(
        image,
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT
    )


# ============================================================
# Save calibration
# ============================================================

def save_calibration():

    data = {
        "source_fov": source_fov,

        "distortion": {
            "k1": k1,
            "k2": k2,
            "k3": k3,
            "k4": k4
        },

        "optical_center": {
            "x": center_x,
            "y": center_y
        },

        "virtual_fov": virtual_fov
    }

    with open(
        "novex_calibration.json",
        "w"
    ) as f:

        json.dump(
            data,
            f,
            indent=4
        )

    print()
    print("================================")
    print("CALIBRATION SAVED")
    print("================================")
    print(json.dumps(data, indent=4))
    print()


# ============================================================
# Reset
# ============================================================

def reset():

    cv2.setTrackbarPos(
        "Source FOV",
        "CALIBRATION",
        180
    )

    for name in [
        "K1",
        "K2",
        "K3",
        "K4"
    ]:

        cv2.setTrackbarPos(
            name,
            "CALIBRATION",
            1000
        )

    cv2.setTrackbarPos(
        "Center X",
        "CALIBRATION",
        1000
    )

    cv2.setTrackbarPos(
        "Center Y",
        "CALIBRATION",
        1000
    )

    cv2.setTrackbarPos(
        "Virtual FOV",
        "CALIBRATION",
        60
    )


# ============================================================
# Slider callbacks
# ============================================================

def nothing(x):
    pass


# ============================================================
# Main
# ============================================================

def main():

    global yaw
    global pitch

    cap = cv2.VideoCapture(
        CAMERA_INDEX
    )

    if not cap.isOpened():

        print(
            "ERROR: Could not open camera."
        )

        return

    cap.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        CAMERA_WIDTH
    )

    cap.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        CAMERA_HEIGHT
    )

    cap.set(
        cv2.CAP_PROP_FPS,
        30
    )

    # --------------------------------------------------------
    # Calibration window
    # --------------------------------------------------------

    cv2.namedWindow(
        "CALIBRATION",
        cv2.WINDOW_NORMAL
    )

    # FOV
    cv2.createTrackbar(
        "Source FOV",
        "CALIBRATION",
        180,
        SOURCE_FOV_MAX,
        nothing
    )

    # Distortion
    for name in [
        "K1",
        "K2",
        "K3",
        "K4"
    ]:

        cv2.createTrackbar(
            name,
            "CALIBRATION",
            1000,
            2000,
            nothing
        )

    # Optical center
    cv2.createTrackbar(
        "Center X",
        "CALIBRATION",
        1000,
        2000,
        nothing
    )

    cv2.createTrackbar(
        "Center Y",
        "CALIBRATION",
        1000,
        2000,
        nothing
    )

    # Virtual camera FOV
    cv2.createTrackbar(
        "Virtual FOV",
        "CALIBRATION",
        60,
        120,
        nothing
    )

    print()
    print("==============================================")
    print("        NOVEX CAMERA CALIBRATION")
    print("==============================================")
    print()
    print("SLIDERS:")
    print("  Source FOV")
    print("  K1 K2 K3 K4")
    print("  Center X / Center Y")
    print("  Virtual FOV")
    print()
    print("KEYBOARD:")
    print("  LEFT / RIGHT = yaw")
    print("  UP / DOWN    = pitch")
    print("  A / D        = yaw")
    print("  W / S        = pitch")
    print("  R            = reset")
    print("  P            = print values")
    print("  S            = save calibration")
    print("  ESC          = quit")
    print()
    print("Put STRAIGHT LINES in view.")
    print("A door frame, window, wall, etc.")
    print("Try to make them straight in the corrected image.")
    print()

    while True:

        ok, frame = cap.read()

        if not ok:
            print(
                "ERROR: Could not read frame."
            )
            break

        h, w = frame.shape[:2]

        # ----------------------------------------------------
        # Split binocular frame
        # ----------------------------------------------------

        half = w // 2

        left = frame[:, :half]
        right = frame[:, half:]

        # ----------------------------------------------------
        # Update sliders
        # ----------------------------------------------------

        update_parameters()

        # ----------------------------------------------------
        # Correct both eyes
        # ----------------------------------------------------

        left_corrected = correct_image(
            left
        )

        right_corrected = correct_image(
            right
        )

        # ----------------------------------------------------
        # Resize raw images
        # ----------------------------------------------------

        left_raw = cv2.resize(
            left,
            (
                DISPLAY_WIDTH,
                DISPLAY_HEIGHT
            )
        )

        right_raw = cv2.resize(
            right,
            (
                DISPLAY_WIDTH,
                DISPLAY_HEIGHT
            )
        )

        # ----------------------------------------------------
        # Build comparison
        # ----------------------------------------------------

        top = np.hstack(
            (
                left_raw,
                left_corrected
            )
        )

        bottom = np.hstack(
            (
                right_raw,
                right_corrected
            )
        )

        display = np.vstack(
            (
                top,
                bottom
            )
        )

        # ----------------------------------------------------
        # Labels
        # ----------------------------------------------------

        cv2.putText(
            display,
            "LEFT RAW",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display,
            "LEFT CORRECTED",
            (
                DISPLAY_WIDTH + 15,
                30
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display,
            "RIGHT RAW",
            (
                15,
                DISPLAY_HEIGHT + 30
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display,
            "RIGHT CORRECTED",
            (
                DISPLAY_WIDTH + 15,
                DISPLAY_HEIGHT + 30
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        # ----------------------------------------------------
        # Current values
        # ----------------------------------------------------

        info = (
            f"FOV {source_fov:.1f} | "
            f"K1 {k1:.3f} "
            f"K2 {k2:.3f} "
            f"K3 {k3:.3f} "
            f"K4 {k4:.3f}"
        )

        cv2.putText(
            display,
            info,
            (
                15,
                DISPLAY_HEIGHT * 2 - 20
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1
        )

        cv2.imshow(
            "CALIBRATION",
            display
        )

        # ----------------------------------------------------
        # Keyboard
        # ----------------------------------------------------

        key = cv2.waitKeyEx(1)

        if key == 27:
            break

        # Arrow keys
        elif key in (
            81,
            2424832
        ):
            yaw -= 3

        elif key in (
            83,
            2555904
        ):
            yaw += 3

        elif key in (
            82,
            2490368
        ):
            pitch += 3

        elif key in (
            84,
            2621440
        ):
            pitch -= 3

        # WASD
        elif key in (
            ord("a"),
            ord("A")
        ):
            yaw -= 3

        elif key in (
            ord("d"),
            ord("D")
        ):
            yaw += 3

        elif key in (
            ord("w"),
            ord("W")
        ):
            pitch += 3

        elif key in (
            ord("s"),
            ord("S")
        ):
            save_calibration()

        elif key in (
            ord("r"),
            ord("R")
        ):
            yaw = 0
            pitch = 0
            reset()

        elif key in (
            ord("p"),
            ord("P")
        ):

            print()
            print("========== CURRENT VALUES ==========")
            print(
                f"Source FOV : {source_fov:.6f}"
            )
            print(
                f"K1         : {k1:.6f}"
            )
            print(
                f"K2         : {k2:.6f}"
            )
            print(
                f"K3         : {k3:.6f}"
            )
            print(
                f"K4         : {k4:.6f}"
            )
            print(
                f"Center X   : {center_x:.6f}"
            )
            print(
                f"Center Y   : {center_y:.6f}"
            )
            print(
                f"Virtual FOV: {virtual_fov:.6f}"
            )
            print(
                f"Yaw        : {yaw:.6f}"
            )
            print(
                f"Pitch      : {pitch:.6f}"
            )
            print(
                "===================================="
            )
            print()

        pitch = max(
            -89,
            min(89, pitch)
        )

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()