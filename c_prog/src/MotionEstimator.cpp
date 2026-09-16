#include "MotionEstimator.hpp"

#include "Log.hpp"

#include <opencv2/calib3d.hpp>

#include <cmath>

namespace novex
{

namespace
{

// Motion limits used only to reject a solution that is physically
// impossible for a handheld or vehicle-mounted camera over one frame
// interval. These catch the degenerate PnP solutions that occasionally
// survive RANSAC on a nearly planar scene, which would otherwise be
// integrated into the pose and never recovered from.
constexpr double kMaxSpeed = 15.0;              // metres per second
constexpr double kMaxAngularRate = 12.0;        // radians per second

} // namespace

MotionEstimator::MotionEstimator(const VIOConfig& config,
                                 const StereoCalibration& calibration)
    : config(config), calibration(calibration)
{
    objectPoints.reserve(static_cast<size_t>(config.maxFeatures));
    imagePoints.reserve(static_cast<size_t>(config.maxFeatures));
    normalisedPoints.reserve(static_cast<size_t>(config.maxFeatures));
    inlierIndices.reserve(static_cast<size_t>(config.maxFeatures));

    rvec = cv::Mat::zeros(3, 1, CV_64F);
    tvec = cv::Mat::zeros(3, 1, CV_64F);
}

MotionResult MotionEstimator::estimate(
    const std::vector<Feature>& features,
    double deltaTime,
    Profiler& profiler)
{
    MotionResult result;

    objectPoints.clear();
    imagePoints.clear();

    for (const Feature& feature : features)
    {
        // hasDepth was set by the stereo stage on the PREVIOUS frame,
        // so position3D is expressed in the previous left camera's
        // coordinates, while point is the observation in the current
        // image. That is exactly the pairing PnP needs.
        if (!feature.hasDepth)
        {
            continue;
        }

        objectPoints.push_back(feature.position3D);
        imagePoints.push_back(feature.point);
    }

    result.correspondences = static_cast<int>(objectPoints.size());

    // AP3P needs four points for a minimal solution; asking RANSAC to
    // work with barely more than that produces poses that are
    // technically consistent and practically meaningless.
    if (result.correspondences < std::max(6, config.minInliersForTracking))
    {
        result.failureReason = "too few features with depth";
        return result;
    }

    ScopedStage timing(profiler, Stage::Motion);

    cv::fisheye::undistortPoints(
        imagePoints,
        normalisedPoints,
        calibration.leftK(),
        calibration.leftDistortion()
    );

    // With the distortion already removed, the PnP camera is an ideal
    // unit-focal pinhole. The RANSAC threshold is therefore in
    // normalised units, which conveniently makes it resolution
    // independent.
    const cv::Matx33d identityIntrinsics = cv::Matx33d::eye();
    const cv::Vec4d noDistortion = cv::Vec4d::all(0.0);

    inlierIndices.clear();

    bool solved = false;

    try
    {
        solved = cv::solvePnPRansac(
            objectPoints,
            normalisedPoints,
            identityIntrinsics,
            noDistortion,
            rvec,
            tvec,
            false,
            config.ransacIterations,
            static_cast<float>(config.ransacReprojectionError),
            config.ransacConfidence,
            inlierIndices,
            cv::SOLVEPNP_AP3P
        );
    }
    catch (const cv::Exception& error)
    {
        LOG_WARN("motion: solvePnPRansac threw: %s", error.what());
        result.failureReason = "solver error";
        return result;
    }

    result.inliers = static_cast<int>(inlierIndices.size());

    if (!solved || result.inliers < config.minInliersForTracking)
    {
        result.failureReason = "not enough inliers";
        return result;
    }

    // Refine on the inlier set only. RANSAC returns the minimal-sample
    // pose; a least-squares fit over every inlier is what actually
    // makes the estimate accurate, and it costs very little.
    std::vector<cv::Point3f> inlierObject;
    std::vector<cv::Point2f> inlierImage;

    inlierObject.reserve(inlierIndices.size());
    inlierImage.reserve(inlierIndices.size());

    for (int index : inlierIndices)
    {
        inlierObject.push_back(objectPoints[static_cast<size_t>(index)]);
        inlierImage.push_back(normalisedPoints[static_cast<size_t>(index)]);
    }

    try
    {
        cv::solvePnPRefineLM(
            inlierObject,
            inlierImage,
            identityIntrinsics,
            noDistortion,
            rvec,
            tvec
        );
    }
    catch (const cv::Exception& error)
    {
        LOG_WARN("motion: refinement threw: %s", error.what());
        // The unrefined RANSAC pose is still usable.
    }

    cv::Mat rotationMatrix;

    cv::Rodrigues(rvec, rotationMatrix);

    for (int row = 0; row < 3; ++row)
    {
        for (int col = 0; col < 3; ++col)
        {
            result.rotation(row, col) =
                rotationMatrix.at<double>(row, col);
        }

        result.translation[row] = tvec.at<double>(row);
    }

    for (int i = 0; i < 3; ++i)
    {
        if (!std::isfinite(result.translation[i]))
        {
            result.failureReason = "non-finite solution";
            return result;
        }
    }

    if (deltaTime > 1e-6)
    {
        const double speed = cv::norm(result.translation) / deltaTime;

        const double angle = std::acos(
            std::max(-1.0, std::min(1.0,
                (cv::trace(result.rotation) - 1.0) * 0.5))
        );

        const double angularRate = angle / deltaTime;

        if (speed > kMaxSpeed || angularRate > kMaxAngularRate)
        {
            LOG_DEBUG(
                "motion: rejecting implausible solution "
                "(%.1f m/s, %.1f rad/s over %.4f s)",
                speed, angularRate, deltaTime
            );

            result.failureReason = "implausible motion";
            return result;
        }
    }

    result.success = true;

    return result;
}

} // namespace novex
