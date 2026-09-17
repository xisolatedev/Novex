#include "StateEstimator.hpp"

#include "Log.hpp"

#include <cmath>

namespace novex
{

namespace
{

// Weight of a new velocity measurement in the low-pass. Chosen so the
// velocity settles within roughly a tenth of a second at 30 fps, which
// is fast enough to be useful and slow enough not to be dominated by
// per-frame PnP noise.
constexpr double kVelocityAlpha = 0.3;

Eigen::Matrix3d fromCv(const cv::Matx33d& source)
{
    Eigen::Matrix3d destination;

    for (int row = 0; row < 3; ++row)
    {
        for (int col = 0; col < 3; ++col)
        {
            destination(row, col) = source(row, col);
        }
    }

    return destination;
}

// Orthonormalises a rotation that has accumulated numerical drift.
// Without this, integrating thousands of small rotations slowly
// destroys the matrix, and the resulting quaternion stops being a
// rotation at all.
Eigen::Matrix3d reorthonormalise(const Eigen::Matrix3d& rotation)
{
    const Eigen::JacobiSVD<Eigen::Matrix3d> svd(
        rotation,
        Eigen::ComputeFullU | Eigen::ComputeFullV
    );

    Eigen::Matrix3d result = svd.matrixU() * svd.matrixV().transpose();

    if (result.determinant() < 0.0)
    {
        Eigen::Matrix3d correction = Eigen::Matrix3d::Identity();
        correction(2, 2) = -1.0;

        result = svd.matrixU() * correction * svd.matrixV().transpose();
    }

    return result;
}

} // namespace

StateEstimator::StateEstimator(const VIOConfig& config)
    : config(config)
{
    reset();
}

void StateEstimator::reset()
{
    current = VIOState();

    current.imuEnabled = config.imuEnabled;

    worldFromCamera = Eigen::Matrix3d::Identity();
    positionInWorld = Eigen::Vector3d::Zero();

    referenceRotation = Eigen::Matrix3d::Identity();
    referencePosition = Eigen::Vector3d::Zero();

    filteredVelocity.setZero();

    originRotation = Eigen::Matrix3d::Identity();
    originPosition = Eigen::Vector3d::Zero();
    originActive = false;

    initialised = false;
    lastTimestamp = 0.0;

    biasAccumulator.setZero();
    biasSamples = 0;
}

void StateEstimator::recenter()
{
    // Snapshot the current internal pose as the new reporting frame.
    // Note what is NOT touched: worldFromCamera, positionInWorld,
    // filteredVelocity, the gyro bias, and the tracker's features,
    // which this class cannot see anyway. Tracking continues across
    // this call without so much as a dropped frame.
    originRotation = worldFromCamera;
    originPosition = positionInWorld;

    originActive = true;
    ++recenters;

    updatePublishedPose();
}

void StateEstimator::updatePublishedPose()
{
    // Express the internal pose in the origin frame:
    //   R_out = R_origin^T * R_world_camera
    //   p_out = R_origin^T * (p_world - p_origin)
    // With no recentre both reduce to the internal values, so the
    // default path costs one transpose-multiply and nothing else.
    const Eigen::Matrix3d rotated =
        originRotation.transpose() * worldFromCamera;

    current.position =
        originRotation.transpose() * (positionInWorld - originPosition);

    current.velocity = originRotation.transpose() * filteredVelocity;

    current.orientation = Eigen::Quaterniond(rotated);
    current.orientation.normalize();
}

Eigen::Matrix3d StateEstimator::cameraFromBody() const
{
    Eigen::Matrix3d rotation;

    for (int row = 0; row < 3; ++row)
    {
        for (int col = 0; col < 3; ++col)
        {
            rotation(row, col) =
                config.imuRotationCameraFromBody[
                    static_cast<size_t>(row * 3 + col)];
        }
    }

    return rotation;
}

bool StateEstimator::gyroRotation(const std::vector<IMUSample>& samples,
                                  cv::Matx33d& rotation) const
{
    if (samples.size() < 2)
    {
        return false;
    }

    // Straight rectangular integration of the bias-corrected gyro in
    // the body frame, then rotated into the camera frame. At 200 Hz
    // over a 33 ms frame this is a handful of increments, so a fancier
    // integrator would buy nothing measurable.
    Eigen::Matrix3d accumulated = Eigen::Matrix3d::Identity();

    for (size_t i = 1; i < samples.size(); ++i)
    {
        const double dt =
            samples[i].timestamp - samples[i - 1].timestamp;

        if (dt <= 0.0 || dt > 0.5)
        {
            continue;
        }

        const Eigen::Vector3d rate =
            samples[i].gyroscope - current.gyroBias;

        const Eigen::Vector3d increment = rate * dt;

        const double angle = increment.norm();

        if (angle < 1e-12)
        {
            continue;
        }

        const Eigen::AngleAxisd step(angle, increment / angle);

        accumulated = accumulated * step.toRotationMatrix();
    }

    const Eigen::Matrix3d bodyToCamera = cameraFromBody();

    // Rotation of the camera frame implied by the body rotation.
    const Eigen::Matrix3d inCamera =
        bodyToCamera * accumulated * bodyToCamera.transpose();

    // The estimator wants R_current_previous, and the integrated
    // rotation describes how the body moved from previous to current,
    // so the transform of coordinates is its transpose.
    const Eigen::Matrix3d asCoordinateTransform = inCamera.transpose();

    for (int row = 0; row < 3; ++row)
    {
        for (int col = 0; col < 3; ++col)
        {
            rotation(row, col) = asCoordinateTransform(row, col);
        }
    }

    return true;
}

void StateEstimator::applyMotion(const MotionResult& motion,
                                 double timestamp,
                                 double deltaTime,
                                 bool advanceReference)
{
    if (!motion.success)
    {
        return;
    }

    // motion is X_current = R X_reference + t. The world pose composes
    // with its inverse, onto the REFERENCE pose:
    //   R_wc' = R_wref * R^T
    //   t_wc' = t_wref - R_wc' * t
    //
    // The reference is the KEYFRAME the 3D points were measured in.
    // Composing onto it, rather than onto the previous frame's pose,
    // means each frame's pose is measured afresh against that keyframe
    // and per-frame errors do not integrate. It also keeps a rejected
    // interval's motion instead of losing it, and ignores any gyro
    // propagation applied while vision was lost.
    const Eigen::Matrix3d relativeRotation = fromCv(motion.rotation);

    const Eigen::Vector3d relativeTranslation(
        motion.translation[0],
        motion.translation[1],
        motion.translation[2]
    );

    const Eigen::Vector3d previousPosition = positionInWorld;

    worldFromCamera = referenceRotation * relativeRotation.transpose();
    worldFromCamera = reorthonormalise(worldFromCamera);

    positionInWorld =
        referencePosition - worldFromCamera * relativeTranslation;

    if (advanceReference)
    {
        referenceRotation = worldFromCamera;
        referencePosition = positionInWorld;
    }

    // Velocity is the change since the last ACCEPTED pose over the time
    // since it - not over `deltaTime`, which spans back to the keyframe.
    const double velocityInterval = (initialised && timestamp > lastTimestamp)
        ? timestamp - lastTimestamp
        : deltaTime;

    if (velocityInterval > 1e-6)
    {
        const Eigen::Vector3d instantaneous =
            (positionInWorld - previousPosition) / velocityInterval;

        filteredVelocity = initialised
            ? filteredVelocity * (1.0 - kVelocityAlpha) +
                  instantaneous * kVelocityAlpha
            : instantaneous;
    }

    initialised = true;
    lastTimestamp = timestamp;

    current.timestamp = timestamp;
    current.tracking = true;
    current.inlierFeatures = motion.inliers;
    current.lostFrames = 0;

    updatePublishedPose();
}

void StateEstimator::reanchorReference()
{
    referenceRotation = worldFromCamera;
    referencePosition = positionInWorld;
}

void StateEstimator::applyTrackingLoss(
    const std::vector<IMUSample>& samples,
    double timestamp)
{
    current.tracking = false;
    current.inlierFeatures = 0;
    current.timestamp = timestamp;

    ++current.lostFrames;

    // Velocity decays rather than persisting: reporting the last
    // measured velocity indefinitely while blind would be a lie a
    // consumer could not detect.
    filteredVelocity *= 0.5;

    updatePublishedPose();

    if (!config.imuEnabled || !config.imuPropagateOnLoss)
    {
        return;
    }

    cv::Matx33d gyroDelta;

    if (!gyroRotation(samples, gyroDelta))
    {
        return;
    }

    // Orientation only. Integrating accelerometer data to keep the
    // position moving would diverge within a few seconds on any
    // consumer part, and a position that is silently wrong is worse
    // than one that is visibly stale.
    const Eigen::Matrix3d relative = fromCv(gyroDelta);

    worldFromCamera =
        reorthonormalise(worldFromCamera * relative.transpose());

    updatePublishedPose();

    lastTimestamp = timestamp;
}

void StateEstimator::updateBiases(const std::vector<IMUSample>& samples,
                                  bool visuallyStationary)
{
    if (!config.imuEnabled || samples.empty())
    {
        return;
    }

    if (!visuallyStationary)
    {
        return;
    }

    // Only the gyro bias is estimated. Accelerometer bias is not
    // separable from gravity without observing the platform in several
    // orientations, so it is left at zero rather than being filled
    // with a number that looks like an estimate.
    for (const IMUSample& sample : samples)
    {
        if (sample.gyroscope.norm() > config.imuStaticGyroThreshold * 4.0)
        {
            continue;
        }

        biasAccumulator += sample.gyroscope;
        ++biasSamples;
    }

    if (biasSamples > 100)
    {
        const Eigen::Vector3d estimate =
            biasAccumulator / static_cast<double>(biasSamples);

        current.gyroBias = estimate;

        // Keep the window bounded so the estimate can still follow a
        // slow thermal drift.
        if (biasSamples > 4000)
        {
            biasAccumulator = estimate * 1000.0;
            biasSamples = 1000;
        }
    }
}

} // namespace novex
