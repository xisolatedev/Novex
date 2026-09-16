#include "Gui.hpp"

#include "Log.hpp"

#include <opencv2/highgui.hpp>
#include <opencv2/imgproc.hpp>

#include <cstdio>

namespace novex
{

namespace
{

const char* kWindowName = "Novex VIO";

const cv::Scalar kGreen(80, 220, 80);
const cv::Scalar kAmber(60, 190, 240);
const cv::Scalar kRed(70, 70, 240);
const cv::Scalar kWhite(240, 240, 240);
const cv::Scalar kShadow(20, 20, 20);

void putLabel(cv::Mat& canvas,
              const std::string& text,
              int x,
              int y,
              const cv::Scalar& colour)
{
    // Drawn twice: dark underneath, colour on top. Overlay text on a
    // camera image is unreadable otherwise, since the background is
    // whatever the room happens to be.
    cv::putText(canvas, text, cv::Point(x + 1, y + 1),
                cv::FONT_HERSHEY_SIMPLEX, 0.42, kShadow, 2,
                cv::LINE_AA);

    cv::putText(canvas, text, cv::Point(x, y),
                cv::FONT_HERSHEY_SIMPLEX, 0.42, colour, 1,
                cv::LINE_AA);
}

} // namespace

Gui::Gui(const VIOConfig& config)
    : config(config)
{
}

Gui::~Gui()
{
    close();
}

bool Gui::open()
{
    if (!config.guiEnabled)
    {
        return false;
    }

    try
    {
        cv::namedWindow(kWindowName, cv::WINDOW_AUTOSIZE);
        windowOpen = true;
    }
    catch (const cv::Exception& error)
    {
        // OpenCV built without a GUI backend, or no display available.
        // Neither is fatal: the estimator does not need a window.
        LOG_ERROR(
            "gui: cannot create a window (%s). Running without "
            "display; use --mode daemon to suppress this.",
            error.what()
        );

        available = false;
        windowOpen = false;
    }

    return windowOpen;
}

void Gui::close()
{
    if (windowOpen)
    {
        try
        {
            cv::destroyWindow(kWindowName);
        }
        catch (const cv::Exception&)
        {
            // Nothing useful to do while shutting down.
        }

        windowOpen = false;
    }
}

bool Gui::draw(const Camera& camera, const VIO& vio)
{
    if (!windowOpen || !available)
    {
        return true;
    }

    const cv::Mat& left = camera.getLeftImage();
    const cv::Mat& right = camera.getRightImage();

    if (left.empty())
    {
        return true;
    }

    const bool showRight = config.guiShowRight && !right.empty();

    const int width = showRight ? left.cols * 2 : left.cols;

    if (canvas.rows != left.rows ||
        canvas.cols != width ||
        canvas.type() != CV_8UC3)
    {
        canvas.create(left.rows, width, CV_8UC3);
    }

    cv::Mat leftPane = canvas(cv::Rect(0, 0, left.cols, left.rows));

    cv::cvtColor(left, leftPane, cv::COLOR_GRAY2BGR);

    if (showRight)
    {
        cv::Mat rightPane =
            canvas(cv::Rect(left.cols, 0, right.cols, right.rows));

        cv::cvtColor(right, rightPane, cv::COLOR_GRAY2BGR);

        cv::line(canvas,
                 cv::Point(left.cols, 0),
                 cv::Point(left.cols, left.rows),
                 kShadow, 1);
    }

    if (config.guiShowFeatures)
    {
        for (const Feature& feature : vio.features())
        {
            // Green means the feature currently carries stereo depth
            // and will contribute to the next motion estimate; amber
            // means it is tracked but has no depth.
            const cv::Scalar colour = feature.hasDepth ? kGreen : kAmber;

            cv::circle(leftPane, feature.point, 2, colour, cv::FILLED,
                       cv::LINE_AA);

            if (feature.age > 0)
            {
                cv::line(leftPane,
                         feature.previousPoint,
                         feature.point,
                         colour, 1, cv::LINE_AA);
            }
        }
    }

    drawOverlay(canvas, camera, vio.snapshot());

    cv::imshow(kWindowName, canvas);

    const int key = cv::waitKey(1);

    return !(key == 27 || key == 'q');
}

void Gui::drawOverlay(cv::Mat& target,
                      const Camera& camera,
                      const VIOSnapshot& snapshot)
{
    const VIOState& state = snapshot.state;

    char line[256];

    int y = 18;

    const int step = 16;

    snprintf(line, sizeof(line),
             "capture %.1f fps   processing %.1f fps   latency %.1f ms",
             snapshot.captureFPS,
             snapshot.processingFPS,
             snapshot.latencySeconds * 1e3);

    putLabel(target, line, 8, y, kWhite);
    y += step;

    snprintf(line, sizeof(line),
             "cam %dx%d %s   dropped %llu",
             camera.getWidth(), camera.getHeight(),
             camera.status().fourcc.c_str(),
             static_cast<unsigned long long>(state.droppedFrames));

    putLabel(target, line, 8, y, kWhite);
    y += step;

    putLabel(target,
             state.tracking ? "TRACKING" : "TRACKING LOST",
             8, y,
             state.tracking ? kGreen : kRed);

    y += step;

    snprintf(line, sizeof(line),
             "features %d   inliers %d   stereo %d/%d",
             state.trackedFeatures,
             state.inlierFeatures,
             snapshot.stereoTriangulated,
             snapshot.stereoMatched);

    putLabel(target, line, 8, y, kWhite);
    y += step;

    snprintf(line, sizeof(line),
             "pos  % .3f % .3f % .3f m",
             state.position.x(), state.position.y(), state.position.z());

    putLabel(target, line, 8, y, kWhite);
    y += step;

    snprintf(line, sizeof(line),
             "vel  % .3f % .3f % .3f m/s",
             state.velocity.x(), state.velocity.y(), state.velocity.z());

    putLabel(target, line, 8, y, kWhite);
    y += step;

    snprintf(line, sizeof(line),
             "quat % .3f % .3f % .3f % .3f",
             state.orientation.x(), state.orientation.y(),
             state.orientation.z(), state.orientation.w());

    putLabel(target, line, 8, y, kWhite);
    y += step;

    if (state.imuEnabled)
    {
        snprintf(line, sizeof(line),
                 "IMU %s   %.0f Hz   bias % .4f % .4f % .4f",
                 snapshot.imuRunning ? "running" : "stalled",
                 snapshot.imuRateHz,
                 state.gyroBias.x(), state.gyroBias.y(),
                 state.gyroBias.z());

        putLabel(target, line, 8, y,
                 snapshot.imuRunning ? kGreen : kRed);
    }
    else
    {
        putLabel(target, "IMU disabled - stereo visual odometry",
                 8, y, kAmber);
    }

    y += step;

    const double* stage = snapshot.stageMilliseconds;

    snprintf(line, sizeof(line),
             "ms  cap %.1f  dec %.1f  pre %.1f  det %.1f  trk %.1f  "
             "ste %.1f  mot %.1f  imu %.1f  tot %.1f",
             stage[static_cast<int>(Stage::Capture)],
             stage[static_cast<int>(Stage::Decode)],
             stage[static_cast<int>(Stage::Preprocess)],
             stage[static_cast<int>(Stage::Detect)],
             stage[static_cast<int>(Stage::Track)],
             stage[static_cast<int>(Stage::Stereo)],
             stage[static_cast<int>(Stage::Motion)],
             stage[static_cast<int>(Stage::Imu)],
             stage[static_cast<int>(Stage::Total)]);

    putLabel(target, line, 8, y, kWhite);

    putLabel(target, "esc or q to quit", 8, target.rows - 10, kWhite);
}

} // namespace novex
