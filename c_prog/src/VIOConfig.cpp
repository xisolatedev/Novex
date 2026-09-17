#include "VIOConfig.hpp"

#include "Yaml.hpp"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace novex
{

namespace
{

bool parseLogLevel(const std::string& name, LogLevel& out)
{
    if (name == "debug") { out = LogLevel::Debug; return true; }
    if (name == "info")  { out = LogLevel::Info;  return true; }
    if (name == "warn")  { out = LogLevel::Warn;  return true; }
    if (name == "error") { out = LogLevel::Error; return true; }
    if (name == "none")  { out = LogLevel::None;  return true; }

    return false;
}

} // namespace

bool VIOConfig::loadFile(const std::string& path)
{
    Yaml yaml;

    if (!yaml.loadFile(path))
    {
        LOG_ERROR("config: %s", yaml.error().c_str());
        return false;
    }

    const std::string modeName = yaml.getString("mode", "daemon");

    if (modeName == "gui")
    {
        mode = RunMode::Gui;
    }
    else if (modeName == "daemon")
    {
        mode = RunMode::Daemon;
    }
    else
    {
        LOG_ERROR("config: unknown mode '%s'", modeName.c_str());
        return false;
    }

    const std::string levelName = yaml.getString("log_level", "info");

    if (!parseLogLevel(levelName, logLevel))
    {
        LOG_ERROR("config: unknown log_level '%s'", levelName.c_str());
        return false;
    }

    imuEnabled = yaml.getBool("imu.enabled", imuEnabled);

    debugEnabled = yaml.getBool("debug.enabled", debugEnabled);

    webEnabled     = yaml.getBool("web.enabled", webEnabled);
    webHost        = yaml.getString("web.host", webHost);
    webPort        = yaml.getInt("web.port", webPort);
    webUpdateHz    = yaml.getDouble("web.update_hz", webUpdateHz);
    webRoot        = yaml.getString("web.root", webRoot);
    webNodePath    = yaml.getString("web.node_path", webNodePath);
    webAutoStart   = yaml.getBool("web.auto_start", webAutoStart);

    calibrationPath =
        yaml.getString("calibration_path", calibrationPath);

    statsIntervalSeconds =
        yaml.getDouble("stats_interval_s", statsIntervalSeconds);

    cameraDevice     = yaml.getInt("camera.device", cameraDevice);
    cameraWidth      = yaml.getInt("camera.width", cameraWidth);
    cameraHeight     = yaml.getInt("camera.height", cameraHeight);
    cameraFPS        = yaml.getInt("camera.fps", cameraFPS);
    cameraMJPEG      = yaml.getBool("camera.mjpeg", cameraMJPEG);
    cameraDirectGray = yaml.getBool("camera.direct_gray", cameraDirectGray);
    cameraSwapEyes   = yaml.getBool("camera.swap_eyes", cameraSwapEyes);

    maxFrameDrop = yaml.getInt("camera.max_frame_drop", maxFrameDrop);

    cameraBufferSize =
        yaml.getInt("camera.buffer_size", cameraBufferSize);

    maxFeatures       = yaml.getInt("features.max", maxFeatures);
    redetectRatio     = yaml.getDouble("features.redetect_ratio", redetectRatio);
    gridCols          = yaml.getInt("features.grid_cols", gridCols);
    gridRows          = yaml.getInt("features.grid_rows", gridRows);
    minFeatureDistance= yaml.getDouble("features.min_distance", minFeatureDistance);
    detectorQuality   = yaml.getDouble("features.quality", detectorQuality);
    klWindowSize      = yaml.getInt("features.klt_window", klWindowSize);
    klPyramidLevels   = yaml.getInt("features.klt_levels", klPyramidLevels);

    forwardBackwardThreshold =
        yaml.getDouble("features.fb_threshold_px", forwardBackwardThreshold);

    stereoEnabled = yaml.getBool("stereo.enabled", stereoEnabled);

    stereoEpipolarThresholdPx =
        yaml.getDouble("stereo.epipolar_threshold_px",
                       stereoEpipolarThresholdPx);

    if (yaml.has("stereo.epipolar_threshold"))
    {
        // Deliberately not converted: the old value lived on the
        // normalised plane, where its meaning varied ~13x across the
        // fisheye, so there is no single equivalent angle.
        LOG_WARN(
            "config: stereo.epipolar_threshold (normalised units) is "
            "no longer used; set stereo.epipolar_threshold_px instead"
        );
    }

    stereoForwardBackwardThreshold =
        yaml.getDouble("stereo.fb_threshold_px",
                       stereoForwardBackwardThreshold);

    minDepthMeters = yaml.getDouble("stereo.min_depth_m", minDepthMeters);
    maxDepthMeters = yaml.getDouble("stereo.max_depth_m", maxDepthMeters);

    minInliersForTracking =
        yaml.getInt("motion.min_inliers", minInliersForTracking);

    ransacReprojectionError =
        yaml.getDouble("motion.ransac_error", ransacReprojectionError);

    ransacIterations = yaml.getInt("motion.ransac_iterations", ransacIterations);
    ransacConfidence = yaml.getDouble("motion.ransac_confidence", ransacConfidence);

    motionInlierThresholdPx =
        yaml.getDouble("motion.inlier_threshold_px", motionInlierThresholdPx);

    motionRefineIterations =
        yaml.getInt("motion.refine_iterations", motionRefineIterations);

    keyframeRetention =
        yaml.getDouble("motion.keyframe_retention", keyframeRetention);

    keyframeMaxSpan =
        yaml.getInt("motion.keyframe_max_span", keyframeMaxSpan);

    stationaryTestEnabled =
        yaml.getBool("diagnostics.stationary_test", stationaryTestEnabled);

    pointCloudEnabled = yaml.getBool("pointcloud.enabled", pointCloudEnabled);
    pointMapEnabled = yaml.getBool("pointcloud.map_enabled", pointMapEnabled);

    pointCloudMaxPoints =
        yaml.getInt("pointcloud.max_points", pointCloudMaxPoints);

    pointCloudVoxelSize =
        yaml.getDouble("pointcloud.voxel_size_m", pointCloudVoxelSize);

    pointCloudMaxDepth =
        yaml.getDouble("pointcloud.max_depth_m", pointCloudMaxDepth);

    pointCloudMaxDepthSigma =
        yaml.getDouble("pointcloud.max_depth_sigma", pointCloudMaxDepthSigma);

    pointCloudMaxStereoResidualPx =
        yaml.getDouble("pointcloud.max_stereo_residual_px",
                       pointCloudMaxStereoResidualPx);

    pointCloudMinTrackAge =
        yaml.getInt("pointcloud.min_track_age", pointCloudMinTrackAge);

    pointCloudRequireInlier =
        yaml.getBool("pointcloud.require_motion_inlier",
                     pointCloudRequireInlier);

    pointCloudPublishHz =
        yaml.getDouble("pointcloud.publish_hz", pointCloudPublishHz);

    imuBackend    = yaml.getString("imu.backend", imuBackend);
    imuDevicePath = yaml.getString("imu.device_path", imuDevicePath);
    imuRateHz     = yaml.getInt("imu.rate_hz", imuRateHz);
    imuBufferSize = yaml.getInt("imu.buffer_size", imuBufferSize);

    imuPropagateOnLoss =
        yaml.getBool("imu.propagate_on_loss", imuPropagateOnLoss);

    imuStaticGyroThreshold =
        yaml.getDouble("imu.static_gyro_threshold",
                       imuStaticGyroThreshold);

    const std::vector<double> cameraFromBody =
        yaml.getVector("imu.R_camera_from_body");

    if (!cameraFromBody.empty())
    {
        if (cameraFromBody.size() != 9)
        {
            LOG_ERROR(
                "config: imu.R_camera_from_body needs 9 values, got %zu",
                cameraFromBody.size()
            );

            return false;
        }

        for (size_t i = 0; i < 9; ++i)
        {
            imuRotationCameraFromBody[i] = cameraFromBody[i];
        }
    }

    ipcEnabled    = yaml.getBool("ipc.enabled", ipcEnabled);
    ipcSocketPath = yaml.getString("ipc.socket_path", ipcSocketPath);
    ipcMaxClients = yaml.getInt("ipc.max_clients", ipcMaxClients);

    guiShowFeatures = yaml.getBool("gui.show_features", guiShowFeatures);
    guiShowRight    = yaml.getBool("gui.show_right", guiShowRight);

    LOG_INFO("config: loaded %s", path.c_str());

    return true;
}

void VIOConfig::printUsage()
{
    printf(
        "novex-vio - lightweight stereo visual-inertial odometry\n"
        "\n"
        "Usage: novex-vio [options]\n"
        "\n"
        "  --config PATH        configuration file\n"
        "                       (default config/novex_vio.yaml,\n"
        "                        skipped without error if absent)\n"
        "  --calibration PATH   stereo calibration file\n"
        "  --mode gui|daemon    execution mode (default daemon)\n"
        "  --imu                enable the IMU subsystem\n"
        "  --no-imu             disable the IMU subsystem\n"
        "  --imu-backend NAME   none | iio\n"
        "  --imu-device PATH    IIO device directory\n"
        "  --device N           camera index (default 0)\n"
        "  --width N            combined stereo frame width\n"
        "  --height N           combined stereo frame height\n"
        "  --fps N              requested capture rate\n"
        "  --no-mjpeg           do not request MJPG\n"
        "  --features N         target feature count\n"
        "  --no-stereo          disable stereo depth\n"
        "  --socket PATH        IPC socket path\n"
        "  --no-ipc             do not start the IPC server\n"
        "\n"
        "  --keyframe-retention R  new keyframe below this inlier\n"
        "                       retention (0 = frame-to-frame)\n"
        "  --stationary-test    collect drift statistics assuming the\n"
        "                       camera is NOT moved (observes only)\n"
        "  --no-pointcloud      do not build 3D point snapshots\n"
        "  --no-point-map       live points only, no accumulated map\n"
        "  --map-points N       point map budget (default 20000)\n"
        "  --voxel-size M       map voxel edge in metres, 0 = off\n"
        "\n"
        "  --debug              Enable detailed runtime diagnostics\n"
        "                       (per-stage timing, percentiles, and a\n"
        "                        report printed on exit)\n"
        "  --web                Enable local web visualization\n"
        "                       (Node.js + Three.js dashboard on\n"
        "                        http://127.0.0.1:8080)\n"
        "  --web-port N         dashboard port (default 8080)\n"
        "  --web-host ADDR      dashboard bind address\n"
        "                       (default 127.0.0.1; do not expose\n"
        "                        this to a network you do not trust)\n"
        "  --no-web-autostart   do not spawn Node; serve state only\n"
        "  --max-frames N       stop after N processed frames\n"
        "  --log LEVEL          debug | info | warn | error | none\n"
        "  --help               this message\n"
        "\n"
        "Examples:\n"
        "  novex-vio --mode daemon --no-imu\n"
        "  novex-vio --mode daemon --imu\n"
        "  novex-vio --mode gui --no-imu\n"
        "  novex-vio --debug\n"
        "  novex-vio --web\n"
        "  novex-vio --debug --web\n"
    );
}

bool VIOConfig::parseCommandLine(int argc, char** argv, bool& shouldExit)
{
    shouldExit = false;

    // The config file is resolved in a first pass, so that explicit
    // flags always win over whatever the file said regardless of the
    // order they appear in.
    for (int i = 1; i < argc; ++i)
    {
        if (std::strcmp(argv[i], "--help") == 0 ||
            std::strcmp(argv[i], "-h") == 0)
        {
            printUsage();
            shouldExit = true;
            return true;
        }

        if (std::strcmp(argv[i], "--config") == 0 && i + 1 < argc)
        {
            configPath = argv[++i];
        }
    }

    if (!configPath.empty())
    {
        Yaml probe;

        if (probe.loadFile(configPath))
        {
            if (!loadFile(configPath))
            {
                return false;
            }
        }
        else
        {
            // A missing config file is not an error: the defaults are
            // a working configuration. A malformed one is.
            LOG_INFO(
                "config: %s not read (%s); using defaults",
                configPath.c_str(),
                probe.error().c_str()
            );
        }
    }

    for (int i = 1; i < argc; ++i)
    {
        const char* arg = argv[i];

        auto needsValue = [&](const char* name) -> bool
        {
            if (std::strcmp(arg, name) != 0)
            {
                return false;
            }

            if (i + 1 >= argc)
            {
                LOG_ERROR("config: %s needs a value", name);
                return false;
            }

            return true;
        };

        if (std::strcmp(arg, "--config") == 0)
        {
            ++i;   // already handled
        }
        else if (needsValue("--calibration"))
        {
            calibrationPath = argv[++i];
        }
        else if (std::strcmp(arg, "--mode") == 0 && i + 1 < argc)
        {
            const std::string value = argv[++i];

            if (value == "gui")
            {
                mode = RunMode::Gui;
            }
            else if (value == "daemon")
            {
                mode = RunMode::Daemon;
            }
            else
            {
                LOG_ERROR("config: --mode must be gui or daemon");
                return false;
            }
        }
        else if (std::strcmp(arg, "--imu") == 0)
        {
            imuEnabled = true;
        }
        else if (std::strcmp(arg, "--no-imu") == 0)
        {
            imuEnabled = false;
        }
        else if (needsValue("--imu-backend"))
        {
            imuBackend = argv[++i];
        }
        else if (needsValue("--imu-device"))
        {
            imuDevicePath = argv[++i];
        }
        else if (needsValue("--device"))
        {
            cameraDevice = std::atoi(argv[++i]);
        }
        else if (needsValue("--width"))
        {
            cameraWidth = std::atoi(argv[++i]);
        }
        else if (needsValue("--height"))
        {
            cameraHeight = std::atoi(argv[++i]);
        }
        else if (needsValue("--fps"))
        {
            cameraFPS = std::atoi(argv[++i]);
        }
        else if (std::strcmp(arg, "--no-mjpeg") == 0)
        {
            cameraMJPEG = false;
        }
        else if (needsValue("--features"))
        {
            maxFeatures = std::atoi(argv[++i]);
        }
        else if (std::strcmp(arg, "--no-stereo") == 0)
        {
            stereoEnabled = false;
        }
        else if (needsValue("--socket"))
        {
            ipcSocketPath = argv[++i];
        }
        else if (std::strcmp(arg, "--no-ipc") == 0)
        {
            ipcEnabled = false;
        }
        else if (needsValue("--keyframe-retention"))
        {
            keyframeRetention = std::atof(argv[++i]);
        }
        else if (std::strcmp(arg, "--stationary-test") == 0)
        {
            stationaryTestEnabled = true;
        }
        else if (std::strcmp(arg, "--no-pointcloud") == 0)
        {
            pointCloudEnabled = false;
        }
        else if (std::strcmp(arg, "--no-point-map") == 0)
        {
            pointMapEnabled = false;
        }
        else if (needsValue("--map-points"))
        {
            pointCloudMaxPoints = std::atoi(argv[++i]);
        }
        else if (needsValue("--voxel-size"))
        {
            pointCloudVoxelSize = std::atof(argv[++i]);
        }
        else if (std::strcmp(arg, "--debug") == 0)
        {
            debugEnabled = true;
        }
        else if (std::strcmp(arg, "--no-debug") == 0)
        {
            debugEnabled = false;
        }
        else if (std::strcmp(arg, "--web") == 0)
        {
            webEnabled = true;
        }
        else if (std::strcmp(arg, "--no-web") == 0)
        {
            webEnabled = false;
        }
        else if (needsValue("--web-port"))
        {
            webPort = std::atoi(argv[++i]);
        }
        else if (needsValue("--web-host"))
        {
            webHost = argv[++i];
        }
        else if (needsValue("--web-root"))
        {
            webRoot = argv[++i];
        }
        else if (std::strcmp(arg, "--no-web-autostart") == 0)
        {
            webAutoStart = false;
        }
        else if (needsValue("--max-frames"))
        {
            maxFrames = std::atoi(argv[++i]);
        }
        else if (std::strcmp(arg, "--log") == 0 && i + 1 < argc)
        {
            if (!parseLogLevel(argv[++i], logLevel))
            {
                LOG_ERROR("config: unknown log level '%s'", argv[i]);
                return false;
            }
        }
        else
        {
            LOG_ERROR("config: unrecognised argument '%s'", arg);
            printUsage();
            return false;
        }
    }

    applyDerived();

    return validate();
}

void VIOConfig::applyDerived()
{
    guiEnabled = (mode == RunMode::Gui);

    // The web server reaches the pipeline through the same IPC socket
    // everything else uses, so asking for --web without IPC is a
    // contradiction. Resolve it in favour of what was asked for
    // rather than silently starting a dashboard that shows nothing.
    if (webEnabled && !ipcEnabled)
    {
        LOG_WARN(
            "config: --web needs the IPC socket; re-enabling it"
        );

        ipcEnabled = true;
    }

    if (imuBackend == "none")
    {
        imuEnabled = false;
    }
}

bool VIOConfig::validate() const
{
    if (cameraWidth <= 0 || cameraHeight <= 0)
    {
        LOG_ERROR("config: camera resolution must be positive");
        return false;
    }

    if (cameraWidth % 2 != 0)
    {
        LOG_ERROR(
            "config: combined stereo width %d is odd and cannot be "
            "split into two equal eyes",
            cameraWidth
        );

        return false;
    }

    if (cameraFPS <= 0)
    {
        LOG_ERROR("config: camera fps must be positive");
        return false;
    }

    if (maxFeatures < 20)
    {
        LOG_ERROR(
            "config: features.max = %d is too low to estimate motion",
            maxFeatures
        );

        return false;
    }

    if (gridCols < 1 || gridRows < 1)
    {
        LOG_ERROR("config: feature grid must be at least 1x1");
        return false;
    }

    if (klPyramidLevels < 1 || klWindowSize < 5)
    {
        LOG_ERROR("config: invalid KLT parameters");
        return false;
    }

    if (webEnabled)
    {
        if (webPort < 1 || webPort > 65535)
        {
            LOG_ERROR("config: --web-port %d is out of range", webPort);
            return false;
        }

        if (webUpdateHz <= 0.0 || webUpdateHz > 120.0)
        {
            LOG_ERROR(
                "config: web.update_hz must be between 0 and 120"
            );

            return false;
        }
    }

    if (minDepthMeters <= 0.0 || maxDepthMeters <= minDepthMeters)
    {
        LOG_ERROR("config: stereo depth range is inverted or invalid");
        return false;
    }

    if (keyframeRetention < 0.0 || keyframeRetention >= 1.0 ||
        keyframeMaxSpan < 1)
    {
        LOG_ERROR(
            "config: motion.keyframe_retention must be in [0, 1) and "
            "keyframe_max_span >= 1"
        );

        return false;
    }

    if (!(stereoEpipolarThresholdPx > 0.0) ||
        !(motionInlierThresholdPx > 0.0))
    {
        LOG_ERROR("config: stereo / motion angular thresholds must be > 0");
        return false;
    }

    if (pointCloudEnabled)
    {
        // Upper bound keeps a single map message and the browser's
        // buffers within reason on a 512 MB board.
        if (pointCloudMaxPoints < 100 || pointCloudMaxPoints > 500000)
        {
            LOG_ERROR(
                "config: pointcloud.max_points must be 100..500000"
            );

            return false;
        }

        if (pointCloudVoxelSize < 0.0 ||
            !(pointCloudPublishHz > 0.0) || pointCloudPublishHz > 60.0)
        {
            LOG_ERROR(
                "config: pointcloud.voxel_size_m must be >= 0 and "
                "publish_hz 0..60"
            );

            return false;
        }
    }

    return true;
}

void VIOConfig::logSummary() const
{
    LOG_INFO(
        "config: mode=%s imu=%s stereo=%s ipc=%s",
        (mode == RunMode::Gui) ? "gui" : "daemon",
        imuEnabled ? "enabled" : "disabled",
        stereoEnabled ? "enabled" : "disabled",
        ipcEnabled ? ipcSocketPath.c_str() : "disabled"
    );

    LOG_INFO(
        "config: camera device %d, %dx%d @ %d fps, %s, %s decode",
        cameraDevice,
        cameraWidth,
        cameraHeight,
        cameraFPS,
        cameraMJPEG ? "MJPG" : "default format",
        cameraDirectGray ? "direct-grayscale" : "bgr"
    );

    LOG_INFO(
        "config: up to %d features on a %dx%d grid",
        maxFeatures,
        gridCols,
        gridRows
    );

    if (debugEnabled || webEnabled)
    {
        LOG_INFO(
            "config: debug diagnostics %s, web dashboard %s",
            debugEnabled ? "ON" : "off",
            webEnabled ? "ON" : "off"
        );
    }
}

} // namespace novex
