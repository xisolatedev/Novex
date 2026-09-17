#pragma once

#include "Profiler.hpp"
#include "VIOConfig.hpp"

#include <opencv2/core.hpp>

#include <cstdint>
#include <vector>

namespace novex
{

// One tracked point, carried across frames.
//
// The 3D member lives here rather than in a separate container so that
// when the tracker compacts its list after dropping failed tracks, the
// depth stays attached to its feature automatically. That removes the
// need for any id-to-index map in the hot loop.
struct Feature
{
    uint64_t id = 0;

    cv::Point2f point;        // position in the current left image
    cv::Point2f previousPoint;

    int age = 0;              // frames survived

    // ---- live stereo measurement (THIS frame) ----
    //
    // Position in the current LEFT CAMERA frame, in metres, measured
    // by stereo on the most recent frame. Valid only while hasDepth is
    // true. The point lies exactly on the ray through `point`: the
    // right eye contributes range along that ray and nothing else (see
    // StereoMatcher::compute for why that matters).
    bool hasDepth = false;
    cv::Point3f position3D;

    // Stereo quality, valid with hasDepth.
    //   disparityPx      parallax angle between the two rays, in
    //                    centre-of-image pixels (the fisheye analogue
    //                    of disparity)
    //   depthSigma       relative range uncertainty for one pixel of
    //                    matching error, i.e. sigma_range / range
    //   stereoResidualPx how far the two rays miss each other, as an
    //                    angle in pixels - the epipolar inconsistency
    float disparityPx = 0.0f;
    float depthSigma = 0.0f;
    float stereoResidualPx = 0.0f;

    // ---- reference measurement used by motion estimation ----
    //
    // Position in the left camera frame of the REFERENCE frame - the
    // last frame whose motion was accepted. Normally that is simply
    // the previous frame, so this equals the previous frame's
    // position3D. When a motion estimate is rejected the reference is
    // deliberately NOT advanced, so the next estimate spans the gap
    // instead of silently losing the rejected interval's motion.
    bool hasReference = false;
    cv::Point3f reference3D;

    // Whether this feature was a RANSAC inlier in the latest accepted
    // motion estimate. Used as a consistency filter for the point map.
    bool motionInlier = false;

    // ---- point map fusion ----
    //
    // Every accepted observation of this track, in the internal world
    // frame, fused by inverse range variance. One physical feature
    // becomes ONE map point that sharpens as it is re-observed, rather
    // than a streak of independent noisy points along its viewing ray.
    float fusedWorld[3] = {0.0f, 0.0f, 0.0f};
    float fusedWeight = 0.0f;

    // Map slot holding this track's point, or -1. Only a hint: the map
    // confirms ownership before using it.
    int32_t mapSlot = -1;
};

// Grid-distributed Shi-Tomasi detection plus pyramidal KLT tracking.
//
// Kept intentionally small. The two things that actually matter for
// odometry quality here are that features are spread across the image
// rather than piled onto one textured object, and that bad tracks are
// removed rather than averaged over.
class FeatureTracker
{
public:

    explicit FeatureTracker(const VIOConfig& config);

    void reset();

    // Follows existing features from `previous` into `current`.
    // Features that fail the forward-backward check, leave the image,
    // or fail the flow solver are removed. Must be called before
    // detect() for a given frame.
    void track(const cv::Mat& previous,
               const cv::Mat& current,
               Profiler& profiler);

    // Adds new features in grid cells that are currently empty, up to
    // the configured maximum. Does nothing if the frame is already
    // well populated.
    void detect(const cv::Mat& image, Profiler& profiler);

    std::vector<Feature>& features() { return active; }
    const std::vector<Feature>& features() const { return active; }

    size_t count() const { return active.size(); }

    // How many features the last track() call discarded, and how many
    // the last detect() call added.
    int lastDropped() const { return dropped; }
    int lastDetected() const { return detected; }

private:

    void buildOccupancyMask(const cv::Size& size);

    const VIOConfig& config;

    std::vector<Feature> active;

    uint64_t nextId = 1;

    // Scratch buffers, allocated once and reused. calcOpticalFlowPyrLK
    // and goodFeaturesToTrack both write into vectors; letting them
    // reallocate every frame is a needless per-frame malloc storm on a
    // 512 MB single-board computer.
    std::vector<cv::Point2f> forwardFrom;
    std::vector<cv::Point2f> forwardTo;
    std::vector<cv::Point2f> backwardTo;
    std::vector<uchar> forwardStatus;
    std::vector<uchar> backwardStatus;
    std::vector<float> forwardError;
    std::vector<float> backwardError;

    std::vector<cv::Point2f> fresh;

    cv::Mat occupancy;

    int dropped = 0;
    int detected = 0;
};

} // namespace novex
