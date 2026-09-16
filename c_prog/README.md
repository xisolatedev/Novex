# Novex VIO

A lightweight stereo visual-inertial odometry pipeline for the
Raspberry Pi Zero 2 W. Built from scratch: no ORB-SLAM3, no OpenVINS,
no ROS. Dependencies are OpenCV and Eigen, and nothing else.

The IMU is genuinely optional. With it disabled the system is stereo
visual odometry and nothing is stubbed or faked; with it enabled the
IMU contributes where it can do so honestly (see
[Assumptions](#assumptions)).

Status: **the pipeline runs end to end on real hardware at 30 fps.**
Measured numbers below are from actual runs, not estimates. The
sections on what is *not* finished are as important as the rest, and
are at the bottom.

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
│   ├── lib/novexclient.js       daemon socket client
│   ├── public/                  index.html, app.js, style.css
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
│   ├── StereoMatcher.hpp        left/right matching + triangulation
│   ├── MotionEstimator.hpp      PnP + RANSAC
│   ├── StateEstimator.hpp       pose integration, optional IMU aid
│   ├── IMU.hpp                  optional IMU, threaded ring buffer
│   ├── VIOState.hpp             the published state struct
│   ├── VIO.hpp                  pipeline coordinator
│   ├── StateServer.hpp          Unix-socket IPC
│   └── Gui.hpp                  development display (not core)
├── src/                         one .cpp per header above, plus main.cpp
├── tests/
│   ├── test_novex.cpp           31 in-process checks
│   ├── test_lifecycle.sh        daemon, IPC and signal checks
│   └── test_web.sh              --debug / --web acceptance checks
└── tools/
    ├── novex_state_client.cpp   example IPC client (libc only)
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

Produces `build/novex-vio`, `build/novex-state` and
`build/novex-vio-test`.

`-DNOVEX_NATIVE_ARCH=ON` adds `-mcpu=native`. Use it only when the
binary will run on the machine that built it.

### Run the tests

```bash
./build/novex-vio-test          # 24 checks; needs the camera for 9 of them
./build/novex-vio-test --no-camera
./tests/test_lifecycle.sh       # daemon, IPC, SIGTERM/SIGINT
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
`--log debug`, `--config PATH`. Full list with `--help`.

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

## Measured performance

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

`recenter()` only changes the frame results are *expressed* in. The
estimator keeps integrating in its original frame, so recentring costs
nothing in accuracy and cannot lose tracking. Asserted by checks `D5`
and `D6`.

### Coordinate system

Novex reports poses in the **OpenCV camera convention**, because that
is what its stereo geometry produces — triangulation runs with the left
camera as `[I|0]` and points are accepted on `z > 0`:

```
Novex:     X right,  Y DOWN,  Z forward (along the optical axis)
Three.js:  X right,  Y up,    Z toward the viewer
```

The two differ by a 180° rotation about X, `M = diag(1, -1, -1)`. That
is a **proper rotation** (determinant +1), not a mirror, so:

```
position    (x, y, z)     ->  (x, -y, -z)
quaternion  (x, y, z, w)  ->  (x, -y, -z, w)
```

The conversion happens in the browser; the daemon always emits Novex
coordinates. It was verified numerically against 2000 random rotations
before being written, and is asserted in the C++ suite as check `D7`.

The world frame is the first tracked camera pose, so there is **no
gravity alignment** — "up" is not known without a working IMU.

Euler angles appear in the report and the dashboard for reading only.
The estimator holds a quaternion throughout and never converts
internally.

### Web API

`GET /api/v1/state`, `/status`, `/performance`, `/debug`, `/camera`,
`/health`; `POST /api/v1/vio/{reset,recenter,pause,resume}` and
`/vio/{stereo,imu}?enabled=false`. Live updates come over WebSocket at
`web.update_hz` (default 20 Hz) — deliberately below the 30 fps camera
rate, since the dashboard cannot use more. Full table in
[web/README.md](web/README.md).

The daemon's own socket protocol gained `GET_DEBUG`, `GET_STATUS`,
`GET_CAMERA`, `SUBSCRIBE <hz>`/`UNSUBSCRIBE`, and the control verbs, so
`novex-state` and any other local consumer can use them too.

### Security posture

The dashboard binds to **127.0.0.1** by default and is not meant to
leave the machine. It has no authentication and can reset the
estimator. `--web-host` exists but pointing it at `0.0.0.0` publishes
unauthenticated control of the vehicle's estimator to the network — do
not do that on a network you do not trust.

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

The epipolar threshold is set at 0.008 in normalised units (~2.3 px)
to match what the data supports. **This is a calibration limitation,
not something to tune away** — the fix is a recapture with better
coverage at the edge of the lens.

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
   is sub-pixel disparity, and therefore noise.

---

## Intentionally incomplete

Stated plainly, so nothing here is mistaken for finished work.

- **The IIO IMU backend is implemented but UNTESTED** — no hardware.
  It uses the polled `*_raw` sysfs interface, not the triggered buffer
  interface, which is adequate for the loosely coupled use here but
  caps the practical sample rate.
- **The estimator is loosely coupled, by design.** Vision produces a
  complete relative pose and that pose is integrated. There is no
  joint state, no covariance, no IMU preintegration, no bundle
  adjustment. Those need a measured camera-IMU extrinsic and time
  offset to be worth anything.
- **No gravity alignment and no accelerometer-based levelling.**
- **No loop closure, no mapping, no relocalisation.** Out of scope per
  the brief. This is local odometry: it drifts, and nothing corrects
  it.
- **No keyframing or local bundle adjustment.** Frame-to-frame PnP
  only, so drift accumulates faster than a windowed estimator would.
- **Absolute trajectory accuracy is unmeasured.** There is no ground
  truth on this bench. The tests verify that the pipeline produces a
  well-formed, plausible state at rate — they do **not** verify that
  the trajectory is correct. Comparing against a measured path is the
  obvious next piece of work.
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
- **The dashboard is not tested in a real browser here.** The
  transport, framing, API and coordinate maths are covered by automated
  checks; the rendering has not been through an automated browser test.
- **`--debug` overhead is measured on the development machine only**,
  like every other number in this file.

## What is verified

* `./build/novex-vio-test` — 31 checks, all passing, 0 skipped, with a
  camera attached. Includes the command queue, the debug histogram, the
  `reset` / `recenter` distinction, and the axis conversion.
* `./tests/test_lifecycle.sh` — 10 checks: headless daemon start-up,
  out-of-process IPC, 20 concurrent clients, clean SIGTERM and SIGINT.
* `./tests/test_web.sh` — the `--debug` / `--web` acceptance tests:
  every mode combination, a stalled client failing to stall the VIO,
  browser disconnect and reconnect, all four control commands, and a
  single debug report on exit with the Node child reaped.
