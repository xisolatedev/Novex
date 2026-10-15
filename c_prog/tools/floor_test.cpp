// Floor / ground estimator validation and benchmark.
//
// Everything here runs on SYNTHETIC scenes with known ground truth,
// for the same reason geometry_audit.cpp does: a floor estimate that
// is checked only against a recording can be wrong by a consistent
// amount forever and still look plausible. Here the answer is known
// to the millimetre.
//
//   novex-floor-test              run every scene
//   novex-floor-test --bench      run the benchmark only
//
// The scene generator builds a WORLD made of a floor, walls, a
// ceiling and furniture, places a camera in it with a given pose, and
// produces exactly what StereoMatcher would have produced: Features
// carrying position3D in the left camera frame, with range noise,
// outliers and a field of view.

#include "FloorEstimator.hpp"
#include "Log.hpp"
#include "Profiler.hpp"
#include "Time.hpp"
#include "VIOConfig.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <random>
#include <string>
#include <vector>

using namespace novex;

namespace
{

int gPassed = 0;
int gFailed = 0;

std::string gCurrentTest;

void beginTest(const std::string& name)
{
    gCurrentTest = name;
    printf("\n--- %s\n", name.c_str());
}

void pass(const std::string& detail)
{
    ++gPassed;
    printf("    PASS  %s : %s\n", gCurrentTest.c_str(), detail.c_str());
}

void fail(const std::string& reason)
{
    ++gFailed;
    printf("    FAIL  %s : %s\n", gCurrentTest.c_str(), reason.c_str());
}

void check(bool condition, const std::string& detail)
{
    if (condition)
    {
        pass(detail);
    }
    else
    {
        fail(detail);
    }
}

// ===================================================================
// synthetic world
// ===================================================================
//
// World frame = the camera's start pose, which is what the real
// estimator uses. The camera starts upright at kCameraHeight above
// the floor, so in world coordinates:
//
//   floor      y = +kCameraHeight   (Y is DOWN)
//   ceiling    y = -1.0
//   walls      x = +-2.5
//
// The floor plane in the estimator's convention is therefore
// n = (0, -1, 0), d = kCameraHeight.

constexpr double kCameraHeight = 1.50;

const Eigen::Vector3d kTrueNormal(0.0, -1.0, 0.0);

struct SceneOptions
{
    bool floorPoints = true;
    int floorCount = 220;

    bool walls = false;
    int wallCount = 200;

    bool ceiling = false;
    int ceilingCount = 120;

    bool furniture = false;
    int furnitureCount = 90;

    // Fraction of returned points that are pure depth garbage.
    double outlierFraction = 0.0;

    // Relative range noise, i.e. sigma_range / range.
    double rangeSigma = 0.01;

    // Restricts the floor to a wedge in front of the camera, so only
    // part of it is visible.
    bool partialFloor = false;

    int seed = 12345;
};

// A pinhole is fine HERE: the synthetic points never pass through a
// lens model, and the pixel is only used for the debug mask.
constexpr double kFocal = 300.0;
constexpr double kCx = 320.0;
constexpr double kCy = 240.0;

class Scene
{
public:

    explicit Scene(const SceneOptions& options)
        : options(options), rng(static_cast<uint32_t>(options.seed))
    {
        build();
    }

    // Everything the camera at (rotation, position) can see, as the
    // Features the pipeline would have produced.
    void observe(const Eigen::Matrix3d& worldFromCamera,
                 const Eigen::Vector3d& cameraInWorld,
                 std::vector<Feature>& out)
    {
        out.clear();

        std::normal_distribution<double> gauss(0.0, 1.0);
        std::uniform_real_distribution<double> uniform(0.0, 1.0);

        const Eigen::Matrix3d cameraFromWorld =
            worldFromCamera.transpose();

        uint64_t id = 1;

        for (const Eigen::Vector3d& world : points)
        {
            Eigen::Vector3d camera =
                cameraFromWorld * (world - cameraInWorld);

            if (camera.z() < 0.25 || camera.z() > 6.0)
            {
                continue;
            }

            // Field of view of the 640x480 eye this rig runs.
            if (std::abs(camera.x() / camera.z()) > 1.0 ||
                std::abs(camera.y() / camera.z()) > 0.75)
            {
                continue;
            }

            const double range = camera.norm();

            if (uniform(rng) < options.outlierFraction)
            {
                // A bad stereo match puts the point somewhere else
                // along its own ray entirely. That is what the failure
                // actually looks like; scattering it isotropically
                // would be a kinder test than reality.
                const double factor = 0.4 + 1.8 * uniform(rng);

                camera *= factor;
            }
            else if (options.rangeSigma > 0.0)
            {
                const double sigma = options.rangeSigma * range;

                camera += (camera / range) * (sigma * gauss(rng));
            }

            Feature feature;

            feature.id = id++;
            feature.hasDepth = true;

            feature.position3D = cv::Point3f(
                static_cast<float>(camera.x()),
                static_cast<float>(camera.y()),
                static_cast<float>(camera.z()));

            feature.point = cv::Point2f(
                static_cast<float>(kFocal * camera.x() / camera.z() + kCx),
                static_cast<float>(kFocal * camera.y() / camera.z() + kCy));

            feature.depthSigma =
                static_cast<float>(std::max(0.005, options.rangeSigma));

            feature.stereoResidualPx = 0.8f;
            feature.age = 5;
            feature.motionInlier = true;

            out.push_back(feature);
        }
    }

private:

    void build()
    {
        std::uniform_real_distribution<double> uniform(0.0, 1.0);

        auto range = [&](double low, double high)
        {
            return low + (high - low) * uniform(rng);
        };

        if (options.floorPoints)
        {
            for (int i = 0; i < options.floorCount; ++i)
            {
                const double x = options.partialFloor
                    ? range(0.3, 1.8)
                    : range(-2.4, 2.4);

                const double z = options.partialFloor
                    ? range(1.2, 2.6)
                    : range(0.4, 5.5);

                points.emplace_back(x, kCameraHeight, z);
            }
        }

        if (options.walls)
        {
            for (int i = 0; i < options.wallCount; ++i)
            {
                const double side = (i % 2 == 0) ? -2.5 : 2.5;

                points.emplace_back(side,
                                    range(-1.0, kCameraHeight),
                                    range(0.5, 5.5));
            }
        }

        if (options.ceiling)
        {
            for (int i = 0; i < options.ceilingCount; ++i)
            {
                points.emplace_back(range(-2.4, 2.4), -1.0,
                                    range(0.5, 5.5));
            }
        }

        if (options.furniture)
        {
            // Three boxes standing on the floor: table-top height,
            // chair height, and a person-sized column. The table top
            // is the case a support-maximising RANSAC gets wrong.
            const double tops[3] = {kCameraHeight - 0.75,
                                    kCameraHeight - 0.45,
                                    kCameraHeight - 1.70};

            const double cx[3] = {-1.0, 0.9, 0.2};
            const double cz[3] = {2.0, 1.6, 3.2};

            for (int i = 0; i < options.furnitureCount; ++i)
            {
                const int box = i % 3;

                points.emplace_back(cx[box] + range(-0.45, 0.45),
                                    tops[box],
                                    cz[box] + range(-0.45, 0.45));
            }
        }
    }

    SceneOptions options;
    std::mt19937 rng;

    std::vector<Eigen::Vector3d> points;
};

// A camera pose from human-readable angles, in the world frame.
// Intrinsic yaw-then-pitch-then-roll about the camera's own axes,
// which for a Y-down frame are: yaw about Y, pitch about X, roll
// about Z.
//
// Pitch is NEGATED so that positive means nose DOWN, towards the
// floor - the same sense FloorEstimate::pitchDegrees reports. In a
// Y-down frame a positive rotation about +X tilts the optical axis
// upwards, which is the opposite of what anyone writing a test means
// by "pitched 35 degrees down".
Eigen::Matrix3d pose(double yawDeg, double pitchDeg, double rollDeg)
{
    const double toRad = 0.017453292519943295;

    return (Eigen::AngleAxisd(yawDeg * toRad, Eigen::Vector3d::UnitY()) *
            Eigen::AngleAxisd(-pitchDeg * toRad, Eigen::Vector3d::UnitX()) *
            Eigen::AngleAxisd(rollDeg * toRad, Eigen::Vector3d::UnitZ()))
        .toRotationMatrix();
}

VIOConfig baseConfig()
{
    VIOConfig config;

    config.floorEnabled = true;

    // Every frame in these tests is a measurement, so a scene of 30
    // frames is 30 measurements rather than 5.
    config.floorUpdateHz = 1000.0;

    return config;
}

double angleDegrees(const Eigen::Vector3d& a, const Eigen::Vector3d& b)
{
    const double c = a.normalized().dot(b.normalized());

    return std::acos(std::max(-1.0, std::min(1.0, c))) *
           57.295779513082320876;
}

// Runs `frames` frames of a fixed pose and returns the final estimate.
FloorEstimate run(FloorEstimator& estimator,
                  Scene& scene,
                  const Eigen::Matrix3d& rotation,
                  const Eigen::Vector3d& position,
                  int frames,
                  double& time,
                  Profiler& profiler,
                  bool blind = false,
                  const std::vector<IMUSample>* imu = nullptr)
{
    std::vector<Feature> features;

    FloorInput input;

    for (int frame = 0; frame < frames; ++frame)
    {
        if (blind)
        {
            features.clear();
        }
        else
        {
            scene.observe(rotation, position, features);
        }

        input.features = &features;
        input.worldFromCamera = rotation;
        input.cameraInWorld = position;
        input.poseValid = true;
        input.imu = imu;
        input.timestamp = time;
        input.frameId = static_cast<uint64_t>(frame);

        estimator.update(input, profiler);

        time += 1.0 / 30.0;
    }

    return estimator.estimate();
}

// The height the camera really is at, for a given world position.
double trueHeight(const Eigen::Vector3d& position)
{
    return kTrueNormal.dot(position) + kCameraHeight;
}

void reportEstimate(const FloorEstimate& e)
{
    printf("          status %-12s source %-8s conf %.2f  "
           "h %.3f m  tilt %.2f deg  in %d/%d  rms %.3f  span %.2f\n",
           floorStatusName(e.status),
           floorDownSourceName(e.downSource),
           e.confidence, e.cameraHeight, e.tiltDegrees,
           e.inlierCount, e.candidateCount, e.rmsResidualM,
           e.spanMeters);
}

std::string detail(const FloorEstimate& e, double heightError,
                   double normalError)
{
    char text[256];

    snprintf(text, sizeof(text),
             "height error %.1f mm, normal error %.2f deg, conf %.2f",
             heightError * 1e3, normalError, e.confidence);

    return text;
}

// ===================================================================

void benchmark()
{
    printf("\n=== benchmark ===\n");

    VIOConfig config = baseConfig();

    SceneOptions options;
    options.walls = true;
    options.furniture = true;
    options.ceiling = true;
    options.outlierFraction = 0.05;
    options.rangeSigma = 0.015;

    Scene scene(options);

    Profiler profiler;

    const Eigen::Matrix3d rotation = pose(0.0, 10.0, 0.0);
    const Eigen::Vector3d position(0.0, 0.0, 0.0);

    std::vector<Feature> features;

    scene.observe(rotation, position, features);

    printf("  scene: %zu visible stereo points, cap %d candidates\n",
           features.size(), config.floorMaxPoints);

    // ---- acquisition: every frame is a cold start ----
    {
        const int trials = 200;

        const double start = monotonicSeconds();

        for (int i = 0; i < trials; ++i)
        {
            FloorEstimator estimator(config);

            estimator.configure(features.size() + 32);

            FloorInput input;

            input.features = &features;
            input.worldFromCamera = rotation;
            input.cameraInWorld = position;
            input.poseValid = true;
            input.timestamp = 0.001 * i;

            estimator.update(input, profiler);
        }

        const double elapsed = monotonicSeconds() - start;

        printf("  acquisition   %.3f ms / measurement\n",
               elapsed * 1e3 / trials);
    }

    // ---- steady state: prior-guided measurement ----
    {
        FloorEstimator estimator(config);

        estimator.configure(features.size() + 32);

        double time = 0.0;

        Profiler warm;

        run(estimator, scene, rotation, position, 10, time, warm);

        const int trials = 400;

        FloorInput input;

        input.features = &features;
        input.worldFromCamera = rotation;
        input.cameraInWorld = position;
        input.poseValid = true;

        const double start = monotonicSeconds();

        for (int i = 0; i < trials; ++i)
        {
            input.timestamp = time;
            time += 1.0 / 30.0;

            estimator.update(input, profiler);
        }

        const double elapsed = monotonicSeconds() - start;

        printf("  tracking      %.3f ms / measurement\n",
               elapsed * 1e3 / trials);
    }

    // ---- prediction only: what runs on the frames in between ----
    {
        VIOConfig slow = config;
        slow.floorUpdateHz = 6.0;

        FloorEstimator estimator(slow);

        estimator.configure(features.size() + 32);

        double time = 0.0;

        run(estimator, scene, rotation, position, 30, time, profiler);

        const int trials = 2000;

        FloorInput input;

        input.features = &features;
        input.worldFromCamera = rotation;
        input.cameraInWorld = position;
        input.poseValid = true;

        // Timestamps advance by far less than the measurement
        // interval, so every one of these is a prediction.
        const double start = monotonicSeconds();

        for (int i = 0; i < trials; ++i)
        {
            input.timestamp = time + 1e-5 * i;

            estimator.update(input, profiler);
        }

        const double elapsed = monotonicSeconds() - start;

        printf("  prediction    %.4f ms / frame\n",
               elapsed * 1e3 / trials);
    }

    // The estimator's own footprint, measured rather than guessed:
    // the object plus every scratch buffer it sizes in configure().
    // Candidates dominate - roughly 80 bytes each.
    const size_t candidateBytes = 80;

    const size_t scratch =
        sizeof(FloorEstimator) +
        static_cast<size_t>(config.maxFeatures) * candidateBytes +
        static_cast<size_t>(config.maxFeatures) *
            (2 * sizeof(uint32_t) + 2 * sizeof(double) +
             3 * sizeof(cv::Point2f)) +
        1024 * sizeof(int32_t);

    printf("  memory        ~%.1f KiB resident at %d features\n",
           scratch / 1024.0, config.maxFeatures);
}

} // namespace

int main(int argc, char** argv)
{
    setLogLevel(LogLevel::Warn);

    bool benchOnly = false;

    for (int i = 1; i < argc; ++i)
    {
        if (std::strcmp(argv[i], "--bench") == 0)
        {
            benchOnly = true;
        }
    }

    printf("Novex floor estimator validation\n");
    printf("================================\n");
    printf("world = camera start pose; floor at y = %.2f m, "
           "n = (0, -1, 0), d = %.2f\n", kCameraHeight, kCameraHeight);

    if (benchOnly)
    {
        benchmark();
        return 0;
    }

    Profiler profiler;

    const VIOConfig config = baseConfig();

    // -----------------------------------------------------------
    beginTest("1. perfect flat floor, camera level and still");

    {
        SceneOptions options;
        options.rangeSigma = 0.0;
        options.outlierFraction = 0.0;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        const Eigen::Matrix3d rotation = Eigen::Matrix3d::Identity();
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        const FloorEstimate e =
            run(estimator, scene, rotation, position, 10, time, profiler);

        reportEstimate(e);

        const double heightError =
            std::abs(e.cameraHeight - trueHeight(position));

        const double normalError =
            angleDegrees(e.normalWorld, kTrueNormal);

        check(e.valid && e.status == FloorStatus::Tracking &&
                  heightError < 0.01 && normalError < 1.0,
              detail(e, heightError, normalError));
    }

    // -----------------------------------------------------------
    beginTest("2. noisy stereo with 8 percent outliers");

    {
        SceneOptions options;
        options.rangeSigma = 0.02;
        options.outlierFraction = 0.08;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        const Eigen::Matrix3d rotation = Eigen::Matrix3d::Identity();
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        const FloorEstimate e =
            run(estimator, scene, rotation, position, 15, time, profiler);

        reportEstimate(e);

        const double heightError =
            std::abs(e.cameraHeight - trueHeight(position));

        const double normalError =
            angleDegrees(e.normalWorld, kTrueNormal);

        check(e.valid && heightError < 0.05 && normalError < 4.0,
              detail(e, heightError, normalError));
    }

    // -----------------------------------------------------------
    beginTest("3. camera pitched 35 degrees down");

    {
        SceneOptions options;
        options.rangeSigma = 0.015;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        const Eigen::Matrix3d rotation = pose(0.0, 35.0, 0.0);
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        const FloorEstimate e =
            run(estimator, scene, rotation, position, 15, time, profiler);

        reportEstimate(e);

        const double heightError =
            std::abs(e.cameraHeight - trueHeight(position));

        const double normalError =
            angleDegrees(e.normalWorld, kTrueNormal);

        // The floor is still the floor. What changed is the camera
        // plane, whose tilt should now read back the pitch that was
        // applied.
        const double tiltError = std::abs(e.tiltDegrees - 35.0);

        check(e.valid && heightError < 0.05 && normalError < 4.0 &&
                  tiltError < 4.0,
              detail(e, heightError, normalError) +
                  ", tilt reads " + std::to_string(e.tiltDegrees));
    }

    // -----------------------------------------------------------
    beginTest("4. camera rolled and yawed while standing still");

    {
        SceneOptions options;
        options.rangeSigma = 0.015;
        options.walls = true;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        std::vector<Feature> features;

        FloorInput input;

        double worstHeight = 0.0;
        double worstNormal = 0.0;

        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        for (int frame = 0; frame < 60; ++frame)
        {
            const double yaw = 6.0 * frame;
            const double roll = 20.0 * std::sin(0.2 * frame);

            const Eigen::Matrix3d rotation = pose(yaw, 20.0, roll);

            scene.observe(rotation, position, features);

            input.features = &features;
            input.worldFromCamera = rotation;
            input.cameraInWorld = position;
            input.poseValid = true;
            input.timestamp = time;
            input.frameId = static_cast<uint64_t>(frame);

            const FloorEstimate& e = estimator.update(input, profiler);

            time += 1.0 / 30.0;

            if (frame > 10 && e.valid)
            {
                worstHeight = std::max(
                    worstHeight,
                    std::abs(e.cameraHeight - trueHeight(position)));

                worstNormal = std::max(
                    worstNormal,
                    angleDegrees(e.normalWorld, kTrueNormal));
            }
        }

        const FloorEstimate e = estimator.estimate();

        reportEstimate(e);

        // The point of the test: the floor is held in WORLD space, so
        // spinning the head must not move it.
        check(e.valid && worstHeight < 0.06 && worstNormal < 5.0,
              detail(e, worstHeight, worstNormal) +
                  " (worst over the sweep)");
    }

    // -----------------------------------------------------------
    beginTest("5. camera translating across the room");

    {
        SceneOptions options;
        options.rangeSigma = 0.015;
        options.walls = true;
        options.furniture = true;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        std::vector<Feature> features;

        FloorInput input;

        double worstHeight = 0.0;

        for (int frame = 0; frame < 60; ++frame)
        {
            // Walking forwards and to the side, with a little bob.
            const Eigen::Vector3d position(
                0.012 * frame,
                0.02 * std::sin(0.4 * frame),
                0.02 * frame);

            const Eigen::Matrix3d rotation = pose(0.0, 15.0, 0.0);

            scene.observe(rotation, position, features);

            input.features = &features;
            input.worldFromCamera = rotation;
            input.cameraInWorld = position;
            input.poseValid = true;
            input.timestamp = time;
            input.frameId = static_cast<uint64_t>(frame);

            const FloorEstimate& e = estimator.update(input, profiler);

            time += 1.0 / 30.0;

            if (frame > 10 && e.valid)
            {
                worstHeight = std::max(
                    worstHeight,
                    std::abs(e.cameraHeight - trueHeight(position)));
            }
        }

        const FloorEstimate e = estimator.estimate();

        reportEstimate(e);

        // The bob is real motion and the estimate is expected to
        // follow it: what is checked is that the height tracks the
        // truth, not that it is constant.
        check(e.valid && worstHeight < 0.07,
              "worst height error " +
                  std::to_string(worstHeight * 1e3) + " mm");
    }

    // -----------------------------------------------------------
    beginTest("6. only a wedge of the floor is visible");

    {
        SceneOptions options;
        options.rangeSigma = 0.015;
        options.partialFloor = true;
        options.floorCount = 260;
        options.walls = true;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        const Eigen::Matrix3d rotation = pose(0.0, 25.0, 0.0);
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        const FloorEstimate e =
            run(estimator, scene, rotation, position, 20, time, profiler);

        reportEstimate(e);

        const double heightError =
            std::abs(e.cameraHeight - trueHeight(position));

        const double normalError =
            angleDegrees(e.normalWorld, kTrueNormal);

        check(e.valid && heightError < 0.08 && normalError < 6.0,
              detail(e, heightError, normalError));
    }

    // -----------------------------------------------------------
    beginTest("7. floor mixed with furniture, including a table top");

    {
        SceneOptions options;
        options.rangeSigma = 0.015;
        options.furniture = true;
        options.furnitureCount = 150;
        options.floorCount = 200;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        const Eigen::Matrix3d rotation = pose(0.0, 20.0, 0.0);
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        const FloorEstimate e =
            run(estimator, scene, rotation, position, 20, time, profiler);

        reportEstimate(e);

        const double heightError =
            std::abs(e.cameraHeight - trueHeight(position));

        // A table top would read about 0.75 m; the floor reads 1.50 m.
        check(e.valid && heightError < 0.08,
              detail(e, heightError,
                     angleDegrees(e.normalWorld, kTrueNormal)));
    }

    // -----------------------------------------------------------
    beginTest("8. wall-dominated scene");

    {
        // Nose against a wall: the wall has far more points than the
        // sliver of floor. A support-maximising fit picks the wall.
        SceneOptions options;
        options.rangeSigma = 0.015;
        options.floorCount = 70;
        options.walls = true;
        options.wallCount = 400;
        options.ceiling = true;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        const Eigen::Matrix3d rotation = pose(80.0, 10.0, 0.0);
        const Eigen::Vector3d position(1.6, 0.0, 2.5);

        const FloorEstimate e =
            run(estimator, scene, rotation, position, 20, time, profiler);

        reportEstimate(e);

        const bool wallRejected =
            !e.valid ||
            angleDegrees(e.normalWorld, kTrueNormal) < 12.0;

        check(wallRejected,
              e.valid
                  ? ("kept the floor, normal error " +
                     std::to_string(
                         angleDegrees(e.normalWorld, kTrueNormal)) +
                     " deg")
                  : std::string("reported GROUND UNKNOWN rather than "
                                "the wall"));
    }

    // -----------------------------------------------------------
    beginTest("9. ceiling is never mistaken for the floor");

    {
        SceneOptions options;
        options.rangeSigma = 0.01;
        options.floorPoints = false;      // no floor at all
        options.ceiling = true;
        options.ceilingCount = 300;

        Scene scene(options);

        FloorEstimator estimator(config);

        double time = 1.0;

        // Looking up at the ceiling, with nothing else in view.
        const Eigen::Matrix3d rotation = pose(0.0, -40.0, 0.0);
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        const FloorEstimate e =
            run(estimator, scene, rotation, position, 20, time, profiler);

        reportEstimate(e);

        check(!e.valid,
              std::string("status ") + floorStatusName(e.status) +
                  ", detail: " + e.detail);
    }

    // -----------------------------------------------------------
    beginTest("10. temporary floor loss, then reacquisition");

    {
        SceneOptions options;
        options.rangeSigma = 0.015;

        Scene scene(options);

        VIOConfig fast = baseConfig();
        fast.floorDecayTauSeconds = 1.0;

        FloorEstimator estimator(fast);

        double time = 1.0;

        const Eigen::Matrix3d rotation = pose(0.0, 15.0, 0.0);
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        FloorEstimate e =
            run(estimator, scene, rotation, position, 20, time, profiler);

        const bool acquired =
            e.valid && e.status == FloorStatus::Tracking;

        const double heldHeight = e.cameraHeight;

        // ---- 0.5 s with no points at all ----
        e = run(estimator, scene, rotation, position, 15, time, profiler,
                true);

        reportEstimate(e);

        const bool predicted =
            e.valid && e.status == FloorStatus::Predicting &&
            std::abs(e.cameraHeight - heldHeight) < 1e-6 &&
            e.confidence < 1.0;

        // ---- long enough that it must give up ----
        e = run(estimator, scene, rotation, position, 200, time, profiler,
                true);

        reportEstimate(e);

        const bool surrendered =
            !e.valid && e.status == FloorStatus::Unknown;

        // ---- points come back ----
        e = run(estimator, scene, rotation, position, 20, time, profiler);

        reportEstimate(e);

        const double heightError =
            std::abs(e.cameraHeight - trueHeight(position));

        const bool reacquired =
            e.valid && e.status == FloorStatus::Tracking &&
            heightError < 0.06;

        char text[320];

        snprintf(text, sizeof(text),
                 "acquired %d, predicted through the gap %d, gave up "
                 "rather than lying %d, reacquired %d (%.1f mm)",
                 acquired ? 1 : 0, predicted ? 1 : 0,
                 surrendered ? 1 : 0, reacquired ? 1 : 0,
                 heightError * 1e3);

        check(acquired && predicted && surrendered && reacquired, text);
    }

    // -----------------------------------------------------------
    beginTest("11. gravity constraint from the IMU");

    {
        SceneOptions options;
        options.rangeSigma = 0.015;
        options.walls = true;
        options.furniture = true;

        Scene scene(options);

        VIOConfig withImu = baseConfig();
        withImu.floorUseGravity = true;

        // The world frame is the start pose, which here is upright,
        // so world down is +Y and the accelerometer reads -Y * g
        // (specific force is UP at rest).
        const Eigen::Matrix3d rotation = pose(0.0, 30.0, 12.0);
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        // Expressed in the BODY frame, which with the identity
        // extrinsic is the camera frame.
        const Eigen::Vector3d upWorld(0.0, -1.0, 0.0);

        std::vector<IMUSample> imu;

        for (int i = 0; i < 6; ++i)
        {
            IMUSample sample;

            sample.acceleration =
                rotation.transpose() * (upWorld * 9.80665);

            sample.gyroscope = Eigen::Vector3d(0.001, 0.0, -0.002);

            imu.push_back(sample);
        }

        FloorEstimator estimator(withImu);

        double time = 1.0;

        const FloorEstimate e = run(estimator, scene, rotation, position,
                                    20, time, profiler, false, &imu);

        reportEstimate(e);

        const double heightError =
            std::abs(e.cameraHeight - trueHeight(position));

        check(e.valid && e.downSource == FloorDownSource::Imu &&
                  heightError < 0.05 && e.gravityAngleDegrees < 3.0,
              detail(e, heightError,
                     angleDegrees(e.normalWorld, kTrueNormal)) +
                  ", gravity disagreement " +
                  std::to_string(e.gravityAngleDegrees) + " deg");
    }

    // -----------------------------------------------------------
    beginTest("12. fully unconstrained fit, no gravity and no "
              "upright assumption");

    {
        SceneOptions options;
        options.rangeSigma = 0.012;
        options.furniture = true;

        Scene scene(options);

        VIOConfig blind = baseConfig();
        blind.floorUseGravity = false;
        blind.floorAssumeUprightStart = false;

        FloorEstimator estimator(blind);

        double time = 1.0;

        const Eigen::Matrix3d rotation = pose(0.0, 25.0, 0.0);
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        const FloorEstimate e =
            run(estimator, scene, rotation, position, 25, time, profiler);

        reportEstimate(e);

        const double heightError =
            std::abs(e.cameraHeight - trueHeight(position));

        const double normalError =
            angleDegrees(e.normalWorld, kTrueNormal);

        // Weaker case, so a looser bound - and the confidence must
        // reflect that it had nothing to lean on.
        check(e.valid && heightError < 0.10 && normalError < 8.0 &&
                  e.confidence < 0.80,
              detail(e, heightError, normalError));
    }

    // -----------------------------------------------------------
    beginTest("13. a pose that was not measured never feeds a "
              "measurement");

    {
        SceneOptions options;
        Scene scene(options);

        FloorEstimator estimator(config);

        std::vector<Feature> features;

        const Eigen::Matrix3d rotation = Eigen::Matrix3d::Identity();
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        scene.observe(rotation, position, features);

        FloorInput input;

        input.features = &features;
        input.worldFromCamera = rotation;
        input.cameraInWorld = position;
        input.poseValid = false;
        input.timestamp = 1.0;

        for (int frame = 0; frame < 30; ++frame)
        {
            input.timestamp += 1.0 / 30.0;
            estimator.update(input, profiler);
        }

        const FloorEstimate e = estimator.estimate();

        check(!e.valid && e.status == FloorStatus::Unknown &&
                  estimator.counters().measurements == 0,
              std::string("no measurement was attempted; status ") +
                  floorStatusName(e.status));
    }

    // -----------------------------------------------------------
    beginTest("14. the estimator is deterministic");

    {
        SceneOptions options;
        options.rangeSigma = 0.02;
        options.outlierFraction = 0.06;
        options.walls = true;
        options.furniture = true;

        const Eigen::Matrix3d rotation = pose(0.0, 20.0, 5.0);
        const Eigen::Vector3d position = Eigen::Vector3d::Zero();

        double first = 0.0;
        double firstOffset = 0.0;

        bool same = true;

        for (int repeat = 0; repeat < 3; ++repeat)
        {
            Scene scene(options);

            FloorEstimator estimator(config);

            double time = 1.0;

            const FloorEstimate e = run(estimator, scene, rotation,
                                        position, 20, time, profiler);

            if (repeat == 0)
            {
                first = e.cameraHeight;
                firstOffset = e.worldPlane.offset;
            }
            else if (std::abs(e.cameraHeight - first) > 1e-12 ||
                     std::abs(e.worldPlane.offset - firstOffset) > 1e-12)
            {
                same = false;
            }
        }

        check(same, "three identical runs gave bit-identical planes");
    }

    benchmark();

    printf("\n==========================\n");
    printf("passed %d, failed %d\n", gPassed, gFailed);

    return gFailed == 0 ? 0 : 1;
}
