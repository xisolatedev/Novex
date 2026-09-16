#include "VIO.hpp"

#include "Log.hpp"
#include "Time.hpp"

#include <cmath>

namespace novex
{

namespace
{

// Median flow below this many pixels, with enough tracks to trust the
// median, is taken as "not moving" for the purpose of gyro bias
// estimation. Deliberately conservative: a wrong stationary call
// poisons the bias.
constexpr double kStationaryFlowPixels = 0.4;

} // namespace

VIO::VIO(const VIOConfig& config,
         const StereoCalibration& calibration,
         IMU* imu)
    : config(config),
      calibration(calibration),
      imu(imu),
      tracker(config),
      stereo(config, calibration),
      motion(config, calibration),
      estimator(config),
      collector(config.debugEnabled)
{
    imuSamples.reserve(512);
    pendingCommands.reserve(CommandQueue::Capacity);

    stereoRuntimeEnabled = config.stereoEnabled;
    imuRuntimeEnabled = config.imuEnabled;

    collector.start(monotonicSeconds());
}

void VIO::processCommands()
{
    if (queue.drain(pendingCommands) == 0)
    {
        return;
    }

    for (const Command& command : pendingCommands)
    {
        apply(command);
    }

    publish();
}

void VIO::apply(const Command& command)
{
    // Running on the VIO thread, between frames. That is the whole
    // point of the queue: tearing down the tracker's feature list
    // from an IPC thread while track() is walking it would be a
    // straightforward data race.
    switch (command.type)
    {
        case CommandType::Reset:
        {
            tracker.reset();
            estimator.reset();

            havePrevious = false;
            previousTimestamp = 0.0;

            ++resets;

            LOG_INFO("vio: reset - tracking and estimator restarted");
            break;
        }

        case CommandType::Recenter:
        {
            // Deliberately does NOT touch the tracker or the
            // estimator's integration. Only the reporting frame moves.
            estimator.recenter();

            LOG_INFO(
                "vio: recentred - origin moved to the current pose, "
                "tracking untouched"
            );

            break;
        }

        case CommandType::Pause:
        {
            if (!paused)
            {
                paused = true;
                LOG_INFO("vio: paused");
            }

            break;
        }

        case CommandType::Resume:
        {
            if (paused)
            {
                paused = false;

                // Drop the temporal link. The previous frame is now
                // arbitrarily old, and asking KLT to match across
                // that gap would produce confident nonsense.
                havePrevious = false;

                LOG_INFO("vio: resumed");
            }

            break;
        }

        case CommandType::SetStereoEnabled:
        {
            stereoRuntimeEnabled = command.flag;

            LOG_INFO(
                "vio: stereo depth %s",
                command.flag ? "enabled" : "disabled"
            );

            break;
        }

        case CommandType::SetImuEnabled:
        {
            // Only stops the pipeline CONSUMING samples. The IMU
            // thread keeps sampling, so re-enabling is instant and
            // the buffer is warm.
            imuRuntimeEnabled = command.flag && config.imuEnabled;

            if (command.flag && !config.imuEnabled)
            {
                LOG_WARN(
                    "vio: cannot enable the IMU, it was not started "
                    "(run with --imu)"
                );
            }
            else
            {
                LOG_INFO(
                    "vio: IMU consumption %s",
                    imuRuntimeEnabled ? "enabled" : "disabled"
                );
            }

            break;
        }
    }
}

bool VIO::initialise(const cv::Size& size)
{
    if (!calibration.isLoaded())
    {
        LOG_ERROR("vio: calibration is not loaded");
        return false;
    }

    if (!calibration.isAdapted() ||
        calibration.currentResolution() != size)
    {
        LOG_ERROR(
            "vio: calibration has not been adapted to the %dx%d "
            "images the camera is producing",
            size.width, size.height
        );

        return false;
    }

    eyeSize = size;

    tracker.reset();
    estimator.reset();

    havePrevious = false;
    previousTimestamp = 0.0;

    initialised = true;

    LOG_INFO(
        "vio: initialised for %dx%d per eye, %s",
        size.width,
        size.height,
        config.stereoEnabled
            ? "stereo depth enabled"
            : "stereo depth DISABLED (no metric scale)"
    );

    publish();

    return true;
}

bool VIO::process(const cv::Mat& left,
                  const cv::Mat& right,
                  double timestamp)
{
    if (!initialised)
    {
        LOG_ERROR("vio: process() before initialise()");
        return false;
    }

    ScopedStage totalTiming(timings, Stage::Total);

    timings.noteCapture(timestamp);

    {
        ScopedStage preprocessTiming(timings, Stage::Preprocess);

        if (left.empty() || left.type() != CV_8UC1)
        {
            LOG_WARN("vio: left image is empty or not 8-bit gray");
            return false;
        }

        if (stereoRuntimeEnabled &&
            (right.empty() || right.size() != left.size()))
        {
            LOG_WARN("vio: right image missing or mismatched");
            return false;
        }

        if (left.size() != eyeSize)
        {
            LOG_ERROR(
                "vio: image size changed from %dx%d to %dx%d; the "
                "calibration no longer applies",
                eyeSize.width, eyeSize.height,
                left.cols, left.rows
            );

            return false;
        }
    }

    const double deltaTime = havePrevious
        ? timestamp - previousTimestamp
        : 0.0;

    // Collect the IMU samples that fall in this frame interval. Doing
    // this by timestamp rather than by count is the whole point of
    // insisting on real timestamps: a dropped frame or a jittery USB
    // delivery changes the interval, and a fixed 1/30 s assumption
    // would silently misalign the two sensors.
    imuSamples.clear();

    if (imu != nullptr && imu->isEnabled() && imuRuntimeEnabled &&
        havePrevious)
    {
        ScopedStage imuTiming(timings, Stage::Imu);

        imu->samplesBetween(previousTimestamp, timestamp, imuSamples);

        collector.noteImuSamples(imuSamples.size());
    }

    if (havePrevious)
    {
        tracker.track(previousLeft, left, timings);
    }

    bool tracked = false;

    if (havePrevious && deltaTime > 0.0)
    {
        const MotionResult result = motion.estimate(
            tracker.features(),
            deltaTime,
            timings
        );

        if (result.success)
        {
            ScopedStage stateTiming(timings, Stage::State);

            estimator.applyMotion(result, timestamp, deltaTime);
            tracked = true;
        }
        else
        {
            ScopedStage stateTiming(timings, Stage::State);

            estimator.applyTrackingLoss(imuSamples, timestamp);

            LOG_EVERY(
                LogLevel::Warn,
                2.0,
                "vio: motion estimation failed (%s), %d features with "
                "depth, %d inliers",
                result.failureReason ? result.failureReason : "unknown",
                result.correspondences,
                result.inliers
            );
        }

        estimator.updateBiases(imuSamples, isVisuallyStationary());
    }
    else if (havePrevious)
    {
        ScopedStage stateTiming(timings, Stage::State);

        estimator.applyTrackingLoss(imuSamples, timestamp);
    }

    // Top up features and give them depth for the NEXT frame's motion
    // estimate. Detection runs before stereo so that new features get
    // depth immediately rather than sitting idle for a frame.
    tracker.detect(left, timings);

    if (stereoRuntimeEnabled)
    {
        stereo.compute(left, right, tracker.features(), timings);
    }
    else
    {
        stereo.clearDepth(tracker.features());
    }

    previousLeft = left;
    previousTimestamp = timestamp;
    havePrevious = true;

    VIOState& state = estimator.mutableState();

    state.timestamp = timestamp;
    state.trackedFeatures = static_cast<int>(tracker.count());
    state.stereoFeatures = stereo.stats().triangulated;
    state.imuEnabled =
        (imu != nullptr) && imu->isEnabled() && imuRuntimeEnabled;

    state.imuHealthy = state.imuEnabled && imu->isRunning();
    ++state.frameId;

    const double now = monotonicSeconds();

    timings.noteProcessed(now);
    timings.noteLatency(now - timestamp);

    // Ends the Total stage before the collector reads it, so the
    // figure recorded is the whole frame rather than most of it.
    timings.end(Stage::Total);
    totalTiming.release();

    collector.noteFrame(
        monotonicSeconds(),
        timings,
        state,
        stereo.stats().triangulated,
        tracked
    );

    publish();

    return tracked;
}

bool VIO::isVisuallyStationary() const
{
    const std::vector<Feature>& features = tracker.features();

    if (features.size() < 20)
    {
        return false;
    }

    // A mean would be dragged around by a single bad track; with
    // hundreds of features a simple count above threshold is both
    // cheaper than a median and harder to fool.
    size_t moving = 0;

    for (const Feature& feature : features)
    {
        const cv::Point2f flow = feature.point - feature.previousPoint;

        if (flow.x * flow.x + flow.y * flow.y >
            kStationaryFlowPixels * kStationaryFlowPixels)
        {
            ++moving;
        }
    }

    return moving * 10 < features.size();
}

void VIO::noteDroppedFrames(int count)
{
    if (count <= 0)
    {
        return;
    }

    estimator.mutableState().droppedFrames +=
        static_cast<uint64_t>(count);

    collector.noteDroppedFrames(count);

    publish();
}

void VIO::noteFailedFrame()
{
    collector.noteFailedFrame();
}

void VIO::publish()
{
    VIOSnapshot fresh;

    fresh.state = estimator.state();

    fresh.captureFPS = timings.captureFPS();
    fresh.processingFPS = timings.processingFPS();
    fresh.latencySeconds = timings.latency();

    for (int i = 0; i < static_cast<int>(Stage::Count); ++i)
    {
        fresh.stageMilliseconds[i] =
            timings.average(static_cast<Stage>(i)) * 1e3;
    }

    fresh.stereoMatched = stereo.stats().matched;
    fresh.stereoTriangulated = stereo.stats().triangulated;

    fresh.paused = paused;
    fresh.stereoEnabled = stereoRuntimeEnabled;
    fresh.imuEnabled = imuRuntimeEnabled &&
                       (imu != nullptr) && imu->isEnabled();

    fresh.resetCount = resets;
    fresh.recenterCount = estimator.recenterCount();
    fresh.originRecentered = estimator.hasOrigin();

    if (imu != nullptr)
    {
        const IMU::Health health = imu->health();

        fresh.imuRunning = health.running;
        fresh.imuRateHz = health.measuredRateHz;
    }

    // The lock covers only this assignment. It never overlaps image
    // processing, so a client asking for state cannot delay a frame.
    std::lock_guard<std::mutex> lock(snapshotMutex);

    published = fresh;
}

VIOSnapshot VIO::snapshot() const
{
    std::lock_guard<std::mutex> lock(snapshotMutex);

    return published;
}

} // namespace novex
