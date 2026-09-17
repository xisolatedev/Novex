// novex-replay: run a novex-record recording through the real VIO.
//
//   novex-replay DIR [novex-vio flags...]
//
// Uses the VIO class exactly as the daemon does - same tracker, stereo,
// motion, estimator, diagnostics and point map - with the recorded
// camera timestamps. No camera, no IPC, no GUI. Prints the full --debug
// report (and the stationary report with --stationary-test).
//
// Timing figures from a replay measure this machine decoding PNGs, not
// the camera path; compare geometry and drift across replays, and
// performance on live runs.

#include "DebugReporter.hpp"
#include "Log.hpp"
#include "StereoCalibration.hpp"
#include "Time.hpp"
#include "VIO.hpp"
#include "VIOConfig.hpp"

#include <opencv2/imgcodecs.hpp>

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

int main(int argc, char** argv)
{
    using namespace novex;

    if (argc < 2)
    {
        fprintf(stderr, "usage: novex-replay DIR [novex-vio flags]\n");
        return 1;
    }

    const std::string directory = argv[1];

    std::vector<char*> forwarded = { argv[0] };

    for (int i = 2; i < argc; ++i)
    {
        forwarded.push_back(argv[i]);
    }

    VIOConfig config;

    bool shouldExit = false;

    if (!config.parseCommandLine(static_cast<int>(forwarded.size()),
                                 forwarded.data(), shouldExit) ||
        shouldExit)
    {
        return 1;
    }

    config.debugEnabled = true;
    config.ipcEnabled = false;
    config.webEnabled = false;
    config.imuEnabled = false;

    setLogLevel(config.logLevel);

    std::vector<double> timestamps;

    {
        const std::string timesPath = directory + "/times.txt";

        FILE* times = std::fopen(timesPath.c_str(), "r");

        if (times == nullptr)
        {
            fprintf(stderr, "cannot read %s\n", timesPath.c_str());
            return 1;
        }

        int index = 0;
        double stamp = 0.0;

        while (std::fscanf(times, "%d %lf", &index, &stamp) == 2)
        {
            timestamps.push_back(stamp);
        }

        std::fclose(times);
    }

    if (timestamps.empty())
    {
        fprintf(stderr, "recording %s is empty\n", directory.c_str());
        return 1;
    }

    StereoCalibration calibration;

    if (!calibration.load(config.calibrationPath))
    {
        return 1;
    }

    // Two buffers in turn, as the camera does, so the previous frame
    // stays valid for KLT without a copy.
    cv::Mat buffers[2];

    {
        char name[1024];
        snprintf(name, sizeof(name), "%s/00000.png", directory.c_str());
        buffers[0] = cv::imread(name, cv::IMREAD_GRAYSCALE);
    }

    if (buffers[0].empty() || buffers[0].cols % 2 != 0)
    {
        fprintf(stderr, "cannot read the first frame of %s\n",
                directory.c_str());
        return 1;
    }

    const cv::Size eye(buffers[0].cols / 2, buffers[0].rows);

    calibration.setCurrentResolution(eye);

    VIO vio(config, calibration, nullptr);

    if (!vio.initialise(eye))
    {
        return 1;
    }

    const size_t limit = config.maxFrames > 0
        ? std::min(timestamps.size(), static_cast<size_t>(config.maxFrames))
        : timestamps.size();

    for (size_t i = 0; i < limit; ++i)
    {
        cv::Mat& frame = buffers[i % 2];

        if (i > 0)
        {
            char name[1024];
            snprintf(name, sizeof(name), "%s/%05zu.png",
                     directory.c_str(), i);
            frame = cv::imread(name, cv::IMREAD_GRAYSCALE);
        }

        if (frame.empty())
        {
            fprintf(stderr, "frame %zu missing; stopping\n", i);
            break;
        }

        const cv::Mat left = frame(cv::Rect(0, 0, eye.width, eye.height));
        const cv::Mat right =
            frame(cv::Rect(eye.width, 0, eye.width, eye.height));

        vio.processCommands();
        vio.process(left, right, timestamps[i]);
    }

    DebugStatistics final = vio.debug().finalise(monotonicSeconds());

    const VIOSnapshot last = vio.snapshot();

    // Rates from the recording's own timestamps, not from how fast
    // this machine replayed it.
    const double span = timestamps[limit - 1] - timestamps[0];

    final.runtimeSeconds = span;
    final.cameraFPS = span > 0.0 ? (limit - 1) / span : 0.0;
    final.vioFPS = final.cameraFPS;

    final.featureDetectionMs =
        last.stageMilliseconds[static_cast<int>(Stage::Detect)];
    final.featureTrackingMs =
        last.stageMilliseconds[static_cast<int>(Stage::Track)];
    final.stereoMatchingMs =
        last.stageMilliseconds[static_cast<int>(Stage::Stereo)];
    final.motionEstimationMs =
        last.stageMilliseconds[static_cast<int>(Stage::Motion)];
    final.stateEstimationMs =
        last.stageMilliseconds[static_cast<int>(Stage::State)];
    final.stateEstimationMeasured = true;
    final.trackedFeatures = last.state.trackedFeatures;
    final.orientation = last.state.orientation;
    final.stationary = last.stationary;
    final.pointCloudEnabled = last.pointCloudEnabled;
    final.pointMapEnabled = last.pointMapEnabled;
    final.pointCounters = last.pointCounters;
    final.mapCapacity = last.mapCapacity;
    final.voxelSize = last.voxelSize;

    printf("REPLAY of %s: %zu frames, %.2f s of recorded time\n",
           directory.c_str(), limit, span);
    printf("(stage timings below are this machine replaying PNGs)\n\n");

    DebugReporter::print(final);

    return 0;
}
