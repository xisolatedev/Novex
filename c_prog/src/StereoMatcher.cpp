#include "StereoMatcher.hpp"

#include "FisheyeGeometry.hpp"
#include "Log.hpp"

#include <opencv2/calib3d.hpp>
#include <opencv2/video/tracking.hpp>

#include <algorithm>
#include <cmath>

namespace novex
{

namespace
{

// Median by partial sort. Destroys the order of `values`, which are
// scratch anyway.
double medianOf(std::vector<double>& values)
{
    if (values.empty())
    {
        return 0.0;
    }

    const size_t middle = values.size() / 2;

    std::nth_element(values.begin(),
                     values.begin() + static_cast<long>(middle),
                     values.end());

    return values[middle];
}

double standardDeviationOf(const std::vector<double>& values)
{
    if (values.size() < 2)
    {
        return 0.0;
    }

    double sum = 0.0;
    double squares = 0.0;

    for (double value : values)
    {
        sum += value;
        squares += value * value;
    }

    const double n = static_cast<double>(values.size());
    const double mean = sum / n;

    return std::sqrt(std::max(0.0, squares / n - mean * mean));
}

} // namespace

StereoMatcher::StereoMatcher(const VIOConfig& config,
                             const StereoCalibration& calibration)
    : config(config), calibration(calibration)
{
    // Calibration convention: X_right = R X_left + T. So a direction
    // seen by the right camera is R^T times it in the left frame, and
    // the right optical centre (X_right = 0) sits at -R^T T.
    rotationRightToLeft = calibration.rotation().t();
    rightCentreInLeft = -(rotationRightToLeft * calibration.translation());

    const size_t capacity = static_cast<size_t>(config.maxFeatures) + 32;

    leftPoints.reserve(capacity);
    rightPoints.reserve(capacity);
    backPoints.reserve(capacity);
    candidateIndex.reserve(capacity);
    candidateRight.reserve(capacity);
    disparityScratch.reserve(capacity);
    depthScratch.reserve(capacity);
    residualScratch.reserve(capacity);
}

bool StereoMatcher::intersectOnLeftRay(const cv::Vec3d& uL,
                                       const cv::Vec3d& uR,
                                       const cv::Vec3d& C,
                                       RayIntersection& out)
{
    const double a = uL.dot(uR);
    const double denominator = 1.0 - a * a;

    // Parallel rays: no parallax at all, so no range.
    if (denominator < 1e-14)
    {
        return false;
    }

    const double lc = uL.dot(C);
    const double rc = uR.dot(C);

    out.range = (lc - a * rc) / denominator;
    out.rightRange = (a * lc - rc) / denominator;

    // Cheirality for BOTH cameras.
    if (!(out.range > 0.0) || !(out.rightRange > 0.0))
    {
        return false;
    }

    out.point = uL * out.range;
    out.miss = (C + uR * out.rightRange) - out.point;
    out.missRadians = cv::norm(out.miss) / out.range;
    out.parallaxRadians = angleBetweenUnit(uL, uR);

    return true;
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

    // Resolved on first use rather than in the constructor: the
    // calibration is adapted to the camera's negotiated mode after the
    // pipeline objects exist.
    const cv::Matx33d& leftK = calibration.leftK();

    radiansPerPixel = 2.0 / (leftK(0, 0) + leftK(1, 1));

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
        leftK,
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
        candidateRight.push_back(matched);
    }

    lastStats.matched = static_cast<int>(candidateIndex.size());
    lastStats.rejectedMatch = lastStats.attempted - lastStats.matched;

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

    // ---------------------------------------------------------------
    // Triangulation ON THE LEFT RAY
    //
    // This is the fix for the dominant drift source measured on this
    // rig, so the reasoning is recorded in full.
    //
    // The previous implementation used cv::triangulatePoints (linear
    // DLT). DLT returns a compromise point between the two rays: when
    // the rays do not intersect exactly - and with this calibration
    // they miss by a median of several tenths of a pixel, with a
    // SYSTEMATIC vertical component - the returned point does not lie
    // on the left observation ray. Reprojected into the left image it
    // misses the very pixel it was triangulated from.
    //
    // Measured on a 600-frame recording of a stationary camera, the
    // DLT points reprojected a median 0.445 px from their own left
    // observations, with a mean vertical offset of +0.218 px. Motion is
    // estimated by PnP from those 3D points to the next frame's left
    // observations, so every frame PnP "explains" that consistent
    // offset as a small rotation. It re-occurs every frame because the
    // points are re-triangulated every frame, so it integrates: 58.8
    // degrees of rotation and 1.01 m of position drift in 20 s with
    // the camera not moving at all.
    //
    // Keeping the point ON the left ray and taking only its RANGE from
    // the right eye makes the left reprojection exact by construction.
    // On the same recording the drift became 0.57 degrees and 0.016 m.
    // Stereo calibration error now only affects range along the ray -
    // a scale error on translation - and can no longer manufacture
    // rotation.
    //
    // The range is the point on the left ray closest to the right ray:
    // minimise |lambda uL - (C + mu uR)|^2 over lambda, mu, with uL and
    // uR unit bearings in the left frame and C the right optical
    // centre. With a = uL . uR:
    //
    //   lambda = (uL.C - a uR.C) / (1 - a^2)
    //   mu     = (a uL.C - uR.C) / (1 - a^2)
    //
    // Closed form, no SVD, no allocation - cheaper than the DLT it
    // replaces. Everything is an angle, so the thresholds mean the same
    // thing at the centre and at the edge of the fisheye.
    // ---------------------------------------------------------------

    const double epipolarLimit =
        config.stereoEpipolarThresholdPx * radiansPerPixel;

    disparityScratch.clear();
    depthScratch.clear();
    residualScratch.clear();

    double verticalOffsetSum = 0.0;

    for (size_t i = 0; i < candidateIndex.size(); ++i)
    {
        const size_t featureIndex =
            static_cast<size_t>(candidateIndex[i]);

        const cv::Vec3d uL = bearingFromNormalised(
            leftNormalised[featureIndex]
        );

        const cv::Vec3d uR = rotationRightToLeft *
            bearingFromNormalised(rightNormalised[i]);

        RayIntersection ray;

        if (!intersectOnLeftRay(uL, uR, rightCentreInLeft, ray))
        {
            // Parallel rays, or converging behind a lens: far points
            // whose matching error exceeds their true parallax get the
            // disparity sign wrong and land here.
            ++lastStats.rejectedDepth;
            continue;
        }

        // How far apart the rays pass, seen from the left camera. This
        // is the epipolar error as an angle, uniform across the lens.
        if (ray.missRadians > epipolarLimit)
        {
            ++lastStats.rejectedEpipolar;
            continue;
        }

        const cv::Vec3d& onLeft = ray.point;
        const cv::Vec3d& miss = ray.miss;
        const double lambda = ray.range;
        const double residual = ray.missRadians;

        const double depth = onLeft[2];

        // Cheirality plus a depth window. Points beyond the far limit
        // are not wrong so much as unmeasurable: at a 110 mm baseline
        // their disparity is under a pixel, so their range is noise.
        if (!(depth > config.minDepthMeters) ||
            !(depth < config.maxDepthMeters))
        {
            ++lastStats.rejectedDepth;
            continue;
        }

        // Parallax between the rays as seen from the point. For a
        // small angle, range ~ baseline / parallax, so a one-pixel
        // matching error changes range by the fraction
        // (one pixel) / parallax.
        const double parallax = ray.parallaxRadians;

        Feature& feature = features[featureIndex];

        feature.hasDepth = true;
        feature.position3D = cv::Point3f(
            static_cast<float>(onLeft[0]),
            static_cast<float>(onLeft[1]),
            static_cast<float>(onLeft[2])
        );

        feature.disparityPx = static_cast<float>(parallax / radiansPerPixel);
        feature.depthSigma = static_cast<float>(
            radiansPerPixel / std::max(parallax, 1e-9)
        );
        feature.stereoResidualPx =
            static_cast<float>(residual / radiansPerPixel);

        disparityScratch.push_back(feature.disparityPx);
        depthScratch.push_back(depth);
        residualScratch.push_back(feature.stereoResidualPx);

        verticalOffsetSum += (miss[1] / lambda) / radiansPerPixel;

        ++lastStats.triangulated;
    }

    if (lastStats.triangulated == 0)
    {
        return;
    }

    const auto bounds =
        std::minmax_element(depthScratch.begin(), depthScratch.end());

    lastStats.depthMin = *bounds.first;
    lastStats.depthMax = *bounds.second;
    lastStats.depthStd = standardDeviationOf(depthScratch);
    lastStats.disparityStdPx = standardDeviationOf(disparityScratch);

    lastStats.depthMedian = medianOf(depthScratch);
    lastStats.disparityMedianPx = medianOf(disparityScratch);
    lastStats.residualMedianPx = medianOf(residualScratch);

    lastStats.verticalOffsetMeanPx =
        verticalOffsetSum / lastStats.triangulated;
}

} // namespace novex
