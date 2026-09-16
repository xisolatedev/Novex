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
    bool success = false;

    // Transform from the previous left-camera frame to the current
    // one: X_current = rotation * X_previous + translation. Metres.
    cv::Matx33d rotation = cv::Matx33d::eye();
    cv::Vec3d translation = cv::Vec3d::all(0.0);

    int correspondences = 0;   // features carrying usable depth
    int inliers = 0;           // survivors of RANSAC

    const char* failureReason = nullptr;
};

// Frame-to-frame motion from stereo depth, by PnP with RANSAC.
//
// Each feature contributes a 3D point measured by stereo in the
// PREVIOUS frame and its 2D observation in the CURRENT frame. Solving
// for the pose that reprojects one onto the other gives fully metric
// motion - the scale comes from the calibrated baseline, so there is
// no monocular scale ambiguity to resolve and nothing to initialise.
//
// The 2D observations are undistorted through the fisheye model first,
// so the PnP itself runs on an ideal unit-focal camera. That is what
// lets a standard solver be used without ever applying pinhole
// assumptions to distorted coordinates.
//
// There is deliberately no IMU rotation prior here. Seeding the solver
// with the integrated gyro was tried and removed: cv::solvePnPRansac
// ignores useExtrinsicGuess, verified by handing it a deliberately
// absurd guess and getting a bit-identical answer back from both AP3P
// and ITERATIVE. That is not a defect in OpenCV - RANSAC over minimal
// samples is a global search and has no starting point to improve.
// Keeping the parameter would have been a knob that did nothing.
class MotionEstimator
{
public:

    MotionEstimator(const VIOConfig& config,
                    const StereoCalibration& calibration);

    MotionResult estimate(const std::vector<Feature>& features,
                          double deltaTime,
                          Profiler& profiler);

private:

    const VIOConfig& config;
    const StereoCalibration& calibration;

    std::vector<cv::Point3f> objectPoints;
    std::vector<cv::Point2f> imagePoints;
    std::vector<cv::Point2f> normalisedPoints;
    std::vector<int> inlierIndices;

    cv::Mat rvec;
    cv::Mat tvec;
};

} // namespace novex
