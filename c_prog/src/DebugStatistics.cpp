#include "DebugStatistics.hpp"

#include <algorithm>
#include <cmath>

namespace novex
{

namespace
{

// The dashboard updates at 10-30 Hz, so republishing faster than this
// only costs lock traffic on the frame path.
constexpr double kPublishInterval = 0.1;

} // namespace

DebugCollector::DebugCollector(bool enabled)
    : enabled(enabled)
{
    published.enabled = enabled;

    disparityHistogram.bucketWidth = 0.1;
    reprojectionHistogram.bucketWidth = 0.005;
    pointDepthHistogram.bucketWidth = 0.05;
}

void DebugCollector::Histogram::add(double value)
{
    if (!std::isfinite(value))
    {
        return;
    }

    const int last = static_cast<int>(sizeof(buckets) / sizeof(buckets[0])) - 1;

    const int index = std::min(
        last, std::max(0, static_cast<int>(value / bucketWidth))
    );

    ++buckets[index];
    ++samples;
}

double DebugCollector::Histogram::median() const
{
    if (samples == 0)
    {
        return 0.0;
    }

    const uint64_t target = (samples + 1) / 2;

    uint64_t seen = 0;

    const int total = static_cast<int>(sizeof(buckets) / sizeof(buckets[0]));

    for (int i = 0; i < total; ++i)
    {
        seen += buckets[i];

        if (seen >= target)
        {
            return (i + 0.5) * bucketWidth;
        }
    }

    return total * bucketWidth;
}

void DebugCollector::noteGeometry(const FrameDiagnostics& frame)
{
    if (!enabled)
    {
        return;
    }

    lastGeometry = frame;

    if (frame.trackedFeatures > 0 && frame.frameId > 1)
    {
        flowSum += frame.flowMedianPx;
        ++flowFrames;
    }

    if (frame.stereoValid && frame.stereoPoints > 0)
    {
        ++geometryFrames;

        disparitySum += frame.disparityMedianPx;
        depthSum += frame.depthMedian;
        stereoResidualSum += frame.stereoResidualMedianPx;
        stereoVerticalSum += frame.stereoVerticalOffsetPx;

        disparityHistogram.add(frame.disparityMedianPx);
    }

    if (frame.mapInnovationSamples > 0)
    {
        ++innovationFrames;
        innovationSum += frame.mapInnovationMedianPct;
    }

    if (frame.motionAccepted)
    {
        ++motionFrames;

        reprojectionSum += frame.reprojectionMedianPx;
        inlierRatioSum += frame.inlierRatio;
        inlierSum += frame.inliers;
        relativeRotationSum += frame.relativeRotationDeg;
        relativeTranslationSum += frame.relativeTranslationM * 1e3;
        rotationSigmaSum += frame.rotationSigmaDeg;
        translationSigmaSum += frame.translationSigmaMm;

        reprojectionHistogram.add(frame.reprojectionMedianPx);
    }
}

void DebugCollector::notePoints(const LivePoint* points, size_t count,
                                size_t mapSize)
{
    if (!enabled)
    {
        return;
    }

    for (size_t i = 0; i < count; ++i)
    {
        const double depth = points[i].depth;

        pointDepthSum += depth;
        pointDepthMax = std::max(pointDepthMax, depth);
        pointDepthHistogram.add(depth);
    }

    pointDepthCount += count;

    mapSizeNow = mapSize;
    mapSizePeak = std::max(mapSizePeak, mapSize);
}

void DebugCollector::start(double now)
{
    startTime = now;
    lastPublish = now;
}

void DebugCollector::noteFrame(double now,
                               const Profiler& profiler,
                               const VIOState& state,
                               int stereoTriangulated,
                               bool tracked)
{
    if (!enabled)
    {
        return;
    }

    // Everything below is O(1) and allocation-free. That is the whole
    // reason the histogram exists instead of a growing sample vector:
    // percentiles over an entire multi-hour run, at the cost of one
    // array increment per frame.
    const double frameMs = profiler.last(Stage::Total) * 1e3;

    if (frames == 0)
    {
        frameTimeMin = frameMs;
        frameTimeMax = frameMs;
        featureMin = state.trackedFeatures;
        featureMax = state.trackedFeatures;
    }
    else
    {
        frameTimeMin = std::min(frameTimeMin, frameMs);
        frameTimeMax = std::max(frameTimeMax, frameMs);
        featureMin = std::min(featureMin, state.trackedFeatures);
        featureMax = std::max(featureMax, state.trackedFeatures);
    }

    ++frames;

    frameTimeSum += frameMs;

    const int bucket = std::min(
        BucketCount,
        std::max(0, static_cast<int>(frameMs / BucketMs))
    );

    ++histogram[bucket];

    featureSum += static_cast<uint64_t>(std::max(0, state.trackedFeatures));

    stereoSum += static_cast<uint64_t>(std::max(0, stereoTriangulated));

    if (stereoTriangulated <= 0)
    {
        ++framesWithoutStereo;
    }

    if (tracked)
    {
        ++successes;
    }
    else
    {
        ++failures;
    }

    // Trajectory length is the sum of per-frame position deltas. It is
    // path length, not displacement, and it inherits every bit of the
    // odometry's drift - it is a diagnostic, not a measurement.
    if (havePosition)
    {
        trajectoryDistance += (state.position - lastPosition).norm();
    }

    lastPosition = state.position;
    havePosition = true;

    if (now - lastPublish >= kPublishInterval)
    {
        publish(now);
        lastPublish = now;
    }
}

void DebugCollector::noteDroppedFrames(int count)
{
    if (enabled && count > 0)
    {
        dropped += static_cast<uint64_t>(count);
    }
}

void DebugCollector::noteFailedFrame()
{
    if (enabled)
    {
        ++failed;
    }
}

void DebugCollector::noteImuSamples(size_t count)
{
    if (enabled)
    {
        imuSampleCount += count;
    }
}

double DebugCollector::percentile(double fraction) const
{
    if (frames == 0)
    {
        return 0.0;
    }

    const uint64_t target = static_cast<uint64_t>(
        std::ceil(fraction * static_cast<double>(frames))
    );

    uint64_t seen = 0;

    for (int i = 0; i <= BucketCount; ++i)
    {
        seen += histogram[i];

        if (seen >= target)
        {
            if (i == BucketCount)
            {
                // Overflow bin: report the ceiling rather than
                // pretending to know the value.
                return BucketCount * BucketMs;
            }

            // Midpoint of the bucket.
            return (i + 0.5) * BucketMs;
        }
    }

    return frameTimeMax;
}

void DebugCollector::publish(double now)
{
    DebugStatistics fresh;

    fresh.enabled = true;

    fresh.runtimeSeconds = now - startTime;

    fresh.framesProcessed = frames;
    fresh.droppedFrames = dropped;
    fresh.failedFrames = failed;

    fresh.averageFrameTimeMs = frames
        ? frameTimeSum / static_cast<double>(frames)
        : 0.0;

    fresh.minFrameTimeMs = frameTimeMin;
    fresh.maxFrameTimeMs = frameTimeMax;

    fresh.trackingFailures = failures;
    fresh.successfulFrames = successes;

    fresh.averageTrackedFeatures = frames
        ? static_cast<double>(featureSum) / static_cast<double>(frames)
        : 0.0;

    fresh.minTrackedFeatures = featureMin;
    fresh.maxTrackedFeatures = featureMax;

    fresh.stereoMatchesTotal = stereoSum;

    fresh.averageStereoMatches = frames
        ? static_cast<double>(stereoSum) / static_cast<double>(frames)
        : 0.0;

    fresh.framesWithoutStereo = framesWithoutStereo;

    fresh.imuSamples = imuSampleCount;

    fresh.trajectoryDistanceMeters = trajectoryDistance;

    fresh.position = lastPosition;

    std::lock_guard<std::mutex> lock(mutex);

    // Fields the caller fills in from the live snapshot are preserved
    // by copying only what this collector owns.
    const DebugStatistics previous = published;

    fresh.cameraFPS = previous.cameraFPS;
    fresh.vioFPS = previous.vioFPS;
    fresh.captureMs = previous.captureMs;
    fresh.decodeMs = previous.decodeMs;
    fresh.featureDetectionMs = previous.featureDetectionMs;
    fresh.featureTrackingMs = previous.featureTrackingMs;
    fresh.stereoMatchingMs = previous.stereoMatchingMs;
    fresh.motionEstimationMs = previous.motionEstimationMs;
    fresh.imuProcessingMs = previous.imuProcessingMs;
    fresh.trackedFeatures = previous.trackedFeatures;
    fresh.stereoMatchesCurrent = previous.stereoMatchesCurrent;
    fresh.orientation = previous.orientation;

    published = fresh;
}

DebugStatistics DebugCollector::snapshot() const
{
    std::lock_guard<std::mutex> lock(mutex);

    return published;
}

DebugStatistics DebugCollector::finalise(double now) const
{
    DebugStatistics final;

    {
        std::lock_guard<std::mutex> lock(mutex);
        final = published;
    }

    if (!enabled)
    {
        return final;
    }

    final.enabled = true;

    final.runtimeSeconds = now - startTime;

    final.framesProcessed = frames;
    final.droppedFrames = dropped;
    final.failedFrames = failed;

    final.averageFrameTimeMs = frames
        ? frameTimeSum / static_cast<double>(frames)
        : 0.0;

    final.minFrameTimeMs = frameTimeMin;
    final.maxFrameTimeMs = frameTimeMax;

    // Percentiles are computed only here, at exit, from the histogram
    // that was filled in O(1) per frame.
    final.p50FrameTimeMs = percentile(0.50);
    final.p90FrameTimeMs = percentile(0.90);
    final.p99FrameTimeMs = percentile(0.99);

    final.trackingFailures = failures;
    final.successfulFrames = successes;

    final.averageTrackedFeatures = frames
        ? static_cast<double>(featureSum) / static_cast<double>(frames)
        : 0.0;

    final.minTrackedFeatures = featureMin;
    final.maxTrackedFeatures = featureMax;

    final.stereoMatchesTotal = stereoSum;

    final.averageStereoMatches = frames
        ? static_cast<double>(stereoSum) / static_cast<double>(frames)
        : 0.0;

    final.framesWithoutStereo = framesWithoutStereo;
    final.imuSamples = imuSampleCount;
    final.trajectoryDistanceMeters = trajectoryDistance;
    final.position = lastPosition;

    auto mean = [](double sum, uint64_t n)
    {
        return n ? sum / static_cast<double>(n) : 0.0;
    };

    final.geometryFrames = geometryFrames;
    final.averageDisparityPx = mean(disparitySum, geometryFrames);
    final.medianDisparityPx = disparityHistogram.median();
    final.averageDepthM = mean(depthSum, geometryFrames);
    final.averageStereoResidualPx = mean(stereoResidualSum, geometryFrames);
    final.averageStereoVerticalOffsetPx =
        mean(stereoVerticalSum, geometryFrames);

    final.motionFrames = motionFrames;
    final.averageReprojectionPx = mean(reprojectionSum, motionFrames);
    final.medianReprojectionPx = reprojectionHistogram.median();
    final.averageInlierRatio = mean(inlierRatioSum, motionFrames);
    final.averageInliers = mean(inlierSum, motionFrames);
    final.averageRelativeRotationDeg = mean(relativeRotationSum, motionFrames);
    final.averageRelativeTranslationMm =
        mean(relativeTranslationSum, motionFrames);
    final.averageRotationSigmaDeg = mean(rotationSigmaSum, motionFrames);
    final.averageTranslationSigmaMm = mean(translationSigmaSum, motionFrames);
    final.averageFlowPx = mean(flowSum, flowFrames);

    final.motionRejected = lastGeometry.motionRejectedTotal;
    final.referenceResets = lastGeometry.referenceResetsTotal;
    final.stereoRejected = lastGeometry.stereoRejectedTotal;
    final.correspondencesRejected =
        lastGeometry.correspondencesRejectedTotal;

    final.accumulatedRotationDeg = lastGeometry.accumulatedRotationDeg;
    final.accumulatedTranslationM = lastGeometry.accumulatedTranslationM;
    final.netRotationDeg = lastGeometry.netRotationDeg;
    final.netTranslationM = lastGeometry.netTranslationM;

    final.pointDepthSamples = pointDepthCount;
    final.averagePointDepthM = mean(pointDepthSum, pointDepthCount);
    final.medianPointDepthM = pointDepthHistogram.median();
    final.maxPointDepthM = pointDepthMax;
    final.innovationFrames = innovationFrames;
    final.averageInnovationPct = mean(innovationSum, innovationFrames);
    final.mapPoints = mapSizeNow;
    final.mapPeakPoints = mapSizePeak;

    // Overall rate across the whole run, rather than the smoothed
    // instantaneous rate the Profiler tracks.
    if (final.runtimeSeconds > 0.0)
    {
        final.vioFPS =
            static_cast<double>(frames) / final.runtimeSeconds;
    }

    return final;
}

} // namespace novex
