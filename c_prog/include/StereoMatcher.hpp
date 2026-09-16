#pragma once

#include "FeatureTracker.hpp"
#include "Profiler.hpp"
#include "StereoCalibration.hpp"
#include "VIOConfig.hpp"

#include <opencv2/core.hpp>

#include <vector>

namespace novex
{

// Associates left-image features with the right image and gives them
// metric depth.
//
// The images are never rectified. On a Kannala-Brandt fisheye a
// pinhole rectification cannot represent the full field of view at all
// - the projection diverges towards 90 degrees of incidence - so
// rectifying would mean throwing away the wide periphery this
// calibration was deliberately built around. Instead the raw images
// are matched photometrically, and the lens model is applied to the
// resulting POINTS, where it is exact and cheap.
//
// That gives an honest split:
//   * matching happens in raw pixels, where KLT does not care what
//     lens produced them
//   * geometry happens in normalised camera coordinates, where
//     Kannala-Brandt has already been undone properly
//
// No pinhole stereo equation is ever applied to a distorted
// coordinate.
class StereoMatcher
{
public:

    struct Stats
    {
        int attempted = 0;
        int matched = 0;              // survived left-right-left KLT
        int rejectedEpipolar = 0;
        int rejectedDepth = 0;
        int triangulated = 0;
    };

    StereoMatcher(const VIOConfig& config,
                  const StereoCalibration& calibration);

    // Fills in hasDepth / position3D on every feature. Features that
    // cannot be matched or triangulated are left with hasDepth false;
    // they are still tracked, they just carry no depth this frame.
    void compute(const cv::Mat& left,
                 const cv::Mat& right,
                 std::vector<Feature>& features,
                 Profiler& profiler);

    // Clears all depth, for when stereo is switched off.
    void clearDepth(std::vector<Feature>& features);

    const Stats& stats() const { return lastStats; }

private:

    const VIOConfig& config;
    const StereoCalibration& calibration;

    // Essential matrix in normalised coordinates, E = [T]x R, built
    // once from the calibration.
    cv::Matx33d essential;

    // Projection matrices for triangulation in normalised
    // coordinates: left is [I|0], right is [R|T].
    cv::Matx34d leftProjection;
    cv::Matx34d rightProjection;

    // Scratch, reused every frame.
    std::vector<cv::Point2f> leftPoints;
    std::vector<cv::Point2f> rightPoints;
    std::vector<cv::Point2f> backPoints;
    std::vector<uchar> forwardStatus;
    std::vector<uchar> backwardStatus;
    std::vector<float> forwardError;
    std::vector<float> backwardError;

    std::vector<cv::Point2f> leftNormalised;
    std::vector<cv::Point2f> rightNormalised;
    std::vector<cv::Point2f> seedNormalised;

    std::vector<int> candidateIndex;

    // Left points here are already in normalised camera coordinates,
    // reused from the seeding step; the right ones are still raw
    // pixels awaiting undistortion.
    std::vector<cv::Point2f> candidateLeftNormalised;
    std::vector<cv::Point2f> candidateRight;

    cv::Mat triangulated;

    Stats lastStats;
};

} // namespace novex
