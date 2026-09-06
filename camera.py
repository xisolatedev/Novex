import cv2
import numpy as np
import math

CAMERA = 0

# Camera output
CAM_W = 2560
CAM_H = 720

# Virtual camera
OUT_W = 640
OUT_H = 480
FOV = 60.0

# Assumed source fisheye FOV.
# Change this later after we determine the exact lens.
SOURCE_FOV = 180.0

yaw = 0.0
pitch = 0.0


def make_map(src_w, src_h, yaw_deg, pitch_deg):
    """
    Convert an approximate 180-degree fisheye image
    into a normal perspective 60-degree view.
    """

    f = (OUT_W / 2) / math.tan(math.radians(FOV / 2))

    x, y = np.meshgrid(
        np.arange(OUT_W),
        np.arange(OUT_H)
    )

    cx = OUT_W / 2
    cy = OUT_H / 2

    # Perspective camera rays
    X = (x - cx) / f
    Y = (y - cy) / f
    Z = np.ones_like(X)

    length = np.sqrt(X * X + Y * Y + Z * Z)

    X /= length
    Y /= length
    Z /= length

    # -------------------------
    # Pitch
    # -------------------------

    p = math.radians(pitch_deg)

    Y2 = Y * math.cos(p) - Z * math.sin(p)
    Z2 = Y * math.sin(p) + Z * math.cos(p)

    Y = Y2
    Z = Z2

    # -------------------------
    # Yaw
    # -------------------------

    a = math.radians(yaw_deg)

    X2 = X * math.cos(a) + Z * math.sin(a)
    Z2 = -X * math.sin(a) + Z * math.cos(a)

    X = X2
    Z = Z2

    # -------------------------
    # Fisheye projection
    # -------------------------

    theta = np.arccos(np.clip(Z, -1, 1))

    source_f = (
        min(src_w, src_h)
        / math.radians(SOURCE_FOV)
    )

    radius = source_f * theta

    xy = np.sqrt(X * X + Y * Y)

    safe_xy = np.where(xy < 1e-8, 1, xy)

    map_x = (
        src_w / 2
        + radius * X / safe_xy
    )

    map_y = (
        src_h / 2
        + radius * Y / safe_xy
    )

    # Outside the fisheye image
    valid = theta <= math.radians(SOURCE_FOV / 2)

    map_x[~valid] = -1
    map_y[~valid] = -1

    return (
        map_x.astype(np.float32),
        map_y.astype(np.float32)
    )


def render(eye):
    global yaw, pitch

    h, w = eye.shape[:2]

    map_x, map_y = make_map(
        w,
        h,
        yaw,
        pitch
    )

    return cv2.remap(
        eye,
        map_x,
        map_y,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT
    )


def main():

    global yaw, pitch, FOV

    cap = cv2.VideoCapture(CAMERA)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_H)
    cap.set(cv2.CAP_PROP_FPS, 30)

    if not cap.isOpened():
        print("ERROR: Could not open camera.")
        return

    print()
    print("NOVEX VIRTUAL STEREO CAMERA")
    print("============================")
    print()
    print("Arrow keys:")
    print("  LEFT / RIGHT = yaw")
    print("  UP / DOWN    = pitch")
    print()
    print("WASD:")
    print("  A / D = yaw")
    print("  W / S = pitch")
    print()
    print("R = reset")
    print("+ / - = change FOV")
    print("ESC = quit")
    print()

    while True:

        ok, frame = cap.read()

        if not ok:
            print("Camera frame failed.")
            break

        h, w = frame.shape[:2]

        # ---------------------------------
        # Split binocular image
        # ---------------------------------

        half = w // 2

        left = frame[:, :half]
        right = frame[:, half:]

        # ---------------------------------
        # Create virtual views
        # ---------------------------------

        left_view = render(left)
        right_view = render(right)

        # ---------------------------------
        # Combine stereo views
        # ---------------------------------

        stereo = np.hstack(
            (left_view, right_view)
        )

        # ---------------------------------
        # Information overlay
        # ---------------------------------

        cv2.putText(
            stereo,
            f"FOV: {FOV:.0f}",
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.putText(
            stereo,
            f"Yaw: {yaw:.0f}",
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.putText(
            stereo,
            f"Pitch: {pitch:.0f}",
            (10, 90),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )

        cv2.imshow(
            "Novex Virtual Stereo Camera",
            stereo
        )

        # ---------------------------------
        # Keyboard
        # ---------------------------------

        key = cv2.waitKeyEx(1)

        if key == 27:
            break

        # Arrow keys
        if key in (81, 2424832):
            yaw -= 4

        elif key in (83, 2555904):
            yaw += 4

        elif key in (82, 2490368):
            pitch += 4

        elif key in (84, 2621440):
            pitch -= 4

        # WASD
        elif key in (ord("a"), ord("A")):
            yaw -= 4

        elif key in (ord("d"), ord("D")):
            yaw += 4

        elif key in (ord("w"), ord("W")):
            pitch += 4

        elif key in (ord("s"), ord("S")):
            pitch -= 4

        # Reset
        elif key in (ord("r"), ord("R")):
            yaw = 0
            pitch = 0

        # FOV
        elif key in (ord("+"), ord("=")):
            FOV = min(120, FOV + 5)

        elif key in (ord("-"), ord("_")):
            FOV = max(20, FOV - 5)

        pitch = max(-89, min(89, pitch))

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()