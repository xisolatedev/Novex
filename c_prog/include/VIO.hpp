#pragma once

#include "CommandQueue.hpp"
#include "DebugStatistics.hpp"
#include "FeatureTracker.hpp"
#include "IMU.hpp"
#include "MotionEstimator.hpp"
#include "Profiler.hpp"
#include "StateEstimator.hpp"
#include "StereoCalibration.hpp"
#include "StereoMatcher.hpp"
#include "VIOConfig.hpp"
#include "VIOState.hpp"

#include <opencv2/core.hpp>

#include <mutex>
#include <vector>

namespace novex
{

// A consistent view of the estimator and its performance, taken under
// one lock. This is what the IPC server hands to clients: it copies
// the snapshot and releases the lock immediately, so serving a client
// never holds up a frame.
struct VIOSnapshot
{
    VIOState state;

    double captureFPS = 0.0;
    double processingFPS = 0.0;
    double latencySeconds = 0.0;

    double stageMilliseconds[static_cast<int>(Stage::Count)] = {};

    int stereoMatched = 0;
    int stereoTriangulated = 0;

    bool imuRunning = false;
    double imuRateHz = 0.0;

    // Runtime control state, so external consumers can show it
    // without guessing from the config file.
    bool paused = false;
    bool stereoEnabled = true;
    bool imuEnabled = false;

    uint64_t resetCount = 0;
    uint64_t recenterCount = 0;
    bool originRecentered = false;
};

class VIO
{
public:

    VIO(const VIOConfig& config,
        const StereoCalibration& calibration,
        IMU* imu);

    // Prepares the pipeline for a given per-eye image size. Called
    // once the camera has negotiated its actual mode.
    bool initialise(const cv::Size& eyeSize);

    // Runs one frame. `left` and `right` must be single-channel
    // grayscale views of the same size; they are not copied and must
    // stay valid until the next call.
    //
    // Returns true when a pose was produced this frame. A false return
    // is a tracking failure, not an error: the last state is still
    // available and marked as not tracking.
    bool process(const cv::Mat& left,
                 const cv::Mat& right,
                 double timestamp);

    // Notes that frames were discarded to keep up, so the count
    // reaches clients.
    void noteDroppedFrames(int count);

    void noteFailedFrame();

    // Applies everything queued by other threads. Must be called from
    // the VIO thread once per loop iteration, INCLUDING while paused -
    // otherwise a resume command would never be seen.
    void processCommands();

    bool isPaused() const { return paused; }

    // The queue other threads push to. Safe to call from anywhere.
    CommandQueue& commands() { return queue; }

    // Present whether or not --debug is set; when it is not, the
    // collector is disabled and every note* call is a no-op.
    DebugCollector& debug() { return collector; }
    const DebugCollector& debug() const { return collector; }

    VIOSnapshot snapshot() const;

    // For the GUI, which runs on the same thread as processing and so
    // does not need the lock.
    const std::vector<Feature>& features() const
    {
        return tracker.features();
    }

    const Profiler& profiler() const { return timings; }
    Profiler& profiler() { return timings; }

    const VIOState& state() const { return estimator.state(); }

private:

    void publish();

    void apply(const Command& command);

    bool isVisuallyStationary() const;

    const VIOConfig& config;
    const StereoCalibration& calibration;

    IMU* imu;

    FeatureTracker tracker;
    StereoMatcher stereo;
    MotionEstimator motion;
    StateEstimator estimator;

    Profiler timings;

    // Header sharing the previous frame's pixels. Valid because the
    // camera alternates between two frame buffers, so the frame before
    // last is the one being overwritten, never this one.
    cv::Mat previousLeft;

    double previousTimestamp = 0.0;

    bool havePrevious = false;

    cv::Size eyeSize;
    bool initialised = false;

    std::vector<IMUSample> imuSamples;

    CommandQueue queue;
    std::vector<Command> pendingCommands;

    DebugCollector collector;

    // Runtime overrides of the corresponding config values. The config
    // stays const; these are what the pipeline actually reads.
    bool paused = false;
    bool stereoRuntimeEnabled = true;
    bool imuRuntimeEnabled = false;

    uint64_t resets = 0;

    mutable std::mutex snapshotMutex;
    VIOSnapshot published;
};

} // namespace novex
