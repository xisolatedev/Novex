#pragma once

#include "IMU.hpp"
#include "MotionEstimator.hpp"
#include "VIOConfig.hpp"
#include "VIOState.hpp"

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <opencv2/core.hpp>

#include <cstdint>
#include <vector>

namespace novex
{

// Turns per-frame relative motion into a global pose, with optional
// help from the IMU.
//
// SCOPE, stated plainly: this is a LOOSELY COUPLED estimator. Vision
// produces a complete relative pose, and that pose is integrated. The
// IMU is used in the two places where it helps without needing a
// camera-IMU extrinsic calibration that does not exist yet:
//
//   * to carry orientation forward while vision is lost, instead of
//     freezing the last pose
//   * to estimate the gyro bias while the platform is stationary
//
// It is NOT used to seed the PnP solver. That was tried and removed:
// cv::solvePnPRansac ignores useExtrinsicGuess, so the seed did
// nothing. See the note in MotionEstimator.hpp.
//
// It is NOT a tightly coupled filter. There is no joint state, no
// covariance, no IMU preintegration between keyframes and no bundle
// adjustment. Those need a measured camera-IMU extrinsic and time
// offset to be worth anything, and inventing either would produce a
// system that looks finished and drifts for reasons nobody can find.
class StateEstimator
{
public:

    explicit StateEstimator(const VIOConfig& config);

    // Restarts the estimator: pose back to identity, velocity and
    // bias cleared, origin cleared.
    void reset();

    // Redefines the reported origin as the current pose WITHOUT
    // touching the estimator.
    //
    // These are deliberately different operations and must not be
    // merged. reset() throws away what the estimator knows and starts
    // tracking again from nothing. recenter() keeps every bit of that
    // - the integrated pose, the velocity filter, the gyro bias -
    // and only changes the frame the answer is expressed in. The
    // internal integration continues in the original frame, so
    // recentring costs nothing in accuracy and cannot lose tracking.
    void recenter();

    uint64_t recenterCount() const { return recenters; }
    bool hasOrigin() const { return originActive; }

    // Integrates buffered gyro samples over the interval and returns
    // the implied camera rotation. Returns false when there is
    // nothing to integrate.
    bool gyroRotation(const std::vector<IMUSample>& samples,
                      cv::Matx33d& rotation) const;

    // Applies a successful visual motion estimate. The motion is
    // relative to the REFERENCE pose (the pose at the last accepted
    // estimate), not to whatever the published pose currently is, so
    // an estimate that spans rejected frames composes onto the frame
    // its 3D points were actually measured in. `deltaTime` is the time
    // since that reference.
    //
    // `advanceReference` makes the resulting pose the new reference -
    // true for frame-to-frame operation, and whenever a new keyframe is
    // created. While it stays false, successive estimates all compose
    // onto the same keyframe pose, so their errors do not accumulate.
    void applyMotion(const MotionResult& motion,
                     double timestamp,
                     double deltaTime,
                     bool advanceReference = true);

    // Moves the reference to the current pose without a measurement.
    // Used when the features that carried reference depth are gone and
    // the pipeline has to start linking from the current frame; the
    // motion during the gap is then genuinely unmeasured, and the
    // caller counts it as such.
    void reanchorReference();

    // The pose the estimator integrates in, before the recenter origin
    // is applied: X_internal = internalRotation * X_camera +
    // internalPosition. The point map is stored in this frame, so it
    // survives recenter unchanged.
    const Eigen::Matrix3d& internalRotation() const
    {
        return worldFromCamera;
    }

    const Eigen::Vector3d& internalPosition() const
    {
        return positionInWorld;
    }

    // The reporting origin inside the internal frame. Identity until
    // recenter(). X_reported = originRotation^T (X_internal -
    // originPosition).
    const Eigen::Matrix3d& originRotationMatrix() const
    {
        return originRotation;
    }

    const Eigen::Vector3d& originPositionVector() const
    {
        return originPosition;
    }

    // Called when vision failed for this frame. If the IMU is
    // available, orientation is propagated with the gyro; position is
    // held, because dead-reckoning position from a consumer
    // accelerometer diverges in seconds and a held position is at
    // least honestly wrong.
    void applyTrackingLoss(const std::vector<IMUSample>& samples,
                           double timestamp);

    // Updates the gyro bias estimate while the platform is judged
    // stationary by vision.
    void updateBiases(const std::vector<IMUSample>& samples,
                      bool visuallyStationary);

    const VIOState& state() const { return current; }
    VIOState& mutableState() { return current; }

private:

    Eigen::Matrix3d cameraFromBody() const;

    // Recomputes the published pose from the internal pose and the
    // current origin. Called from every path that changes either.
    void updatePublishedPose();

    const VIOConfig& config;

    VIOState current;

    // The estimator integrates in this frame always. Nothing below
    // ever rewrites it, which is what makes recentring free.
    Eigen::Matrix3d worldFromCamera = Eigen::Matrix3d::Identity();
    Eigen::Vector3d positionInWorld = Eigen::Vector3d::Zero();

    // Pose of the frame the current reference depths were measured in.
    Eigen::Matrix3d referenceRotation = Eigen::Matrix3d::Identity();
    Eigen::Vector3d referencePosition = Eigen::Vector3d::Zero();

    // The frame results are REPORTED in. Identity until recenter().
    Eigen::Matrix3d originRotation = Eigen::Matrix3d::Identity();
    Eigen::Vector3d originPosition = Eigen::Vector3d::Zero();

    bool originActive = false;
    uint64_t recenters = 0;

    bool initialised = false;

    double lastTimestamp = 0.0;

    // Low-pass on velocity. A per-frame finite difference of position
    // is far too noisy to hand to a consumer as-is.
    Eigen::Vector3d filteredVelocity = Eigen::Vector3d::Zero();

    // Running mean of the gyro while stationary.
    Eigen::Vector3d biasAccumulator = Eigen::Vector3d::Zero();
    uint64_t biasSamples = 0;
};

} // namespace novex
