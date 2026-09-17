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
//   * geometry happens on unit bearing vectors, where Kannala-Brandt
//     has already been undone properly
//
// No pinhole stereo equation is ever applied to a distorted
// coordinate.
class StereoMatcher
{
public:

    // Everything here is a measurement of the most recent compute()
    // call. The distribution figures cover triangulated points only.
    struct Stats
    {
        int attempted = 0;
        int matched = 0;              // survived left-right-left KLT
        int rejectedMatch = 0;        // KLT failed, left the image or
                                      // failed forward-backward
        int rejectedEpipolar = 0;     // rays miss each other
        int rejectedDepth = 0;        // behind a camera, no parallax,
                                      // or outside the depth window
        int triangulated = 0;

        // Parallax between the two rays, in centre-of-image pixels.
        double disparityMedianPx = 0.0;
        double disparityStdPx = 0.0;

        // Depth (z in the left camera), metres.
        double depthMedian = 0.0;
        double depthMin = 0.0;
        double depthMax = 0.0;
        double depthStd = 0.0;

        // How far the left and right rays miss each other, as an angle
        // in pixels. Median over triangulated points.
        double residualMedianPx = 0.0;

        // Signed vertical miss (right-eye ray relative to the left-eye
        // ray, +y is image down), mean over triangulated points. A
        // correct stereo calibration gives zero mean here; a persistent
        // offset is a calibration error that no amount of tuning of
        // this pipeline can remove.
        double verticalOffsetMeanPx = 0.0;
    };

    // Result of intersecting a left ray with a right ray.
    struct RayIntersection
    {
        double range = 0.0;          // along the left ray, metres
        double rightRange = 0.0;     // along the right ray, metres
        cv::Vec3d point;             // range * uL, left camera frame
        cv::Vec3d miss;              // right ray point - left ray point
        double missRadians = 0.0;    // |miss| / range
        double parallaxRadians = 0.0;
    };

    // The point ON THE LEFT RAY closest to the right ray. Pure
    // geometry, used by compute() and exposed so it can be verified in
    // isolation. `uL` and `uR` are unit bearings, both expressed in the
    // LEFT camera orientation; `rightCentre` is the right optical
    // centre in the left frame. Returns false for parallel rays or a
    // point behind either camera.
    static bool intersectOnLeftRay(const cv::Vec3d& uL,
                                   const cv::Vec3d& uR,
                                   const cv::Vec3d& rightCentre,
                                   RayIntersection& out);

    StereoMatcher(const VIOConfig& config,
                  const StereoCalibration& calibration);

    // Fills in hasDepth / position3D and the stereo quality fields on
    // every feature. Features that cannot be matched or triangulated
    // are left with hasDepth false; they are still tracked, they just
    // carry no depth this frame. Reference depths used for motion are
    // not touched.
    void compute(const cv::Mat& left,
                 const cv::Mat& right,
                 std::vector<Feature>& features,
                 Profiler& profiler);

    // Clears all live depth, for when stereo is switched off.
    void clearDepth(std::vector<Feature>& features);

    const Stats& stats() const { return lastStats; }

private:

    const VIOConfig& config;
    const StereoCalibration& calibration;

    // R^T, and the right camera's optical centre in the left frame,
    // -R^T T. Precomputed: every triangulation needs both.
    cv::Matx33d rotationRightToLeft;
    cv::Vec3d rightCentreInLeft;

    // Angle subtended by one pixel at the centre of the left image.
    double radiansPerPixel = 0.0;

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
    std::vector<cv::Point2f> candidateRight;

    std::vector<double> disparityScratch;
    std::vector<double> depthScratch;
    std::vector<double> residualScratch;

    Stats lastStats;
};

} // namespace novex
