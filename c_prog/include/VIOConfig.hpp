#pragma once

#include "Log.hpp"

#include <array>
#include <string>

namespace novex
{

enum class RunMode
{
    Daemon,   // default: headless, no display, IPC server
    Gui       // development only
};

// Every runtime knob lives here, so that the four required
// combinations - GUI/daemon x IMU/no-IMU - and everything else are
// selected at run time and never require a rebuild.
//
// Precedence: built-in defaults, then the config file, then the
// command line.
struct VIOConfig
{
    // ---- execution ----

    RunMode mode = RunMode::Daemon;

    bool imuEnabled = false;   // off unless asked for; no hardware assumed
    bool guiEnabled = false;   // derived from mode

    LogLevel logLevel = LogLevel::Info;

    // --debug: collect detailed per-frame diagnostics and print a
    // report on exit. Off by default so the normal run pays nothing
    // for it.
    bool debugEnabled = false;

    // --web: start the Node.js visualisation server as a managed
    // child process and stream state to it.
    bool webEnabled = false;

    std::string configPath = "config/novex_vio.yaml";
    std::string calibrationPath = "config/stereo_calibration.yaml";

    // How often the daemon prints a performance line. Never per frame.
    double statsIntervalSeconds = 5.0;

    // Stop after this many processed frames; 0 means run forever.
    // Used by the self-test and for bounded benchmark runs.
    int maxFrames = 0;

    // ---- camera ----

    int cameraDevice = 0;

    // The combined side-by-side frame. Left eye is the left half.
    int cameraWidth = 1280;
    int cameraHeight = 480;
    int cameraFPS = 30;

    bool cameraMJPEG = true;

    // Decode MJPG straight to grayscale instead of to BGR and then
    // converting. Measured on the development machine: 4.18 ms vs
    // 6.00 ms per 1280x480 frame. Colour is never used by the
    // pipeline; only the GUI wants it, and it can live without it.
    bool cameraDirectGray = true;

    bool cameraSwapEyes = false;

    // V4L2 queue depth. 0 leaves it to the driver, which is the right
    // default: forcing it to 1 halves the frame rate on this camera.
    // See the note in Camera::applyFormat.
    int cameraBufferSize = 0;

    // ---- overload handling ----

    // When processing falls behind, discard queued frames rather than
    // working through a growing backlog. 0 disables dropping.
    int maxFrameDrop = 3;

    // ---- features ----

    int maxFeatures = 400;

    // Re-detect once tracking falls below this fraction of maxFeatures.
    double redetectRatio = 0.6;

    int gridCols = 8;
    int gridRows = 6;

    double minFeatureDistance = 12.0;
    double detectorQuality = 0.01;

    int klWindowSize = 21;
    int klPyramidLevels = 3;

    // Forward-backward consistency threshold in pixels. A track that
    // does not return to within this distance of where it started is
    // discarded.
    double forwardBackwardThreshold = 1.0;

    // ---- stereo ----

    bool stereoEnabled = true;

    // How far the left and right rays may miss each other, as an
    // ANGLE expressed in centre-of-image pixels. Angular so it means
    // the same thing at the centre and at the edge of the fisheye; the
    // old normalised-plane threshold was ~13x stricter in the corners
    // than in the middle.
    double stereoEpipolarThresholdPx = 2.5;

    // Forward-backward threshold for the left-right match. Looser than
    // the temporal one on purpose: the two images come from different
    // lenses with different local distortion, so a patch is never
    // quite the same shape in both.
    double stereoForwardBackwardThreshold = 1.5;
    double minDepthMeters = 0.15;
    double maxDepthMeters = 25.0;

    // ---- motion ----

    int    minInliersForTracking = 12;

    // RANSAC hypothesis threshold, normalised camera units. Only used
    // to propose a pose; final inliers are chosen by angle below.
    double ransacReprojectionError = 0.004;
    int    ransacIterations = 100;
    double ransacConfidence = 0.99;

    // Final inlier threshold, as an angle in centre-of-image pixels.
    double motionInlierThresholdPx = 1.5;

    // Gauss-Newton iterations per refinement round.
    int    motionRefineIterations = 8;

    // Keyframe-relative estimation. Motion is estimated against the 3D
    // points of a KEYFRAME rather than of the previous frame; a new
    // keyframe is taken when the inliers still linking to it fall below
    // this fraction of the inliers of its first estimate, or when it is
    // keyframeMaxSpan frames old. 0 = frame-to-frame (every frame is a
    // keyframe), which integrates every frame's error.
    double keyframeRetention = 0.7;
    int    keyframeMaxSpan = 300;

    // ---- diagnostics ----

    // --stationary-test: collect drift statistics from start-up, on
    // the assumption the camera is not being moved. It only OBSERVES;
    // it never suppresses or alters motion.
    bool stationaryTestEnabled = false;

    // ---- point cloud ----

    // Live stereo points are published every frame they exist; this
    // only controls whether the snapshot is built at all.
    bool pointCloudEnabled = true;

    // Accumulate points into a world-space map.
    bool pointMapEnabled = true;

    // Hard budget on map size. When full, the stalest, lowest-quality
    // points are evicted.
    int pointCloudMaxPoints = 20000;

    // Voxel edge for deduplication, metres. 0 disables voxelisation
    // and the map becomes a plain ring of the most recent points.
    double pointCloudVoxelSize = 0.03;

    // Quality gates for adding a point to the MAP. The live view shows
    // every stereo point regardless - it is a diagnostic.
    double pointCloudMaxDepth = 6.0;           // metres
    double pointCloudMaxDepthSigma = 0.15;     // relative, at 1 px
    // Defaults to the stereo matcher's own gate, i.e. no extra cut:
    // on this rig the median ray miss is ~1.3 px (a calibration
    // offset, see the geometry audit), and a tighter map gate would
    // discard most of the scene.
    double pointCloudMaxStereoResidualPx = 2.5;
    int    pointCloudMinTrackAge = 1;          // frames
    bool   pointCloudRequireInlier = true;     // motion inlier

    // Rate at which point snapshots are handed to the IPC server.
    // Independent of the VIO rate.
    double pointCloudPublishHz = 15.0;

    // ---- floor / ground estimation ----
    //
    // Estimates the ground plane from the stereo points the pipeline
    // already produces. Runs at its own rate; see FloorEstimator.hpp
    // for the frames and the plane convention.

    bool floorEnabled = true;

    // Rate of the full measurement cycle. Prediction still runs every
    // frame, and costs almost nothing. 6 Hz is plenty for a floor:
    // it does not move.
    double floorUpdateHz = 6.0;

    // Hard cap on the points one measurement considers. Candidates
    // beyond this are decimated deterministically.
    int floorMaxPoints = 300;

    // ---- candidate gates ----
    double floorMinDepth = 0.25;              // metres
    double floorMaxDepth = 6.0;
    double floorMaxDepthSigma = 0.15;         // relative, at 1 px
    double floorMaxStereoResidualPx = 2.5;
    int    floorMinTrackAge = 1;              // frames
    bool   floorRequireMotionInlier = false;

    // ---- acquisition ----

    // Bin width of the height histogram used when an up direction is
    // known, metres.
    double floorHeightBinM = 0.05;

    // A height cluster counts as significant at this fraction of the
    // largest cluster in the scene. The LOWEST significant cluster is
    // taken as the floor, which is what keeps a table top or a desk
    // from winning on sheer point count.
    double floorClusterPeakFraction = 0.25;

    // Half-width of the seed band around the chosen cluster, metres.
    double floorClusterBandM = 0.08;

    // Inlier band of a fitted plane, metres.
    double floorInlierBandM = 0.05;

    // Band searched around the already-tracked plane, metres. Wider
    // than the inlier band so a slowly changing floor is still found.
    double floorPriorBandM = 0.12;

    // Hypotheses tried when there is no up direction at all.
    int floorRansacIterations = 80;

    // ---- validation ----
    int    floorMinInliers = 25;
    double floorMinInlierFraction = 0.12;
    double floorMaxResidualM = 0.05;
    double floorMinSpanM = 0.30;              // in-plane extent
    double floorMinHeightM = 0.05;
    double floorMaxHeightM = 4.0;

    // Fraction of candidate points that must lie on or above the
    // plane. A ceiling fails this outright.
    double floorMinAboveFraction = 0.75;

    // Maximum angle between the floor normal and the up direction,
    // when one is known.
    double floorMaxTiltDeg = 25.0;

    // ---- fitting ----
    int    floorIrlsIterations = 4;
    double floorHuberM = 0.03;                // metres

    // ---- temporal ----

    // Blend gain, scaled by the measurement's confidence.
    double floorBlendAlpha = 0.5;

    // Confidence decays with this time constant while no measurement
    // is accepted.
    double floorDecayTauSeconds = 2.0;

    int    floorMinInitObservations = 3;
    double floorTrackingConfidence = 0.40;
    double floorLostConfidence = 0.15;
    double floorUnknownConfidence = 0.05;

    // A measurement further than this from the tracked plane is
    // rejected as an outlier - until floorReacquireAfter of them in a
    // row, at which point the tracked plane is abandoned.
    double floorMaxJumpDeg = 12.0;
    double floorMaxJumpM = 0.25;
    int    floorReacquireAfter = 5;

    // ---- gravity ----

    bool   floorUseGravity = true;

    // up = floor_accel_sign * normalise(acceleration). +1 for an IMU
    // reporting specific force, which is the usual case; -1 for one
    // whose driver already negates it.
    double floorAccelSign = 1.0;

    // A sample is used for gravity only when |a| is within this
    // fraction of 1 g and the gyro is below the threshold.
    double floorGravityToleranceRatio = 0.12;
    double floorStaticGyroThreshold = 0.35;   // rad/s
    double floorGravityAlpha = 0.05;

    // With no IMU, assume the device was roughly upright at start-up,
    // so world down is the camera's +Y at that moment. Reported as
    // downSource = nominal and penalised in the confidence, never
    // silently treated as a measurement.
    bool floorAssumeUprightStart = true;

    std::array<double, 3> floorNominalDownWorld = {0.0, 1.0, 0.0};

    // ---- IMU ----

    // Backend name. "none" disables it entirely. "iio" reads a Linux
    // Industrial I/O device, which is how an MPU6050/ICM20948 style
    // sensor appears on a Raspberry Pi with a kernel driver loaded.
    std::string imuBackend = "iio";
    std::string imuDevicePath;       // e.g. /sys/bus/iio/devices/iio:device0
    int imuRateHz = 200;
    int imuBufferSize = 2048;

    // Carry orientation forward with the gyro while vision is lost,
    // instead of freezing the last pose.
    bool imuPropagateOnLoss = true;

    // Rotation from the IMU body frame to the left camera frame,
    // row-major.
    //
    // IDENTITY IS A PLACEHOLDER, NOT A MEASUREMENT. There is no
    // camera-IMU extrinsic calibration in this project yet, and no IMU
    // hardware to calibrate against. Until one exists, the IMU is used
    // only where a wrong extrinsic cannot corrupt the estimate: as a
    // solver seed, and for propagation during a vision dropout.
    std::array<double, 9> imuRotationCameraFromBody = {
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0
    };

    // Below this angular rate, and with the camera judged still, the
    // gyro bias estimate is updated.
    double imuStaticGyroThreshold = 0.03;   // rad/s

    // ---- IPC ----

    bool ipcEnabled = true;
    std::string ipcSocketPath = "/tmp/novex-vio.sock";
    int ipcMaxClients = 8;

    // ---- web visualisation ----

    // Bound to loopback by default and deliberately not configurable
    // to 0.0.0.0 by accident: this is an unauthenticated development
    // dashboard that can reset the estimator.
    std::string webHost = "127.0.0.1";
    int webPort = 8080;

    // Rate at which the daemon pushes state to a subscriber. The
    // dashboard cannot use more than this and the VIO runs at 30 fps
    // regardless.
    double webUpdateHz = 20.0;

    // Directory holding the Node server. Resolved relative to the
    // working directory when not absolute.
    std::string webRoot = "web";

    // Leave empty to use whatever `node` is on PATH.
    std::string webNodePath;

    // Set false to run the Node server yourself, for example under a
    // debugger or nodemon, while novex-vio just serves the socket.
    bool webAutoStart = true;

    // ---- GUI ----

    bool guiShowFeatures = true;
    bool guiShowRight = true;

    bool loadFile(const std::string& path);

    // Returns false if the arguments are malformed or --help was
    // asked for; `shouldExit` distinguishes the two.
    bool parseCommandLine(int argc, char** argv, bool& shouldExit);

    static void printUsage();

    void applyDerived();
    bool validate() const;

    void logSummary() const;
};

} // namespace novex
