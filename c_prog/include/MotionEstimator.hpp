#pragma once

#include "FeatureTracker.hpp"
#include "Profiler.hpp"
#include "StereoCalibration.hpp"
#include "VIOConfig.hpp"

#include <opencv2/core.hpp>

#include <vector>

namespace novex
{

struct MotionResult
{
    // True when the estimate was accepted and may be integrated.
    bool success = false;

    // True when there were enough correspondences to try at all.
    bool attempted = false;

    // Transform from the REFERENCE left-camera frame to the current
    // one: X_current = rotation * X_reference + translation. Metres.
    // The reference is normally the previous frame; see
    // Feature::reference3D.
    cv::Matx33d rotation = cv::Matx33d::eye();
    cv::Vec3d translation = cv::Vec3d::all(0.0);

    int correspondences = 0;   // features carrying a reference depth
    int inliers = 0;           // survivors of RANSAC + refinement

    double inlierRatio = 0.0;

    // Final reprojection error of the inliers through the real fisheye
    // model, in pixels. Measured, not estimated.
    double reprojectionMedianPx = 0.0;
    double reprojectionMaxPx = 0.0;

    // 1-sigma uncertainty of this estimate from the refinement's
    // normal equations and its own residual scatter, worst axis.
    double rotationSigmaDeg = 0.0;
    double translationSigmaMm = 0.0;

    // Smallest / largest eigenvalue of the normal matrix. Tiny means
    // some combination of rotation and translation is barely
    // observable in this scene.
    double conditioning = 0.0;

    const char* failureReason = nullptr;
};

// Frame-to-frame motion from stereo depth, by PnP with RANSAC and a
// robust refinement on bearing angles.
//
// Each feature contributes a 3D point measured by stereo in the
// REFERENCE frame and its 2D observation in the CURRENT frame. Solving
// for the pose that reprojects one onto the other gives fully metric
// motion - the scale comes from the calibrated baseline, so there is
// no monocular scale ambiguity to resolve and nothing to initialise.
//
// Two stages:
//
//  1. cv::solvePnPRansac (AP3P) on undistorted normalised coordinates
//     proposes a pose and rejects gross outliers. Its threshold lives
//     on the normalised image plane, which on a fisheye is NOT uniform
//     (see FisheyeGeometry.hpp), so its inlier set is treated only as
//     a hypothesis.
//
//  2. Inliers are re-selected by ANGULAR residual, uniformly across
//     the lens, and the pose is refined by iteratively reweighted
//     Gauss-Newton with a Huber loss on those angles. The reported
//     residuals, uncertainty and conditioning come from this stage.
//
// There is deliberately no IMU rotation prior here. Seeding the solver
// with the integrated gyro was tried and removed: cv::solvePnPRansac
// ignores useExtrinsicGuess, verified by handing it a deliberately
// absurd guess and getting a bit-identical answer back from both AP3P
// and ITERATIVE. That is not a defect in OpenCV - RANSAC over minimal
// samples is a global search and has no starting point to improve.
class MotionEstimator
{
public:

    MotionEstimator(const VIOConfig& config,
                    const StereoCalibration& calibration);

    // Uses reference3D / point on every feature with hasReference, and
    // writes motionInlier on every feature. `deltaTime` is the time
    // since the reference frame.
    MotionResult estimate(std::vector<Feature>& features,
                          double deltaTime,
                          Profiler& profiler);

private:

    // Robust Gauss-Newton on the given inlier set. Returns false on a
    // numerically singular system. Fills the normal matrix of the
    // final iteration and the weighted residual sum.
    bool refine(double huberRadians,
                double hessian[36],
                double& weightedSquares);

    // Re-selects inliers over every correspondence by angle. Returns
    // the count.
    int classify(double thresholdRadians);

    const VIOConfig& config;
    const StereoCalibration& calibration;

    std::vector<cv::Point3f> objectPoints;
    std::vector<cv::Point2f> imagePoints;
    std::vector<cv::Point2f> normalisedPoints;
    std::vector<int> featureIndex;
    std::vector<int> ransacInliers;

    // Unit observation bearings and the refinement's inlier flags,
    // parallel to objectPoints.
    std::vector<cv::Vec3d> bearings;
    std::vector<unsigned char> inlier;

    std::vector<double> residualScratch;

    // Current pose hypothesis, X_current = R X_reference + t.
    cv::Matx33d rotation = cv::Matx33d::eye();
    cv::Vec3d translation = cv::Vec3d::all(0.0);

    cv::Mat rvec;
    cv::Mat tvec;
};

} // namespace novex
