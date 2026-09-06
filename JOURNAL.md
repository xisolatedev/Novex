# Novex Engineering Journal

Novex is an experimental autonomous robotics/drone project focused on lightweight onboard perception, stereo vision, visual-inertial odometry, localization, navigation, communications, and eventually multi-drone coordination. This journal is the project's engineering log — a record of what was actually built, tested, measured, and learned, in chronological order.

---

## 2026-09-05 — Lightweight Stereo VIO Direction

### Goal

We want real-time 3D positional tracking for Novex without requiring a heavyweight SLAM system on the drone.

### Previous Approach

We investigated ORB-SLAM3, including its stereo fisheye (Kannala-Brandt) capabilities and its large visual vocabulary. The work lives in `slam_test/` — a standalone ORB-SLAM3 stereo test rig with a PySide6 GUI, real-time 3D map/trajectory view, a ChArUco-based stereo calibration tool with automated view-quality filtering, and a dedicated Stereo Configuration Workbench for tuning rectified output against the fisheye lenses (see `slam_test/README.md`).

ORB-SLAM3 successfully produced a sparse 3D map from the stereo camera — real tracking, real triangulated map points, not a simulation. But a full ORB-SLAM3 stack is likely too computationally and memory intensive for very small onboard hardware such as the Raspberry Pi Zero 2 W. Measured on this development machine (Intel i5-7500 @ 3.4 GHz, single core pinned via `taskset`):

- Minimum process memory footprint to load and track: **~580 MB**, of which the ORB vocabulary file alone accounts for **~427 MB** resident (the vocabulary file on disk is 139 MB; it expands substantially once parsed into memory).
- Per-frame tracking cost at 1280x720 with 1200 ORB features, one CPU core: **~56 ms/frame (~17.7 fps)**.
- At 848x480 with 1200 features, one core: **~32 ms/frame (~30.8 fps)**.
- At 640x360 with 800 features, one core: **~23 ms/frame (~43.4 fps)**.

The Raspberry Pi Zero 2 W has 512 MB of total system RAM, which is less than the measured ORB-SLAM3 vocabulary footprint alone — before accounting for the OS, camera buffers, or anything else. It also uses a quad-core Cortex-A53 at 1 GHz, substantially slower per-core than the development machine these numbers were measured on. We have not benchmarked ORB-SLAM3 directly on a Pi Zero 2 W; the memory arithmetic alone (580 MB required vs 512 MB available) is sufficient to rule it out for this hardware without needing a live test.

### New Direction: Stereo VIO

We are investigating a lightweight Stereo Visual-Inertial Odometry (VIO) system as a smaller, faster alternative to running the full ORB-SLAM3 stack onboard.

The intended pipeline:

```
Stereo Camera
  -> image preprocessing
  -> feature detection
  -> lightweight feature tracking
  -> stereo correspondence
  -> triangulation
  -> visual odometry
       +
     IMU
  -> state estimation / sensor fusion
  -> 6-DOF pose
```

The immediate goal is local motion estimation — knowing how the drone has moved relative to where it started a moment ago — rather than maintaining a massive persistent global map with loop closure and long-term relocalization.

**This is a planned direction, not an implemented system.** No VIO code exists yet in the repository. The stereo camera calibration, capture pipeline, and rectification tooling built for the ORB-SLAM3 test are expected to carry over directly, since VIO needs the same measured intrinsics/extrinsics.

### Why VIO

- Stereo cameras provide metric depth from binocular geometry — no monocular scale ambiguity.
- An IMU provides high-rate motion information between camera frames, filling in the gaps a camera alone cannot see (fast rotation, motion blur, textureless surfaces).
- Visual tracking provides drift correction that IMU-only dead reckoning cannot, since IMU integration drifts unboundedly on its own.
- The combination can provide a full 6-DOF pose (position + orientation).
- VIO can potentially run on much smaller hardware than a complete feature-based SLAM system, because it does not need to maintain a large persistent map, a bag-of-words vocabulary for place recognition, or run global bundle adjustment.
- Loop closure and large-scale mapping can be treated as later features layered on top, rather than requirements for the first flight/localization system to work at all.

### Target Hardware

- **Raspberry Pi Zero 2 W** — lightweight onboard estimation candidate. Ruled out for running the current ORB-SLAM3 stack (see memory measurements above); its viability for a lightweight VIO implementation has not yet been tested.
- **ESP32-class microcontrollers** — deterministic low-level control and sensor handling (motor control, IMU polling at fixed rates, safety interlocks).
- **Raspberry Pi 5** — heavier compute candidate for development, global mapping, or anything too heavy for the Zero 2 W.
- **Stereo USB camera** — synchronized binocular vision. Currently the GXIVISION-LSM22100 module (see `slam_test/README.md` hardware section): 2560x720 combined MJPEG frame, 3.0 x 3.0 um pixels, ~1.3 mm fisheye lenses per eye (measured field of view is lens- and calibration-dependent; see the calibration tooling for current measured values).
- **IMU** — required for the VIO system. Not yet selected or integrated. No gyroscope/accelerometer hardware is present on the current bench setup.

### Planned Development Stages

1. Obtain accurate stereo camera calibration.
2. Implement reliable stereo image capture and timestamps.
3. Detect a small number of stable visual features.
4. Track features between frames using lightweight optical flow such as pyramidal KLT.
5. Establish left/right stereo correspondences.
6. Triangulate tracked features into 3D.
7. Implement stereo visual odometry.
8. Integrate IMU measurements.
9. Implement state estimation / VIO.
10. Visualize real-time 6-DOF trajectory.
11. Benchmark CPU usage, memory usage, latency, FPS, tracking quality, and drift.
12. Optimize and test on Raspberry Pi Zero 2 W.
13. Only after the estimator is stable, integrate it with the flight-control system.

### Calibration Requirements

Accurate calibration is critical to a working VIO system. The eventual system needs:

- left camera intrinsics
- right camera intrinsics
- lens distortion parameters
- stereo rotation
- stereo translation / baseline
- camera-to-IMU extrinsics
- synchronized timestamps
- IMU bias/noise characterization

**DO NOT use visual perspective-remapping values as a substitute for physical stereo calibration.** The hand-tuned FOV/distortion slider values used for the early visual preview tooling (`calibrator.py`, `fast_camera.py`, `camera.py` at the project root) are a visual correction only — they were never fitted to a physical target of known size, they describe one lens with no information about the relationship between the two lenses, and they cannot provide a baseline. All metric calibration used by the ORB-SLAM3 test rig and any future VIO work comes from `slam_test/src/calibrate_stereo.py` photographing a ChArUco board of a physically measured square size. See `slam_test/README.md` for the full explanation of why this distinction matters and what breaks if it is ignored.

### Important Design Principle

> Novex does not need to understand the entire world to fly safely. The first onboard estimator only needs to maintain a sufficiently accurate estimate of its own motion and pose.

Global mapping, loop closure, multi-drone coordination, and heavier AI can potentially be handled by more capable hardware later (e.g. a Raspberry Pi 5, or offboard compute the drone streams to). The first onboard estimator's job is narrower and more achievable: know where you are relative to where you just were, well enough to fly.

---

## Engineering Log Format

Use this format for all future entries.

## YYYY-MM-DD — Short Title

### Goal

What are we trying to accomplish?

### What We Changed

Actual code, hardware, algorithms, configuration, or architecture changes.

### Experiments

What was tested?

### Results

What happened? Include measured numbers when available.

### Problems

What failed or behaved unexpectedly?

### Investigation

What did we determine was causing the problem?

### Decision

What did we decide to do next, and why?

### Next Steps

Concrete tasks for the next development session.

### Metrics

If applicable:

- FPS:
- latency:
- CPU:
- RAM:
- feature count:
- tracked features:
- stereo match rate:
- position drift:
- rotational drift:
- IMU rate:
- camera rate:

Do not fabricate measurements. If a metric has not been measured, write `Not measured`.

---

## Journal Rules

- Never fabricate measurements or test results.
- Record failures, not just successful experiments.
- Prefer measured data over assumptions.
- Record why major architecture decisions were made.
- Keep entries chronological.
- Do not rewrite old entries to make experiments look successful.
- Link to relevant source files when useful.
- Record hardware changes and calibration changes.
- Record important bugs and their root causes.
- Clearly distinguish between hypotheses and verified results.
