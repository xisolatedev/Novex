#pragma once

#include "Diagnostics.hpp"
#include "PointCloud.hpp"
#include "Profiler.hpp"
#include "VIOState.hpp"

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <cstdint>
#include <mutex>

namespace novex
{

// A copyable summary of everything --debug collects. Readers (the IPC
// server, and therefore the web dashboard) get one of these; they
// never see the accumulators.
struct DebugStatistics
{
    bool enabled = false;

    double runtimeSeconds = 0.0;

    uint64_t framesProcessed = 0;
    uint64_t droppedFrames = 0;
    uint64_t failedFrames = 0;

    double cameraFPS = 0.0;
    double vioFPS = 0.0;

    // Whole-pipeline per-frame time.
    double averageFrameTimeMs = 0.0;
    double minFrameTimeMs = 0.0;
    double maxFrameTimeMs = 0.0;

    // From the histogram, so they cover the entire run rather than a
    // recent window.
    double p50FrameTimeMs = 0.0;
    double p90FrameTimeMs = 0.0;
    double p99FrameTimeMs = 0.0;

    // Per-stage means. These are per INVOCATION, matching Profiler:
    // detection does not run every frame, so its figure is what a
    // detection costs when it happens.
    double captureMs = 0.0;
    double decodeMs = 0.0;
    double featureDetectionMs = 0.0;
    double featureTrackingMs = 0.0;
    double stereoMatchingMs = 0.0;
    double motionEstimationMs = 0.0;
    double imuProcessingMs = 0.0;

    // State estimation is not separately timed; see the note in
    // DebugCollector::note. Reported as unavailable rather than
    // invented.
    bool stateEstimationMeasured = false;
    double stateEstimationMs = 0.0;

    int trackedFeatures = 0;
    double averageTrackedFeatures = 0.0;
    int minTrackedFeatures = 0;
    int maxTrackedFeatures = 0;

    uint64_t trackingFailures = 0;
    uint64_t successfulFrames = 0;

    // Stereo triangulation, accumulated and current.
    uint64_t stereoMatchesTotal = 0;
    double averageStereoMatches = 0.0;
    int stereoMatchesCurrent = 0;
    uint64_t framesWithoutStereo = 0;

    uint64_t imuSamples = 0;

    double trajectoryDistanceMeters = 0.0;

    // ---- geometry, averaged over frames that measured it ----
    uint64_t geometryFrames = 0;
    double averageDisparityPx = 0.0;     // mean of per-frame medians
    double medianDisparityPx = 0.0;      // median of per-frame medians
    double averageDepthM = 0.0;          // mean of per-frame medians
    double averageStereoResidualPx = 0.0;
    double averageStereoVerticalOffsetPx = 0.0;

    uint64_t motionFrames = 0;           // accepted estimates
    double averageReprojectionPx = 0.0;  // mean of per-frame medians
    double medianReprojectionPx = 0.0;   // median of per-frame medians
    double averageInlierRatio = 0.0;
    double averageInliers = 0.0;
    double averageRelativeRotationDeg = 0.0;
    double averageRelativeTranslationMm = 0.0;
    double averageRotationSigmaDeg = 0.0;
    double averageTranslationSigmaMm = 0.0;
    double averageFlowPx = 0.0;          // mean of per-frame medians

    uint64_t motionRejected = 0;
    uint64_t referenceResets = 0;
    uint64_t stereoRejected = 0;
    uint64_t correspondencesRejected = 0;

    // ---- drift ----
    double accumulatedRotationDeg = 0.0;
    double accumulatedTranslationM = 0.0;
    double netRotationDeg = 0.0;
    double netTranslationM = 0.0;

    // Copied in from the live snapshot at exit.
    StationaryReport stationary;

    // ---- point cloud ----
    bool pointCloudEnabled = false;
    bool pointMapEnabled = false;
    PointCloudCounters pointCounters;
    uint64_t pointDepthSamples = 0;
    double averagePointDepthM = 0.0;
    double medianPointDepthM = 0.0;
    double maxPointDepthM = 0.0;
    uint64_t innovationFrames = 0;
    double averageInnovationPct = 0.0;   // mean of per-frame medians
    size_t mapPoints = 0;
    size_t mapPeakPoints = 0;
    size_t mapCapacity = 0;
    double voxelSize = 0.0;

    Eigen::Vector3d position = Eigen::Vector3d::Zero();
    Eigen::Quaterniond orientation = Eigen::Quaterniond::Identity();

    EIGEN_MAKE_ALIGNED_OPERATOR_NEW
};

// Accumulates the statistics above.
//
// Everything in the per-frame path is a handful of increments,
// comparisons and one histogram bump - no allocation, no sorting, no
// locking. The only lock is taken when publishing the summary, which
// is a copy of one struct, and when a reader asks for it.
//
// The collector OBSERVES the pipeline. It never owns or mutates VIO
// state; VIO passes it the values it already computed.
class DebugCollector
{
public:

    // Frame times are bucketed at this resolution, up to the ceiling.
    // Anything slower lands in the overflow bin and is reported as
    // "at least" the ceiling, which is honest and costs nothing.
    static constexpr double BucketMs = 0.25;
    static constexpr int BucketCount = 800;   // 0 .. 200 ms

    explicit DebugCollector(bool enabled);

    bool isEnabled() const { return enabled; }

    void start(double now);

    // Called once per processed frame, from the VIO thread only.
    void noteFrame(double now,
                   const Profiler& profiler,
                   const VIOState& state,
                   int stereoTriangulated,
                   bool tracked);

    void noteDroppedFrames(int count);
    void noteFailedFrame();
    void noteImuSamples(size_t count);

    // Geometry of one processed frame. VIO thread only.
    void noteGeometry(const FrameDiagnostics& frame);

    // Depths of this frame's live stereo points, and the map size.
    void notePoints(const LivePoint* points, size_t count,
                    size_t mapSize);

    // Thread-safe copy of the current summary.
    DebugStatistics snapshot() const;

    // Recomputes percentiles from the histogram and returns the final
    // summary. Cheap enough to call at exit; not called per frame.
    DebugStatistics finalise(double now) const;

private:

    void publish(double now);

    double percentile(double fraction) const;

    bool enabled = false;

    double startTime = 0.0;

    uint64_t frames = 0;
    uint64_t dropped = 0;
    uint64_t failed = 0;
    uint64_t failures = 0;
    uint64_t successes = 0;
    uint64_t framesWithoutStereo = 0;
    uint64_t imuSampleCount = 0;

    double frameTimeSum = 0.0;
    double frameTimeMin = 0.0;
    double frameTimeMax = 0.0;

    uint64_t featureSum = 0;
    int featureMin = 0;
    int featureMax = 0;

    uint64_t stereoSum = 0;

    double trajectoryDistance = 0.0;
    Eigen::Vector3d lastPosition = Eigen::Vector3d::Zero();
    bool havePosition = false;

    uint32_t histogram[BucketCount + 1] = {};

    // Fixed-bucket histograms for run medians of geometry. Same idea
    // as the frame-time histogram: O(1) per sample, medians at exit.
    struct Histogram
    {
        double bucketWidth = 1.0;
        uint32_t buckets[1024] = {};
        uint64_t samples = 0;

        void add(double value);
        double median() const;
    };

    Histogram disparityHistogram;       // 0.1 px buckets
    Histogram reprojectionHistogram;    // 0.005 px buckets
    Histogram pointDepthHistogram;      // 0.05 m buckets

    uint64_t geometryFrames = 0;
    double disparitySum = 0.0;
    double depthSum = 0.0;
    double stereoResidualSum = 0.0;
    double stereoVerticalSum = 0.0;

    uint64_t motionFrames = 0;
    double reprojectionSum = 0.0;
    double inlierRatioSum = 0.0;
    double inlierSum = 0.0;
    double relativeRotationSum = 0.0;
    double relativeTranslationSum = 0.0;
    double rotationSigmaSum = 0.0;
    double translationSigmaSum = 0.0;

    uint64_t flowFrames = 0;
    double flowSum = 0.0;

    uint64_t innovationFrames = 0;
    double innovationSum = 0.0;

    FrameDiagnostics lastGeometry;

    uint64_t pointDepthCount = 0;
    double pointDepthSum = 0.0;
    double pointDepthMax = 0.0;
    size_t mapSizeNow = 0;
    size_t mapSizePeak = 0;

    // Publishing throttled to a few times a second: the dashboard
    // cannot use more, and it keeps the lock off the frame path.
    double lastPublish = 0.0;

    mutable std::mutex mutex;
    DebugStatistics published;
};

} // namespace novex
