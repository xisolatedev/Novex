#include "FeatureTracker.hpp"

#include "Log.hpp"

#include <opencv2/imgproc.hpp>
#include <opencv2/video/tracking.hpp>

#include <cmath>

namespace novex
{

FeatureTracker::FeatureTracker(const VIOConfig& config)
    : config(config)
{
    active.reserve(static_cast<size_t>(config.maxFeatures) + 32);

    forwardFrom.reserve(active.capacity());
    forwardTo.reserve(active.capacity());
    backwardTo.reserve(active.capacity());
    forwardStatus.reserve(active.capacity());
    backwardStatus.reserve(active.capacity());
    forwardError.reserve(active.capacity());
    backwardError.reserve(active.capacity());
    fresh.reserve(active.capacity());
}

void FeatureTracker::reset()
{
    active.clear();

    dropped = 0;
    detected = 0;
}

void FeatureTracker::track(const cv::Mat& previous,
                           const cv::Mat& current,
                           Profiler& profiler)
{
    dropped = 0;

    if (active.empty() || previous.empty() || current.empty())
    {
        return;
    }

    if (previous.size() != current.size())
    {
        LOG_WARN(
            "tracker: frame size changed between frames; dropping all "
            "tracks"
        );

        reset();
        return;
    }

    ScopedStage timing(profiler, Stage::Track);

    forwardFrom.clear();

    for (const Feature& feature : active)
    {
        forwardFrom.push_back(feature.point);
    }

    const cv::Size window(config.klWindowSize, config.klWindowSize);

    const cv::TermCriteria criteria(
        cv::TermCriteria::COUNT + cv::TermCriteria::EPS,
        20,
        0.03
    );

    cv::calcOpticalFlowPyrLK(
        previous,
        current,
        forwardFrom,
        forwardTo,
        forwardStatus,
        forwardError,
        window,
        config.klPyramidLevels,
        criteria
    );

    // Forward-backward check. Tracking the result back to the previous
    // frame and requiring it to land where it started is the cheapest
    // reliable way to catch the failures KLT reports as successes:
    // features that slid along an edge, or latched onto an occluding
    // boundary. Those produce confident, wrong motion, which is far
    // worse for RANSAC than a missing track.
    cv::calcOpticalFlowPyrLK(
        current,
        previous,
        forwardTo,
        backwardTo,
        backwardStatus,
        backwardError,
        window,
        config.klPyramidLevels,
        criteria
    );

    const float threshold =
        static_cast<float>(config.forwardBackwardThreshold *
                           config.forwardBackwardThreshold);

    // Features too close to the border cannot support a full KLT
    // window on the next frame, and their flow is unreliable now.
    const float border =
        static_cast<float>(config.klWindowSize / 2 + 2);

    const float maxX = static_cast<float>(current.cols) - border;
    const float maxY = static_cast<float>(current.rows) - border;

    size_t kept = 0;

    for (size_t i = 0; i < active.size(); ++i)
    {
        if (!forwardStatus[i] || !backwardStatus[i])
        {
            continue;
        }

        const cv::Point2f& tracked = forwardTo[i];

        if (tracked.x < border || tracked.y < border ||
            tracked.x > maxX   || tracked.y > maxY)
        {
            continue;
        }

        const cv::Point2f drift = backwardTo[i] - forwardFrom[i];

        if (drift.x * drift.x + drift.y * drift.y > threshold)
        {
            continue;
        }

        // Compaction in place: survivors move down over the failures,
        // carrying their id, age and depth with them. No allocation,
        // and no separate bookkeeping to keep in step.
        Feature& destination = active[kept];

        destination = active[i];
        destination.previousPoint = forwardFrom[i];
        destination.point = tracked;
        destination.age += 1;

        ++kept;
    }

    dropped = static_cast<int>(active.size() - kept);

    active.resize(kept);
}

void FeatureTracker::buildOccupancyMask(const cv::Size& size)
{
    if (occupancy.size() != size || occupancy.type() != CV_8UC1)
    {
        occupancy.create(size, CV_8UC1);
    }

    occupancy.setTo(cv::Scalar(255));

    const int radius = static_cast<int>(
        std::lround(config.minFeatureDistance)
    );

    for (const Feature& feature : active)
    {
        cv::circle(
            occupancy,
            feature.point,
            radius,
            cv::Scalar(0),
            cv::FILLED
        );
    }
}

void FeatureTracker::detect(const cv::Mat& image, Profiler& profiler)
{
    detected = 0;

    if (image.empty())
    {
        return;
    }

    const int target = config.maxFeatures;

    const int threshold = static_cast<int>(
        config.redetectRatio * target
    );

    // Redetecting every frame would be wasteful; redetecting only when
    // the count collapses lets coverage rot in one corner of the
    // image. Triggering on a fraction of the target is the compromise.
    if (static_cast<int>(active.size()) >= threshold &&
        !active.empty())
    {
        return;
    }

    ScopedStage timing(profiler, Stage::Detect);

    buildOccupancyMask(image.size());

    const int cols = config.gridCols;
    const int rows = config.gridRows;

    const int perCell = std::max(
        1,
        (target + cols * rows - 1) / (cols * rows)
    );

    // Count how full each cell already is, so detection effort goes
    // only where the image is actually empty.
    std::vector<int> occupancyCount(
        static_cast<size_t>(cols * rows), 0
    );

    const float cellWidth  = static_cast<float>(image.cols) / cols;
    const float cellHeight = static_cast<float>(image.rows) / rows;

    for (const Feature& feature : active)
    {
        const int cx = std::min(
            cols - 1,
            static_cast<int>(feature.point.x / cellWidth)
        );

        const int cy = std::min(
            rows - 1,
            static_cast<int>(feature.point.y / cellHeight)
        );

        ++occupancyCount[static_cast<size_t>(cy * cols + cx)];
    }

    const int border = config.klWindowSize / 2 + 2;

    for (int cy = 0; cy < rows; ++cy)
    {
        for (int cx = 0; cx < cols; ++cx)
        {
            if (static_cast<int>(active.size()) >= target)
            {
                break;
            }

            const size_t cellIndex =
                static_cast<size_t>(cy * cols + cx);

            const int deficit = perCell - occupancyCount[cellIndex];

            if (deficit <= 0)
            {
                continue;
            }

            const int x0 = static_cast<int>(cx * cellWidth);
            const int y0 = static_cast<int>(cy * cellHeight);

            const int x1 = (cx == cols - 1)
                ? image.cols
                : static_cast<int>((cx + 1) * cellWidth);

            const int y1 = (cy == rows - 1)
                ? image.rows
                : static_cast<int>((cy + 1) * cellHeight);

            const cv::Rect cell(x0, y0, x1 - x0, y1 - y0);

            if (cell.width < 8 || cell.height < 8)
            {
                continue;
            }

            // Detecting per cell rather than once over the whole
            // image matters on a fisheye view of a room: a single
            // global quality threshold is set by the most textured
            // object in frame and suppresses everything on the walls,
            // which is exactly where features are needed for rotation.
            fresh.clear();

            cv::goodFeaturesToTrack(
                image(cell),
                fresh,
                deficit,
                config.detectorQuality,
                config.minFeatureDistance,
                occupancy(cell),
                3,
                false
            );

            if (fresh.empty())
            {
                continue;
            }

            cv::cornerSubPix(
                image(cell),
                fresh,
                cv::Size(5, 5),
                cv::Size(-1, -1),
                cv::TermCriteria(
                    cv::TermCriteria::COUNT + cv::TermCriteria::EPS,
                    10,
                    0.03
                )
            );

            for (const cv::Point2f& point : fresh)
            {
                if (static_cast<int>(active.size()) >= target)
                {
                    break;
                }

                const cv::Point2f global(
                    point.x + static_cast<float>(x0),
                    point.y + static_cast<float>(y0)
                );

                if (global.x < border ||
                    global.y < border ||
                    global.x > image.cols - border ||
                    global.y > image.rows - border)
                {
                    continue;
                }

                Feature feature;

                feature.id = nextId++;
                feature.point = global;
                feature.previousPoint = global;
                feature.age = 0;
                feature.hasDepth = false;

                active.push_back(feature);

                // Block this neighbourhood for the remaining cells, so
                // features are not packed against a cell boundary.
                cv::circle(
                    occupancy,
                    global,
                    static_cast<int>(
                        std::lround(config.minFeatureDistance)
                    ),
                    cv::Scalar(0),
                    cv::FILLED
                );

                ++detected;
            }
        }
    }
}

} // namespace novex
