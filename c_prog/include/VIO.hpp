#pragma once

#include "CommandQueue.hpp"
#include "DebugStatistics.hpp"
#include "Diagnostics.hpp"
#include "FeatureTracker.hpp"
#include "FloorEstimator.hpp"
#include "IMU.hpp"
#include "MotionEstimator.hpp"
#include "PointCloud.hpp"
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

    // Geometry measurements of the most recent frame, with run totals.
    FrameDiagnostics diagnostics;

    // Live stationary-test statistics; haveData false if never run.
    StationaryReport stationary;

    // Point cloud state. Counters are run totals since start-up.
    bool pointCloudEnabled = false;
    bool pointMapEnabled = false;
    size_t livePoints = 0;
    size_t mapPoints = 0;
    size_t mapCapacity = 0;
    double voxelSize = 0.0;
    uint32_t mapEpoch = 0;
    PointCloudCounters pointCounters;

    // Ground plane estimate. Its planes are in the CAMERA frame and
    // the INTERNAL world frame; use planeInFrame() with the origin
    // below to express the world plane in the reported frame.
    FloorEstimate floor;

    // Recenter origin inside the internal frame, as a quaternion and
    // position. Lets a viewer that stores data in the internal frame
    // (the point map, the trajectory) express it in the reported one.
    Eigen::Quaterniond originOrientation = Eigen::Quaterniond::Identity();
    Eigen::Vector3d originPosition = Eigen::Vector3d::Zero();

    EIGEN_MAKE_ALIGNED_OPERATOR_NEW
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

    // Point snapshots for the IPC server. The VIO thread only ever
    // try_locks inside it, so a reader can never stall a frame.
    PointCloudChannel& pointChannel() { return points; }

    const FrameDiagnostics& diagnostics() const { return frameDiagnostics; }

    StationaryReport stationaryReport() const { return stationary.report(); }

    const PointCloudCounters& pointCounters() const { return pointTotals; }

    const PointMap& pointMap() const { return map; }

    // Ground plane. Same threading rule as features(): the estimator
    // itself is touched only from the VIO thread, while the copyable
    // estimate travels in the snapshot.
    const FloorEstimator& floorEstimator() const { return floor; }
    FloorEstimator& floorEstimator() { return floor; }

    // Needed by anything that has to project 3D results back into the
    // image, which is the GUI and nothing else.
    const StereoCalibration& stereoCalibration() const
    {
        return calibration;
    }

private:

    void publish();

    void apply(const Command& command);

    bool isVisuallyStationary() const;

    void measureFlow();

    // Whether an accepted estimate should make this frame a new
    // keyframe.
    bool keyframeDue(const MotionResult& result);

    // After stereo: advance or keep the motion reference depths.
    void updateReferences(bool motionAccepted, bool newKeyframe,
                          double timestamp);

    void fillMotionDiagnostics(const MotionResult& result,
                               const Eigen::Matrix3d& previousRotation,
                               const Eigen::Vector3d& previousPosition);

    void buildPointCloud(const cv::Mat& left, bool poseValid,
                         double timestamp);

    void updateFloor(bool poseValid, double timestamp);

    const VIOConfig& config;
    const StereoCalibration& calibration;

    IMU* imu;

    FeatureTracker tracker;
    StereoMatcher stereo;
    MotionEstimator motion;
    StateEstimator estimator;
    FloorEstimator floor;

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

    // ---- motion reference ----
    double referenceTimestamp = 0.0;
    int referenceSpan = 0;

    // Inliers of the first estimate against the current keyframe, the
    // baseline its retention is measured against. 0 = not yet known.
    int keyframeInliers = 0;
    uint64_t keyframes = 0;

    // ---- diagnostics ----
    FrameDiagnostics frameDiagnostics;
    StationaryDiagnostic stationary;
    std::vector<double> flowScratch;

    // ---- point cloud ----
    PointMap map;
    PointCloudChannel points;
    PointCloudCounters pointTotals;
    std::vector<LivePoint> liveScratch;
    std::vector<float> innovationScratch;
    double lastPointPublish = -1.0;

    mutable std::mutex snapshotMutex;
    VIOSnapshot published;
};

} // namespace novex
