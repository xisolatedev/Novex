#pragma once

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <cstdint>

namespace novex
{

// The estimator's output. Deliberately a plain, fixed-size,
// copyable struct: the IPC server takes a snapshot of it under a
// mutex, and copying ~200 bytes is what keeps a state request from
// ever stalling the processing loop.
struct VIOState
{
    // Camera timestamp of the frame this state was computed from,
    // CLOCK_MONOTONIC seconds. Not the time the state was published.
    double timestamp = 0.0;

    // Pose of the camera in the world frame, where "world" is the
    // first tracked camera pose. X_world = orientation * X_camera +
    // position.
    Eigen::Vector3d position = Eigen::Vector3d::Zero();
    Eigen::Vector3d velocity = Eigen::Vector3d::Zero();

    Eigen::Quaterniond orientation = Eigen::Quaterniond::Identity();

    // Estimated only when the IMU is enabled; left at zero otherwise.
    Eigen::Vector3d accelerationBias = Eigen::Vector3d::Zero();
    Eigen::Vector3d gyroBias = Eigen::Vector3d::Zero();

    bool tracking = false;

    // Features currently being followed between frames.
    int trackedFeatures = 0;

    // Features that survived RANSAC in the last motion estimate.
    int inlierFeatures = 0;

    // Features that carried a stereo depth in the last frame.
    int stereoFeatures = 0;

    bool imuEnabled = false;
    bool imuHealthy = false;

    // Monotonically increasing count of frames the pipeline actually
    // processed, and of frames it dropped to keep up.
    uint64_t frameId = 0;
    uint64_t droppedFrames = 0;

    // Consecutive frames for which motion estimation failed. Non-zero
    // means the pose is being carried forward rather than measured.
    int lostFrames = 0;

    EIGEN_MAKE_ALIGNED_OPERATOR_NEW
};

} // namespace novex
