#!/usr/bin/env python3
"""
NOVEX - ORB-SLAM3 stereo test.

    python src/main.py                    live camera
    python src/main.py --replay <dir>     replay a recording
    python src/main.py --no-slam          camera + GUI only

Start-up order, and what each step proves:

    1. Camera      - the device opens and the mode it ACTUALLY
                     negotiated is printed, not the one we asked for.
    2. Stereo      - one combined frame splits into two equal eyes.
    3. Calibration - a real chessboard stereo calibration exists.
                     If not, SLAM is refused and the reason is stated.
    4. Rectify     - fisheye pair -> ideal pinhole pair, maps built once.
    5. ORB-SLAM3   - the real library starts on its own thread.
    6. GUI         - opens and displays what the above produce.

If step 3 fails the GUI still opens, so the camera and display layers
remain testable, but the SLAM panel reads CALIBRATION REQUIRED and no
pose is ever shown. Nothing is faked to fill the gap.
"""

import argparse
import os
import sys
import threading
import time

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from camera import StereoCamera  # noqa: E402
from calibration import (  # noqa: E402
    TemporaryLensModel,
    StereoRectifier,
    FisheyeStereoModel,
    calibration_status,
)
from recorder import StereoRecorder, ReplayCamera  # noqa: E402
from slam import SlamWorker, PlaneWorker  # noqa: E402
from affinity import default_layout, pin_current_thread, AffinityReport  # noqa: E402


LINE = "=" * 62


def load_exported_settings(path):
    """Load a workbench export plus its pipeline sidecar."""
    if not os.path.exists(path):
        print(f"ERROR: settings file not found: {path}")
        return None

    sidecar_path = os.path.splitext(path)[0] + ".novex.yaml"
    if not os.path.exists(sidecar_path):
        print(f"ERROR: no pipeline sidecar next to {path}")
        print(f"  expected: {sidecar_path}")
        print("  An ORB-SLAM3 settings file holds only the RECTIFIED")
        print("  intrinsics, which is not enough to rebuild the remap that")
        print("  produced those images. Re-export from src/workbench.py,")
        print("  which writes both files together.")
        return None

    with open(sidecar_path) as f:
        side = yaml.safe_load(f)

    # Write the sidecar's calibration where the normal loading path can
    # consume it unchanged.
    import tempfile
    tmp = os.path.join(tempfile.mkdtemp(prefix="novex_export_"),
                       "stereo_calibration.yaml")
    with open(tmp, "w") as f:
        yaml.safe_dump(side["calibration"], f, sort_keys=False)

    # Report immediately, before anything else can fail. What
    # configuration is in force is the first thing you want to know.
    out = side.get("output", {})
    print(f"Using workbench export: {path}")
    print(f"  camera model : {side.get('camera_model')}")
    print(f"  output       : {out.get('width')}x{out.get('height')} "
          f"@ {out.get('hfov_deg', 0):.1f} deg")
    print(f"  baseline     : {side['calibration'].get('baseline_m', 0) * 1000:.2f} mm")
    print(f"  source calib : {side.get('source_calibration')}")

    experimental = side.get("experimental_parameters") or []
    if experimental:
        print("  WARNING: contains HAND-ADJUSTED, non-measured values:")
        for k in experimental:
            print(f"    {k}")
    else:
        print("  all camera parameters are as measured")

    return {"sidecar": side, "calibration_path": tmp,
            "settings_path": os.path.abspath(path),
            "experimental": experimental}


def deep_merge(base, override):
    """Merge `override` into `base`, recursing into dicts.

    Used so a profile can change just `slam.orb.n_features` without
    having to restate the whole slam section.
    """
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def apply_profile(cfg, name):
    """Apply a named profile from config, returning what it changed."""
    profiles = cfg.get("profiles") or {}
    if name not in profiles:
        raise SystemExit(
            f"Unknown profile '{name}'. Available: {', '.join(sorted(profiles))}")

    profile = dict(profiles[name])

    # Exposure/gain are not config sections; they map onto V4L2
    # controls, so pull them out before merging the rest.
    exposure_ms = profile.pop("exposure_ms", None)
    gain = profile.pop("gain", None)

    deep_merge(cfg, profile)
    return exposure_ms, gain


def resolve(path):
    """Config paths are relative to the project root."""
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


class AppState:
    """Everything the GUI needs, assembled once at start-up."""

    def __init__(self):
        self.root = ROOT
        self.camera = None
        self.worker = None
        self.recorder = None
        self.rectifier = None
        self.temporary_lens = None
        self.slam_enabled = False
        self.slam_disabled_reason = ""
        self.scale_unverified = False
        self.plane_worker = None
        self.profile = None
        self.cpu_layout = {}
        self.affinity = AffinityReport()
        self.camera_model = None
        self.gui_fps = 30

    def shutdown(self):
        if self.recorder is not None and self.recorder.is_recording:
            print("Stopping recording...")
            self.recorder.stop()

        if self.plane_worker is not None:
            self.plane_worker.stop()
            self.plane_worker = None

        if self.worker is not None:
            print("Shutting down ORB-SLAM3...")
            self.worker.stop()
            self.worker = None

        if self.camera is not None:
            self.camera.stop()
            self.camera = None


# --------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Novex ORB-SLAM3 stereo test")
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "camera.yaml"))
    ap.add_argument(
        "--calibration",
        default=os.path.join(ROOT, "config", "stereo_calibration.yaml"),
    )
    ap.add_argument("--camera", type=int, default=None, help="override camera index")
    ap.add_argument("--replay", default=None, help="replay a recorded session")
    ap.add_argument("--loop", action="store_true", help="loop the replay")
    ap.add_argument(
        "--no-slam",
        action="store_true",
        help="camera and GUI only, do not start ORB-SLAM3",
    )
    ap.add_argument(
        "--settings", default=None, metavar="YAML",
        help="use a settings file exported by src/workbench.py instead of "
             "generating one. Its .novex.yaml sidecar is read alongside so "
             "the image pipeline matches the file exactly.")
    ap.add_argument(
        "--profile", default=None,
        help="apply a named profile from config/camera.yaml "
             "(quality, balanced, fast, fastest)")
    ap.add_argument(
        "--fast", action="store_true",
        help="shorthand for --profile fast: 848x480 at the camera's full "
             "30 fps, tuned for fast movement")
    ap.add_argument(
        "--lock-exposure", type=float, default=None, metavar="MS",
        help="pin the sensor to manual exposure of MS milliseconds and "
             "disable auto white balance. Keeps both eyes at matching "
             "brightness and avoids rolling-shutter motion blur. Try 20.")
    ap.add_argument(
        "--orbslam-viewer",
        action="store_true",
        help="also open ORB-SLAM3's own Pangolin viewer, as a cross-check "
             "that the Novex GUI shows the same pose",
    )
    args = ap.parse_args()

    print()
    print("NOVEX ORB-SLAM3 TEST")
    print("---------------------")
    print()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    # ----------------------------------------------------------
    # A workbench export replaces both the calibration and the output
    # geometry, so it is resolved before the normal path.
    # ----------------------------------------------------------
    exported = None
    if args.settings:
        exported = load_exported_settings(args.settings)
        if exported is None:
            return 1
        args.calibration = exported["calibration_path"]


    profile_name = "fast" if args.fast else args.profile
    profile_exposure = profile_gain = None
    if profile_name:
        profile_exposure, profile_gain = apply_profile(cfg, profile_name)
        print(f"Profile: {profile_name.upper()}")
        r = cfg.get("rectification", {})
        o = cfg.get("slam", {}).get("orb", {})
        print(f"  rectified : {r.get('width')}x{r.get('height')} per eye")
        print(f"  features  : {o.get('n_features')}  levels {o.get('n_levels')}  "
              f"FAST {o.get('ini_th_fast')}/{o.get('min_th_fast')}")
        if profile_exposure:
            print(f"  exposure  : {profile_exposure} ms (short, to freeze motion)")
        print()

    state = AppState()
    state.profile = profile_name
    state.gui_fps = cfg.get("gui", {}).get("fps", 30)

    # ------------------------------------------------------
    # CPU layout
    # ------------------------------------------------------
    cpu_cfg = cfg.get("cpu") or {}
    layout = default_layout() if cpu_cfg.get("auto", True) else {}
    for key in ("camera", "slam", "gui"):
        if cpu_cfg.get(key):
            layout[key] = cpu_cfg[key]
    state.cpu_layout = layout

    if layout:
        print(f"CPU layout: camera {layout.get('camera')}  "
              f"slam {layout.get('slam')}  gui {layout.get('gui')}")
        state.affinity.add(pin_current_thread(layout.get("gui"), "gui/main"))

    # ----------------------------------------------------------
    # 1. Camera
    # ----------------------------------------------------------
    cam_cfg = cfg["camera"]
    index = args.camera if args.camera is not None else cam_cfg["index"]

    if args.replay:
        print(f"Camera: REPLAY {args.replay}")
        try:
            camera = ReplayCamera(args.replay, loop=args.loop)
        except Exception as exc:  # noqa: BLE001
            print(f"Camera: FAILED - {exc}")
            return 1
        if not camera.open():
            print(f"Camera: FAILED - {camera.error}")
            return 1
    else:
        camera = StereoCamera(
            index=index,
            width=cam_cfg["width"],
            height=cam_cfg["height"],
            fps=cam_cfg["fps"],
            fourcc=cam_cfg["fourcc"],
        )

        if not camera.open():
            print("Camera: FAILED")
            print(f"  {camera.error}")
            return 1

        print("Camera: CONNECTED")

        # Pin exposure / white balance if asked. This module runs
        # AGC/AEC/AWB automatically and has a rolling shutter, so
        # leaving it on auto costs both stereo consistency and, in dim
        # light, motion blur. See config/camera.yaml.
        camera.cpu_cores = layout.get("camera")

        controls = dict(cam_cfg.get("controls") or {})
        if profile_exposure is not None:
            controls.update({
                "auto_exposure": 1,
                "white_balance_automatic": 0,
                "exposure_time_absolute": max(1, int(round(profile_exposure * 10))),
            })
            if profile_gain is not None:
                controls["gain"] = profile_gain
        if args.lock_exposure is not None:
            controls.update({
                "auto_exposure": 1,
                "white_balance_automatic": 0,
                # UVC exposure_time_absolute is in units of 100 us.
                "exposure_time_absolute": max(1, int(round(args.lock_exposure * 10))),
            })
        if controls:
            applied, failed = camera.apply_controls(controls)
            if applied:
                print(f"Camera controls: {applied}")
            if failed:
                print(f"Camera controls REJECTED: {failed}")

    a = camera.actual
    print(f"Resolution: {a['width']}x{a['height']}")
    print(f"Format: {a.get('fourcc', '?')}")
    print(f"FPS: {a.get('fps', '?')}")

    for w in camera.mode_warnings():
        print(f"  WARNING: {w}")

    eye_w = a["width"] // 2
    eye_h = a["height"]
    print()
    print(f"Stereo: READY  (left {eye_w}x{eye_h}, right {eye_w}x{eye_h})")

    camera.start()
    state.camera = camera

    # ----------------------------------------------------------
    # 2. Temporary lens model - preview only
    # ----------------------------------------------------------
    if "temporary_lens" in cfg:
        state.temporary_lens = TemporaryLensModel(**cfg["temporary_lens"])

    # ----------------------------------------------------------
    # 3. Calibration
    # ----------------------------------------------------------
    print()
    calib_cfg = cfg.get("calibration") or {}
    status, message, calib = calibration_status(
        args.calibration,
        max_baseline_m=calib_cfg.get("max_baseline_m", 0.095),
    )

    if status == "MISSING":
        print("SLAM: CALIBRATION REQUIRED  (no calibration file yet)")
        print()
        print(message)
        state.slam_enabled = False
        state.slam_disabled_reason = "no stereo calibration file"
    elif status != "OK":
        print("SLAM: CALIBRATION UNUSABLE")
        print()
        print(message)
        state.slam_enabled = False
        state.slam_disabled_reason = f"{status}: calibration unusable"
    elif args.no_slam:
        print("SLAM: DISABLED (--no-slam)")
        state.slam_enabled = False
        state.slam_disabled_reason = "--no-slam was given"
    else:
        if getattr(calib, "scale_unverified", False):
            print("Calibration: LOADED - SCALE UNVERIFIED")
            state.scale_unverified = True
        else:
            print("Calibration: OK")
        print(message)

        for w in calib.sanity_warnings():
            print(f"  WARNING: {w}")

        # ------------------------------------------------------
        # 4. Rectification
        # ------------------------------------------------------
        rect_cfg = cfg.get("rectification", {})
        camera_model = cfg.get("slam", {}).get("camera_model", "fisheye")

        if exported is not None:
            side = exported["sidecar"]
            camera_model = side["camera_model"]
            rect_cfg = dict(rect_cfg)
            rect_cfg["width"] = side["output"]["width"]
            rect_cfg["height"] = side["output"]["height"]
            rect_cfg["target_hfov_deg"] = side["output"]["hfov_deg"]
            if side.get("experimental_parameters"):
                # Surface it in the GUI too, next to the pose numbers
                # those values affect.
                state.scale_unverified = True

        out_w = rect_cfg.get("width") or calib.image_size[0]
        out_h = rect_cfg.get("height") or calib.image_size[1]

        if camera_model == "fisheye":
            # Downscaling a fisheye is only valid if both axes scale
            # equally; otherwise the lens model itself would change.
            native_w, native_h = calib.image_size
            out_h = int(round(out_w * native_h / float(native_w)))

        out_size = (int(out_w), int(out_h))

        if tuple(calib.image_size) != (eye_w, eye_h):
            print()
            print(
                f"  WARNING: the calibration was made at "
                f"{calib.image_size[0]}x{calib.image_size[1]} per eye but the "
                f"camera is delivering {eye_w}x{eye_h}. The intrinsics do not "
                f"transfer between resolutions. Recalibrate at the current mode."
            )

        try:
            if camera_model == "fisheye":
                # No rectification at all: ORB-SLAM3 gets the raw
                # fisheye images and applies Kannala-Brandt itself.
                state.rectifier = FisheyeStereoModel(calib, out_size=out_size)
            elif camera_model == "rectified":
                state.rectifier = StereoRectifier(
                    calib,
                    out_size=out_size,
                    balance=rect_cfg.get("balance", 0.0),
                    fov_scale=rect_cfg.get("fov_scale", 1.0),
                    target_hfov_deg=rect_cfg.get("target_hfov_deg", 100.0),
                )
            else:
                raise ValueError(
                    f"unknown slam.camera_model '{camera_model}' "
                    f"(expected 'fisheye' or 'rectified')")
            state.camera_model = camera_model
        except Exception as exc:  # noqa: BLE001
            print(f"Camera model setup FAILED - {exc}")
            state.slam_enabled = False
            state.slam_disabled_reason = f"rectification failed: {exc}"
        else:
            print()
            print(f"Camera model: {camera_model.upper()}")
            print(state.rectifier.describe())
            for w in state.rectifier.consistency_warnings():
                print(f"  WARNING: {w}")

            # --------------------------------------------------
            # 5. ORB-SLAM3
            # --------------------------------------------------
            slam_cfg = cfg["slam"]
            settings_path = resolve(slam_cfg["settings_out"])
            vocab_path = resolve(slam_cfg["vocabulary"])

            if exported is not None:
                # Use the exported file verbatim - the whole point is
                # that it needs no conversion.
                settings_path = os.path.abspath(args.settings)
                print(f"\nORB-SLAM3 settings: {settings_path} (exported, as-is)")
            else:
                state.rectifier.write_orbslam3_settings(
                    settings_path,
                    fps=a.get("fps") or cam_cfg["fps"],
                    orb=slam_cfg.get("orb", {}),
                    th_depth=slam_cfg.get("th_depth", 40.0),
                )
                print(f"\nORB-SLAM3 settings written: {settings_path}")

            if not SlamWorker.native_available():
                print()
                print("SLAM: MODULE NOT BUILT")
                print(f"  {SlamWorker.native_error()}")
                print("  Build it with:")
                print("    bash scripts/01_build_orbslam3.sh")
                print("    bash scripts/02_build_binding.sh")
                state.slam_enabled = False
                state.slam_disabled_reason = "novex_orbslam3 module not built"
            elif not os.path.exists(vocab_path):
                print()
                print(f"SLAM: VOCABULARY MISSING at {vocab_path}")
                print("  bash scripts/01_build_orbslam3.sh extracts it.")
                state.slam_enabled = False
                state.slam_disabled_reason = "ORB vocabulary missing"
            else:
                state.recorder = StereoRecorder(os.path.join(ROOT, "recordings"))

                state.worker = SlamWorker(
                    camera=camera,
                    rectifier=state.rectifier,
                    vocabulary_path=vocab_path,
                    settings_path=settings_path,
                    use_orbslam_viewer=args.orbslam_viewer,
                    map_update_every=slam_cfg.get("map_update_every", 10),
                    recorder=state.recorder,
                    verbosity=slam_cfg.get("verbosity", 1),
                )
                state.worker.cpu_cores = layout.get("slam")
                state.slam_enabled = True

                plane_cfg = slam_cfg.get("planes") or {}
                if plane_cfg.get("enabled", True):
                    state.plane_worker = PlaneWorker(state.worker, plane_cfg)

                print()
                print("SLAM: WAITING FOR MOTION")
                print(f"  SLAM confined to cores {layout.get('slam')}, "
                      f"capture to {layout.get('camera')}")
                print("  (loading the ORB vocabulary takes 10-20 seconds)")
                state.worker.start()
                if state.plane_worker is not None:
                    state.plane_worker.start()

                # Sweep OpenCV's worker pool onto the SLAM cores once
                # the pipeline is warm. The pool is created lazily and
                # can predate the SLAM thread, so it does not inherit
                # the mask - see affinity.confine_stray_threads.
                if layout.get("slam"):
                    state.worker.ready.wait(timeout=60)
                    time.sleep(1.0)
                    exempt = {camera.capture_tid, threading.get_native_id()}
                    for line in state.worker.confine_helpers(exempt):
                        state.affinity.add(line)
                        print(f"  {line}")

    if state.recorder is None:
        state.recorder = StereoRecorder(os.path.join(ROOT, "recordings"))

    # ----------------------------------------------------------
    # 6. GUI
    # ----------------------------------------------------------
    print()
    print(LINE)
    print(" Opening GUI. Keys: R reset  C views  F features  M points")
    print("               T trajectory  P planes  1 first-person")
    print("               G snap to ground  D debug  V record  ESC quit")
    print(LINE)
    print()

    from PySide6.QtWidgets import QApplication  # noqa: E402
    from gui import MainWindow  # noqa: E402

    app = QApplication(sys.argv)
    window = MainWindow(state)
    window.show()

    code = app.exec()

    state.shutdown()

    # ORB-SLAM3's Shutdown() joins its own threads and occasionally
    # does not return. The work is done by this point, so exit hard
    # rather than hanging on the way out.
    os._exit(code)


if __name__ == "__main__":
    sys.exit(main())
