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

    // Position in the LEFT CAMERA frame of the frame in which it was
    // last triangulated, in metres. Valid only while hasDepth is true.
    bool hasDepth = false;
    cv::Point3f position3D;
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
