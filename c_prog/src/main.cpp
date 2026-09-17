#include "Camera.hpp"
#include "DebugReporter.hpp"
#include "Gui.hpp"
#include "IMU.hpp"
#include "Log.hpp"
#include "StateServer.hpp"
#include "StereoCalibration.hpp"
#include "Time.hpp"
#include "VIO.hpp"
#include "VIOConfig.hpp"
#include "WebServer.hpp"

#include <algorithm>
#include <csignal>
#include <cstring>
#include <cstdio>
#include <memory>

namespace
{

volatile sig_atomic_t gStopRequested = 0;

void handleSignal(int signalNumber)
{
    // Async-signal-safe: set a flag and return. Everything else -
    // closing the camera, joining threads, unlinking the socket -
    // happens on the main thread once the loop notices.
    (void)signalNumber;

    gStopRequested = 1;
}

void installSignalHandlers()
{
    struct sigaction action;

    std::memset(&action, 0, sizeof(action));

    action.sa_handler = handleSignal;

    sigaction(SIGINT, &action, nullptr);
    sigaction(SIGTERM, &action, nullptr);

    // A hung-up terminal must not kill a daemon started over SSH.
    signal(SIGHUP, SIG_IGN);
}

} // namespace

int main(int argc, char** argv)
{
    using namespace novex;

    VIOConfig config;

    bool shouldExit = false;

    if (!config.parseCommandLine(argc, argv, shouldExit))
    {
        return 1;
    }

    if (shouldExit)
    {
        return 0;
    }

    setLogLevel(config.logLevel);

    LOG_INFO("novex-vio starting");

    config.logSummary();

    installSignalHandlers();

    // ---- calibration ----

    StereoCalibration calibration;

    if (!calibration.load(config.calibrationPath))
    {
        LOG_ERROR(
            "fatal: no usable stereo calibration at '%s'",
            config.calibrationPath.c_str()
        );

        return 1;
    }

    // ---- camera ----

    Camera camera(config);

    if (!camera.open())
    {
        LOG_ERROR("fatal: camera unavailable");
        return 1;
    }

    // The calibration is adapted to the mode the camera actually
    // negotiated, not the one that was requested. If the driver gave
    // us something else, this is where that gets accounted for rather
    // than corrupting every subsequent measurement.
    if (!calibration.setCurrentResolution(camera.eyeSize()))
    {
        LOG_ERROR("fatal: cannot adapt the calibration to this mode");
        return 1;
    }

    if (logLevel() <= LogLevel::Debug)
    {
        fputs(calibration.describe().c_str(), stderr);
    }

    // ---- IMU (optional) ----

    IMU imu(config);

    if (!imu.start())
    {
        LOG_ERROR("fatal: IMU was requested and failed to start");
        return 1;
    }

    // ---- pipeline ----

    VIO vio(config, calibration, &imu);

    if (!vio.initialise(camera.eyeSize()))
    {
        LOG_ERROR("fatal: VIO initialisation failed");
        return 1;
    }

    StateServer server(config, vio);

    server.attachCamera(&camera);

    if (!server.start())
    {
        LOG_ERROR("fatal: IPC server failed to start");
        return 1;
    }

    // ---- web dashboard (optional) ----

    WebServer web(config);

    if (!web.start())
    {
        LOG_ERROR("fatal: web server failed to start");
        return 1;
    }

    std::unique_ptr<Gui> gui;

    if (config.guiEnabled)
    {
        gui.reset(new Gui(config));

        if (!gui->open())
        {
            LOG_WARN("gui: continuing without a window");
        }
    }

    LOG_INFO("novex-vio running; SIGINT or SIGTERM to stop");

    // ---- main loop ----

    const double framePeriod = 1.0 / config.cameraFPS;

    double nextStatsTime = monotonicSeconds() + config.statsIntervalSeconds;

    int consecutiveFailures = 0;
    int processedFrames = 0;

    // Learned floor for how stale a frame is by the time it has been
    // processed. Starts high so the first frames are never treated as
    // a backlog.
    double baselineLag = 1e9;

    bool running = true;

    while (running && gStopRequested == 0)
    {
        // Drained every iteration, including while paused - otherwise
        // a queued RESUME would never be seen and the daemon would be
        // stuck. This is the only place estimator state is mutated
        // from outside the pipeline.
        vio.processCommands();

        web.poll();

        bool grabbed = false;

        {
            ScopedStage captureTiming(vio.profiler(), Stage::Capture);

            grabbed = camera.grab();
        }

        if (grabbed)
        {
            // Reported separately from the capture stage above, which
            // is dominated by waiting for the sensor. This is the part
            // that actually costs CPU.
            Profiler& profiler = vio.profiler();

            profiler.begin(Stage::Decode);
            profiler.endWith(
                Stage::Decode,
                camera.status().lastDecodeSeconds
            );
        }

        if (!grabbed)
        {
            ++consecutiveFailures;

            // A single empty frame is normal on a USB camera. A long
            // run of them means the device has gone away, and looping
            // forever on a dead camera is not "graceful".
            if (consecutiveFailures >= 60)
            {
                LOG_ERROR(
                    "camera: %d consecutive failed frames; giving up",
                    consecutiveFailures
                );

                break;
            }

            LOG_WARN_EVERY(2.0, "camera: frame grab failed");

            vio.noteFailedFrame();

            continue;
        }

        consecutiveFailures = 0;

        if (vio.isPaused())
        {
            // Frames are still grabbed while paused, deliberately.
            // Stopping the grab would let the driver's queue fill and
            // turn resume into a burst of stale frames; discarding
            // them keeps the stream healthy and resume instant.
            if (gui)
            {
                if (!gui->draw(camera, vio))
                {
                    running = false;
                }
            }

            continue;
        }

        vio.process(
            camera.getLeftImage(),
            camera.getRightImage(),
            camera.getTimestamp()
        );

        ++processedFrames;

        if (gui)
        {
            if (!gui->draw(camera, vio))
            {
                LOG_INFO("gui: quit requested");
                running = false;
            }
        }

        // Overload handling.
        //
        // The question is whether frames are QUEUEING UP in the
        // driver, not whether the newest state is old. Those are
        // different: even a pipeline that comfortably keeps up
        // reports a lag of decode plus processing time, because the
        // frame is timestamped when the sensor captured it and read
        // out only after the work is done. Measured here that floor
        // is around 50 ms, so a fixed "lag above 1.5 frame periods
        // means behind" rule fires on every single frame and throws
        // away good ones - it halved the throughput to 15 fps before
        // this was measured.
        //
        // So the baseline lag is learned instead. The minimum lag
        // seen is the pipeline's inherent latency; anything more than
        // one further frame period above it is a genuine backlog.
        // The floor is allowed to creep upward slowly so that a
        // permanent slowdown is eventually accepted as the new
        // normal rather than causing perpetual dropping.
        {
            const double lag =
                monotonicSeconds() - camera.getTimestamp();

            baselineLag = std::min(lag, baselineLag + 0.0005);

            if (config.maxFrameDrop > 0)
            {
                const double excess = lag - baselineLag;

                if (excess > framePeriod)
                {
                    const int behind =
                        static_cast<int>(excess / framePeriod);

                    const int dropped = camera.dropQueuedFrames(
                        std::min(config.maxFrameDrop, behind)
                    );

                    vio.noteDroppedFrames(dropped);

                    if (dropped > 0)
                    {
                        LOG_WARN_EVERY(
                            5.0,
                            "pipeline: %.1f ms behind its %.1f ms "
                            "baseline, dropped %d stale frame(s)",
                            lag * 1e3,
                            baselineLag * 1e3,
                            dropped
                        );
                    }
                }
            }
        }

        const double now = monotonicSeconds();

        if (now >= nextStatsTime)
        {
            nextStatsTime = now + config.statsIntervalSeconds;

            char summary[512];

            vio.profiler().formatSummary(summary, sizeof(summary));

            const VIOState& state = vio.state();

            LOG_INFO("perf: %s", summary);

            LOG_INFO(
                "state: %s  features %d  inliers %d  stereo %d  "
                "pos % .3f % .3f % .3f  dropped %llu",
                state.tracking ? "tracking" : "LOST",
                state.trackedFeatures,
                state.inlierFeatures,
                state.stereoFeatures,
                state.position.x(),
                state.position.y(),
                state.position.z(),
                static_cast<unsigned long long>(state.droppedFrames)
            );

            const FrameDiagnostics& g = vio.diagnostics();

            LOG_INFO(
                "geometry: flow %.2f px  depth %.2f m  disparity %.1f px  "
                "reproj %.3f px  inliers %d/%d  rel %.3f deg %.2f mm  "
                "rejected motion %llu",
                g.flowMedianPx,
                g.depthMedian,
                g.disparityMedianPx,
                g.reprojectionMedianPx,
                g.inliers,
                g.correspondences,
                g.relativeRotationDeg,
                g.relativeTranslationM * 1e3,
                static_cast<unsigned long long>(g.motionRejectedTotal)
            );
        }

        if (config.maxFrames > 0 && processedFrames >= config.maxFrames)
        {
            LOG_INFO(
                "reached --max-frames %d; stopping",
                config.maxFrames
            );

            running = false;
        }
    }

    if (gStopRequested != 0)
    {
        LOG_INFO("signal received; shutting down");
    }

    // Ordered teardown. The dashboard goes first so it stops asking
    // for state before the state stops existing, then clients, then
    // the sampling thread, then the device.
    web.stop();
    server.stop();
    imu.stop();

    if (gui)
    {
        gui->close();
    }

    camera.close();

    LOG_INFO(
        "novex-vio stopped after %d processed frames "
        "(%llu captured, %llu dropped, %llu failed)",
        processedFrames,
        static_cast<unsigned long long>(camera.status().framesCaptured),
        static_cast<unsigned long long>(camera.status().framesDropped),
        static_cast<unsigned long long>(camera.status().framesFailed)
    );

    // The debug report is printed exactly once, here, on the single
    // exit path. Every earlier `return 1` is a start-up failure, where
    // there is nothing measured to report.
    // Without --debug the stationary test still reports: it is its
    // own diagnostic. With --debug it is part of the full report.
    if (!config.debugEnabled &&
        (config.stationaryTestEnabled || vio.stationaryReport().haveData))
    {
        DebugReporter::printStationary(vio.stationaryReport());
    }

    if (config.debugEnabled)
    {
        DebugStatistics final =
            vio.debug().finalise(monotonicSeconds());

        // Fill in the figures the collector does not own from the
        // final live snapshot, so the report and the dashboard agree.
        const VIOSnapshot last = vio.snapshot();

        final.cameraFPS = last.captureFPS;

        final.captureMs =
            last.stageMilliseconds[static_cast<int>(Stage::Capture)];
        final.decodeMs =
            last.stageMilliseconds[static_cast<int>(Stage::Decode)];
        final.featureDetectionMs =
            last.stageMilliseconds[static_cast<int>(Stage::Detect)];
        final.featureTrackingMs =
            last.stageMilliseconds[static_cast<int>(Stage::Track)];
        final.stereoMatchingMs =
            last.stageMilliseconds[static_cast<int>(Stage::Stereo)];
        final.motionEstimationMs =
            last.stageMilliseconds[static_cast<int>(Stage::Motion)];
        final.imuProcessingMs =
            last.stageMilliseconds[static_cast<int>(Stage::Imu)];

        final.stateEstimationMs =
            last.stageMilliseconds[static_cast<int>(Stage::State)];
        final.stateEstimationMeasured = true;

        final.trackedFeatures = last.state.trackedFeatures;
        final.stereoMatchesCurrent = last.stereoTriangulated;
        final.orientation = last.state.orientation;

        final.stationary = last.stationary;

        final.pointCloudEnabled = last.pointCloudEnabled;
        final.pointMapEnabled = last.pointMapEnabled;
        final.pointCounters = last.pointCounters;
        final.mapCapacity = last.mapCapacity;
        final.voxelSize = last.voxelSize;

        DebugReporter::print(final);
    }

    return 0;
}
