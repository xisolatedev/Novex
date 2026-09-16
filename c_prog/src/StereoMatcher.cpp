#include "StereoMatcher.hpp"

#include "Log.hpp"

#include <opencv2/calib3d.hpp>
#include <opencv2/video/tracking.hpp>

#include <cmath>

namespace novex
{

StereoMatcher::StereoMatcher(const VIOConfig& config,
                             const StereoCalibration& calibration)
    : config(config), calibration(calibration)
{
    const cv::Matx33d& R = calibration.rotation();
    const cv::Vec3d&   T = calibration.translation();

    // E = [T]x R, with the calibration's convention X_right = R
    // X_left + T. Used only to reject matches that are geometrically
    // impossible, before spending anything on triangulation.
    const cv::Matx33d skew(
             0.0, -T[2],  T[1],
            T[2],   0.0, -T[0],
           -T[1],  T[0],   0.0
    );

    essential = skew * R;

    leftProjection = cv::Matx34d(
        1.0, 0.0, 0.0, 0.0,
        0.0, 1.0, 0.0, 0.0,
        0.0, 0.0, 1.0, 0.0
    );

    rightProjection = cv::Matx34d(
        R(0, 0), R(0, 1), R(0, 2), T[0],
        R(1, 0), R(1, 1), R(1, 2), T[1],
        R(2, 0), R(2, 1), R(2, 2), T[2]
    );

    leftPoints.reserve(static_cast<size_t>(config.maxFeatures));
    rightPoints.reserve(static_cast<size_t>(config.maxFeatures));
    backPoints.reserve(static_cast<size_t>(config.maxFeatures));
    candidateIndex.reserve(static_cast<size_t>(config.maxFeatures));
    candidateLeftNormalised.reserve(static_cast<size_t>(config.maxFeatures));
    candidateRight.reserve(static_cast<size_t>(config.maxFeatures));
}

void StereoMatcher::clearDepth(std::vector<Feature>& features)
{
    for (Feature& feature : features)
    {
        feature.hasDepth = false;
    }
}

void StereoMatcher::compute(const cv::Mat& left,
                            const cv::Mat& right,
                            std::vector<Feature>& features,
                            Profiler& profiler)
{
    lastStats = Stats();

    clearDepth(features);

    if (features.empty() || left.empty() || right.empty())
    {
        return;
    }

    if (left.size() != right.size())
    {
        LOG_WARN("stereo: eye images differ in size; skipping");
        return;
    }

    ScopedStage timing(profiler, Stage::Stereo);

    lastStats.attempted = static_cast<int>(features.size());

    leftPoints.clear();

    for (const Feature& feature : features)
    {
        leftPoints.push_back(feature.point);
    }

    // Seed the search with where each feature WOULD land in the right
    // image if it were infinitely far away.
    //
    // This matters more than it looks. The two lenses have noticeably
    // different principal points - cx 305.8 against 334.1, cy 247.0
    // against 227.2 at 640x480 - so the same ray lands roughly 28 px
    // apart horizontally and 20 px apart vertically in raw pixels
    // before any disparity is involved. Starting KLT at the identity
    // asks it to cross that gap plus the disparity with a 21 px
    // window, and measured on this camera it failed the
    // forward-backward check on 72% of features for that reason
    // alone.
    //
    // Unprojecting through the left lens, rotating by the calibrated
    // R, and reprojecting through the right lens removes all of it -
    // the lens difference, the principal point offset and the small
    // stereo rotation - and leaves only the disparity itself, which is
    // what the search is actually for.
    cv::fisheye::undistortPoints(
        leftPoints,
        leftNormalised,
        calibration.leftK(),
        calibration.leftDistortion()
    );

    const cv::Matx33d& R = calibration.rotation();

    seedNormalised.clear();

    for (const cv::Point2f& point : leftNormalised)
    {
        const cv::Vec3d bearing =
            R * cv::Vec3d(point.x, point.y, 1.0);

        if (bearing[2] > 1e-6)
        {
            seedNormalised.push_back(cv::Point2f(
                static_cast<float>(bearing[0] / bearing[2]),
                static_cast<float>(bearing[1] / bearing[2])
            ));
        }
        else
        {
            // Behind the right camera's principal axis; no sensible
            // seed exists, so fall back to the raw position.
            seedNormalised.push_back(point);
        }
    }

    // Written straight into rightPoints, which calcOpticalFlowPyrLK
    // then uses as its starting guess and overwrites with the result.
    cv::fisheye::distortPoints(
        seedNormalised,
        rightPoints,
        calibration.rightK(),
        calibration.rightDistortion()
    );

    const cv::Size window(config.klWindowSize, config.klWindowSize);

    const cv::TermCriteria criteria(
        cv::TermCriteria::COUNT + cv::TermCriteria::EPS,
        20,
        0.03
    );

    cv::calcOpticalFlowPyrLK(
        left,
        right,
        leftPoints,
        rightPoints,
        forwardStatus,
        forwardError,
        window,
        config.klPyramidLevels,
        criteria,
        cv::OPTFLOW_USE_INITIAL_FLOW
    );

    // Same left-right-left consistency requirement as the temporal
    // tracker. Repetitive texture is the normal case indoors, and a
    // one-way match on a repeating pattern is confidently wrong.
    cv::calcOpticalFlowPyrLK(
        right,
        left,
        rightPoints,
        backPoints,
        backwardStatus,
        backwardError,
        window,
        config.klPyramidLevels,
        criteria
    );

    const float fbThreshold =
        static_cast<float>(config.stereoForwardBackwardThreshold *
                           config.stereoForwardBackwardThreshold);

    candidateIndex.clear();
    candidateLeftNormalised.clear();
    candidateRight.clear();

    for (size_t i = 0; i < features.size(); ++i)
    {
        if (!forwardStatus[i] || !backwardStatus[i])
        {
            continue;
        }

        const cv::Point2f& matched = rightPoints[i];

        if (matched.x < 0.0f || matched.y < 0.0f ||
            matched.x >= right.cols || matched.y >= right.rows)
        {
            continue;
        }

        const cv::Point2f drift = backPoints[i] - leftPoints[i];

        if (drift.x * drift.x + drift.y * drift.y > fbThreshold)
        {
            continue;
        }

        candidateIndex.push_back(static_cast<int>(i));
        candidateLeftNormalised.push_back(leftNormalised[i]);
        candidateRight.push_back(matched);
    }

    lastStats.matched = static_cast<int>(candidateIndex.size());

    if (candidateIndex.empty())
    {
        return;
    }

    // The left points were already undistorted to build the seed, so
    // only the matched right points remain. This is where the fisheye
    // model is applied - to coordinates, exactly, rather than by
    // resampling the whole image and losing the periphery.
    cv::fisheye::undistortPoints(
        candidateRight,
        rightNormalised,
        calibration.rightK(),
        calibration.rightDistortion()
    );

    // Epipolar rejection using the Sampson distance, in normalised
    // camera units. Everything from here on is ordinary two-view
    // geometry on bearing vectors, with no lens distortion left in it.
    std::vector<int> surviving;
    surviving.reserve(candidateIndex.size());

    std::vector<cv::Point2f> keptLeft;
    std::vector<cv::Point2f> keptRight;

    keptLeft.reserve(candidateIndex.size());
    keptRight.reserve(candidateIndex.size());

    const double epipolarThreshold =
        config.stereoEpipolarThreshold * config.stereoEpipolarThreshold;

    for (size_t i = 0; i < candidateIndex.size(); ++i)
    {
        const cv::Vec3d xLeft(
            candidateLeftNormalised[i].x, candidateLeftNormalised[i].y, 1.0
        );

        const cv::Vec3d xRight(
            rightNormalised[i].x, rightNormalised[i].y, 1.0
        );

        const cv::Vec3d line  = essential * xLeft;
        const cv::Vec3d line2 = essential.t() * xRight;

        const double numerator = xRight.dot(line);

        const double denominator =
            line[0]  * line[0]  + line[1]  * line[1] +
            line2[0] * line2[0] + line2[1] * line2[1];

        if (denominator < 1e-12)
        {
            ++lastStats.rejectedEpipolar;
            continue;
        }

        if ((numerator * numerator) / denominator > epipolarThreshold)
        {
            ++lastStats.rejectedEpipolar;
            continue;
        }

        surviving.push_back(candidateIndex[i]);
        keptLeft.push_back(candidateLeftNormalised[i]);
        keptRight.push_back(rightNormalised[i]);
    }

    if (surviving.empty())
    {
        return;
    }

    cv::triangulatePoints(
        leftProjection,
        rightProjection,
        keptLeft,
        keptRight,
        triangulated
    );

    for (int i = 0; i < triangulated.cols; ++i)
    {
        const float w = triangulated.at<float>(3, i);

        if (std::abs(w) < 1e-9f)
        {
            ++lastStats.rejectedDepth;
            continue;
        }

        const cv::Point3f point(
            triangulated.at<float>(0, i) / w,
            triangulated.at<float>(1, i) / w,
            triangulated.at<float>(2, i) / w
        );

        // Cheirality plus a depth window. Points beyond the far limit
        // are not wrong so much as unmeasurable: at a 110 mm baseline
        // their disparity is under a pixel, so their depth is noise
        // and they would drag the motion estimate around.
        if (!(point.z > config.minDepthMeters) ||
            !(point.z < config.maxDepthMeters))
        {
            ++lastStats.rejectedDepth;
            continue;
        }

        // Must also be in front of the right camera.
        const cv::Vec3d inRight =
            calibration.rotation() *
                cv::Vec3d(point.x, point.y, point.z) +
            calibration.translation();

        if (inRight[2] <= 0.0)
        {
            ++lastStats.rejectedDepth;
            continue;
        }

        Feature& feature =
            features[static_cast<size_t>(surviving[static_cast<size_t>(i)])];

        feature.hasDepth = true;
        feature.position3D = point;

        ++lastStats.triangulated;
    }
}

} // namespace novex
