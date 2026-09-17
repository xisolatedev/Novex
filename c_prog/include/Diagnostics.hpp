#pragma once

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <cstdint>

namespace novex
{

// Geometry measurements for ONE processed frame.
//
// Every field is computed from real data by the stage that owns it.
// Nothing is estimated from nominal values, and nothing is filled in
// when a stage did not run: the `*Valid` flags say which blocks hold
// measurements for this frame. Plain data, fixed size, cheap to copy
// into a snapshot.
//
// Units: pixels are centre-of-image pixels for angular quantities
// (angle x focal length); metres; degrees.
struct FrameDiagnostics
{
    uint64_t frameId = 0;
    double timestamp = 0.0;

    // ---- tracking (temporal KLT) ----
    int trackedFeatures = 0;
    int trackRejected = 0;          // dropped by the tracker this frame
    int detectedFeatures = 0;       // new this frame
    double flowMedianPx = 0.0;
    double flowMeanPx = 0.0;

    // ---- stereo ----
    bool stereoValid = false;
    int stereoAttempted = 0;
    int stereoPoints = 0;           // triangulated, valid depth
    int stereoRejected = 0;         // attempted - stereoPoints
    int stereoRejectedMatch = 0;
    int stereoRejectedEpipolar = 0;
    int stereoRejectedDepth = 0;
    double disparityMedianPx = 0.0;
    double disparityStdPx = 0.0;
    double depthMedian = 0.0;
    double depthMin = 0.0;
    double depthMax = 0.0;
    double depthStd = 0.0;
    double stereoResidualMedianPx = 0.0;
    double stereoVerticalOffsetPx = 0.0;

    // ---- motion ----
    bool motionAttempted = false;
    bool motionAccepted = false;
    const char* motionRejectReason = nullptr;   // static string or null
    int correspondences = 0;
    int inliers = 0;
    int rejectedCorrespondences = 0;
    double inlierRatio = 0.0;
    double reprojectionMedianPx = 0.0;
    double reprojectionMaxPx = 0.0;
    double rotationSigmaDeg = 0.0;
    double translationSigmaMm = 0.0;
    double conditioning = 0.0;

    // Frames between the keyframe this estimate was measured against
    // and the current frame.
    int referenceSpanFrames = 0;

    // The RAW estimate, as the camera's motion from the keyframe to
    // now, in keyframe camera axes (valid when motionAccepted). Kept
    // separately from the per-frame relative motion below so the
    // stationary test can re-compose poses independently.
    double estimateRotationVector[3] = {0.0, 0.0, 0.0};   // rad
    double estimateTranslation[3] = {0.0, 0.0, 0.0};      // m

    // This frame became the new keyframe / reference.
    bool keyframeCreated = false;

    // Relative motion camera(reference) -> camera(current), valid
    // when motionAccepted.
    double relativeRotationDeg = 0.0;
    double relativeTranslationM = 0.0;
    double relativeRotationVector[3] = {0.0, 0.0, 0.0};   // axis*angle, rad
    double relativeTranslation[3] = {0.0, 0.0, 0.0};      // reference cam frame

    // ---- point map ----
    // Median distance of this frame's observations from their track's
    // fused map point, as a percentage of range. Stereo repeatability
    // and pose consistency together; 0 samples = not measured.
    double mapInnovationMedianPct = 0.0;
    int mapInnovationSamples = 0;

    // ---- state ----
    double velocity[3] = {0.0, 0.0, 0.0};   // m/s, reported frame
    double speed = 0.0;
    double poseDeltaM = 0.0;       // change of the published position
    double poseDeltaDeg = 0.0;     // change of the published orientation

    // ---- run totals, carried forward every frame ----
    uint64_t motionRejectedTotal = 0;
    uint64_t keyframesTotal = 0;
    uint64_t referenceResetsTotal = 0;     // motion genuinely unmeasured
    uint64_t stereoRejectedTotal = 0;
    uint64_t correspondencesRejectedTotal = 0;

    // Sums of per-frame relative motion magnitudes. They show how much
    // motion the estimator MEASURED, independently of whether it
    // cancels out.
    double accumulatedRotationDeg = 0.0;
    double accumulatedTranslationM = 0.0;

    // Net displacement of the internal pose from the start / last
    // reset.
    double netRotationDeg = 0.0;
    double netTranslationM = 0.0;
};

// Statistics collected while the camera is known to be stationary.
//
// It OBSERVES. It never suppresses, clamps or corrects motion: the
// whole point is to measure what the estimator does when the true
// answer is zero, and attribute any drift to a stage:
//
//   A. feature tracking    optical flow is not ~0
//   B. stereo depth        systematic stereo inconsistency
//   C. motion estimation   consistent non-zero relative motion from
//                          stationary measurements
//   D. state integration   relative motions ~0, but the integrated
//                          pose still moves
//
// To separate C from D it re-composes poses itself from the RAW
// keyframe-relative estimates and the keyframe events, independently of
// StateEstimator, and compares the two.
struct StationaryReport
{
    bool active = false;
    bool haveData = false;

    double durationSeconds = 0.0;
    uint64_t frames = 0;
    uint64_t acceptedEstimates = 0;
    uint64_t rejectedEstimates = 0;

    // Per-frame relative translation magnitude, mm.
    double translationMeanMm = 0.0;
    double translationStdMm = 0.0;

    // Mean relative translation VECTOR, mm per frame. Noise averages
    // towards zero; a bias does not. Its magnitude compared with
    // translationStdMm / sqrt(N) says which one it is.
    double translationBiasMm[3] = {0.0, 0.0, 0.0};
    double translationBiasSignificance = 0.0;   // |bias| / standard error

    // Per-frame relative rotation magnitude, degrees.
    double rotationMeanDeg = 0.0;
    double rotationStdDeg = 0.0;
    double rotationBiasDeg[3] = {0.0, 0.0, 0.0};
    double rotationBiasSignificance = 0.0;

    double flowMeanPx = 0.0;             // mean of per-frame medians
    double depthMedianM = 0.0;           // mean of per-frame medians
    double reprojectionMedianPx = 0.0;   // mean of per-frame medians
    double inlierRatio = 0.0;
    double stereoResidualPx = 0.0;
    double stereoVerticalOffsetPx = 0.0;

    // Drift of the estimator's pose over the window.
    double positionDriftM = 0.0;
    double positionDrift[3] = {0.0, 0.0, 0.0};
    double orientationDriftDeg = 0.0;

    // The same, from integrating the measured relative motions here,
    // independently of the state estimator.
    double measuredPositionDriftM = 0.0;
    double measuredOrientationDriftDeg = 0.0;

    // Which stage the numbers point at, or null when nothing stands
    // out. Advisory text for humans; never fed back into anything.
    const char* indication = nullptr;
};

class StationaryDiagnostic
{
public:

    // Starts a fresh window at the given internal pose.
    void start(double timestamp,
               const Eigen::Matrix3d& rotation,
               const Eigen::Vector3d& position);

    void stop();

    // Called when the frame just passed to update() became the new
    // keyframe, after update().
    void noteKeyframe();

    bool isActive() const { return active; }

    // Called once per processed frame, with the estimator's internal
    // pose AFTER this frame.
    void update(const FrameDiagnostics& frame,
                const Eigen::Matrix3d& rotation,
                const Eigen::Vector3d& position);

    StationaryReport report() const;

private:

    bool active = false;
    bool everStarted = false;

    double startTime = 0.0;
    double lastTime = 0.0;

    Eigen::Matrix3d startRotation = Eigen::Matrix3d::Identity();
    Eigen::Vector3d startPosition = Eigen::Vector3d::Zero();

    Eigen::Matrix3d lastRotation = Eigen::Matrix3d::Identity();
    Eigen::Vector3d lastPosition = Eigen::Vector3d::Zero();

    // Independent composition of the raw estimates onto this class's
    // own copy of the keyframe pose, relative to the window start.
    Eigen::Matrix3d measuredRotation = Eigen::Matrix3d::Identity();
    Eigen::Vector3d measuredPosition = Eigen::Vector3d::Zero();
    Eigen::Matrix3d keyframeRotation = Eigen::Matrix3d::Identity();
    Eigen::Vector3d keyframePosition = Eigen::Vector3d::Zero();

    // False until the first keyframe inside the window: estimates
    // before it are relative to a keyframe this class never saw, so the
    // estimator's pose at window start stands in for it.
    bool haveKeyframe = false;

    uint64_t frames = 0;
    uint64_t accepted = 0;
    uint64_t rejected = 0;

    double translationSum = 0.0;
    double translationSquares = 0.0;
    Eigen::Vector3d translationVectorSum = Eigen::Vector3d::Zero();
    Eigen::Vector3d translationComponentSquares = Eigen::Vector3d::Zero();

    double rotationSum = 0.0;
    double rotationSquares = 0.0;
    Eigen::Vector3d rotationVectorSum = Eigen::Vector3d::Zero();
    Eigen::Vector3d rotationComponentSquares = Eigen::Vector3d::Zero();

    double flowSum = 0.0;
    double depthSum = 0.0;
    uint64_t depthFrames = 0;
    double reprojectionSum = 0.0;
    double inlierRatioSum = 0.0;
    double stereoResidualSum = 0.0;
    double stereoVerticalSum = 0.0;
};

} // namespace novex
