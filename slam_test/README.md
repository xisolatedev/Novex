# Novex — ORB-SLAM3 Stereo SLAM Test

A minimal proof-of-concept for the Novex project: point a USB binocular
camera around a room and watch **real ORB-SLAM3** estimate its trajectory
in a desktop GUI.

This is a test rig, not the Novex system. It does one thing: prove that
this camera plus ORB-SLAM3 can track motion in your room.

The SLAM is real. Poses, tracking state, feature counts, map points and
keyframes all come out of the actual ORB-SLAM3 library (UZ-SLAMLab
upstream) through a pybind11 binding. Nothing is simulated. Where a value
is unavailable the GUI shows `--` rather than a plausible-looking number.

---

## Contents

- [What you get](#what-you-get)
- [Architecture](#architecture)
- [Hardware assumptions](#hardware-assumptions)
- [Installation](#installation)
- [Calibration — read this](#calibration--read-this)
- [Running](#running)
- [Controls](#controls)
- [Recording and replay](#recording-and-replay)
- [Configuration](#configuration)
- [Performance](#performance)
- [Troubleshooting](#troubleshooting)
- [Honest limitations](#honest-limitations)

---

## What you get

A single window showing:

```
+------------------------------+---------------------------+
| LEFT CAMERA                  | RIGHT CAMERA              |
|  (raw / rectified / ORB)     |                           |
+------------------------------+---------------------------+
|                              | SLAM                      |
|                              |   Tracking     OK         |
|      3D TRAJECTORY           |   Camera FPS   29.7       |
|      + map points            |   SLAM FPS     14.2       |
|      + keyframes             |   Features     250        |
|      + live camera frustum   |   Map points   3000       |
|                              | POSE                      |
|                              |   X Y Z, roll/pitch/yaw   |
|                              | DEBUG (toggle with D)     |
+------------------------------+---------------------------+
```

- Live left and right images, switchable between **Raw**, **Rectified**
  and **ORB features**.
- ORB keypoints drawn on the left image: grey dots for detected features,
  green boxes for features matched to a map point.
- Real ORB-SLAM3 tracking state: `NO_IMAGES_YET`, `NOT_INITIALIZED`,
  `OK`, `RECENTLY_LOST`, `LOST`, `OK_KLT`.
- Position in metres and orientation in degrees.
- Real-time 3D view: trajectory, map point cloud, keyframes, coordinate
  axes and the live camera pose, orbitable with the mouse.
- Camera FPS, SLAM FPS, GUI FPS, per-stage latency, dropped frames.
- Record and replay, so you can walk the room once and debug against
  that same walk repeatedly.

---

## Architecture

```
USB camera (one 2560x720 MJPEG frame containing both eyes)
     |
     v
Capture thread ------> latest-frame slot (no queue, newest wins)
     |
     +--> GUI thread (raw preview, 30 fps)
     |
     v
SLAM thread
     |  split the SAME frame:  left = [:, :1280]   right = [:, 1280:]
     |  BGR -> grayscale
     |  fisheye rectification (precomputed remap tables)
     v
ORB_SLAM3::System::TrackStereo      <-- real ORB-SLAM3, C++
     |
     v
published snapshot (pose, state, keypoints, map)
     |
     v
GUI thread reads the snapshot and draws
```

Why this shape:

- **The stereo pair can never desynchronise.** The camera delivers both
  eyes inside one frame, so splitting that single buffer is the entire
  synchronisation story. There is no possibility of pairing left frame
  #100 with right frame #103.
- **No queues anywhere.** The capture thread overwrites a single slot.
  A slow consumer misses frames instead of accumulating latency.
- **The GUI never calls into ORB-SLAM3.** It reads the last published
  snapshot. A slow repaint cannot stall SLAM, and slow SLAM cannot
  freeze the window.
- **The GIL is released** for the whole of `TrackStereo`, so the capture
  thread keeps running at full rate while ORB-SLAM3 works.
- **Frames are never processed twice.** Consumers ask for a frame newer
  than the last id they saw.

### Layout

```
slam_test/
├── README.md
├── requirements.txt
├── config/
│   ├── camera.yaml                  capture + pipeline settings (edit this)
│   ├── stereo_calibration.yaml      REAL calibration (produced by you)
│   └── orbslam3_stereo.yaml         GENERATED for ORB-SLAM3, do not edit
├── scripts/
│   ├── 00_install_system_deps.sh    the only step needing sudo
│   ├── 01_build_orbslam3.sh         builds Pangolin + ORB-SLAM3
│   ├── 02_build_binding.sh          builds the Python module
│   └── patch_orbslam3.py            modern-toolchain fixes for upstream
├── native/
│   ├── CMakeLists.txt
│   └── orbslam3_binding.cpp         pybind11 wrapper around ORB-SLAM3
├── src/
│   ├── main.py                      start-up and wiring
│   ├── camera.py                    threaded stereo capture
│   ├── calibration.py               calibration, rectification, config gen
│   ├── calibrate_stereo.py          calibration capture + solve
│   ├── workbench.py                 stereo configuration workbench (GUI)
│   ├── workbench_core.py            its parameter model, metrics, export
│   ├── charuco.py                   ChArUco board + stereo extrinsics
│   ├── make_board.py                printable board generator
│   ├── slam.py                      ORB-SLAM3 worker thread
│   ├── trajectory.py                pose maths and trajectory buffer
│   ├── viewer3d.py                  3D map/trajectory view
│   ├── recorder.py                  record and replay
│   └── gui.py                       PySide6 main window
├── calibration/pairs/               captured chessboard images
├── recordings/                      recorded sessions, saved trajectories
└── third_party/
    ├── ORB_SLAM3/                   upstream, patched by our script
    ├── Pangolin/
    └── install/                     local prefix, nothing touches the system
```

---

## Hardware assumptions

Camera: **GXIVISION-LSM22100** USB stereo module.

| Property | Value | Why it matters here |
|---|---|---|
| Output | one combined 2560x720 frame | both eyes in a single readout, so the stereo pair cannot desynchronise |
| Left / right | columns 0–1279 / 1280–2559 | split from the same buffer |
| Mode | MJPEG 2560x720 @ 30 fps | the only full-resolution mode; YUY2 at this size is 5 fps |
| Interface | USB 2.0 | MJPEG is mandatory, not a preference |
| Sensor | 1/4", **3.0 x 3.0 µm** pixels | with a 1.3 mm lens this gives ~433 px/radian, which sets how big your calibration board must be |
| Focus | fixed, **5 cm to infinity** | you can hold the calibration board close |
| Shutter | **electronic rolling** | see below |
| AGC / AEC / AWB | **auto by default** | see below |
| Module size | 100 x 22 x 16 mm | bounds the baseline: it cannot exceed 100 mm, and the app checks this |

Two of these deserve attention because they directly cost you tracking:

**Rolling shutter.** ORB-SLAM3 assumes a global shutter. On a rolling
shutter, camera motion shears the image — the top and bottom of a frame
are exposed at different times. Move smoothly, and keep the exposure
short.

**Automatic exposure and white balance.** If the two eyes drift to
different exposures, the same surface has different intensity in each
image, which undermines exactly what stereo matching depends on.
Measured on this camera: on auto, left/right mean brightness were
**76.5 / 78.1**; locked, they were **43.0 / 43.0**. Auto exposure also
lengthens the shutter in dim rooms, and a long shutter on a rolling
shutter turns motion into blur.

Both are fixed the same way:

```bash
python src/main.py --lock-exposure 20          # 20 ms, manual, AWB off
python src/calibrate_stereo.py ... --lock-exposure 20
```

or by filling in `camera.controls` in `config/camera.yaml`. If the room
is too dark at 20 ms, raise `gain` before raising exposure — gain adds
noise, but exposure adds motion blur, and blur is what breaks tracking.

None of this is assumed silently. On start-up the app prints the mode
the driver **actually** negotiated and warns if it differs from the
request.

## Installation

Tested on Linux Mint 22.3 (Ubuntu 24.04 base), gcc 13, CMake 3.28,
Python 3.12.

### 1. System packages — the only step needing root

```bash
cd slam_test
sudo bash scripts/00_install_system_deps.sh
```

What it installs and why:

| Package | Why |
|---|---|
| `build-essential`, `cmake`, `git`, `pkg-config` | ORB-SLAM3 is C++14 built with CMake |
| `libopencv-dev` | image handling, ORB extraction, rectification. ORB-SLAM3 requires OpenCV ≥ 4.4 |
| `libeigen3-dev` | all linear algebra in ORB-SLAM3, g2o and Sophus. Header-only |
| `libboost-serialization-dev` | ORB-SLAM3's map save/load |
| `libssl-dev` | ORB-SLAM3 links `-lcrypto` for map file checksums |
| `libglew-dev`, `libepoxy-dev`, mesa/X11/Wayland dev headers | needed to build Pangolin |
| `python3-dev` | headers for the pybind11 extension module |
| `v4l-utils` | `v4l2-ctl`, used to inspect what the camera really supports |

**Why Pangolin at all?** ORB-SLAM3's library includes `Viewer.cc` and
`MapDrawer.cc`, which link against Pangolin, so it is a hard build
dependency. This app builds the ORB-SLAM3 `System` with the viewer
**disabled** and draws its own 3D view, so Pangolin never opens a window
unless you pass `--orbslam-viewer`.

### 2. Python environment

```bash
cd ..                       # the Novex repo root
python3 -m venv .venv       # skip if .venv already exists
.venv/bin/pip install -r slam_test/requirements.txt
```

### 3. Build ORB-SLAM3

```bash
cd slam_test
bash scripts/01_build_orbslam3.sh
```

Takes 20–45 minutes. It:

1. Applies `scripts/patch_orbslam3.py` to upstream ORB-SLAM3 (see below).
2. Builds and locally installs Pangolin into `third_party/install`,
   with `CMAKE_INSTALL_RPATH=$ORIGIN`. That is not cosmetic: Pangolin
   is a dozen interdependent libraries, and a parent's `RUNPATH` is not
   inherited by transitive dependencies, so without `$ORIGIN` the
   Python module fails to import with
   `libpango_windowing.so: cannot open shared object file`.
3. Extracts the 145 MB ORB vocabulary.
4. Builds DBoW2, then ORB-SLAM3 itself (g2o comes along as a subproject).

The number of parallel jobs is derived from **free RAM**, not core count.
ORB-SLAM3 has translation units needing over 1 GB each, and over-
parallelising on a low-memory machine gets the build killed by the OOM
killer in a way that looks like a random compiler crash.

#### What the patch script changes, and why

Upstream ORB-SLAM3 does not compile on a 2024-era toolchain. Every change
is listed in `scripts/patch_orbslam3.py` with its reason:

- `cmake_minimum_required(2.8)` → `3.16`. CMake ≥ 3.27 refuses 2.8 outright.
- `-std=c++11` → `-std=c++14`. The bundled Sophus and g2o need C++14.
- `-fPIC` forced, because the libraries get linked into a Python module.
- `<cstdint>` added to five headers. gcc 13 no longer includes it transitively.
- The ~70 dataset example executables are not built. Only
  `libORB_SLAM3.so` is needed, and skipping them saves a lot of time.
- **Two genuine upstream bug fixes**, both found by running this code.
  `Camera.type: "Rectified"` never allocates a camera-2 model (a
  rectified pair shares one set of intrinsics plus a baseline), but
  `Settings`' `operator<<` dereferences that pointer unconditionally for
  STEREO, and the `Settings` constructor never initialises it. Since
  `System`'s constructor prints the settings, **every rectified stereo
  configuration segfaults on start-up** — upstream's own KITTI example
  included. The patch initialises the pointers and guards the print.
- **The one behavioural change:** two public getters, `GetAtlas()` and
  `GetTracker()`, are added to `System.h` so the GUI can read the map.
  ORB-SLAM3's algorithms are untouched.

The script is idempotent, and `git -C third_party/ORB_SLAM3 diff` shows
exactly what was changed.

### 4. Build the Python binding

```bash
bash scripts/02_build_binding.sh
```

Produces `src/novex_orbslam3*.so` and immediately imports it to prove it
links correctly.

---

## Calibration — read this

**The temporary slider values cannot drive stereo SLAM, and this app will
not pretend otherwise.**

The values you tuned by eye:

```
Source FOV : 112.0     K1: 0.141   K2: 0.0135   K3: 0.0   K4: 0.003
Center X/Y : 0.0       Virtual FOV: 99.0
```

are a *visual* correction. They make straight lines look straight. They
were never fitted to anything of known size, and — decisively — they
describe **one** lens. They say nothing about where the two lenses sit
relative to each other.

Stereo SLAM needs four things, and the sliders provide none of them
metrically:

1. **Per-eye intrinsics** `fx, fy, cx, cy` — the sliders assume both eyes
   are identical and perfectly centred. Real lenses are neither.
2. **Per-eye Kannala-Brandt distortion** `k1..k4` — fitted by eye, so
   they carry no metric meaning.
3. **Rotation R between the eyes** — completely unknown. A fraction of a
   degree of relative yaw breaks stereo matching, because ORB-SLAM3
   searches for correspondences along image rows.
4. **Translation T, and therefore the BASELINE** — completely unknown.
   This is the fatal one. The baseline is what converts disparity into
   metres. Without it there is no scale and stereo ORB-SLAM3 cannot
   initialise.

Until a real calibration exists, the app runs, shows the camera, and
displays **`CALIBRATION REQUIRED`** where SLAM would be. That is
deliberate. A fake baseline would produce a trajectory that looks
plausible and means nothing.

### Producing a real calibration

Calibration uses a **ChArUco** board by default: a chessboard with a
unique ArUco marker in every white square.

That choice is forced by this lens. A plain chessboard is only detected
when the **entire** board is inside the frame, so it can never reach the
frame corners — which on a ~112 degree fisheye is exactly where the
distortion you need to measure lives. The result is a calibration that
is well constrained in the middle and guessing at the edges. ChArUco
markers identify themselves, so **partial views still work**: you can
push the board half out of frame, into a corner, and every corner still
visible is used.

In testing against known ground truth, 13 of 28 views were partial —
those are views a plain chessboard would have discarded.

**1. Generate and print the board**

```bash
python src/make_board.py --squares 8x6 --square-size-mm 40
```

This writes `calibration/board.svg` (print this — SVG carries true
physical dimensions) and `calibration/board.png`. An 8x6 board with
40 mm squares is 32x24 cm and fits A3 landscape.

Print at **100% / "Actual size"**, with "fit to page" OFF. The sheet
includes a **100 mm verification ruler** — measure it. If it is not
100 mm, your printer rescaled the page and every distance ORB-SLAM3
reports will be wrong by that factor.

Glue it to something **rigid and flat**. A slight curve quietly
corrupts the whole calibration.

**2. Size the board for your lens**

This is what "barely finds it" means. With 3.0 µm pixels and a 1.3 mm
lens your eye is about 433 px/radian, so apparent square size is
`433 x square_size / distance`:

| Distance | 20 mm squares | 40 mm squares |
|---|---|---|
| 40 cm | 22 px | 43 px |
| 60 cm | 14 px | 29 px |
| 100 cm | **9 px** | 17 px |

OpenCV needs ~20 px per square for good subpixel corners and gives up
below ~10. **20 mm squares are too small** at any comfortable working
distance. Use 40 mm and work at 30–60 cm; the module focuses from 5 cm,
so getting close is fine. The live window shows a `px/square` readout so
you can see this directly.

**3. Measure a square with a ruler**, then run:

```bash
python src/calibrate_stereo.py --squares 8x6 \
    --square-size 0.0398 --marker-size 0.0298 --lock-exposure 20
```

`--squares` is the board size in **squares** for ChArUco (it was inner
corners for the old chessboard mode). `--square-size` is what you
measured, in metres — trust the ruler, not the number you asked for.

**4. Capture 20–40 pairs.** `SPACE` captures, `A` auto-captures. The
window shows a **coverage grid**: red cells have no data yet. Get every
cell green, including the corners — with ChArUco you can let the board
hang off the edge to do it. Tilt 30–45 degrees in several directions;
head-on views alone cannot separate focal length from distance.

**5. Press `C`.** It fits each eye with `cv2.fisheye.calibrate`, then
estimates the stereo transform, prints the RMS errors and the
**measured baseline**, and writes `config/stereo_calibration.yaml`.

Sanity check the result: per-eye RMS well under 1 px, and a baseline
that matches what you can measure between the lenses with a ruler. The
app also checks it for you — it knows the module is only 100 mm wide,
so it will reject an impossible baseline, and it flags the two eyes
disagreeing on focal length or non-square pixels.

#### "My camera is already distorted — don't I have to fix that first?"

No. That is backwards, and it is the most common way to ruin a
calibration.

**The curving is the measurement.** Calibration works by photographing
an object whose real geometry you know (squares of a size you measured)
and fitting a model to how your lens bends it. The distortion is the
signal, not noise to be removed first. So the tool is fed **raw**
frames, and it never applies the temporary FOV/K1–K4 slider correction.
If you undistorted the images first, the fit would be describing your
hand-tuned guess rather than your lens.

You do not need to know your FOV in advance either. The calibration
determines it, and the tool prints it:

```
MEASURED FOV: 156.8 deg horizontal, 88.1 vertical, 179.8 diagonal
```

#### If it really is a 180 degree lens

"180 degrees" on a spec sheet is almost always the **diagonal**. On a
1280x720 eye that works out as:

| Spec (diagonal) | Horizontal | Vertical |
|---|---|---|
| 180° | 157° | 88° |
| 150° | 131° | 74° |
| 120° | 105° | 59° |

Your hand-tuned model used f = 720/rad(112) = 368 px/rad, which implies
199° horizontal and 112° vertical — so your "112" was the **vertical**
span in your own parameterisation. A 180° diagonal spec does not
contradict it.

Three things follow for a lens this wide:

1. **The model has limits near the rim.** OpenCV's Kannala-Brandt model
   is parameterised through `theta = atan(r)`, which becomes singular
   at exactly 90° from the axis — the edge of a 180° field. It fits
   well out to roughly 150–160° and degrades beyond. Cover the frame,
   but do not expect the outermost ring to be trustworthy, and do not
   judge the calibration by it.

2. **A pinhole image cannot hold 180°.** `tan(90°)` is infinite. So
   rectification necessarily discards field of view — that is geometry,
   not a bug:

   | Kept FOV | Centre resolution | |
   |---|---|---|
   | 90° | 11.2 px/deg | |
   | 110° | 7.8 px/deg | |
   | 120° | 6.4 px/deg | wasteful |
   | 140° | 4.1 px/deg | impractical |

   With a 180°-diagonal lens the default `fov_scale: 1.0` lands at about
   **120° rectified horizontal**, which is a reasonable place to be. The
   app warns if your settings push past 130° or below 55°. Tune
   `rectification.fov_scale` and `rectification.balance` in
   `config/camera.yaml`; aim for 90–110°.

3. **Wide is good for SLAM.** A wide field sees more of the room, so
   features stay in view during rotation, which is exactly when
   narrow-FOV stereo SLAM loses tracking. Losing some FOV to
   rectification still leaves you better off than a narrow lens.

If you later want the full field, ORB-SLAM3 has a native
`KannalaBrandt8` fisheye stereo mode that skips pinhole rectification
altogether. `src/calibration.py` is structured so `StereoRectifier` is
the only component that knows about the camera model, so that path can
be added without touching the camera, SLAM or GUI layers.

#### A note on the stereo maths

`cv2.fisheye.calibrate` accepts a different number of points in every
view, which is what makes partial ChArUco views usable.
`cv2.fisheye.stereoCalibrate` does **not** — it reshapes its inputs and
requires a uniform count, and fails outright on variable counts. So the
stereo extrinsics are computed differently: the board pose is solved
independently in each eye with `solvePnP` on undistorted points, and
the camera-to-camera transform (which must be identical for every view,
since the rig is rigid) is averaged across views via quaternions with
outlier rejection.

Validated against known ground truth in simulation: baseline recovered
to **0.10%**, rotation to **0.08 degrees**, and rectified rows aligned
to **0.09 px**.

### Why not feed the fisheye images to ORB-SLAM3 directly?

ORB-SLAM3 does support a `KannalaBrandt8` fisheye stereo mode. This app
uses the better-trodden path instead: rectify the fisheye pair into an
ideal pinhole pair with `cv2.fisheye`, and hand ORB-SLAM3
`Camera.type: "Rectified"`. ORB-SLAM3's own rectification only handles
the pinhole radtan model, which does not fit this lens, so the fisheye
rectification has to happen on our side either way.

`src/calibration.py` is deliberately modular — `StereoRectifier` is the
only thing that knows about the camera model, so a native KB8 path can be
added later without touching the camera, SLAM or GUI layers.

---

## Running

```bash
cd slam_test
../.venv/bin/python src/main.py
```

Expected output before the window opens:

```
NOVEX ORB-SLAM3 TEST
---------------------

Camera: CONNECTED
Resolution: 2560x720
Format: MJPG
FPS: 30

Stereo: READY  (left 1280x720, right 1280x720)

Calibration: OK
REAL stereo calibration (fisheye)
  BASELINE    : 62.41 mm  (measured)
  RMS stereo  : 0.3812 px

SLAM: WAITING FOR MOTION
  (loading the ORB vocabulary takes 10-20 seconds)
```

Then the GUI opens. To initialise, **translate the camera sideways** —
walk it 30–50 cm across the room. Rotating on the spot gives stereo no new
information and will not initialise. When `Tracking` turns green and reads
`OK`, ORB-SLAM3 has locked on and the 3D view starts drawing your path.

Useful variants:

```bash
../.venv/bin/python src/main.py --no-slam          # camera + GUI only
../.venv/bin/python src/main.py --camera 2         # different device
../.venv/bin/python src/main.py --replay recordings/2026-09-05_14-31-02
../.venv/bin/python src/main.py --orbslam-viewer   # also open ORB-SLAM3's own viewer
```

`--orbslam-viewer` is a useful cross-check: it opens ORB-SLAM3's native
Pangolin window alongside the Novex GUI. Both should show the same pose,
because both read the same `System`.

Bring-up steps can also be run alone:

```bash
../.venv/bin/python src/camera.py        # step 1: prove the camera and the split
```

---

## Controls

| Key | Action |
|---|---|
| `R` | Reset SLAM (clears the map and trajectory) |
| `C` | Cycle camera view: Raw → Rectified → ORB features |
| `F` | Jump to the ORB feature view |
| `M` | Toggle map points in the 3D view |
| `T` | Toggle the trajectory |
| `P` | Toggle detected planes |
| `1` | First-person mode (ride the camera) |
| `G` | Snap the view to the detected ground plane |
| `D` | Toggle the debug panel |
| `V` | Start / stop recording |
| `ESC` | Quit |

All of these also exist as buttons. In the 3D view: left-drag orbits,
right-drag pans, the wheel zooms, and double-click toggles follow-camera.
In first-person mode the wheel changes field of view instead of zoom.

---

## Speed: profiles and CPU isolation

### Profiles

```bash
python src/main.py --fast              # 848x480 @ 30 fps, for fast movement
python src/main.py --profile quality   # 1280x720, 4000 features
python src/main.py --profile fastest   # 640x360, maximum rate
```

Measured on real frames from this camera:

| Profile | Size | Features | Stereo | SLAM fps |
|---|---|---|---|---|
| `quality` | 1280x720 | 4005 | 1345 | 6.8 |
| `balanced` | 960x540 | 1505 | 504 | 12.3 |
| **`fast`** | 848x480 | 1205 | 405 | **29.0** |
| `fastest` | 640x360 | 703 | 247 | 47.7 |

**The key insight for fast movement: what breaks tracking is not a low
feature count, it is large motion BETWEEN frames.** Running at 29 fps
with 1200 features tracks fast motion far better than 7 fps with 4000,
because each frame has moved roughly a quarter as far. Resolution is
the cheapest thing to trade, since ORB extraction cost is close to
linear in pixel count.

`fast` also drops the shutter to **8 ms**. On a rolling-shutter sensor
a long exposure shears and blurs the frame while the camera moves, and
blurred corners do not match between eyes or across frames. If the
image is too dark at 8 ms, raise `gain` rather than exposure.

Profiles are defined in `config/camera.yaml` and merge into the config,
so a profile only states what it changes.

Note the calibration is resolution-independent here: `StereoRectifier`
derives the rectified intrinsics from the target FOV and output size,
so switching profiles does **not** invalidate your calibration.

### CPU isolation

On a 4-core machine the capture thread, ORB-SLAM3 and the GUI all
compete. When they collide the symptom is not a graceful slowdown - the
capture thread gets descheduled while ORB-SLAM3 optimises and frames
are dropped at the USB layer, gone for good. Measured on this machine
under load, `cap.grab()` alone - pure USB dequeue, no decoding - took
117 ms per frame.

So threads are pinned:

```
core 0        cores 1..N-1
camera + GUI  ORB-SLAM3
```

Two Linux behaviours make this work, both verified here:

- `sched_setaffinity(0, mask)` applies to the **calling thread**, not
  the process.
- A thread **inherits** its creator's mask. ORB-SLAM3 spawns its own
  threads (LocalMapping, LoopClosing, two ORB extractors per stereo
  frame), and because they are created underneath the pinned SLAM
  worker they are confined automatically.

There is one exception, and it took measuring to find. **OpenCV's
parallel worker pool is created lazily**, on whichever thread first
triggers parallel work - in practice the main thread, while building
the rectification maps. Those pool threads therefore predate the SLAM
worker and do not inherit its mask; they were observed running on cores
`0-3` while the SLAM worker was correctly confined to `1-3`, which put
`cv2.remap` straight back onto the capture core. They are swept onto
the SLAM cores after start-up (`affinity.confine_stray_threads`).

The debug panel (`D`) shows the requested layout and the actual mask of
every thread, so you can confirm it rather than trust it. Override with
the `cpu:` section of `config/camera.yaml`.

## Stereo Configuration Workbench

```bash
python src/workbench.py --lock-exposure 20
```

A **standalone** tool for finding the best rectified configuration and
exporting it for ORB-SLAM3. It reads your calibration and **never**
writes to `config/stereo_calibration.yaml` or
`config/orbslam3_stereo.yaml` — verified by checksum in the test suite.

### The number to steer by

After rectification a real 3D point must land on the same image **row**
in both eyes. So the headline metric is the **median vertical offset**
of stereo feature matches, plus the fraction within 1.5 px. Measured on
real frames from this camera:

| | median epipolar error | inliers |
|---|---|---|
| correct geometry | **0.00 px** | 79.5% |
| with 1° of induced rotation error | **7.17 px** | 0.5% |

That collapse is what makes the tool useful: you can *see* when a
parameter change is wrong, not just guess. ORB-SLAM3's rectified stereo
matching searches along rows, so this is exactly the property it needs.

The statistic is deliberately the **median**, not the mean. Repetitive
texture produces a tail of gross mismatches whose vertical offset is
huge; on real frames the mean read 16.7 px while the median read 0.00,
and the mean barely moved when geometry was deliberately broken. Match
filtering is mutual-nearest-neighbour + Lowe ratio + Hamming cap +
octave consistency + bounded positive disparity.

### Views (keys 1-6)

1. **Raw fisheye** — unmodified sensor data
2. **Rectified pair** — what ORB-SLAM3 would receive
3. **Feature matches** — green within 1.5 px, red beyond
4. **Epipolar check** — row guides, with vertical error drawn per match
5. **Disparity / depth** — SGBM, a diagnostic only; ORB-SLAM3 never uses it
6. **Stereo overlap** — green where both eyes see the scene

### What you can adjust

Every intrinsic (fx, fy, cx, cy), all four Kannala-Brandt coefficients,
and the full extrinsics (rotation as Rodrigues degrees, translation in
mm) per eye — plus rectified FOV, output resolution, zoom, principal
point shift and fps. Presets at 90/100/110/120/130°, and any custom
value.

**Measured versus experimental is enforced throughout.** Every
parameter remembers its calibrated value. Change one and it turns
**amber**, the validation panel names it, the export dialog asks you to
confirm, the exported YAML carries a warning header listing every
changed value with its measured original, and `main.py` prints the same
warning when it loads the file. A guess can never quietly become a
measurement.

### Validation

Physically impossible configurations are errors and block export: zero
baseline, a pinhole asked for ≥175° (`tan(90°)` is infinite), negative
focal lengths. Suspicious ones warn: baseline wider than the 100 mm
module, the two eyes disagreeing on focal length, an optical centre
outside the image, relative rotation above 5°, a baseline not mostly
along X, or asking for more field than the lens actually measures.

### Comparing and motion testing

**Snapshot current** records the configuration with its live metrics
into a table; **Restore selected** brings one back. **Motion test**
samples for 10 seconds while you move the camera and reports mean/worst
match count, inlier rate and epipolar error — a configuration that
holds up while moving is one ORB-SLAM3 can track with, which a static
check cannot tell you.

### Export

**Export for ORB-SLAM3** writes a complete, valid settings file —
camera model, intrinsics, distortion, stereo parameters, resolution,
fps, ORB and viewer settings — plus a `.novex.yaml` **sidecar**.

The sidecar matters. An ORB-SLAM3 `Rectified` file contains only the
*rectified* intrinsics, by design, because that is all ORB-SLAM3 needs.
But the application also has to rebuild the remap that produced those
images, which needs the raw fisheye K/D/R/T and the chosen output
geometry — none of which appear in that file. The sidecar carries them,
so the export needs no hand-conversion:

```bash
python src/main.py --settings config/workbench_rectified_120deg_1280x720.yaml
```

`main.py` uses the exported YAML **verbatim** for ORB-SLAM3 and rebuilds
the identical pipeline from the sidecar.

## Camera model: native fisheye vs rectified

Set `slam.camera_model` in `config/camera.yaml`. The default is
**`fisheye`**: the raw left/right frames go straight into ORB-SLAM3,
which applies the Kannala-Brandt model itself (`Camera.type:
"KannalaBrandt8"` — the same mode TUM-VI uses with 195 degree lenses).
Nothing is undistorted, nothing is remapped, nothing is cropped.

|  | `fisheye` (default) | `rectified` |
|---|---|---|
| Field of view kept | **all of it** | ~100 deg of ~169 |
| Per-frame remap | none | ~13 ms |
| Resampling | none | bilinear |
| Stereo matching | descriptor + Lowe ratio | epipolar row search |
| Depth available | inside the lens overlap | whole image |

**Why this helps rotational drift.** Rectifying to a pinhole image
discards the periphery, and the periphery is where image motion is
largest under rotation — so it is what most strongly constrains the
rotation estimate. Keeping the full field gives the optimiser far
better angular leverage. It also removes the remap and the resampling
that slightly softens corners.

**What it does not do, to be clear about it:**

- It is still **sparse**. ORB-SLAM3 computes depth at ORB keypoints
  only, never per pixel. Not rectifying does not produce a dense depth
  map and cannot.
- Stereo depth still only exists where the two lenses **overlap**.
  Features outside it are tracked monocularly — useful for rotation
  and for the map, but carrying no depth.
- Dense per-pixel depth would need a *rectified* pair, because block
  matchers search along image rows. The two goals genuinely pull apart.

The overlap band is computed, not guessed: points are placed across the
left camera's field at room depth, projected through both calibrated
lenses, and the columns where they land in both become
`Camera1/2.overlappingBegin/End`.

`Stereo.T_c1_c2` is derived from the measured calibration as
`[R^T | -R^T T]`, verified by round-trip to 0 micrometres.

### Downscaling still keeps the full field of view

The speed profiles work in fisheye mode too. Kannala-Brandt distortion
is a function of the **incidence angle**, not pixel size, so halving
the image halves `fx, fy, cx, cy` and leaves `k1..k4` untouched.
Measured FOV is identical at every scale (169.2 deg at 1280x720,
169.1 at 640x360) — the whole fisheye circle is still there, just
sampled less finely. Height is snapped to preserve the aspect ratio,
since scaling the axes differently would change the lens model.

### Two upstream bugs this exposed

Both are patched by `scripts/patch_orbslam3.py`:

1. **`Settings::readCamera2()` reads the right camera's distortion from
   `Camera1.k1..k4`.** A copy-paste slip: the right lens is modelled
   with the *left* lens's distortion. It matters most exactly where
   fisheye stereo is worth using.

2. **`ORBmatcher::SearchByProjection` (the relocalisation overload)
   reads out of bounds in fisheye mode.** A fisheye Frame holds both
   images' keypoints, `N = Nleft + Nright`, but `mvKeysUn` only ever
   gets `Nleft` entries. `GetFeaturesInArea` searches both grids and
   can return an index past that. Most of ORBmatcher guards this; this
   overload does not. It crashed roughly **one run in three**, always
   after tracking was lost and relocalisation began:

   ```
   ORBmatcher::SearchByProjection <- Tracking::Relocalization <- Track
   ```

   After the fix: 6 clean runs out of 6, across 60-109 track losses and
   15-27 map resets each — so the crash path was exercised hard.
   Harmless in the rectified path, where `Nleft == -1`.

Also note the GUI judges **Stereo %** against a lower threshold in
fisheye mode. Fisheye stereo matching is brute-force descriptor
matching with Lowe's ratio and no epipolar constraint, so it
legitimately yields a smaller fraction than a rectified row search;
holding both to the same bar would just paint a working setup red.

## Aggressive extraction, and using both cameras

The shipped ORB settings are deliberately far past ORB-SLAM3's defaults,
to pull out every usable point:

| | default | shipped |
|---|---|---|
| `n_features` | 1200 | **4000** |
| `n_levels` | 8 | **10** |
| `iniThFAST` / `minThFAST` | 20 / 7 | **10 / 3** |
| `Stereo.ThDepth` | 40 | **60** |

Lowering the FAST thresholds is what actually finds features on bland
surfaces — painted walls, doors, carpet — where the defaults find
nothing. Measured on real frames from this camera:

| Setting | Features L/R | Stereo matched | Track | FPS |
|---|---|---|---|---|
| default | 1205 | 391 (32%) | 82 ms | 12.1 |
| **shipped** | 4005 | **1377 (34%)** | 158 ms | 6.3 |
| extreme (8000/12 levels) | 8007 | 2840 (36%) | 240 ms | 4.2 |

**There is a real trade-off here and it is worth understanding.** More
features means a denser map, but a lower frame rate means larger motion
between frames, and large inter-frame motion is what actually breaks
tracking. If you find tracking dropping out while you walk, lower
`slam.orb.n_features` first — it is close to linear in cost, whereas
the FAST thresholds are what buy you coverage on bland surfaces.
(Those timings were taken on a loaded CPU, so they are pessimistic;
close other applications.)

### Is the second camera actually being used?

The SLAM panel answers this directly, rather than leaving you to
assume it:

- **Features L / Features R** — features extracted in each eye. If the
  right count is much lower, that eye is dim, dirty or out of focus.
- **Stereo pts** and **Stereo %** — how many left features found a
  match in the right image. This is the honest measure of stereo
  contribution: an unmatched feature carries **no depth** and behaves
  monocularly. The figure is colour-coded (green above 40%, red below
  20%).
- **Depth m** — the range of depths stereo actually recovered.

If Stereo % is low, the usual causes are a bad calibration (check the
rectified view: the two eyes must be row-aligned), one eye being darker
than the other (use `--lock-exposure`), or a scene with repetitive
texture, which makes matches ambiguous.

## First-person mode

Press `1` (or the button) to ride the camera: the 3D view is rendered
from the SLAM pose itself, so you see the map from where the camera is,
moving as you move it. The wheel changes field of view rather than
zoom, and the camera frustum is not drawn since you are inside it.

Press `1` again for the orbit view.

## Plane and ground detection

Planes are fitted to the **same 3D points ORB-SLAM3 triangulated** —
nothing is invented, and nothing is meshed. Sequential RANSAC finds the
plane with the most inliers, removes those points and repeats.

Detected planes are drawn as grid patches covering only the extent
their inlier points actually span, so a plane fitted to a small patch
is not rendered as an infinite floor. The ground is drawn in green,
other planes in blue, each with a short normal arrow.

The GEOMETRY panel reports the plane count, the ground's inlier count,
its distance, the camera's tilt relative to it, and the fit time.
Press `G` to snap the view to look down at the ground.

This runs on **its own thread**. A RANSAC pass over a few thousand
points costs tens of milliseconds, which would otherwise show up as a
periodic stall in tracking.

**An honest caveat about "ground".** There is no IMU, so gravity is
unknown and the world frame is simply wherever the camera was when
tracking initialised. The ground is identified by a stated assumption:
the camera's own +Y axis points down in the OpenCV convention, so if
you were holding the camera roughly upright at start-up, world +Y is
roughly down. The largest horizontal plane below the camera path is
then called the ground. **If you started with the camera tilted, this
will be wrong** — and a plane that fits the normal test but sits above
the camera is labelled `ceil` rather than silently called the floor.

Verified against a synthetic room: ground recovered at 1.500 m against
a 1.5 m ground truth, with the wall correctly classified separately.

Tunable under `slam.planes` in `config/camera.yaml`.

## Recording and replay

Press `V` (or the Record button). Recording writes the **raw** combined
2560x720 frames, before any rectification, so a recording stays valid even
if you redo the calibration later.

```
recordings/2026-09-05_14-31-02/
├── stereo.avi       raw combined frames, MJPG
├── timestamps.txt   one capture timestamp per frame
└── meta.yaml        resolution and negotiated camera mode
```

Replay it through the identical pipeline:

```bash
../.venv/bin/python src/main.py --replay recordings/2026-09-05_14-31-02
../.venv/bin/python src/main.py --replay recordings/2026-09-05_14-31-02 --loop
```

Encoding runs on its own thread behind a bounded queue. If the disk cannot
keep up, frames are **dropped and counted** (shown in the debug panel)
rather than stalling SLAM.

`Save trajectory (TUM)` writes the keyframe trajectory in TUM format to
`recordings/`, which standard SLAM evaluation tools can read.

---

## Configuration

Everything worth changing lives in `config/camera.yaml`, commented inline.
The values you are most likely to touch:

| Setting | Meaning |
|---|---|
| `camera.index` | which `/dev/videoN` |
| `camera.swap_eyes` | set true if the physical left lens lands on the right half |
| `rectification.width/height` | resolution fed to ORB-SLAM3. Default is full native 1280x720 — nothing is downsampled before SLAM. **Halve these first if SLAM FPS is too low** |
| `rectification.balance` | 0 = crop to valid pixels (no black edges, narrower FOV); 1 = keep the whole FOV with black wedges |
| `slam.orb.n_features` | 1200 by default. More features track better and run slower |
| `slam.th_depth` | how far "close" reaches, in baselines. With a few-cm baseline this must be generous or nothing indoors counts as close |

`config/orbslam3_stereo.yaml` is **generated** from your calibration on
every start. Editing it accomplishes nothing; change `camera.yaml` or
recalibrate.

---

## Performance

Measured on this machine (4 cores, 1280x720 per eye, unloaded):

| Stage | Cost |
|---|---|
| MJPEG capture | ~3 ms decode; transport-bound at 30 fps |
| BGR → grayscale, both eyes | ~3 ms |
| Fisheye rectification, both eyes | ~13 ms |
| `TrackStereo` (real ORB-SLAM3, 1200 features) | **40 ms → 25 fps** |
| GUI repaint | 2–5 ms |

So expect roughly **17–20 fps of SLAM** against a 30 fps camera at full
1280x720. At 640x480 `TrackStereo` drops to 24 ms (42 fps).

**Machine load matters more than any of this.** Measured on this box
while Chrome had it at load average 12 on 4 cores, `cap.grab()` alone —
pure USB dequeue, no decoding — took 117 ms per frame, dragging the
camera to 8 fps. The camera and the pipeline were fine; the CPU was
simply not available. Close heavy applications before a SLAM run.

Deliberate choices:

- Remap tables are built **once** at start-up, never per frame.
- Grayscale conversion happens **before** rectification, not after —
  remapping one channel instead of three is about 35% faster.
- Camera images are scaled to their on-screen size exactly once, with
  `cv2.resize`, rather than being rescaled by Qt on every repaint.
- The map is copied to the GUI every 10 tracked frames, not every frame.
  It can hold tens of thousands of points; copying it per frame would
  cost more than tracking.
- The 3D view is software-rendered with QPainter. A polyline plus a few
  thousand points does not need OpenGL, and this avoids a whole class of
  GL driver problems on Linux.

SLAM will run slower than the camera. That is expected and is not a bug —
the debug panel shows how many frames were skipped. Camera capture stays
at full rate regardless.

---

## Troubleshooting

**`Could not open camera index 0`**
Check `ls /dev/video*`, close anything else using the camera, and confirm
your user is in the `video` group: `groups | grep video`. If not:
`sudo usermod -aG video $USER`, then log out and back in.

**Camera negotiated YUYV instead of MJPG, and FPS collapsed**
The app warns about this explicitly. Uncompressed YUYV cannot carry
2560x720 at 30 fps over USB. Check what the device offers:
`v4l2-ctl -d /dev/video0 --list-formats-ext`. If it opened on the wrong
node, try `--camera 1`.

**Resolution came back as something else**
The driver rejected the request. The app prints the actual mode; use
`v4l2-ctl --list-formats-ext` to find a mode the camera really supports
and set it in `config/camera.yaml`.

**`SLAM: CALIBRATION REQUIRED`**
Working as intended. See [Calibration](#calibration--read-this).

**`novex_orbslam3` module not built**
Run `scripts/01_build_orbslam3.sh` then `scripts/02_build_binding.sh`.
If the import fails with an undefined symbol, the binding and ORB-SLAM3
were built against different OpenCV versions — delete `native/build` and
rebuild.

**ORB-SLAM3 exits immediately with "parameter must be an integer number"**
`Camera.fps`, `Camera.width`, `Camera.height`, `Camera.RGB` and the
integer ORB extractor settings are read with `readParameter<int>`, and
ORB-SLAM3 calls `exit(-1)` — killing the whole process — if the YAML
holds `30.0` instead of `30`. `calibration.py` coerces these when it
generates the file, so this only bites if you hand-edit
`config/orbslam3_stereo.yaml`. Don't; regenerate it.

**The binding fails to compile with pybind11 errors**
`native/CMakeLists.txt` builds at C++14 to match ORB-SLAM3's own flags.
pybind11 3.x works at C++14 but is happier at C++17; if you hit template
errors from pybind11 headers, change `set(CMAKE_CXX_STANDARD 14)` to `17`
there. Mixing C++14 and C++17 translation units is safe with the same
compiler and libstdc++.

**Build killed with no error / "internal compiler error"**
Out of memory. The build script picks its job count from free RAM, but
you can force it lower: `MAKEFLAGS=-j1 bash scripts/01_build_orbslam3.sh`.

**State never leaves `NOT_INITIALIZED`**
Stereo initialisation needs texture and translation.
- Move the camera **sideways** 30–50 cm. Rotating in place will not work.
- Point it at something textured. Blank walls have no features.
- Check the ORB feature view (`F`). Under ~150 features means the scene
  is too plain or too dark.
- Check the rectified view (`C`). If it looks warped or the two eyes are
  not row-aligned, the calibration is bad — recalibrate.

**Tracking goes `LOST` constantly**
Usually motion blur or a poor calibration. Move more slowly, add light,
and confirm your stereo RMS was well under 1 px. Reduce
`rectification.width/height` to raise SLAM FPS — low frame rate means big
inter-frame motion, which is what actually breaks tracking.

**Trajectory scale looks wrong** (you walked 3 m, it says 1 m)
Your `--square-size` was wrong. Every distance scales linearly with it.
Re-measure the printed board and recalibrate.

**The app hangs on exit**
ORB-SLAM3's `Shutdown()` occasionally does not return. `main.py` calls
`os._exit()` after shutdown for exactly this reason. If it still hangs,
the SLAM threads deadlocked upstream; kill it.

---

## What has actually been verified

Proven by running it on this machine:

- The binding compiles, links and imports against the real
  `libORB_SLAM3.so`.
- OpenCV 4.6 (linked into the C++ side) and OpenCV 5.0 (the Python
  wheel) coexist in one process in either import order. The binding
  passes numpy arrays, never `cv::Mat`, across the boundary.
- `ORB_SLAM3::System` constructs in ~6 s and **tracks**: on a
  synthetic-but-geometrically-exact rectified stereo sequence it
  reached state `OK` and held it.
- **Metric scale is correct.** Against a known 1.170 m translation,
  ORB-SLAM3 reported 1.167 m — 0.3% error. This is the end-to-end proof
  that the baseline → `Stereo.b` → metric-pose path is right.
- Map points, keyframe positions, map stats, `reset()` and `shutdown()`
  all return sensible data.
- The camera negotiates 2560x720 MJPG, and the two halves are confirmed
  to be genuinely different images rather than one duplicated frame.
- The GUI renders in both states — tracking, and CALIBRATION REQUIRED —
  across all three view modes.
- The **whole calibration path**, against known ground truth in a
  simulated fisheye stereo rig: baseline recovered to **0.10%**,
  relative rotation to **0.08 degrees**, per-eye RMS ~0.28 px, and
  rectified rows aligned to **0.09 px**. 13 of 28 views were partial,
  which is the case a plain chessboard cannot handle.
- Manual exposure control on the real camera: both eyes locked to
  identical brightness.

Not yet verified, because it needs your calibration:

- That ORB-SLAM3 tracks on **real images from this camera**. The
  synthetic test proves the plumbing and the scale maths; it cannot
  prove your lenses, your lighting or your room will give ORB enough to
  work with. That is what the first real run is for.

---

## Honest limitations

- **Not calibrated until you calibrate it.** The shipped configuration
  contains no stereo calibration. That is the point.
- **No IMU.** The world frame is wherever the camera happened to be when
  tracking initialised. It is not gravity-aligned, so "up" in the 3D view
  is not up in your room, and the floor grid is a scale reference rather
  than a horizon.
- **Scale rests on one ruler measurement.** The chessboard square size is
  the only place metric truth enters the system.
- **The camera model is a compromise.** Rectifying a ~112° fisheye into a
  pinhole image loses field of view at the edges (that is what `balance`
  trades). ORB-SLAM3's native fisheye stereo mode would keep more of it;
  this is left as a later step.
- **The two eyes share one sensor readout** and are genuinely
  synchronised, which is a real advantage — but the app has no way to
  verify the vendor did not do something strange internally. If SLAM
  behaves oddly despite a good calibration, that is worth checking.
- **Loop closure will jump the trajectory.** When ORB-SLAM3 recognises a
  place it has seen, it corrects the whole map, and the drawn path moves.
  That is correct behaviour, not a glitch.
- **Performance is CPU-bound.** No GPU is used by anything here.
- **Only the STEREO sensor mode is wired up.** Monocular, RGB-D and the
  inertial modes exist in ORB-SLAM3 but are not exposed.

---

## Licence note

ORB-SLAM3 is GPLv3 (UZ-SLAMLab). It is fetched into `third_party/` at
build time, not vendored here. Anything you distribute that links it
inherits that obligation.
