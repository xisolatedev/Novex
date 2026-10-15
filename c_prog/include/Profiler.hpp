#pragma once

#include "Time.hpp"

#include <cstddef>

namespace novex
{

// Pipeline stages that are measured independently. Keep this list
// short and fixed: the profiler is a plain array indexed by this enum,
// so it allocates nothing at run time.
enum class Stage
{
    Capture = 0,      // whole grab(), including the wait for the sensor
    Decode,           // MJPG decode only - the CPU part of capture
    Preprocess,       // splitting eyes, any image preparation
    Detect,           // feature detection
    Track,            // temporal KLT
    Stereo,           // left/right matching + triangulation
    Motion,           // PnP / RANSAC
    State,            // pose integration / estimator update
    Imu,              // IMU sample consumption
    PointCloud,       // 3D point snapshot + map insertion + publish
    Floor,            // ground plane measurement (not the per-frame
                      // prediction, which is too small to time)
    Total,            // whole frame, capture included
    Count
};

const char* stageName(Stage stage);

// Fixed-size rolling window of per-stage timings, plus measured frame
// rates. Nothing here is estimated from a nominal FPS: both rates come
// from differences of real timestamps.
class Profiler
{
public:

    static constexpr int Window = 64;

    void begin(Stage stage);
    void end(Stage stage);

    // Records a duration measured elsewhere, for stages timed inside
    // another component.
    void endWith(Stage stage, double seconds);

    // Records a completed capture, identified by its camera timestamp.
    // Capture FPS is measured from those timestamps, so it reflects
    // what the sensor actually delivered.
    void noteCapture(double cameraTimestamp);

    // Records a frame that was actually processed by the VIO pipeline.
    // This diverges from capture FPS when frames are dropped to keep
    // up.
    void noteProcessed(double now);

    double last(Stage stage) const;

    // Mean over the recorded window. Note this is per INVOCATION, not
    // per frame: detection only runs on the frames where the feature
    // count has fallen far enough, so its average is what a detection
    // costs when it happens, not what it adds to every frame. The
    // Total stage is the one to read for per-frame cost.
    double average(Stage stage) const;

    double captureFPS() const;
    double processingFPS() const;

    // Age of the most recent processed frame at the moment it finished:
    // camera timestamp to end of processing. This is the real
    // sensor-to-state latency.
    double latency() const;

    void noteLatency(double seconds);

    // Millisecond figures for the whole pipeline in one line, for
    // periodic logging and the GUI overlay.
    void formatSummary(char* buffer, size_t size) const;

private:

    double startTime[static_cast<int>(Stage::Count)] = {};
    double samples[static_cast<int>(Stage::Count)][Window] = {};
    int    count[static_cast<int>(Stage::Count)] = {};
    int    cursor[static_cast<int>(Stage::Count)] = {};

    double lastCaptureStamp = -1.0;
    double lastProcessStamp = -1.0;

    double captureRate = 0.0;
    double processRate = 0.0;

    double latencySeconds = 0.0;
};

// Times a scope and reports it to a profiler on destruction.
class ScopedStage
{
public:

    ScopedStage(Profiler& profiler, Stage stage)
        : profiler(profiler), stage(stage)
    {
        profiler.begin(stage);
    }

    ~ScopedStage()
    {
        if (!released)
        {
            profiler.end(stage);
        }
    }

    // Hands the timing back to the caller, which has already recorded
    // it. Used where a stage must be closed before the end of the
    // scope so that its value can be read.
    void release()
    {
        released = true;
    }

private:

    Profiler& profiler;
    Stage stage;
    bool released = false;
};

} // namespace novex
