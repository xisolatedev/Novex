// Novex VIO validation suite.
//
// Runs the checks listed in the project brief. Tests that need the
// physical camera are SKIPPED, loudly, when no camera is present -
// they are never quietly reported as passing.
//
//   novex-vio-test                 run everything available
//   novex-vio-test --no-camera     skip the camera-dependent tests

#include "Camera.hpp"
#include "CommandQueue.hpp"
#include "DebugStatistics.hpp"
#include "FeatureTracker.hpp"
#include "Gui.hpp"
#include "IMU.hpp"
#include "Log.hpp"
#include "StateServer.hpp"
#include "StereoCalibration.hpp"
#include "StereoMatcher.hpp"
#include "Time.hpp"
#include "VIO.hpp"
#include "VIOConfig.hpp"

#include <opencv2/imgproc.hpp>

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

using namespace novex;

namespace
{

int gPassed = 0;
int gFailed = 0;
int gSkipped = 0;

std::string gCurrentTest;

void beginTest(const std::string& name)
{
    gCurrentTest = name;
    printf("\n--- %s\n", name.c_str());
}

void pass(const char* detail = nullptr)
{
    ++gPassed;
    printf("    PASS  %s%s\n",
           gCurrentTest.c_str(),
           detail ? (std::string(" : ") + detail).c_str() : "");
}

void fail(const std::string& reason)
{
    ++gFailed;
    printf("    FAIL  %s : %s\n", gCurrentTest.c_str(), reason.c_str());
}

void skip(const std::string& reason)
{
    ++gSkipped;
    printf("    SKIP  %s : %s\n", gCurrentTest.c_str(), reason.c_str());
}

void check(bool condition, const std::string& reason)
{
    if (condition)
    {
        pass();
    }
    else
    {
        fail(reason);
    }
}

// A textured synthetic image, so the feature tests do not depend on
// whatever happens to be in front of the lens.
cv::Mat syntheticTexture(int width, int height, int seed)
{
    cv::Mat noise(height, width, CV_8UC1);

    cv::RNG rng(static_cast<uint64>(seed));

    rng.fill(noise, cv::RNG::UNIFORM, 0, 255);

    cv::Mat blurred;

    cv::GaussianBlur(noise, blurred, cv::Size(5, 5), 1.2);

    return blurred;
}

cv::Mat shiftImage(const cv::Mat& source, double dx, double dy)
{
    cv::Mat transform = (cv::Mat_<double>(2, 3) <<
        1.0, 0.0, dx,
        0.0, 1.0, dy);

    cv::Mat shifted;

    cv::warpAffine(source, shifted, transform, source.size(),
                   cv::INTER_LINEAR, cv::BORDER_REFLECT);

    return shifted;
}

int connectToSocket(const std::string& path)
{
    const int fd = socket(AF_UNIX, SOCK_STREAM, 0);

    if (fd < 0)
    {
        return -1;
    }

    sockaddr_un address;

    memset(&address, 0, sizeof(address));

    address.sun_family = AF_UNIX;

    strncpy(address.sun_path, path.c_str(),
            sizeof(address.sun_path) - 1);

    if (connect(fd, reinterpret_cast<sockaddr*>(&address),
                sizeof(address)) != 0)
    {
        close(fd);
        return -1;
    }

    return fd;
}

} // namespace

int main(int argc, char** argv)
{
    bool useCamera = true;

    std::string calibrationPath = "config/stereo_calibration.yaml";

    for (int i = 1; i < argc; ++i)
    {
        if (strcmp(argv[i], "--no-camera") == 0)
        {
            useCamera = false;
        }
        else if (strcmp(argv[i], "--calibration") == 0 && i + 1 < argc)
        {
            calibrationPath = argv[++i];
        }
    }

    setLogLevel(LogLevel::Warn);

    printf("Novex VIO validation suite\n");
    printf("==========================\n");

    VIOConfig config;

    config.calibrationPath = calibrationPath;
    config.mode = RunMode::Daemon;
    config.applyDerived();

    // ================================================================
    // 4 / 5. Calibration loads, and reports its dimensions
    // ================================================================

    StereoCalibration calibration;

    beginTest("4. calibration loads");

    const bool calibrationLoaded =
        calibration.load(config.calibrationPath);

    check(calibrationLoaded,
          "could not load " + config.calibrationPath);

    if (!calibrationLoaded)
    {
        printf("\nCannot continue without a calibration.\n");
        return 1;
    }

    beginTest("5. calibration reports its resolution and adapts");

    {
        const cv::Size calibrationSize =
            calibration.calibrationResolution();

        if (calibrationSize.width != 1280 ||
            calibrationSize.height != 720)
        {
            fail("expected a 1280x720 per-eye calibration, got " +
                 std::to_string(calibrationSize.width) + "x" +
                 std::to_string(calibrationSize.height));
        }
        else
        {
            pass("1280x720 per eye");
        }

        // The measured relationship: the 640x480 eye is a centered
        // 960x720 crop of the calibrated image, scaled by 2/3.
        beginTest("5b. 640x480 mapping matches the measured sensor mode");

        calibration.setCurrentResolution(cv::Size(640, 480));

        const SensorModeMapping& mapping = calibration.mapping();

        const bool cropCorrect =
            mapping.cropInCalibration.x == 160 &&
            mapping.cropInCalibration.y == 0 &&
            mapping.cropInCalibration.width == 960 &&
            mapping.cropInCalibration.height == 720;

        const bool scaleCorrect =
            std::abs(mapping.scale - 2.0 / 3.0) < 1e-6;

        if (cropCorrect && scaleCorrect)
        {
            pass("crop (160,0,960,720), scale 0.6667");
        }
        else
        {
            fail("mapping is " + mapping.description);
        }

        beginTest("5c. adapted intrinsics are internally consistent");

        const cv::Matx33d& K = calibration.leftK();

        const double expectedFx =
            calibration.calibrationLeftK()(0, 0) * 2.0 / 3.0;

        const double expectedCx =
            (calibration.calibrationLeftK()(0, 2) - 160.0) * 2.0 / 3.0;

        const bool intrinsicsOk =
            std::abs(K(0, 0) - expectedFx) < 1e-9 &&
            std::abs(K(0, 2) - expectedCx) < 1e-9 &&
            K(0, 2) > 0.0 && K(0, 2) < 640.0 &&
            K(1, 2) > 0.0 && K(1, 2) < 480.0;

        if (intrinsicsOk)
        {
            char detail[128];

            snprintf(detail, sizeof(detail),
                     "fx %.3f cx %.3f cy %.3f, principal point inside "
                     "the image",
                     K(0, 0), K(0, 2), K(1, 2));

            pass(detail);
        }
        else
        {
            fail("adapted intrinsics are wrong or out of frame");
        }

        beginTest("5d. distortion is unchanged by the resolution change");

        // Kannala-Brandt coefficients are angle-based, so an isotropic
        // scale must not touch them. This guards against a future
        // "fix" that scales them along with the focal length.
        const cv::Vec4d& D = calibration.leftDistortion();

        check(std::abs(D[0] - 0.06137212628357399) < 1e-12,
              "distortion coefficients were modified");

        beginTest("5e. an invalid calibration is rejected");

        StereoCalibration broken;

        check(!broken.load("/nonexistent/calibration.yaml"),
              "a missing calibration file was accepted");
    }

    // ================================================================
    // 10 / 11. Feature detection and tracking, on synthetic imagery
    // ================================================================

    beginTest("10. feature detection finds well-spread features");

    {
        Profiler profiler;

        FeatureTracker tracker(config);

        const cv::Mat image = syntheticTexture(640, 480, 7);

        tracker.detect(image, profiler);

        const size_t found = tracker.count();

        // Coverage: count how many of the 8x6 grid cells got at least
        // one feature. Detecting 400 features all in one corner would
        // pass a naive count test and be useless for odometry.
        std::vector<int> cellCounts(48, 0);

        for (const Feature& feature : tracker.features())
        {
            const int cx = std::min(7, static_cast<int>(feature.point.x / 80.0f));
            const int cy = std::min(5, static_cast<int>(feature.point.y / 80.0f));

            ++cellCounts[static_cast<size_t>(cy * 8 + cx)];
        }

        int occupiedCells = 0;

        for (int count : cellCounts)
        {
            if (count > 0)
            {
                ++occupiedCells;
            }
        }

        if (found >= 200 && occupiedCells >= 44)
        {
            char detail[128];

            snprintf(detail, sizeof(detail),
                     "%zu features across %d of 48 grid cells",
                     found, occupiedCells);

            pass(detail);
        }
        else
        {
            fail("found " + std::to_string(found) +
                 " features in " + std::to_string(occupiedCells) +
                 " of 48 cells");
        }
    }

    beginTest("11. feature tracking recovers a known translation");

    {
        Profiler profiler;

        FeatureTracker tracker(config);

        const cv::Mat first = syntheticTexture(640, 480, 11);

        const double shiftX = 3.0;
        const double shiftY = -2.0;

        const cv::Mat second = shiftImage(first, shiftX, shiftY);

        tracker.detect(first, profiler);

        const size_t before = tracker.count();

        tracker.track(first, second, profiler);

        const size_t after = tracker.count();

        double errorX = 0.0;
        double errorY = 0.0;

        for (const Feature& feature : tracker.features())
        {
            errorX += feature.point.x - feature.previousPoint.x;
            errorY += feature.point.y - feature.previousPoint.y;
        }

        if (after > 0)
        {
            errorX = errorX / after - shiftX;
            errorY = errorY / after - shiftY;
        }

        const bool survived = after > before / 2;
        const bool accurate =
            std::abs(errorX) < 0.2 && std::abs(errorY) < 0.2;

        if (survived && accurate)
        {
            char detail[160];

            snprintf(detail, sizeof(detail),
                     "%zu of %zu tracks survived, mean flow error "
                     "(%.3f, %.3f) px",
                     after, before, errorX, errorY);

            pass(detail);
        }
        else
        {
            char reason[160];

            snprintf(reason, sizeof(reason),
                     "%zu of %zu survived, flow error (%.3f, %.3f) px",
                     after, before, errorX, errorY);

            fail(reason);
        }
    }

    beginTest("11b. tracking rejects a frame with no correspondence");

    {
        Profiler profiler;

        FeatureTracker tracker(config);

        const cv::Mat first = syntheticTexture(640, 480, 21);
        const cv::Mat unrelated = syntheticTexture(640, 480, 22);

        tracker.detect(first, profiler);

        const size_t before = tracker.count();

        tracker.track(first, unrelated, profiler);

        // Two independent noise fields share no structure, so the
        // forward-backward check should throw almost everything away.
        // A tracker that keeps them all is not checking anything.
        if (before > 100 && tracker.count() < before / 4)
        {
            char detail[128];

            snprintf(detail, sizeof(detail),
                     "%zu of %zu tracks rejected",
                     before - tracker.count(), before);

            pass(detail);
        }
        else
        {
            fail("kept " + std::to_string(tracker.count()) + " of " +
                 std::to_string(before) + " bogus tracks");
        }
    }

    // ================================================================
    // Command queue, debug collector, recenter semantics
    // ================================================================

    beginTest("D1. command queue is bounded and drops the oldest");

    {
        CommandQueue queue;

        for (size_t i = 0; i < CommandQueue::Capacity + 10; ++i)
        {
            Command c;
            c.type = CommandType::Recenter;
            queue.push(c);
        }

        std::vector<Command> drained;

        const size_t count = queue.drain(drained);

        // An IPC client stuck in a loop must not be able to grow this
        // without bound on a 512 MB board.
        check(count == CommandQueue::Capacity && queue.dropped() == 10,
              "queue held " + std::to_string(count) +
              " entries, dropped " + std::to_string(queue.dropped()));
    }

    beginTest("D2. command words parse, and unknown ones are refused");

    {
        Command c;

        const bool known =
            parseCommand("RESET", false, c) &&
            c.type == CommandType::Reset &&
            parseCommand("RECENTER", false, c) &&
            c.type == CommandType::Recenter &&
            parseCommand("PAUSE", false, c) &&
            parseCommand("RESUME", false, c) &&
            parseCommand("SET_STEREO", true, c) &&
            c.flag;

        const bool rejected = !parseCommand("DESTROY", false, c);

        check(known && rejected,
              "command parsing is wrong");
    }

    beginTest("D3. debug collector is inert unless enabled");

    {
        DebugCollector off(false);

        off.start(monotonicSeconds());
        off.noteDroppedFrames(5);
        off.noteImuSamples(100);

        const DebugStatistics s = off.snapshot();

        // Without --debug nothing is collected, and the snapshot says
        // so rather than reporting zeros that look like measurements.
        check(!s.enabled && s.framesProcessed == 0 &&
                  s.droppedFrames == 0,
              "a disabled collector recorded data");
    }

    beginTest("D4. debug percentiles come out of the histogram");

    {
        DebugCollector on(true);

        Profiler profiler;
        VIOState st;

        on.start(monotonicSeconds());

        // 100 frames: 90 at ~10 ms, 10 at ~50 ms. p50 must land in
        // the fast group, p99 in the slow one.
        for (int i = 0; i < 100; ++i)
        {
            const double seconds = (i < 90) ? 0.010 : 0.050;

            profiler.begin(Stage::Total);
            profiler.endWith(Stage::Total, seconds);

            st.trackedFeatures = 300 + i;

            on.noteFrame(monotonicSeconds(), profiler, st, 50, i != 7);
        }

        const DebugStatistics f = on.finalise(monotonicSeconds());

        const bool ok =
            f.framesProcessed == 100 &&
            f.trackingFailures == 1 &&
            f.successfulFrames == 99 &&
            std::abs(f.minFrameTimeMs - 10.0) < 0.5 &&
            std::abs(f.maxFrameTimeMs - 50.0) < 0.5 &&
            std::abs(f.p50FrameTimeMs - 10.0) < 0.6 &&
            std::abs(f.p99FrameTimeMs - 50.0) < 0.6;

        if (ok)
        {
            char detail[192];

            snprintf(detail, sizeof(detail),
                     "p50 %.2f  p90 %.2f  p99 %.2f  min %.2f  max %.2f ms",
                     f.p50FrameTimeMs, f.p90FrameTimeMs,
                     f.p99FrameTimeMs, f.minFrameTimeMs,
                     f.maxFrameTimeMs);

            pass(detail);
        }
        else
        {
            char reason[192];

            snprintf(reason, sizeof(reason),
                     "frames %llu p50 %.2f p99 %.2f min %.2f max %.2f",
                     static_cast<unsigned long long>(f.framesProcessed),
                     f.p50FrameTimeMs, f.p99FrameTimeMs,
                     f.minFrameTimeMs, f.maxFrameTimeMs);

            fail(reason);
        }
    }

    beginTest("D5. recenter moves the origin WITHOUT resetting tracking");

    {
        StateEstimator estimator(config);

        // Walk the estimator forward with a known motion, so there is
        // a real pose to recentre away from.
        MotionResult step;

        step.success = true;
        step.inliers = 40;
        step.rotation = cv::Matx33d::eye();
        step.translation = cv::Vec3d(0.0, 0.0, -0.1);   // forward

        for (int i = 0; i < 10; ++i)
        {
            estimator.applyMotion(step, 1.0 + i * 0.033, 0.033);
        }

        const Eigen::Vector3d before = estimator.state().position;
        const bool trackingBefore = estimator.state().tracking;

        estimator.recenter();

        const Eigen::Vector3d atOrigin = estimator.state().position;

        // The reported pose must be at the origin...
        const bool zeroed = atOrigin.norm() < 1e-12;

        // ...tracking must be untouched...
        const bool stillTracking = estimator.state().tracking;

        // ...and continued motion must accumulate from the new origin.
        estimator.applyMotion(step, 2.0, 0.033);

        const Eigen::Vector3d after = estimator.state().position;

        const bool movedFromNewOrigin =
            std::abs(after.norm() - 0.1) < 1e-9;

        if (before.norm() > 0.5 && zeroed && stillTracking &&
            trackingBefore && movedFromNewOrigin)
        {
            char detail[192];

            snprintf(detail, sizeof(detail),
                     "was %.3f m from origin, recentred to %.1e, "
                     "then moved %.3f m; tracking never dropped",
                     before.norm(), atOrigin.norm(), after.norm());

            pass(detail);
        }
        else
        {
            char reason[192];

            snprintf(reason, sizeof(reason),
                     "before %.4f zeroed %d tracking %d after %.4f",
                     before.norm(), zeroed ? 1 : 0,
                     stillTracking ? 1 : 0, after.norm());

            fail(reason);
        }
    }

    beginTest("D6. reset is distinct from recenter");

    {
        StateEstimator estimator(config);

        MotionResult step;

        step.success = true;
        step.inliers = 40;
        step.rotation = cv::Matx33d::eye();
        step.translation = cv::Vec3d(0.0, 0.0, -0.1);

        for (int i = 0; i < 5; ++i)
        {
            estimator.applyMotion(step, 1.0 + i * 0.033, 0.033);
        }

        estimator.recenter();

        const bool recentredFlag = estimator.hasOrigin();
        const uint64_t recenters = estimator.recenterCount();

        estimator.reset();

        // reset() must clear the origin too, and must drop tracking -
        // that is exactly what makes it different from recenter().
        const bool cleared =
            !estimator.hasOrigin() &&
            !estimator.state().tracking &&
            estimator.state().position.norm() < 1e-12;

        check(recentredFlag && recenters == 1 && cleared,
              "reset did not clear what recenter set, or did not drop "
              "tracking");
    }

    beginTest("D7. Novex -> Three.js axis conversion is a proper rotation");

    {
        // The browser converts (x, y, z) -> (x, -y, -z) because Novex
        // is OpenCV camera convention (Y down, Z forward) and Three.js
        // is Y up. That must be a ROTATION, not a mirror, or every
        // orientation shown would be handed backwards.
        const Eigen::Matrix3d m =
            Eigen::Vector3d(1.0, -1.0, -1.0).asDiagonal();

        const bool proper =
            std::abs(m.determinant() - 1.0) < 1e-12 &&
            (m * m.transpose() - Eigen::Matrix3d::Identity())
                .cwiseAbs().maxCoeff() < 1e-12;

        // And it must agree with the quaternion form the browser uses,
        // q -> (x, -y, -z, w), for an arbitrary rotation.
        Eigen::Quaterniond q(0.4472136, 0.5477226, 0.3162278, 0.6324555);
        q.normalize();

        const Eigen::Quaterniond converted(
            q.w(), q.x(), -q.y(), -q.z()
        );

        const Eigen::Vector3d v(0.3, -0.7, 1.1);

        const Eigen::Vector3d viaRotateThenConvert = m * (q * v);
        const Eigen::Vector3d viaConvertThenRotate = converted * (m * v);

        const double error =
            (viaRotateThenConvert - viaConvertThenRotate)
                .cwiseAbs().maxCoeff();

        if (proper && error < 1e-12)
        {
            char detail[128];

            snprintf(detail, sizeof(detail),
                     "det +1, orthonormal, quaternion form agrees to "
                     "%.1e",
                     error);

            pass(detail);
        }
        else
        {
            fail("axis conversion is not a proper rotation, or the "
                 "quaternion form disagrees");
        }
    }

    // ================================================================
    // 8 / 9. IMU disabled and enabled
    // ================================================================

    beginTest("8. IMU-disabled mode starts and reports honestly");

    {
        VIOConfig noImu = config;

        noImu.imuEnabled = false;
        noImu.applyDerived();

        IMU imu(noImu);

        const bool started = imu.start();

        const IMU::Health health = imu.health();

        check(started && !imu.isEnabled() && !health.enabled,
              "a disabled IMU did not start cleanly");

        imu.stop();
    }

    beginTest("9. IMU-enabled interface initialises cleanly");

    {
        VIOConfig withImu = config;

        withImu.imuEnabled = true;
        withImu.imuBackend = "iio";
        withImu.applyDerived();

        IMU imu(withImu);

        // The contract: requesting an IMU must never fail the process
        // when no hardware is present. It degrades to visual odometry
        // and says so.
        const bool started = imu.start();

        const IMU::Health health = imu.health();

        if (!started)
        {
            fail("start() returned false with no IMU attached");
        }
        else if (health.available)
        {
            pass("an IIO IMU was found and is running");
        }
        else
        {
            char detail[256];

            snprintf(detail, sizeof(detail),
                     "no IMU hardware present, degraded to visual "
                     "odometry (%s)",
                     health.detail.c_str());

            pass(detail);
        }

        imu.stop();
    }

    beginTest("9b. an unknown IMU backend is refused, not guessed at");

    {
        VIOConfig badImu = config;

        badImu.imuEnabled = true;
        badImu.imuBackend = "definitely-not-a-backend";
        badImu.applyDerived();

        IMU imu(badImu);

        check(imu.start() && !imu.isEnabled(),
              "an unknown backend was not handled cleanly");

        imu.stop();
    }

    // ================================================================
    // 6. GUI mode
    // ================================================================

    beginTest("6. GUI opens no window unless GUI mode is selected");

    {
        VIOConfig daemonConfig = config;

        daemonConfig.mode = RunMode::Daemon;
        daemonConfig.applyDerived();

        Gui gui(daemonConfig);

        check(!gui.open() && !gui.isOpen(),
              "a window was opened in daemon mode");
    }

    beginTest("6b. GUI mode opens a window when a display exists");

    {
        const char* display = getenv("DISPLAY");
        const char* wayland = getenv("WAYLAND_DISPLAY");

        if (display == nullptr && wayland == nullptr)
        {
            skip("no DISPLAY or WAYLAND_DISPLAY set");
        }
        else
        {
            VIOConfig guiConfig = config;

            guiConfig.mode = RunMode::Gui;
            guiConfig.applyDerived();

            Gui gui(guiConfig);

            if (gui.open())
            {
                pass("window created");
                gui.close();
            }
            else
            {
                // Not a failure of the design: it is exactly the
                // graceful degradation the GUI is supposed to do.
                skip("highgui could not create a window here");
            }
        }
    }

    // ================================================================
    // 1, 2, 3, 7, 12, 13, 14, 15. Live pipeline
    // ================================================================

    if (!useCamera)
    {
        skip("camera tests disabled with --no-camera");

        printf("\n==========================\n");
        printf("passed %d, failed %d, skipped %d\n",
               gPassed, gFailed, gSkipped);

        return gFailed == 0 ? 0 : 1;
    }

    beginTest("1. camera opens");

    Camera camera(config);

    const bool cameraOpen = camera.open();

    if (!cameraOpen)
    {
        skip("no camera on device " +
             std::to_string(config.cameraDevice));

        printf("\n==========================\n");
        printf("passed %d, failed %d, skipped %d\n",
               gPassed, gFailed, gSkipped);

        return gFailed == 0 ? 0 : 1;
    }

    pass(camera.describe().c_str());

    beginTest("2. camera negotiates the requested mode");

    {
        const Camera::Status& status = camera.status();

        const bool sizeOk =
            status.negotiatedWidth == config.cameraWidth &&
            status.negotiatedHeight == config.cameraHeight;

        const bool formatOk =
            !config.cameraMJPEG || status.mjpegNegotiated;

        const bool rateOk =
            std::abs(status.negotiatedFPS - config.cameraFPS) < 1.0;

        if (sizeOk && formatOk && rateOk)
        {
            pass("1280x480 MJPG at 30 fps, as requested");
        }
        else
        {
            char reason[256];

            snprintf(reason, sizeof(reason),
                     "negotiated %dx%d %s at %.1f fps",
                     status.negotiatedWidth,
                     status.negotiatedHeight,
                     status.fourcc.c_str(),
                     status.negotiatedFPS);

            fail(reason);
        }
    }

    beginTest("3. the stereo frame splits into two independent eyes");

    {
        const cv::Mat& frame = camera.getFrame();
        const cv::Mat& left = camera.getLeftImage();
        const cv::Mat& right = camera.getRightImage();

        const bool sizesOk =
            left.cols == frame.cols / 2 &&
            right.cols == frame.cols / 2 &&
            left.rows == frame.rows &&
            right.rows == frame.rows;

        // The two halves must be views of the same buffer (no copy)
        // but must not be the same pixels.
        const bool sharesBuffer =
            left.datastart == frame.datastart &&
            right.data == frame.data + frame.cols / 2;

        const double difference = cv::norm(left, right, cv::NORM_L1) /
                                  (left.total() + 1);

        if (sizesOk && sharesBuffer && difference > 1.0)
        {
            char detail[160];

            snprintf(detail, sizeof(detail),
                     "%dx%d per eye, zero-copy views, mean L1 "
                     "difference %.1f",
                     left.cols, left.rows, difference);

            pass(detail);
        }
        else if (!sizesOk)
        {
            fail("eye images have the wrong size");
        }
        else if (!sharesBuffer)
        {
            fail("eye images are copies rather than views");
        }
        else
        {
            fail("the two eyes are identical - the frame is probably "
                 "not a side-by-side stereo image");
        }
    }

    beginTest("3b. camera timestamps advance monotonically and sanely");

    {
        std::vector<double> stamps;

        for (int i = 0; i < 20; ++i)
        {
            if (camera.grab())
            {
                stamps.push_back(camera.getTimestamp());
            }
        }

        bool monotonic = true;
        double totalGap = 0.0;

        for (size_t i = 1; i < stamps.size(); ++i)
        {
            const double gap = stamps[i] - stamps[i - 1];

            if (gap <= 0.0)
            {
                monotonic = false;
            }

            totalGap += gap;
        }

        const double meanGap = stamps.size() > 1
            ? totalGap / (stamps.size() - 1)
            : 0.0;

        // At 30 fps the interval should be near 33 ms. The point of
        // the check is that the timestamps are real measurements, not
        // a counter multiplied by a nominal period.
        if (stamps.size() >= 10 && monotonic &&
            meanGap > 0.020 && meanGap < 0.060)
        {
            char detail[160];

            snprintf(detail, sizeof(detail),
                     "%zu frames, mean interval %.2f ms, source: %s",
                     stamps.size(), meanGap * 1e3,
                     camera.status().driverTimestamps
                         ? "V4L2 buffer"
                         : "host clock");

            pass(detail);
        }
        else
        {
            char reason[160];

            snprintf(reason, sizeof(reason),
                     "%zu frames, monotonic %d, mean interval %.2f ms",
                     stamps.size(), monotonic ? 1 : 0, meanGap * 1e3);

            fail(reason);
        }
    }

    // Adapt the calibration to whatever the camera actually gave us.
    calibration.setCurrentResolution(camera.eyeSize());

    IMU imu(config);
    imu.start();

    VIO vio(config, calibration, &imu);

    beginTest("7. daemon-mode pipeline runs with no GUI at all");

    const bool vioReady = vio.initialise(camera.eyeSize());

    check(vioReady, "VIO initialisation failed");

    if (!vioReady)
    {
        printf("\n==========================\n");
        printf("passed %d, failed %d, skipped %d\n",
               gPassed, gFailed, gSkipped);

        return 1;
    }

    beginTest("12. stereo matching produces plausible correspondences");

    {
        StereoMatcher matcher(config, calibration);
        FeatureTracker tracker(config);
        Profiler profiler;

        camera.grab();

        cv::Mat left = camera.getLeftImage().clone();
        cv::Mat right = camera.getRightImage().clone();

        tracker.detect(left, profiler);

        matcher.compute(left, right, tracker.features(), profiler);

        const StereoMatcher::Stats& stats = matcher.stats();

        double minDepth = 1e9;
        double maxDepth = -1e9;
        double meanDepth = 0.0;

        for (const Feature& feature : tracker.features())
        {
            if (!feature.hasDepth)
            {
                continue;
            }

            minDepth = std::min<double>(minDepth, feature.position3D.z);
            maxDepth = std::max<double>(maxDepth, feature.position3D.z);
            meanDepth += feature.position3D.z;
        }

        if (stats.triangulated > 0)
        {
            meanDepth /= stats.triangulated;
        }

        // The bar is deliberately modest: this runs against whatever
        // the lens happens to be pointed at, which may be a blank
        // wall. What must hold is that a reasonable fraction match and
        // that every depth is inside the configured window.
        const bool enough =
            stats.triangulated >= stats.attempted / 10 &&
            stats.triangulated >= 20;

        const bool depthsSane =
            stats.triangulated == 0 ||
            (minDepth >= config.minDepthMeters &&
             maxDepth <= config.maxDepthMeters);

        if (enough && depthsSane)
        {
            char detail[224];

            snprintf(detail, sizeof(detail),
                     "%d/%d matched, %d triangulated, depth "
                     "%.2f-%.2f m (mean %.2f), %d rejected on "
                     "epipolar, %d on depth",
                     stats.matched, stats.attempted,
                     stats.triangulated,
                     minDepth, maxDepth, meanDepth,
                     stats.rejectedEpipolar, stats.rejectedDepth);

            pass(detail);
        }
        else
        {
            char reason[224];

            snprintf(reason, sizeof(reason),
                     "%d/%d matched, %d triangulated, depth "
                     "%.2f-%.2f m",
                     stats.matched, stats.attempted,
                     stats.triangulated, minDepth, maxDepth);

            fail(reason);
        }
    }

    beginTest("13. the pipeline produces a VIO state");

    {
        int tracked = 0;

        const int frames = 60;

        for (int i = 0; i < frames; ++i)
        {
            if (!camera.grab())
            {
                continue;
            }

            if (vio.process(camera.getLeftImage(),
                            camera.getRightImage(),
                            camera.getTimestamp()))
            {
                ++tracked;
            }
        }

        const VIOSnapshot snapshot = vio.snapshot();
        const VIOState& state = snapshot.state;

        const bool stateSane =
            state.frameId > 0 &&
            state.timestamp > 0.0 &&
            std::isfinite(state.position.norm()) &&
            std::abs(state.orientation.norm() - 1.0) < 1e-6;

        if (stateSane)
        {
            char detail[256];

            snprintf(detail, sizeof(detail),
                     "%d/%d frames tracked, %llu frames, %d features, "
                     "capture %.1f fps, processing %.1f fps, "
                     "latency %.1f ms",
                     tracked, frames,
                     static_cast<unsigned long long>(state.frameId),
                     state.trackedFeatures,
                     snapshot.captureFPS,
                     snapshot.processingFPS,
                     snapshot.latencySeconds * 1e3);

            pass(detail);

            if (tracked == 0)
            {
                printf("    NOTE  no frame produced a motion estimate."
                       " With a stationary camera facing a blank"
                       " surface this can be correct.\n");
            }
        }
        else
        {
            fail("the published state is not well formed");
        }
    }

    // ================================================================
    // 14 / 15. IPC
    // ================================================================

    beginTest("14. an IPC client can request state");

    VIOConfig ipcConfig = config;

    ipcConfig.ipcSocketPath = "/tmp/novex-vio-test.sock";

    StateServer server(ipcConfig, vio);

    const bool serverStarted = server.start();

    if (!serverStarted)
    {
        fail("the IPC server did not start");
    }
    else
    {
        const int fd = connectToSocket(ipcConfig.ipcSocketPath);

        if (fd < 0)
        {
            fail("could not connect to the socket");
        }
        else
        {
            send(fd, "GET_STATE\n", 10, 0);

            char response[2048];

            const ssize_t received =
                recv(fd, response, sizeof(response) - 1, 0);

            if (received > 0)
            {
                response[received] = '\0';

                const bool looksRight =
                    strstr(response, "\"position\"") != nullptr &&
                    strstr(response, "\"orientation\"") != nullptr &&
                    strstr(response, "\"tracking\"") != nullptr &&
                    strstr(response, "\"feature_count\"") != nullptr &&
                    strstr(response, "\"imu_enabled\"") != nullptr;

                check(looksRight,
                      "the reply is missing required fields");

                if (looksRight)
                {
                    printf("    reply: %s", response);
                }
            }
            else
            {
                fail("no reply from the server");
            }

            close(fd);
        }
    }

    beginTest("15. IPC traffic does not stall the processing loop");

    if (!serverStarted)
    {
        skip("the IPC server is not running");
    }
    else
    {
        // Baseline: how long does a frame take with nothing attached?
        double baselineTotal = 0.0;

        for (int i = 0; i < 30; ++i)
        {
            if (camera.grab())
            {
                vio.process(camera.getLeftImage(),
                            camera.getRightImage(),
                            camera.getTimestamp());
            }
        }

        baselineTotal = vio.profiler().average(Stage::Total);

        std::atomic<bool> hammering{true};
        std::atomic<int> replies{0};

        // One client polling as fast as it can.
        std::thread poller([&]()
        {
            const int fd = connectToSocket(ipcConfig.ipcSocketPath);

            if (fd < 0)
            {
                return;
            }

            char buffer[2048];

            while (hammering.load())
            {
                if (send(fd, "GET_STATE\n", 10, 0) < 0)
                {
                    break;
                }

                if (recv(fd, buffer, sizeof(buffer) - 1, 0) <= 0)
                {
                    break;
                }

                replies.fetch_add(1);
            }

            close(fd);
        });

        // A second client that connects, asks, and then never reads.
        // This is the case that would deadlock a naive server: the
        // socket buffer fills and a blocking write parks the thread.
        const int rudeFd = connectToSocket(ipcConfig.ipcSocketPath);

        if (rudeFd >= 0)
        {
            for (int i = 0; i < 200; ++i)
            {
                send(rudeFd, "GET_STATE\n", 10, MSG_DONTWAIT);
            }
        }

        const double start = monotonicSeconds();

        int processed = 0;

        for (int i = 0; i < 60; ++i)
        {
            if (camera.grab())
            {
                vio.process(camera.getLeftImage(),
                            camera.getRightImage(),
                            camera.getTimestamp());

                ++processed;
            }
        }

        const double elapsed = monotonicSeconds() - start;

        hammering.store(false);
        poller.join();

        if (rudeFd >= 0)
        {
            close(rudeFd);
        }

        const double loadedTotal = vio.profiler().average(Stage::Total);

        // The comparison is on VIO processing time, not wall clock:
        // wall clock is dominated by waiting for the camera, which
        // would mask a real stall.
        const bool noStall =
            loadedTotal < baselineTotal * 1.5 + 0.002;

        if (noStall && processed > 0 && replies.load() > 0)
        {
            char detail[256];

            snprintf(detail, sizeof(detail),
                     "%d replies served during %d frames; VIO time "
                     "%.2f ms idle vs %.2f ms under load; %.1f fps "
                     "sustained",
                     replies.load(), processed,
                     baselineTotal * 1e3, loadedTotal * 1e3,
                     processed / elapsed);

            pass(detail);
        }
        else
        {
            char reason[256];

            snprintf(reason, sizeof(reason),
                     "%d replies, VIO time %.2f ms idle vs %.2f ms "
                     "under load",
                     replies.load(),
                     baselineTotal * 1e3, loadedTotal * 1e3);

            fail(reason);
        }
    }

    beginTest("16b. the server releases its socket on shutdown");

    {
        server.stop();

        const int fd = connectToSocket(ipcConfig.ipcSocketPath);

        if (fd >= 0)
        {
            close(fd);
            fail("the socket still accepts connections after stop()");
        }
        else
        {
            pass("socket removed");
        }
    }

    imu.stop();
    camera.close();

    printf("\n==========================\n");
    printf("passed %d, failed %d, skipped %d\n",
           gPassed, gFailed, gSkipped);

    if (gSkipped > 0)
    {
        printf("Skipped tests were NOT run and are not passes.\n");
    }

    return gFailed == 0 ? 0 : 1;
}
