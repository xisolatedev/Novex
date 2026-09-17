#include "VIO.hpp"

#include "Log.hpp"
#include "Time.hpp"

#include <opencv2/calib3d.hpp>

#include <algorithm>
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

// Map point fusion: the fused weight is capped at this many current
// observations, which gives the fusion a memory of roughly that many
// frames, and range sigma never counts as better than 2 mm.
constexpr float kFusionMemory = 25.0f;
constexpr float kFusionSigmaFloor = 0.002f;

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

    flowScratch.reserve(static_cast<size_t>(config.maxFeatures) + 32);

    if (config.pointCloudEnabled)
    {
        // Every buffer the point pipeline will ever use is sized here,
        // once. Nothing below allocates per frame or per point.
        const size_t liveCapacity =
            static_cast<size_t>(config.maxFeatures) + 32;

        liveScratch.resize(liveCapacity);
        innovationScratch.reserve(liveCapacity);

        const size_t mapCapacity = config.pointMapEnabled
            ? static_cast<size_t>(config.pointCloudMaxPoints)
            : 1;

        map.configure(mapCapacity, config.pointCloudVoxelSize);
        points.configure(liveCapacity, mapCapacity);
    }

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
            referenceTimestamp = 0.0;
            referenceSpan = 0;
            keyframeInliers = 0;

            // Totals that describe "this estimate" start again; run
            // counters of rejected work are kept, they describe the
            // run.
            frameDiagnostics.accumulatedRotationDeg = 0.0;
            frameDiagnostics.accumulatedTranslationM = 0.0;
            frameDiagnostics.netRotationDeg = 0.0;
            frameDiagnostics.netTranslationM = 0.0;

            // The map lives in the estimator's internal frame, which
            // reset has just discarded, so its points no longer refer
            // to anything. A new epoch tells every viewer to drop it.
            if (config.pointCloudEnabled)
            {
                map.clear(monotonicSeconds());
            }

            // A running stationary window restarts at the new origin
            // rather than attributing the reset jump to drift.
            if (stationary.isActive())
            {
                stationary.start(monotonicSeconds(),
                                 estimator.internalRotation(),
                                 estimator.internalPosition());
            }

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
                // that gap would produce confident nonsense. The
                // motion reference restarts with it.
                havePrevious = false;
                referenceSpan = 0;
                keyframeInliers = 0;

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

        case CommandType::StationaryTest:
        {
            if (command.flag)
            {
                stationary.start(estimator.state().timestamp,
                                 estimator.internalRotation(),
                                 estimator.internalPosition());

                LOG_INFO(
                    "vio: stationary test started - keep the camera "
                    "still; motion is measured, never suppressed"
                );
            }
            else if (stationary.isActive())
            {
                stationary.stop();
                LOG_INFO("vio: stationary test stopped");
            }

            break;
        }

        case CommandType::ClearMap:
        {
            if (config.pointCloudEnabled)
            {
                map.clear(monotonicSeconds());
                LOG_INFO("vio: point map cleared, tracking untouched");
            }

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
    referenceTimestamp = 0.0;
    referenceSpan = 0;

    if (config.stationaryTestEnabled)
    {
        stationary.start(monotonicSeconds(),
                         estimator.internalRotation(),
                         estimator.internalPosition());

        LOG_INFO(
            "vio: stationary test enabled from start-up - keep the "
            "camera still; motion is measured, never suppressed"
        );
    }

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

    // Time since the motion REFERENCE frame, which is what the visual
    // estimate actually spans. It is the previous frame's interval
    // except after rejected frames.
    const double referenceDelta = havePrevious
        ? timestamp - referenceTimestamp
        : 0.0;

    // Fresh per-frame record; run totals carried from the last frame.
    {
        const FrameDiagnostics last = frameDiagnostics;

        frameDiagnostics = FrameDiagnostics();

        frameDiagnostics.motionRejectedTotal = last.motionRejectedTotal;
        frameDiagnostics.referenceResetsTotal = last.referenceResetsTotal;
        frameDiagnostics.stereoRejectedTotal = last.stereoRejectedTotal;
        frameDiagnostics.correspondencesRejectedTotal =
            last.correspondencesRejectedTotal;
        frameDiagnostics.accumulatedRotationDeg =
            last.accumulatedRotationDeg;
        frameDiagnostics.accumulatedTranslationM =
            last.accumulatedTranslationM;
    }

    frameDiagnostics.timestamp = timestamp;

    const Eigen::Vector3d publishedPositionBefore =
        estimator.state().position;

    const Eigen::Matrix3d internalRotationBefore =
        estimator.internalRotation();

    const Eigen::Vector3d internalPositionBefore =
        estimator.internalPosition();

    const Eigen::Quaterniond publishedOrientationBefore =
        estimator.state().orientation;

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

        frameDiagnostics.trackRejected = tracker.lastDropped();

        measureFlow();

        ++referenceSpan;
    }

    bool tracked = false;
    bool newKeyframe = false;

    if (havePrevious && referenceDelta > 0.0)
    {
        const MotionResult result = motion.estimate(
            tracker.features(),
            referenceDelta,
            timings
        );

        if (result.success)
        {
            ScopedStage stateTiming(timings, Stage::State);

            newKeyframe = keyframeDue(result);

            estimator.applyMotion(result, timestamp, referenceDelta,
                                  newKeyframe);
            tracked = true;
        }
        else
        {
            ScopedStage stateTiming(timings, Stage::State);

            estimator.applyTrackingLoss(imuSamples, timestamp);

            LOG_EVERY(
                LogLevel::Warn,
                2.0,
                "vio: motion estimate rejected (%s), %d features with "
                "reference depth, %d inliers",
                result.failureReason ? result.failureReason : "unknown",
                result.correspondences,
                result.inliers
            );
        }

        fillMotionDiagnostics(result,
                              internalRotationBefore,
                              internalPositionBefore);

        estimator.updateBiases(imuSamples, isVisuallyStationary());
    }
    else if (havePrevious)
    {
        ScopedStage stateTiming(timings, Stage::State);

        estimator.applyTrackingLoss(imuSamples, timestamp);
    }

    // Top up features and give them depth. Detection runs before
    // stereo so that new features get depth immediately rather than
    // sitting idle for a frame.
    tracker.detect(left, timings);

    frameDiagnostics.detectedFeatures = tracker.lastDetected();

    if (stereoRuntimeEnabled)
    {
        stereo.compute(left, right, tracker.features(), timings);

        const StereoMatcher::Stats& s = stereo.stats();

        frameDiagnostics.stereoValid = true;
        frameDiagnostics.stereoAttempted = s.attempted;
        frameDiagnostics.stereoPoints = s.triangulated;
        frameDiagnostics.stereoRejected = s.attempted - s.triangulated;
        frameDiagnostics.stereoRejectedMatch = s.rejectedMatch;
        frameDiagnostics.stereoRejectedEpipolar = s.rejectedEpipolar;
        frameDiagnostics.stereoRejectedDepth = s.rejectedDepth;
        frameDiagnostics.disparityMedianPx = s.disparityMedianPx;
        frameDiagnostics.disparityStdPx = s.disparityStdPx;
        frameDiagnostics.depthMedian = s.depthMedian;
        frameDiagnostics.depthMin = s.depthMin;
        frameDiagnostics.depthMax = s.depthMax;
        frameDiagnostics.depthStd = s.depthStd;
        frameDiagnostics.stereoResidualMedianPx = s.residualMedianPx;
        frameDiagnostics.stereoVerticalOffsetPx = s.verticalOffsetMeanPx;

        frameDiagnostics.stereoRejectedTotal +=
            static_cast<uint64_t>(std::max(0, frameDiagnostics.stereoRejected));
    }
    else
    {
        stereo.clearDepth(tracker.features());
    }

    updateReferences(tracked, newKeyframe, timestamp);

    if (config.pointCloudEnabled)
    {
        buildPointCloud(left, tracked, timestamp);
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

    frameDiagnostics.frameId = state.frameId;
    frameDiagnostics.trackedFeatures = state.trackedFeatures;

    for (int k = 0; k < 3; ++k)
    {
        frameDiagnostics.velocity[k] = state.velocity(k);
    }

    frameDiagnostics.speed = state.velocity.norm();

    frameDiagnostics.poseDeltaM =
        (state.position - publishedPositionBefore).norm();

    frameDiagnostics.poseDeltaDeg =
        publishedOrientationBefore.angularDistance(state.orientation) *
        57.29577951308232;

    frameDiagnostics.netRotationDeg =
        Eigen::AngleAxisd(estimator.internalRotation()).angle() *
        57.29577951308232;

    frameDiagnostics.netTranslationM = estimator.internalPosition().norm();

    frameDiagnostics.keyframesTotal = keyframes;

    stationary.update(frameDiagnostics,
                      estimator.internalRotation(),
                      estimator.internalPosition());

    if (frameDiagnostics.keyframeCreated)
    {
        stationary.noteKeyframe();
    }

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

    collector.noteGeometry(frameDiagnostics);

    publish();

    return tracked;
}

void VIO::measureFlow()
{
    const std::vector<Feature>& features = tracker.features();

    flowScratch.clear();

    double sum = 0.0;

    for (const Feature& feature : features)
    {
        const cv::Point2f flow = feature.point - feature.previousPoint;
        const double magnitude = std::sqrt(flow.x * flow.x + flow.y * flow.y);

        flowScratch.push_back(magnitude);
        sum += magnitude;
    }

    if (flowScratch.empty())
    {
        return;
    }

    const size_t middle = flowScratch.size() / 2;

    std::nth_element(flowScratch.begin(),
                     flowScratch.begin() + static_cast<long>(middle),
                     flowScratch.end());

    frameDiagnostics.flowMedianPx = flowScratch[middle];
    frameDiagnostics.flowMeanPx = sum / static_cast<double>(flowScratch.size());
}

void VIO::fillMotionDiagnostics(const MotionResult& result,
                                const Eigen::Matrix3d& previousRotation,
                                const Eigen::Vector3d& previousPosition)
{
    FrameDiagnostics& d = frameDiagnostics;

    d.motionAttempted = result.attempted;
    d.motionAccepted = result.success;
    d.motionRejectReason = result.success ? nullptr : result.failureReason;
    d.correspondences = result.correspondences;
    d.inliers = result.inliers;
    d.inlierRatio = result.inlierRatio;
    d.reprojectionMedianPx = result.reprojectionMedianPx;
    d.reprojectionMaxPx = result.reprojectionMaxPx;
    d.rotationSigmaDeg = result.rotationSigmaDeg;
    d.translationSigmaMm = result.translationSigmaMm;
    d.conditioning = result.conditioning;
    d.referenceSpanFrames = referenceSpan;

    if (result.attempted)
    {
        d.rejectedCorrespondences =
            std::max(0, result.correspondences - result.inliers);

        d.correspondencesRejectedTotal +=
            static_cast<uint64_t>(d.rejectedCorrespondences);
    }

    if (!result.success)
    {
        ++d.motionRejectedTotal;
        return;
    }

    // Relative motion is reported PER FRAME, whatever the estimate was
    // measured against: the change of the internal pose since the last
    // frame, expressed in that frame's camera axes. The camera rotated
    // by R_prev^T R_now and moved by R_prev^T (p_now - p_prev).
    const Eigen::Matrix3d& rotationNow = estimator.internalRotation();
    const Eigen::Vector3d& positionNow = estimator.internalPosition();

    const Eigen::AngleAxisd rotation(previousRotation.transpose() * rotationNow);
    const Eigen::Vector3d rotationVector = rotation.axis() * rotation.angle();

    const Eigen::Vector3d displacement =
        previousRotation.transpose() * (positionNow - previousPosition);

    for (int k = 0; k < 3; ++k)
    {
        d.relativeRotationVector[k] = rotationVector(k);
        d.relativeTranslation[k] = displacement(k);
    }

    d.relativeRotationDeg = rotation.angle() * 57.29577951308232;
    d.relativeTranslationM = displacement.norm();

    // Raw estimate against the keyframe, as camera motion: R^T and
    // -R^T t in keyframe axes.
    const cv::Matx33d cameraRotation = result.rotation.t();
    const cv::Vec3d cameraDisplacement = -(cameraRotation * result.translation);

    cv::Vec3d estimateVector;
    cv::Rodrigues(cameraRotation, estimateVector);

    for (int k = 0; k < 3; ++k)
    {
        d.estimateRotationVector[k] = estimateVector[k];
        d.estimateTranslation[k] = cameraDisplacement[k];
    }

    d.accumulatedRotationDeg += d.relativeRotationDeg;
    d.accumulatedTranslationM += d.relativeTranslationM;
}

bool VIO::keyframeDue(const MotionResult& result)
{
    if (config.keyframeRetention <= 0.0)
    {
        return true;   // frame-to-frame
    }

    // The first estimate against a keyframe sets its baseline: how many
    // inliers it can support when fresh.
    if (keyframeInliers == 0)
    {
        keyframeInliers = result.inliers;
    }

    // Retention falls as tracks from the keyframe are lost or drift out
    // of the inlier set. Below the threshold, a fresh keyframe with
    // today's depths and today's features serves better.
    const double retention =
        static_cast<double>(result.inliers) / keyframeInliers;

    return retention < config.keyframeRetention ||
           referenceSpan >= config.keyframeMaxSpan;
}

void VIO::updateReferences(bool motionAccepted, bool newKeyframe,
                           double timestamp)
{
    std::vector<Feature>& features = tracker.features();

    // A new keyframe was decided with an accepted estimate - or no
    // estimate is possible yet, on the first frame after start, reset
    // or resume. Either way THIS frame's depths become the reference.
    bool advance = newKeyframe || referenceSpan == 0;

    // Whether the estimator's reference pose must be moved here, as
    // opposed to having been moved by applyMotion already.
    bool reanchorPose = referenceSpan == 0;

    if (!advance)
    {
        // Keeping the keyframe: nothing to do unless too few features
        // still carry its depth for any estimate to succeed.
        int carrying = 0;

        for (const Feature& feature : features)
        {
            carrying += feature.hasReference ? 1 : 0;
        }

        if (carrying < std::max(6, config.minInliersForTracking))
        {
            advance = true;
            reanchorPose = true;

            if (!motionAccepted)
            {
                // The pose here is carried forward, not measured, so
                // the motion since the keyframe is genuinely lost.
                ++frameDiagnostics.referenceResetsTotal;

                LOG_EVERY(
                    LogLevel::Warn,
                    2.0,
                    "vio: only %d features carry reference depth; "
                    "re-anchoring at the current frame (motion over the "
                    "last %d frame(s) is unmeasured)",
                    carrying,
                    referenceSpan
                );
            }
        }
    }

    if (!advance)
    {
        return;
    }

    for (Feature& feature : features)
    {
        feature.hasReference = feature.hasDepth;
        feature.reference3D = feature.position3D;
    }

    if (reanchorPose)
    {
        estimator.reanchorReference();
    }

    referenceTimestamp = timestamp;
    referenceSpan = 0;
    keyframeInliers = 0;

    ++keyframes;

    frameDiagnostics.keyframeCreated = true;
}

void VIO::buildPointCloud(const cv::Mat& left, bool poseValid,
                          double timestamp)
{
    ScopedStage timing(timings, Stage::PointCloud);

    const Eigen::Matrix3d& rotation = estimator.internalRotation();
    const Eigen::Vector3d& position = estimator.internalPosition();

    const Eigen::Matrix3f rotationF = rotation.cast<float>();
    const Eigen::Vector3f positionF = position.cast<float>();

    std::vector<Feature>& features = tracker.features();

    size_t liveCount = 0;

    innovationScratch.clear();

    const int maxX = left.cols - 1;
    const int maxY = left.rows - 1;

    for (Feature& feature : features)
    {
        if (!feature.hasDepth || liveCount >= liveScratch.size())
        {
            continue;
        }

        ++pointTotals.generated;

        LivePoint& p = liveScratch[liveCount++];

        p.position[0] = feature.position3D.x;
        p.position[1] = feature.position3D.y;
        p.position[2] = feature.position3D.z;
        p.featureId = static_cast<uint32_t>(feature.id & 0xffffffffu);
        p.depth = feature.position3D.z;
        p.depthSigma = feature.depthSigma;
        p.stereoResidualPx = feature.stereoResidualPx;
        p.age = static_cast<uint8_t>(std::min(feature.age, 255));

        const int px = std::min(maxX, std::max(0,
            static_cast<int>(std::lround(feature.point.x))));
        const int py = std::min(maxY, std::max(0,
            static_cast<int>(std::lround(feature.point.y))));

        p.intensity = left.at<uint8_t>(py, px);

        p.quality = pointQuality(
            feature.depthSigma,
            feature.stereoResidualPx,
            feature.motionInlier,
            config.pointCloudMaxDepthSigma,
            config.pointCloudMaxStereoResidualPx
        );

        p.flags = feature.motionInlier ? LiveFlagMotionInlier : 0;

        // ---- map gates ----
        //
        // Each rejection is counted by reason. They exist so the MAP
        // is made of trustworthy geometry; the live view shows every
        // point regardless, because it is also a diagnostic.
        if (!config.pointMapEnabled)
        {
            continue;
        }

        if (!poseValid)
        {
            // Without an accepted motion estimate this frame, the pose
            // is carried forward rather than measured, and a world
            // point built from it would be placed with a stale pose.
            ++pointTotals.rejectedNoPose;
            continue;
        }

        if (feature.position3D.z > config.pointCloudMaxDepth)
        {
            ++pointTotals.rejectedDepth;
            continue;
        }

        if (feature.depthSigma > config.pointCloudMaxDepthSigma)
        {
            ++pointTotals.rejectedUncertainty;
            continue;
        }

        if (feature.stereoResidualPx > config.pointCloudMaxStereoResidualPx)
        {
            ++pointTotals.rejectedResidual;
            continue;
        }

        if (feature.age < config.pointCloudMinTrackAge)
        {
            ++pointTotals.rejectedTrackAge;
            continue;
        }

        if (config.pointCloudRequireInlier && !feature.motionInlier)
        {
            ++pointTotals.rejectedNotInlier;
            continue;
        }

        p.flags |= LiveFlagMapEligible;

        ++pointTotals.accepted;

        // P_world = R_wc * P_camera + p_wc, with the pose of THIS frame.
        const Eigen::Vector3f world =
            rotationF * Eigen::Vector3f(p.position[0],
                                        p.position[1],
                                        p.position[2]) + positionF;

        // ---- fuse repeated observations of this track ----
        //
        // Range noise lies ALONG the viewing ray, so independent
        // observations of one feature scatter into a streak. Fusing
        // them by inverse range variance turns the streak into one
        // point whose error shrinks as it is re-observed. The weight is
        // bounded to ~kFusionMemory observations, so a point can still
        // follow a slowly drifting pose instead of freezing on old data.
        const float range = Eigen::Vector3f(p.position[0], p.position[1],
                                            p.position[2]).norm();

        const float rangeSigma = std::max(
            feature.depthSigma * range, kFusionSigmaFloor
        );

        const float weight = 1.0f / (rangeSigma * rangeSigma);

        if (feature.fusedWeight > 0.0f)
        {
            const Eigen::Vector3f fused(feature.fusedWorld[0],
                                        feature.fusedWorld[1],
                                        feature.fusedWorld[2]);

            // How far this observation lands from what the track
            // already said, as a fraction of range: stereo repeatability
            // plus pose consistency, measured.
            innovationScratch.push_back((world - fused).norm() / range);

            const float total = feature.fusedWeight + weight;
            const Eigen::Vector3f updated =
                (fused * feature.fusedWeight + world * weight) / total;

            for (int axis = 0; axis < 3; ++axis)
            {
                feature.fusedWorld[axis] = updated(axis);
            }

            feature.fusedWeight = std::min(total, weight * kFusionMemory);
        }
        else
        {
            for (int axis = 0; axis < 3; ++axis)
            {
                feature.fusedWorld[axis] = world(axis);
            }

            feature.fusedWeight = weight;
        }

        feature.mapSlot = map.upsertTrack(
            feature.mapSlot,
            feature.id,
            Eigen::Vector3f(feature.fusedWorld[0], feature.fusedWorld[1],
                            feature.fusedWorld[2]),
            p.quality,
            p.intensity,
            timestamp,
            pointTotals
        );
    }

    if (!innovationScratch.empty())
    {
        const size_t middle = innovationScratch.size() / 2;

        std::nth_element(innovationScratch.begin(),
                         innovationScratch.begin() + static_cast<long>(middle),
                         innovationScratch.end());

        frameDiagnostics.mapInnovationMedianPct =
            innovationScratch[middle] * 100.0;
        frameDiagnostics.mapInnovationSamples =
            static_cast<int>(innovationScratch.size());
    }

    collector.notePoints(liveScratch.data(), liveCount,
                         config.pointMapEnabled ? map.size() : 0);

    const double now = monotonicSeconds();

    if (lastPointPublish >= 0.0 &&
        now - lastPointPublish < 1.0 / config.pointCloudPublishHz)
    {
        return;
    }

    PointPose pose;
    PointPose origin;

    const Eigen::Matrix3d& originR = estimator.originRotationMatrix();
    const Eigen::Vector3d& originP = estimator.originPositionVector();

    for (int row = 0; row < 3; ++row)
    {
        for (int col = 0; col < 3; ++col)
        {
            pose.rotation[row * 3 + col] =
                static_cast<float>(rotation(row, col));
            origin.rotation[row * 3 + col] =
                static_cast<float>(originR(row, col));
        }

        pose.position[row] = static_cast<float>(position(row));
        origin.position[row] = static_cast<float>(originP(row));
    }

    const uint64_t frameId = estimator.state().frameId + 1;

    // Both use try_lock. If the server is mid-read, this frame's
    // snapshot is simply skipped - the map's dirty list is kept, so
    // nothing is lost, only delayed to the next frame.
    const bool liveDone = points.tryPublishLive(
        timestamp, frameId, pose, origin, liveScratch.data(), liveCount
    );

    bool mapDone = true;

    if (config.pointMapEnabled)
    {
        mapDone = points.tryPublishMap(map, timestamp, frameId, pose, origin);

        if (mapDone)
        {
            map.clearDirty();
        }
    }

    if (liveDone && mapDone)
    {
        lastPointPublish = now;
    }
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

    fresh.diagnostics = frameDiagnostics;
    fresh.stationary = stationary.report();

    fresh.pointCloudEnabled = config.pointCloudEnabled;
    fresh.pointMapEnabled = config.pointCloudEnabled && config.pointMapEnabled;
    fresh.livePoints = static_cast<size_t>(
        std::max(0, frameDiagnostics.stereoPoints));
    fresh.mapPoints = config.pointMapEnabled ? map.size() : 0;
    fresh.mapCapacity = config.pointMapEnabled ? map.capacity() : 0;
    fresh.voxelSize = map.voxelSize();
    fresh.mapEpoch = map.epoch();
    fresh.pointCounters = pointTotals;

    fresh.originOrientation =
        Eigen::Quaterniond(estimator.originRotationMatrix());
    fresh.originPosition = estimator.originPositionVector();

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
