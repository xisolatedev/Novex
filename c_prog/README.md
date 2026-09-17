# Novex VIO

A lightweight stereo visual-inertial odometry pipeline for the
Raspberry Pi Zero 2 W. Built from scratch: no ORB-SLAM3, no OpenVINS,
no ROS. Dependencies are OpenCV and Eigen, and nothing else.

The IMU is genuinely optional. With it disabled the system is stereo
visual odometry and nothing is stubbed or faked; with it enabled the
IMU contributes where it can do so honestly (see
[Assumptions](#assumptions)).

Status: **the pipeline runs end to end on real hardware at 30 fps**,
with a live 3D feature point cloud in the dashboard. Measured numbers
below are from actual runs, not estimates. The sections on what is
*not* finished are as important as the rest, and are at the bottom.

**Drift:** the dominant drift sources were found, measured and fixed -
see [Drift: what was wrong and how it was measured](#drift-what-was-wrong-and-how-it-was-measured).
On a 90 s handheld loop, scored against a directly measured ground
truth, the end-pose error went from **52.4° / 4.00 m** to
**4.6° / 0.59 m**; on 100 s with the camera still, from **86.5° /
0.64 m** to **0.83° / 0.035 m**.

---

## Project tree

```
c_prog/
├── CMakeLists.txt
├── README.md
├── config/
│   ├── novex_vio.yaml           runtime configuration (new)
│   ├── stereo_calibration.yaml  the EXISTING calibration, unmodified
│   ├── camera.yaml              legacy, from the ORB-SLAM3 experiment
│   └── orbslam3_stereo.yaml     legacy, from the ORB-SLAM3 experiment
├── deploy/
│   └── novex-vio.service        systemd unit for the Pi
├── web/                         --web dashboard (Node + Three.js)
│   ├── server.js                relay: Unix socket -> WebSocket
│   ├── lib/websocket.js         small RFC 6455 server, no deps
│   ├── lib/novexclient.js       daemon socket client (text + binary)
│   ├── lib/pointcloud.js        point wire format, per-browser map sync
│   ├── public/                  index.html, app.js, style.css
│   │   ├── mesh-worker.js       experimental surface mesh (Web Worker)
│   │   └── vendor/              Three.js r160, vendored
│   ├── tools/mock-daemon.js     TEST FIXTURE (synthetic data)
│   └── README.md
├── include/
│   ├── Time.hpp                 the one clock everything shares
│   ├── Log.hpp                  levelled, rate-limited logging
│   ├── Profiler.hpp             per-stage timing, measured frame rates
│   ├── Yaml.hpp                 small YAML reader (see note below)
│   ├── VIOConfig.hpp            all runtime settings, one place
│   ├── CommandQueue.hpp         reset/recenter/pause -> VIO thread
│   ├── DebugStatistics.hpp      --debug collection (observer only)
│   ├── DebugReporter.hpp        end-of-run report
│   ├── WebServer.hpp            Node child process lifecycle
│   ├── Camera.hpp               V4L2 stereo acquisition
│   ├── StereoCalibration.hpp    calibration + resolution adaptation
│   ├── FeatureTracker.hpp       grid Shi-Tomasi + KLT
│   ├── FisheyeGeometry.hpp      per-point Kannala-Brandt, angular errors
│   ├── StereoMatcher.hpp        left/right matching + left-ray range
│   ├── MotionEstimator.hpp      PnP RANSAC + robust angular refinement
│   ├── Diagnostics.hpp          per-frame geometry, stationary test
│   ├── PointCloud.hpp           3D points, voxel map, binary transport
│   ├── StateEstimator.hpp       pose integration, optional IMU aid
│   ├── IMU.hpp                  optional IMU, threaded ring buffer
│   ├── VIOState.hpp             the published state struct
│   ├── VIO.hpp                  pipeline coordinator
│   ├── StateServer.hpp          Unix-socket IPC
│   └── Gui.hpp                  development display (not core)
├── src/                         one .cpp per header above, plus main.cpp
├── tests/
│   ├── test_novex.cpp           39 in-process checks
│   ├── test_lifecycle.sh        daemon, IPC and signal checks
│   ├── test_web.sh              --debug / --web / point cloud checks
│   └── points_client.js         WebSocket point stream test client
└── tools/
    ├── novex_state_client.cpp   example IPC client (libc only)
    ├── geometry_audit.cpp       calibration + geometry audit
    ├── novex_record.cpp         record raw stereo frames
    ├── novex_replay.cpp         replay a recording through the real VIO
    └── benchmark.sh             measures this machine
```

`config/camera.yaml` and `config/orbslam3_stereo.yaml` are left over
from the earlier ORB-SLAM3 experiment. Novex VIO does not read them.

---

## Build

```bash
sudo apt install build-essential cmake libopencv-dev libeigen3-dev

cd c_prog
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j$(nproc)
```

Produces `build/novex-vio`, `build/novex-state`,
`build/novex-vio-test`, and the tools `build/novex-geometry-audit`,
`build/novex-record` and `build/novex-replay`.

`-DNOVEX_NATIVE_ARCH=ON` adds `-mcpu=native`. Use it only when the
binary will run on the machine that built it.

### Run the tests

```bash
./build/novex-vio-test          # 39 checks; needs the camera for 10 of them
./build/novex-vio-test --no-camera
./tests/test_lifecycle.sh       # daemon, IPC, SIGTERM/SIGINT
./tests/test_web.sh             # --debug/--web, point stream, controls
./build/novex-geometry-audit    # calibration + geometry, known answers
./build/novex-geometry-audit --recording DIR   # + checks on real frames
```

Tests that cannot run are reported as **SKIP**, never as a pass.

---

## Running

The default is daemon mode. All four required combinations work
without recompiling:

```bash
# Daemon, no IMU  - the default deployment mode
./build/novex-vio --mode daemon --no-imu

# Daemon, with IMU
./build/novex-vio --mode daemon --imu

# GUI, no IMU  - development
./build/novex-vio --mode gui --no-imu

# GUI, with IMU
./build/novex-vio --mode gui --imu
```

### Diagnostics

```bash
# Normal - no debug or web overhead at all
./build/novex-vio

# Benchmark: collect statistics, print a report on exit.
# No GUI, no browser, no Node. This is the SSH/Pi mode.
./build/novex-vio --debug

# Live Three.js dashboard at http://127.0.0.1:8080
./build/novex-vio --web

# Both: the dashboard shows live timings and the report
# still prints on exit.
./build/novex-vio --debug --web
```

Open the dashboard at **http://127.0.0.1:8080** (change with
`--web-port`). `--debug` and `--web` compose with every other flag:

```bash
./build/novex-vio --debug --web --mode gui --imu --features 250
```

Useful flags: `--debug`, `--web`, `--web-port N`, `--features N`, `--width/--height/--fps`, `--device N`,
`--socket PATH`, `--no-ipc`, `--no-stereo`, `--max-frames N`,
`--stationary-test`, `--keyframe-retention R`, `--no-pointcloud`,
`--no-point-map`, `--map-points N`, `--voxel-size M`,
`--log debug`, `--config PATH`. Full list with `--help`.

### Record once, replay many times

Estimator changes are compared on **identical input**, never on two
live runs that happened to see different motion:

```bash
./build/novex-record /tmp/loop 2700          # 90 s of lossless frames
./build/novex-replay /tmp/loop               # full --debug report
./build/novex-replay /tmp/loop --keyframe-retention 0 --stationary-test
./build/novex-geometry-audit --recording /tmp/loop
```

`novex-replay` drives the same `VIO` class the daemon uses, with the
recorded camera timestamps. Its stage timings measure PNG replay on
the machine running it; compare geometry and drift across replays and
performance on live runs.

Precedence is defaults, then the config file, then the command line.
A missing config file is not an error; the built-in defaults are a
working configuration.

GUI mode shows both eyes, tracked features (green = carries stereo
depth, amber = tracked without depth), tracking state, pose, IMU
status and every stage timing. It is development-only: the core has no
reference to it, the data flow is Camera → VIO → GUI, and daemon mode
never links a window into existence.

### Querying the daemon

```bash
./build/novex-state                 # one GET_STATE
./build/novex-state --stats         # timings and health
./build/novex-state --watch 10      # poll at 10 Hz
./build/novex-state --socket /tmp/other.sock
```

Real output from a running daemon:

```json
{"timestamp":1246432.492335,"position":[-0.065268,0.286746,0.106452],
 "velocity":[-0.032822,0.058707,0.030666],
 "orientation":[0.069960,0.041879,-0.020200,0.996466],
 "tracking":true,"feature_count":400,"inlier_count":47,
 "stereo_count":72,"imu_enabled":false,"imu_healthy":false,
 "gyro_bias":[0.0,0.0,0.0],"frame_id":182,"dropped_frames":0,
 "lost_frames":0}
```

The protocol is one word in, one line out, on a Unix domain socket:
`GET_STATE`, `GET_STATS`, `PING`, `QUIT`. From a shell:

```bash
printf 'GET_STATE\n' | socat - UNIX-CONNECT:/tmp/novex-vio.sock
```

A client can never stall the pipeline. The server runs on its own
thread and only copies a small struct under a mutex the processing
loop holds for microseconds once per frame; replies use
`MSG_DONTWAIT`, so a client that stops reading loses its reply rather
than parking anything. This is tested: check 15 hammers the socket
from one thread while a second client deliberately never reads, and
compares VIO time under load against idle.

---

## Drift: what was wrong and how it was measured

The symptom: tracking was strong (99%+ success, 150+ inliers) while the
pose drifted badly - tens of degrees and metres per minute, including
while the camera was barely moving. Nothing below was fixed by
clamping, smoothing, zeroing velocity or hiding frames. Each cause was
isolated by measurement, fixed, and re-measured on **identical
recorded input**.

### Method

* **Recordings.** `novex-record` saves lossless stereo frames with
  camera timestamps; `novex-replay` runs them through the real `VIO`
  class. Two recordings are used throughout: `static100` (100 s, camera
  on a desk) and `loop90` (90 s, handheld loop in a dim room, with fast
  turns, returned near the start).
* **Ground truth.** The true start-to-end pose of each recording was
  measured *directly* - ORB matches between the first and last frame,
  stereo depth on the first, one PnP - with no integration at all. For
  `loop90`: **22.48° (mostly yaw), position (−0.053, +0.051, +0.086) m,
  1σ 0.08° / 6 mm**, reproduced on three independent frame pairs within
  0.7° / 1.5 cm. For `static100`: 0.05° / 1 mm, i.e. genuinely still.
* **Stationary test** (`--stationary-test`, below) attributes drift to
  tracking, stereo, motion estimation or integration.

### Finding 1 - triangulated points did not lie on their own pixel

Linear DLT triangulation (`cv::triangulatePoints`) returns a
compromise between the left and right rays. This calibration's rays do
not intersect exactly (see [the calibration audit](#calibration-audit)),
so the 3D point missed the very left pixel it came from:

| 20 s stationary recording | left reprojection of stereo points | net drift |
|---|---|---|
| DLT (original) | median **0.445 px**, mean dy **+0.218 px** | **58.8° / 1.013 m** |
| point kept on the left ray | 0.000 px | 0.57° / 0.016 m |

Motion is PnP from those 3D points to the next frame's pixels, so every
frame PnP explained the constant vertical offset as a small pitch, and
the points were re-triangulated every frame, so it integrated. The
original run's 79.5° final pitch is this mechanism.

**Fix:** stereo now returns the point *on the left ray* closest to the
right ray; the right eye contributes range only
(`StereoMatcher::intersectOnLeftRay`, closed form, cheaper than DLT).
Calibration error can now only scale range, never manufacture
rotation. Regression-tested in `novex-geometry-audit` section 6: a
simulated 0.5 px stereo error with a still camera gives **0** motion,
against 0.042°/frame (1.3°/s) with DLT points.

### Finding 2 - fisheye residuals were weighted on the wrong surface

PnP refinement ran on the normalised image plane, where one pixel at
incidence θ is sec²θ larger than at the centre - about **13×** at the
corner of this 640×480 fisheye. Least squares was dominated by the
edge of the lens, where the calibration is worst. Stereo gating had
the mirror problem (13× stricter at the edge).

**Fix:** OpenCV RANSAC still proposes the pose, but inliers are chosen
by *angle* and the pose is refined by robust (Huber) Gauss-Newton on
bearing angles, which also yields the per-frame uncertainty and
conditioning now reported. Checked with 25% gross outliers and 0.5 px
noise: mean error 0.021° / 0.80 mm, consistent with the reported 1σ.

### Finding 3 - rejected frames silently lost their motion

A rejected estimate left the pose unchanged, and the next estimate
started from the *rejected* frame's depths - so that interval's real
motion was never measured. **Fix:** reference depths are kept across
rejected frames, and the next accepted estimate spans the gap (checked
by test P7). When too few features still carry reference depth, the
re-anchor is counted as genuinely unmeasured motion.

### Finding 4 - frame-to-frame integration drifts along a blind direction

With findings 1-3 fixed, `static100` still drifted 6.06° / 0.169 m,
and the stationary test called it a significant bias (11.2σ / 8.5σ).
Measured:

* brightness stable to 0.7/255 over the window - not illumination;
* chained KLT crept ~1 px from a direct first-to-last-frame KLT over
  90 s - real, but ~30× too small to explain 6°;
* the drift was rotation about x/y **paired with the opposite
  translation**, in the ratio of a pivot about a point 0.85-1.8 m in
  front of the camera. The scene's median depth is 1.35 m. For a scene
  at nearly one depth that pivot barely changes the image, so it is
  weakly observable per frame, and chaining 3000 frame-to-frame
  estimates random-walks along it.

**Fix: keyframe-relative estimation.** Each frame is measured against
a keyframe's 3D points, not the previous frame's, so per-frame errors
no longer integrate. A new keyframe is taken when the inliers still
linking to it fall below `motion.keyframe_retention` (0.7) of its
first estimate's. It reuses the reference-depth mechanism from
finding 3.

### Results, against ground truth

| | loop90 rotation err | loop90 position err | static100 rotation err | static100 position err |
|---|---:|---:|---:|---:|
| original code | 52.4° | 4.00 m | 86.5° | 0.64 m |
| findings 1-3 (frame-to-frame) | 35.6° | 2.24 m | 6.0° | 0.17 m |
| **+ keyframes (default, 0.7)** | **4.6°** | **0.59 m** | **0.83°** | **0.035 m** |

`static100` with keyframes: stationary-test bias 1.4σ / 0.9σ (no longer
significant), drift 0.52°/min. Keyframes raise the median reprojection
error from 0.17 to 0.34 px and lower the inlier ratio from 99% to 87%,
because observations are compared with older depths; that is the
expected cost, and it is reported rather than hidden.

### What is still wrong, measured

* **Stereo calibration.** On real frames the right-eye rays sit a median
  **+0.86 px low** (up to ~2.3 px towards the lens edge; audit section
  8). Since finding 1 this cannot create rotation, but it degrades
  matching and depth. The remedy is a stereo recalibration with better
  edge coverage, not a threshold.
* **Sensitivity is at the single-loop noise level.** On `loop90`,
  single-parameter changes moved the result within about ±2° / ±0.3 m
  (e.g. a 1.5 px epipolar gate: 2.9° / 0.35 m; depth ≤ 5 m: 2.3° /
  0.68 m; retention 0.5 / 0.8 / 0.9: 5.5° / 0.44 m, 3.8° / 0.61 m,
  4.2° / 0.79 m). Defaults were **not** tuned to one loop.
* **KLT creep** (~1 px / 90 s) and depth noise in far scenes (`loop90`
  median depth 3.5 m, 7.4 px parallax) bound what frame-to-keyframe PnP
  can do. There is no bundle adjustment and no loop closure.

---

## The calibration resolution problem

This was the part of the brief most likely to be silently got wrong,
so it was measured rather than assumed.

The existing calibration was captured at **1280×720 per eye**. The
camera mode in use is 1280×480 side by side, so **640×480 per eye**.
Those are different aspect ratios, so the calibration cannot simply be
scaled.

Three hypotheses were possible: the sensor squashes the full frame
anisotropically, it crops, or it does something else. To find out, the
same static scene was captured in both modes and a full affine was
fitted between the left eyes with ORB + RANSAC, then independently for
the right eyes:

```
left  : sx 0.66603  sy 0.66574  origin (159.5, -0.5)  window 960.9 x 721.0
right : sx 0.66708  sy 0.66471  origin (160.2, -0.2)  window 959.4 x 722.1
```

`sx` and `sy` agree to within 0.4%, so the mapping is **isotropic**,
and the implied source window is 960×720 at x = 160. The 640×480 eye
is therefore a **centered 960×720 crop of the calibrated 1280×720
image, scaled by exactly 2/3**.

That matters because it decides what happens to the lens model:

- **Kannala-Brandt k1..k4 are unchanged.** They map an incidence angle
  to a radius, which only holds for a square pixel grid. An isotropic
  scale leaves them exactly valid. An anisotropic one would have
  invalidated them silently.
- **fx, fy are multiplied by 2/3.**
- **cx, cy are shifted by the crop origin, then scaled.**
- **R, T and the baseline are untouched**, being rigid-body extrinsics
  that do not depend on image sampling at all.

`StereoCalibration` keeps the two coordinate sets strictly separate:
`calibrationLeftK()` returns the measured values verbatim,
`leftK()` returns the adapted ones, and `mapping()` describes exactly
how one became the other. The file on disk is never written.

The adaptation is derived from the *negotiated* camera mode, not the
requested one, so a driver that hands back a different resolution is
accounted for rather than corrupting everything downstream.

**This crop costs 25% of the horizontal field of view.** The daemon
warns about it at start-up. The 2560×720 mode keeps all of it and is
also available at 30 fps, at four times the pixel cost.

---

### Calibration audit

`novex-geometry-audit` checks every step with known answers, and with
`--recording DIR` also checks the calibration against real frames. Its
results on this rig:

| check | result |
|---|---|
| adapted K == crop-then-scale of the original, 625 rays incl. far outside the crop | max 6e-5 px (float32 floor) |
| k1..k4 untouched (valid only for an isotropic scale) | exact |
| pixel-centre convention: code aligns pixel centres at the crop origin; area-aligned resampling would differ by 0.5(1−s) | 0.167 px = a **0.033° common rotation**, 0.33 mm depth change at 2 m - negligible, and the ORB affine fit (±0.5 px) cannot tell the two apart, so the measured formula is kept |
| Kannala-Brandt pixel → bearing → pixel over the whole image, both lenses | max 1.7e-5 px, edge included |
| triangulation of known depths 0.3-20 m | max 1.3e-5 relative |
| disparity sign in a common orientation, baseline direction | positive; right eye at (+0.1104, −0.0001, −0.0018) m |
| **extrinsic convention on 5154 real matches**: X_right = R X_left + T | median ray miss **1.26 px**, 4.9% behind camera |
| … the inverted convention | 7.36 px, **82.5%** behind camera |
| … rotation ignored | 1.81 px, 10.7% behind |
| real-frame median vertical miss by radius 0-80 / 80-160 / 160-240 / 240-320 px | +1.32 / +1.03 / +0.32 / +1.15 px (overall **+0.86 px**) |

So the transformation, the lens model, the extrinsic convention, the
disparity and depth signs and the baseline direction are all correct.
What is not perfect is the calibration itself: a persistent vertical
offset between the eyes. It is reported live as "stereo vertical
offset" so a recalibration can be judged by it.

---

## Measured performance

### Before and after the drift and point cloud work

Development machine (Intel i5-8500T), live camera, same scene, 900
frames each, runs alternated original / new / original / new, point
cloud enabled in the new build:

| | original | new |
|---|---:|---:|
| average frame | 6.69 / 6.90 ms | **6.25 / 6.30 ms** |
| p50 / p99 | 6.12 / 15.1-21.1 ms | 5.62 / 13.9-14.1 ms |
| stereo | 3.9 / 3.2 ms | 3.1 / 3.0 ms |
| motion | 0.74 / 0.79 ms | 0.46 / 0.48 ms |
| point cloud stage | - | 0.02 ms |
| process CPU for 900 frames | 40.1 s | 38.6 / 38.9 s |

The new build is slightly **cheaper**: closed-form left-ray range beats
DLT plus its per-frame allocations, and the angular Gauss-Newton beats
`solvePnPRefineLM`.

The same holds on a harder scene. `process()` timed directly over the
first 900 frames of the dim handheld loop recording (~380 features;
the feature count keeps falling below the re-detect threshold, so the
~5 ms detection runs most frames - which is why this scene costs ~12 ms
and a still, textured desk ~6 ms):

| build | mean | p50 | p90 | p99 |
|---|---:|---:|---:|---:|
| original | 13.06 ms | 12.29 | 14.35 | 33.63 |
| new (defaults) | 12.55 ms | 12.31 | 14.16 | 16.37 |
| new, `--no-pointcloud` | 12.69 ms | 12.31 | 14.53 | 18.83 |
| new, frame-to-frame (no keyframes) | 12.33 ms | 11.81 | 13.80 | 22.10 |

The point cloud has no measurable cost and keyframing is within
run-to-run noise.

Visualisation cost, per thread, 25 s windows (the IPC thread is named
`novex-ipc` so this can be read in `top -H`):

| configuration | `novex-ipc` thread | Node relay | avg frame |
|---|---:|---:|---:|
| IPC only | 0.0% | - | 6.38 ms |
| `--web`, no browser | 0.3% | 0.5% | 6.53 ms |
| `--web` + a client taking the binary point stream | 0.4% | 1.1% | 6.09 ms |

Streaming the live points and map deltas at 10 Hz costs under half a
percent of one core on the daemon side; frame-time differences between
rows are run-to-run noise (other desktop load was present).

### Earlier measurements

Development machine, Intel i5-7500, 1280×480 MJPG, 400 features,
600 frames, **0 dropped**:

```
capture 30.0 fps   processing 30.1 fps   latency 54.5 ms
decode      3.6 ms      <- CPU cost of MJPG -> grayscale
preprocess  0.0 ms      <- eye splitting is zero-copy, so genuinely free
detect      5.7 ms      <- per detection, which does not run every frame
track       4.8 ms
stereo      6.3 ms
motion      0.7 ms
total      17.6 ms      <- per-frame processing
peak RSS   90 MB        CPU 115% (OpenCV threads internally)
```

`capture_ms` (15.8 ms) is mostly *blocking wait for the sensor* and is
not CPU. The per-frame CPU cost is `decode_ms + total_ms` ≈ 21 ms of
the 33 ms budget.

Feature-count sweep on the same machine, 400 frames each:

| features | decode | detect | track | stereo | motion | total | CPU/frame | 3D points |
|---------:|-------:|-------:|------:|-------:|-------:|------:|----------:|----------:|
| 150 | 3.66 | 3.44 | 2.45 | 2.83 | 0.50 |  7.37 | 11.0 ms | 42 |
| 250 | 4.21 | 4.98 | 5.08 | 6.67 | 0.57 | 15.72 | 19.9 ms | 60 |
| 400 | 4.07 | 5.85 | 5.01 | 6.93 | 0.59 | 16.38 | 20.4 ms | 81 |
| 600 | 3.76 | 6.59 | 7.16 | 9.76 | 0.81 | 24.10 | 27.9 ms | 98 |

**These are desktop numbers. No Raspberry Pi Zero 2 W was available
during this work, so its performance is genuinely unknown.** A
Cortex-A53 at 1 GHz is several times slower per core than this i5, so
the sensible starting point on the Pi is 150–250 features, not 400.
Run `tools/benchmark.sh` on the board and use the real answer.

### Benchmarking

```bash
./tools/benchmark.sh                  # default config, 600 frames
./tools/benchmark.sh --features 200   # any novex-vio flag passes through
FRAMES=1200 ./tools/benchmark.sh
```

It reports every stage, both measured frame rates, latency, dropped
frames, peak RSS and CPU time, and prints how to read them. Nothing is
estimated from a nominal frame rate: both rates come from differences
of real V4L2 timestamps.

### Three things the measurements caught

Worth recording, because all three looked correct and were not:

1. **`CAP_PROP_BUFFERSIZE = 1` halves the frame rate.** It reads like
   the right way to hold latency down. On this uvcvideo device nothing
   is queued to the hardware while userspace holds the only buffer, so
   every second frame is missed: 15.7 fps instead of 30.0. The queue
   depth is now left to the driver, and latency is controlled by
   explicitly dropping stale frames instead.

2. **The overload heuristic was throwing away good frames.** Dropping
   when lag exceeds 1.5 frame periods sounds reasonable, but the
   pipeline's *inherent* latency is already ~54 ms — a frame is
   timestamped at the sensor and read out only after decode and
   processing. The rule fired on every frame and dropped 59 of 64.
   It now learns the baseline lag and treats only an excess above that
   as a real backlog. Result: 600 frames, 0 dropped.

3. **An IMU rotation prior for the PnP solver did nothing.** Seeding
   `cv::solvePnPRansac` with the integrated gyro via
   `useExtrinsicGuess` looked sensible. Handing it a deliberately
   absurd guess returns a bit-identical answer, from both AP3P and
   ITERATIVE — the flag is ignored, which makes sense once you note
   that RANSAC over minimal samples is a global search with no
   starting point to improve. The plumbing was removed rather than
   left as a knob that quietly did nothing.


---

## Diagnostics: `--debug` and `--web`

Both are off by default and cost nothing when off. Neither can slow the
estimator down.

```
                 NOVEX VIO
                     │
          ┌──────────┴──────────┐
       VIO CORE             DEBUG SYSTEM
          │                     │
          │              ┌──────┴──────┐
          │          Terminal      Unix socket
          │           report            │
          │                          Node.js
          │                             │
          │                          Three.js
          └──────── Pose ───────────────┘
```

### `--debug`

Collects per-frame statistics and prints a report on exit. Designed for
benchmarking the Pi over SSH: no GUI, no browser, no Node.

The per-frame cost is a handful of increments and **one histogram
bucket increment**. Percentiles are computed only at exit, from that
histogram, which is why they cover the entire run rather than a recent
window and still cost O(1) per frame with no allocation. Measured overhead: **none detectable.** Over 400-frame runs, per-frame
pipeline time came out at 13.9 ms plain, 16.0 ms with `--debug`, and
14.7 ms with `--debug --web` — the flagged runs bracket the plain one,
so the spread is scene-dependent run-to-run variance, not a cost. All
three sustained ~31 fps, and resident memory was identical to within
4 kB.

The report goes to **stdout** while all logging goes to **stderr**, so
the two separate cleanly:

```bash
./build/novex-vio --debug 2>/dev/null      # report only
./build/novex-vio --debug >/dev/null       # log only
./build/novex-vio --debug > run.txt        # report to a file
```

Anything the pipeline did not measure is printed as `N/A`, never as a
zero that would read like a measurement.

### `--web`

Starts the Node.js dashboard as a **managed child process** and streams
state to it.

The C++ side gains no HTTP or WebSocket stack. It already exposes a
Unix socket; the Node server subscribes to it and rebroadcasts. That
keeps the network surface out of the process driving the camera, and
means a crashed or wedged dashboard cannot take the estimator with it —
the worst case is a blank browser tab.

The child is started after the pipeline is up, killed on shutdown, and
asked to die with its parent (`PR_SET_PDEATHSIG`), so even a `SIGKILL`
on the daemon cannot leave an orphan holding the port.

`--no-web-autostart` leaves the socket served but spawns nothing, for
running the Node server yourself under a debugger or `nodemon`.

**Cost, measured:** the Node process is a genuine child (its parent is
the daemon), holds about **50 MB RSS**, uses no measurable CPU while
relaying at 20 Hz with no browser attached, and exits **0.52 s** after
the daemon receives `SIGTERM`, releasing its port. The C++ daemon's own
footprint is unchanged at ~89 MB with or without `--web`.

50 MB is not nothing on a 512 MB board. That is a further reason
`--web` is a development tool: benchmark the Pi with `--debug` alone,
which spawns nothing.

The dashboard has **zero npm dependencies** and needs no
`npm install` — see [web/README.md](web/README.md) for why.

### Why the VIO loop can never block

Three separate mechanisms, each tested:

1. **State leaves by snapshot.** The pipeline publishes a small
   copyable struct under a mutex it holds for microseconds once per
   frame. Readers copy and release. Nothing outside the VIO thread ever
   touches estimator objects.
2. **Pushes are non-blocking and droppable.** Subscribers are written
   with `MSG_DONTWAIT`; a subscriber that is not draining its socket
   simply misses that update. The newest state matters, intermediate
   ones do not. The same rule applies again in the Node server, which
   drops a WebSocket frame rather than letting Node buffer without
   limit.
3. **Commands go through a queue.** `reset`, `recenter`, `pause`,
   `resume` and the stereo/IMU toggles are enqueued by whoever asks and
   applied by the VIO thread between frames. The HTTP reply is
   `{"queued":...}` — it does not claim the change has already
   happened.

Verified: with a WebSocket client that connects and then deliberately
never reads, the pipeline advanced 181 frames in 6 seconds — full rate,
no stall.

### `reset` vs `recenter`

These are deliberately different and must not be merged.

| | `reset` | `recenter` |
|---|---|---|
| Tracker features | discarded | **kept** |
| Integrated pose | back to identity | **kept** |
| Velocity filter, gyro bias | cleared | **kept** |
| Reported origin | identity | moved to the current pose |
| Tracking | dropped, must re-initialise | **never interrupted** |
| Keyframe / reference depths | discarded | **kept** |
| Point map | cleared (new epoch) | **kept**, re-expressed through the new origin |
| Dashboard trajectory | cleared | **kept**, re-expressed through the new origin |
| Stationary test window | restarted at the new origin | untouched |

`recenter()` only changes the frame results are *expressed* in. The
estimator keeps integrating in its original frame, so recentring costs
nothing in accuracy and cannot lose tracking. Asserted by checks `D5`
and `D6`.

### Coordinate systems

Everything the daemon emits uses the **OpenCV camera convention**,
right-handed, because that is what the stereo geometry produces:

```
Novex:     X right,  Y DOWN,  Z forward (the LEFT lens' optical axis)
Three.js:  X right,  Y up,    Z toward the viewer
```

Four frames, each named where it is used:

| frame | definition | used for |
|---|---|---|
| camera-local | current left camera | live stereo points, `LIVE` messages |
| internal world | first tracked camera pose after start / reset; `X_int = R_wc X_cam + p_wc` | estimator integration, point map, trajectory |
| reported | `X_rep = R_o^T (X_int − p_o)`; identity until RECENTER | published pose (`position`, `orientation`) |
| Three.js | `X_three = C X_rep`, `C = diag(1, −1, −1)` | the browser scene |

`C` is a 180° rotation about X, a **proper rotation** (determinant +1),
not a mirror: `(x, y, z) -> (x, −y, −z)` and `q(x, y, z, w) ->
(x, −y, −z, w)`. Verified against 2000 random rotations and asserted as
check `D7`. The daemon never converts; the browser applies `C` once, at
the root of its scene graph, and the origin inverse and camera pose
below it - so no axis is flipped anywhere else:

```
scene ─ novexFrame (C) ─┬─ drone (reported pose)
                        └─ internalFrame (O^-1) ─┬─ trajectory, map, mesh
                                                 └─ liveFrame (T_wc) ─ live points
```

The world frame has **no gravity alignment** - "up" is not known
without a working IMU. Euler angles are for reading only; the estimator
holds rotations throughout.

### Web API

`GET /api/v1/state`, `/status`, `/performance`, `/debug`, `/camera`,
`/diagnostics`, `/pointcloud`, `/health`;
`POST /api/v1/vio/{reset,recenter,pause,resume}`,
`/vio/{stereo,imu,stationary}?enabled=false` and `/map/clear`. Live updates come over WebSocket at
`web.update_hz` (default 20 Hz) — deliberately below the 30 fps camera
rate, since the dashboard cannot use more. Full table in
[web/README.md](web/README.md).

The daemon's own socket protocol gained `GET_DEBUG`, `GET_STATUS`,
`GET_CAMERA`, `GET_DIAGNOSTICS`, `SUBSCRIBE <hz>`/`UNSUBSCRIBE`,
`SUBSCRIBE_POINTS <hz>`/`UNSUBSCRIBE_POINTS`, and the control verbs
(including `STATIONARY on|off` and `CLEAR_MAP`), so `novex-state` and
any other local consumer can use them too.

### Security posture

The dashboard binds to **127.0.0.1** by default and is not meant to
leave the machine. It has no authentication and can reset the
estimator. `--web-host` exists but pointing it at `0.0.0.0` publishes
unauthenticated control of the vehicle's estimator to the network — do
not do that on a network you do not trust.

---

## Geometry diagnostics

Computed every frame by the stage that owns each number, published in
the state stream (`geometry`, `drift`, `stationary`, `pointCloud`
objects), `GET_DIAGNOSTICS`, the dashboard, and the `--debug` report.
None is estimated or smoothed; blocks that did not run this frame are
flagged, not zero-filled.

| stage | measurements |
|---|---|
| tracking | median / mean optical flow, tracks dropped, features detected |
| stereo | points, rejections by cause (match / epipolar / depth), disparity median ± std (parallax angle in px), depth median / min / max / std, ray miss, **signed vertical offset** |
| motion | accepted / rejected + reason, correspondences, inliers, inlier ratio, rejected correspondences, reprojection error median / max through the real fisheye model, 1σ rotation / translation, conditioning, keyframe span |
| per-frame motion | relative rotation (magnitude + vector), relative translation (magnitude + vector), pose delta, velocity, speed |
| run totals | motion estimates rejected, keyframes, unmeasured re-anchors, stereo matches rejected, correspondences rejected, accumulated and net rotation / translation |
| point map | median innovation of new observations against their track's fused point (% of range) |

Units: angular quantities are "centre-of-image pixels" (angle × focal
length), since one pixel is close to a constant angle on this lens.

### Stationary-camera test

Start with `--stationary-test`, the dashboard button, or `STATIONARY on`.
It **observes only**; it never suppresses motion. Over the window it
reports mean ± std of per-frame relative translation and rotation, the
mean motion *vector* with its significance (|mean| / standard error),
optical flow, depth, reprojection error, inlier ratio, stereo offset,
accumulated position / orientation drift - and the same drift
re-composed **independently** from the raw keyframe-relative estimates
and keyframe events. Then it names the stage the numbers point at:

* **A tracking** - optical flow well above sensor noise;
* **D integration** - the estimator's pose disagrees with the independent
  re-composition;
* **C motion estimation** (with a **B stereo** signature when the rays'
  vertical offset is large) - consistent motion from still input;
* otherwise, zero-mean noise and its random walk.

---

## 3D feature point cloud

Every tracked feature with valid stereo depth is a 3D point, measured
by the same left-ray stereo geometry the estimator uses. Nothing is
synthesised.

* **Live:** each frame's points, camera-local, with feature id,
  quality, intensity, track age and flags, plus the camera pose they
  were measured at (from the same message, never a later state).
* **Map:** accepted points transformed with that frame's pose,
  `P_world = R_wc P_camera + p_wc`, into the internal world frame.
  Only frames with an accepted motion estimate contribute (a carried
  pose would misplace points).
* **Track fusion.** Range noise lies along the viewing ray, so repeated
  observations of one feature used to scatter into a streak pointing at
  the camera. Each track now fuses its observations by inverse range
  variance (bounded to ~25 frames of memory) and *moves* its single map
  point as the estimate sharpens. On `static100` the map went from 4968
  streak voxels to 693 points, one per physical feature.
* **Voxels + budget.** `voxel_size_m` (3 cm) merges different features
  in the same cube; an open-addressing hash with backward-shift
  deletion keeps lookup O(1) with no allocation. `max_points` (20000)
  is a hard budget; when full, the stalest, lowest-quality slot is
  evicted.
* **Quality gates, map only** (configurable, each rejection counted by
  cause): depth ≤ 6 m, relative range σ ≤ 15% at 1 px, ray miss ≤ the
  stereo gate, track age ≥ 1, motion inlier. The live layer shows every
  point, because it is a diagnostic.
* **Quality score** (0-255, a ranking, not a probability): each of
  range σ, ray miss and inlier status contributes a factor that is 1 for
  a perfect measurement and 0.5 at the configured limit.

### Transport

Binary, little-endian, identical on the daemon socket and the browser
WebSocket; layout in `include/PointCloud.hpp`. `LIVE` entries are
20 bytes; `MAP` messages are **deltas** of 24-byte slot records.

* The VIO thread copies into a shared snapshot with `try_lock` only - it
  never waits for a reader; a busy snapshot is simply retried next frame.
* Each daemon client has a byte-exact outbox. Droppable updates (state,
  live points) are skipped while a client is behind; map deltas are
  never cut mid-message. A client more than 16 MB behind is dropped.
* Receivers hold `(epoch, generation)`. A delta brings a receiver from
  its generation to the newest; a missed round is covered by the next;
  reset / clear starts a new epoch and a full resend.
* The Node relay keeps a map mirror and repeats the scheme **per
  browser**, so a slow or late browser gets exactly what it lacks, and
  subscribes to points only while a browser is connected.
* Verified: a client rebuilding the map from deltas through both hops
  matched the daemon exactly (test_web.sh), and test P5 checks the delta
  scheme through inserts, merges, evictions, skipped publishes and a
  clear.

### Rendering

One `THREE.Points` per layer over preallocated typed arrays, a small
shader for size / brightness by range from the camera (nearer = larger
and brighter), turbo depth colouring, optional fading by last-seen
time, and GPU upload of only the changed slot range. Toggles: live
points, accumulated map, trajectory, camera, mesh, feature-id colours,
depth colouring, fading, grid; presettable from the URL
(`?mesh=1&traj=0`).

**Mesh (experimental, browser only):** at most every 600 ms, a Web
Worker triangulates a copy of the map with local neighbourhood fans -
PCA normal, angular ordering, and triangles only when every edge is
under a configurable length. The point cloud remains the data; the
daemon never waits for it.

---

## Raspberry Pi Zero 2 W deployment

```bash
# On the Pi
sudo apt install build-essential cmake libopencv-dev libeigen3-dev

git clone <this repo> && cd c_prog
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2          # -j4 can exhaust 512 MB while compiling

./build/novex-vio-test           # confirm the camera and calibration
./build/novex-vio --debug --max-frames 900   # benchmark over SSH
./tools/benchmark.sh --features 200
```

Install as a service so it survives the SSH session:

```bash
sudo useradd -r -s /usr/sbin/nologin -G video novex
sudo mkdir -p /opt/novex-vio/bin /opt/novex-vio/config
sudo cp build/novex-vio build/novex-state /opt/novex-vio/bin/
sudo cp config/*.yaml /opt/novex-vio/config/
sudo cp deploy/novex-vio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now novex-vio
journalctl -u novex-vio -f
```

The daemon does not fork or write a pid file. Under systemd that is
the right shape; for a manual run, `nohup ./build/novex-vio &` or a
terminal multiplexer does the job without double-fork machinery.
`SIGHUP` is ignored, so a dropped SSH connection does not kill it.

Notes specific to the board:

- **Build with 512 MB of RAM.** `-j4` on OpenCV-heavy translation
  units can run the Pi out of memory. Use `-j2`, and add swap if the
  compile still fails.
- **Tune features first, resolution second.** Cost is close to linear
  in feature count and roughly linear in pixel count. Halving features
  is the cheaper experiment.
- **Keep the camera on a powered path.** MJPG at 1280×480 is a real
  USB load, and a browned-out hub shows up as dropped frames, not as
  an error.
- **OpenCV uses several threads internally** (the run above hit 115%
  CPU). On four slow cores that is usually a win, but if latency
  jitter matters more than throughput, `cv::setNumThreads(1)` is the
  knob to try.
- **Thermals.** A Zero 2 W under sustained vision load throttles
  without a heatsink. Check `vcgencmd measure_temp` during a
  benchmark; a throttled board silently produces worse numbers.

---

## Design notes

**Why no image rectification.** A pinhole rectification of a fisheye
cannot represent the wide periphery at all — the projection diverges
towards 90° of incidence — and that periphery is exactly what this
calibration was built around. So the raw images are matched
photometrically, where KLT does not care what lens produced them, and
the Kannala-Brandt model is applied to the resulting *points*, where
it is exact and cheap. No pinhole equation is ever applied to a
distorted coordinate.

**Stereo matching is seeded with the calibrated geometry.** The two
lenses have quite different principal points (cx 305.8 vs 334.1, cy
247.0 vs 227.2 at 640×480), so the same ray lands ~28 px apart
horizontally and ~20 px apart vertically before any disparity exists.
Starting KLT at the identity failed the forward-backward check on 72%
of features for that reason alone. Unprojecting through the left lens,
rotating by the calibrated R and reprojecting through the right lens
removes all of it and leaves only the disparity. Measured effect:
triangulated points per frame went from 48 to 74 on the same scene.

**Motion is metric with no initialisation.** Each feature contributes
a 3D point measured by stereo in the previous frame and its 2D
observation in the current one; PnP with RANSAC over those is fully
scaled by the calibrated baseline. There is no monocular scale
ambiguity and nothing to bootstrap.

**Allocation in the loop.** Two camera frame buffers are used in turn,
so the previous frame stays valid for KLT without a copy — the eyes
are `cv::Mat` ROI views, which is why `preprocess` measures 0.0 ms.
The tracker compacts its feature list in place, carrying each
feature's id, age and depth with it, so no id-to-index map is needed.
Scratch vectors are reserved once. `imdecode` writes into a reused
destination.

**Threads, and why each exists.** Three at most: the main loop, the
IMU sampler (only when enabled — it must sample far faster than the
frame rate and keep sampling while a frame is being processed), and
the IPC server (only in daemon mode — so a client cannot stall
processing). Nothing else is threaded.

**MJPG is decoded straight to grayscale.** Setting
`CAP_PROP_CONVERT_RGB=0` yields the raw JPEG bytes, and
`IMREAD_GRAYSCALE` lets libjpeg skip chroma upsampling and the
YUV→BGR conversion entirely. Measured 4.18 ms against 6.00 ms per
frame. Colour is never used by the pipeline. If a driver refuses,
the code detects it at open and falls back.

**One clock.** Every timestamp is `CLOCK_MONOTONIC` seconds. That is
not arbitrary: the V4L2 buffer timestamps OpenCV exposes as
`CAP_PROP_POS_MSEC` are on that clock (verified against
`/proc/uptime`), and so are Linux IIO timestamps. Camera and IMU
samples are therefore directly comparable with no offset estimation.
Camera timestamps are sanity-checked against the host clock at run
time and fall back to it, with a warning, if a driver reports
something else. IMU samples are associated with a frame by timestamp
interval, never by count or by assuming 30 fps means 33.333 ms.

**Why a hand-written YAML reader.** The calibration and config use a
tiny, stable subset of YAML. OpenCV's `FileStorage` cannot read them
(no `%YAML:1.0` header, plain block sequences), and adding yaml-cpp
for ~200 lines of parsing would violate the rule that every dependency
needs a reason. Anything outside the supported subset is reported as a
parse error rather than silently misread — which matters when the data
is a calibration.

---

## A measured finding about the calibration

Epipolar error on live imagery is worse than the calibration's
reported reprojection RMS suggests, and it grows towards the edge of
the frame. Binned by radius from the image centre over 20 frames:

| radius | features | FB failures | mean epipolar error |
|-------:|---------:|------------:|--------------------:|
| 0–80 px | 561 | 68.1% | 2.39 px |
| 80–160 px | 1769 | 60.9% | 2.69 px |
| 160–240 px | 2751 | 62.0% | 3.93 px |
| 240–320 px | 2488 | 76.1% | 5.12 px |

The calibration's own RMS is 0.59 px at 1280×720, which is ~0.39 px at
this scale — several times better than what the pair actually
achieves. Part of that is expected from the stated extrinsic
uncertainty (0.16° of rotation spread is already ~0.8 px at this focal
length, and the baseline standard deviation is 2.2 mm on 110 mm), and
the growth towards the edge is consistent with the partial edge
coverage during the calibration capture that `JOURNAL.md` already
flags as an open problem.

The epipolar gate is now an angle, `stereo.epipolar_threshold_px`
= 2.5 px, the same at the centre and the edge (the old 0.008
normalised-plane gate was ~13× stricter in the corners). The geometry
audit's real-frame section measures the same limitation with the
current matcher: median ray miss 1.26 px and a **systematic vertical
offset of +0.86 px** between the eyes. **This is a calibration
limitation, not something to tune away** — the fix is a recapture with
better coverage at the edge of the lens. Since the drift fix it can no
longer create rotation, and it is shown live as "stereo vertical
offset" so a recalibration can be judged by it.

---

## Assumptions

1. **The 640×480 sensor mode is a centered crop plus isotropic scale
   of the calibrated mode.** Measured on this camera (above), not
   assumed. `StereoCalibration::deriveMapping` generalises the rule to
   other sizes; that generalisation is *not* separately verified for
   other modes, and a different camera family could behave otherwise.
2. **The left eye is the left half of the frame.** `swap_eyes` exists
   in the config if not.
3. **`X_right = R · X_left + T`**, the convention the existing
   calibration file and the generated ORB-SLAM3 config both use.
4. **The world frame is the first tracked camera pose.** There is no
   gravity alignment, so "up" is not known without a working IMU.
5. **No camera-IMU extrinsic calibration exists.**
   `imu.R_camera_from_body` defaults to identity and is labelled a
   placeholder in the config. Because of this, the IMU is used *only*
   where a wrong extrinsic cannot corrupt the estimate: as a seed for
   the PnP solver, and to carry orientation forward while vision is
   lost. It is deliberately not fused into the orientation estimate.
6. **The IIO backend is untested.** No IMU hardware was available. It
   is written to fail cleanly and report why, and the absence of a
   device is a supported configuration rather than an error.
7. **Accelerometer bias is not estimated.** It is not separable from
   gravity without observing several orientations, so the field stays
   zero rather than holding a number that looks like an estimate.
8. **Depth beyond ~25 m is discarded** because at a 110 mm baseline it
   is sub-pixel disparity, and therefore noise. The point MAP is gated
   tighter (6 m, 15% range σ at 1 px) because it is shown as geometry.
9. **The crop-and-scale pixel-centre convention** is the measured one;
   the alternative differs by 0.167 px, audited as a negligible 0.033°
   common rotation.

---

## Intentionally incomplete

Stated plainly, so nothing here is mistaken for finished work.

- **The IIO IMU backend is implemented but UNTESTED** — no hardware.
  It uses the polled `*_raw` sysfs interface, not the triggered buffer
  interface, which is adequate for the loosely coupled use here but
  caps the practical sample rate.
- **The estimator is loosely coupled, by design.** Vision produces a
  complete pose relative to a keyframe, and that pose is composed. There
  is no joint state, no IMU preintegration, no bundle adjustment. The
  per-frame covariance is computed and published but not propagated.
  Those need a measured camera-IMU extrinsic and time offset to be worth
  anything.
- **No gravity alignment and no accelerometer-based levelling.**
- **No loop closure, no mapping, no relocalisation.** Out of scope per
  the brief. This is local odometry: it drifts, and nothing corrects
  it.
- **Keyframes, but no local bundle adjustment.** Each frame is PnP
  against one keyframe; keyframes are not jointly optimised, so drift
  still accumulates keyframe to keyframe.
- **Accuracy is measured on two recordings only** - one 100 s
  stationary, one 90 s handheld loop in a dim room - against a directly
  measured start-to-end pose, not a motion-capture trajectory. The
  loop result is at the noise level of a single run (±~2° / ±0.3 m
  under single-parameter changes). More loops in varied scenes are the
  obvious next step, and `novex-record` / `novex-replay` exist for it.
- **Path length is not a drift metric.** With keyframes each frame is
  measured afresh, so per-frame jitter inflates the summed path (24 m
  on the 90 s loop). End-pose error against ground truth is the metric.
- **The stereo calibration has a measured +0.86 px vertical offset**
  between the eyes. A recalibration is recommended; nothing here
  compensates for it.
- **The mesh is experimental** and browser-side only: local fans over
  the point map, not a surface reconstruction.
- **Velocity is a low-passed finite difference of position**, not an
  estimated state.
- **The camera-mode mapping rule is verified for 1280×720 → 640×480
  only.** Other target sizes use the same generalisation, unverified.
- **`cv::setNumThreads` is not managed.** OpenCV picks its own
  parallelism; on the Pi this may want pinning.
- **No cross-compilation setup.** Building on the Pi works and is what
  is documented.
- **The dashboard has no authentication.** It is a loopback
  development tool, not a hosted service.
- **`web/tools/mock-daemon.js` emits synthetic data.** It is a test
  fixture for the transport and the UI. It proves nothing about the
  estimator and is labelled as such in the file itself.
- **Browser rendering is checked by headless-Chrome screenshots only**
  (live data, point map, mesh, no console errors), not by an automated
  pixel test. The transport, delta sync, API and coordinate maths are
  covered by automated checks.
- **Nothing here has run on a Raspberry Pi Zero 2 W.** Every number is
  from the development machine; the point cloud and diagnostics add
  ~0.02 ms per frame there, which should be re-measured on the board.
- **`--debug` overhead is measured on the development machine only**,
  like every other number in this file.

## What is verified

* `./build/novex-vio-test` — 39 checks, all passing, 0 skipped, with a
  camera attached. Includes the command queue, the debug histogram, the
  `reset` / `recenter` distinction, the axis conversion, and the P
  series: points on their left ray, voxel dedup, budget eviction with
  hash consistency, track point moves and merges, binary map deltas
  reproducing the map exactly, stationary-test attribution, estimates
  spanning rejected frames, and quality-score ordering.
* `./build/novex-geometry-audit [--recording DIR]` — 20 checks against
  known answers and real frames (see [Calibration audit](#calibration-audit)),
  including that a stereo calibration error cannot manufacture motion
  and that the published uncertainty matches the actual error.
* `./tests/test_lifecycle.sh` — 10 checks: headless daemon start-up,
  out-of-process IPC, 20 concurrent clients, clean SIGTERM and SIGINT.
* `./tests/test_web.sh` — 29 checks: every mode combination, a stalled
  client failing to stall the VIO (with binary point streaming active),
  browser disconnect and reconnect, the control commands, the binary
  point stream end to end (valid headers, full map then deltas, map
  rebuilt from deltas equal to the daemon's), the diagnostics endpoint,
  the stationary test from the API, clear-map keeping tracking, and a
  single debug report on exit with the Node child reaped.
