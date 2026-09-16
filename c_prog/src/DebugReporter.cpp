#include "DebugReporter.hpp"

#include <cmath>

namespace novex
{

namespace
{

void rule(FILE* out)
{
    fprintf(out, "========================================\n");
}

void heading(FILE* out, const char* text)
{
    fprintf(out, "\n%s\n", text);
}

} // namespace

void DebugReporter::print(const DebugStatistics& s, FILE* out)
{
    rule(out);
    fprintf(out, "           NOVEX VIO DEBUG\n");
    rule(out);

    if (!s.enabled)
    {
        fprintf(out, "\nDebug statistics were not collected.\n"
                     "Start with --debug to enable them.\n");
        rule(out);
        return;
    }

    heading(out, "Runtime");
    fprintf(out, "  %-22s %8.2f s\n", "Runtime:", s.runtimeSeconds);
    fprintf(out, "  %-22s %8llu\n", "Frames processed:",
            static_cast<unsigned long long>(s.framesProcessed));
    fprintf(out, "  %-22s %8.2f\n", "Camera FPS:", s.cameraFPS);
    fprintf(out, "  %-22s %8.2f\n", "VIO FPS:", s.vioFPS);
    fprintf(out, "  %-22s %8llu\n", "Dropped frames:",
            static_cast<unsigned long long>(s.droppedFrames));
    fprintf(out, "  %-22s %8llu\n", "Failed camera frames:",
            static_cast<unsigned long long>(s.failedFrames));

    heading(out, "Pipeline timing (whole frame)");
    fprintf(out, "  %-22s %8.2f ms\n", "Average frame:",
            s.averageFrameTimeMs);
    fprintf(out, "  %-22s %8.2f ms\n", "Min frame:", s.minFrameTimeMs);
    fprintf(out, "  %-22s %8.2f ms\n", "Max frame:", s.maxFrameTimeMs);
    fprintf(out, "  %-22s %8.2f ms\n", "p50:", s.p50FrameTimeMs);
    fprintf(out, "  %-22s %8.2f ms\n", "p90:", s.p90FrameTimeMs);
    fprintf(out, "  %-22s %8.2f ms\n", "p99:", s.p99FrameTimeMs);

    heading(out, "Pipeline timing (per stage, per invocation)");
    // Three decimals here, not two: pose integration and IMU
    // consumption are genuinely sub-millisecond, and rounding them to
    // 0.00 would read as "not measured" when they were.
    fprintf(out, "  %-22s %8.3f ms\n", "Camera capture:", s.captureMs);
    fprintf(out, "  %-22s %8.3f ms\n", "MJPG decode:", s.decodeMs);
    fprintf(out, "  %-22s %8.3f ms\n", "Feature detection:",
            s.featureDetectionMs);
    fprintf(out, "  %-22s %8.3f ms\n", "Feature tracking:",
            s.featureTrackingMs);
    fprintf(out, "  %-22s %8.3f ms\n", "Stereo matching:",
            s.stereoMatchingMs);
    fprintf(out, "  %-22s %8.3f ms\n", "Motion estimation:",
            s.motionEstimationMs);
    fprintf(out, "  %-22s %8.3f ms\n", "IMU processing:",
            s.imuProcessingMs);

    if (s.stateEstimationMeasured)
    {
        fprintf(out, "  %-22s %8.3f ms\n", "State estimation:",
                s.stateEstimationMs);
    }
    else
    {
        fprintf(out, "  %-22s %8s\n", "State estimation:", "N/A");
    }

    fprintf(out,
            "\n  Note: detection does not run every frame, so its\n"
            "  figure is the cost of one detection, not a per-frame\n"
            "  cost. \"Camera capture\" is mostly the blocking wait for\n"
            "  the sensor and is not CPU time.\n");

    heading(out, "Tracking");
    fprintf(out, "  %-22s %8.1f\n", "Avg features:",
            s.averageTrackedFeatures);
    fprintf(out, "  %-22s %8d\n", "Min features:", s.minTrackedFeatures);
    fprintf(out, "  %-22s %8d\n", "Max features:", s.maxTrackedFeatures);
    fprintf(out, "  %-22s %8llu\n", "Tracking failures:",
            static_cast<unsigned long long>(s.trackingFailures));
    fprintf(out, "  %-22s %8llu\n", "Successful frames:",
            static_cast<unsigned long long>(s.successfulFrames));

    if (s.framesProcessed > 0)
    {
        fprintf(out, "  %-22s %8.1f %%\n", "Success rate:",
                100.0 * static_cast<double>(s.successfulFrames) /
                    static_cast<double>(s.framesProcessed));
    }

    heading(out, "Stereo");
    fprintf(out, "  %-22s %8.1f\n", "Avg triangulated:",
            s.averageStereoMatches);
    fprintf(out, "  %-22s %8llu\n", "Total triangulated:",
            static_cast<unsigned long long>(s.stereoMatchesTotal));
    fprintf(out, "  %-22s %8llu\n", "Frames with no depth:",
            static_cast<unsigned long long>(s.framesWithoutStereo));

    heading(out, "IMU");

    if (s.imuSamples == 0)
    {
        fprintf(out, "  %-22s %8s\n", "IMU samples:", "0");
        fprintf(out,
                "  No IMU samples were consumed. Either the IMU was\n"
                "  disabled, or no supported device was present.\n");
    }
    else
    {
        fprintf(out, "  %-22s %8llu\n", "IMU samples:",
                static_cast<unsigned long long>(s.imuSamples));

        if (s.runtimeSeconds > 0.0)
        {
            fprintf(out, "  %-22s %8.1f Hz\n", "Effective rate:",
                    static_cast<double>(s.imuSamples) / s.runtimeSeconds);
        }
    }

    heading(out, "Pose");
    fprintf(out, "  %-22s X %8.3f  Y %8.3f  Z %8.3f\n",
            "Final position:",
            s.position.x(), s.position.y(), s.position.z());

    fprintf(out, "  %-22s x %8.4f  y %8.4f  z %8.4f  w %8.4f\n",
            "Final orientation:",
            s.orientation.x(), s.orientation.y(),
            s.orientation.z(), s.orientation.w());

    // Euler angles are derived here for reading convenience only. The
    // estimator holds a quaternion throughout and never converts.
    const Eigen::Matrix3d rotation = s.orientation.toRotationMatrix();

    const double roll = std::atan2(rotation(2, 1), rotation(2, 2));

    const double pitch = std::atan2(
        -rotation(2, 0),
        std::sqrt(rotation(2, 1) * rotation(2, 1) +
                  rotation(2, 2) * rotation(2, 2))
    );

    const double yaw = std::atan2(rotation(1, 0), rotation(0, 0));

    constexpr double toDegrees = 57.29577951308232;

    fprintf(out,
            "  %-22s roll %7.2f  pitch %7.2f  yaw %7.2f  (deg)\n",
            "Final euler:",
            roll * toDegrees, pitch * toDegrees, yaw * toDegrees);

    fprintf(out, "  %-22s %8.3f m\n", "Trajectory length:",
            s.trajectoryDistanceMeters);

    fprintf(out,
            "\n  Position is dead-reckoned from frame-to-frame visual\n"
            "  odometry with no loop closure. It drifts, and nothing\n"
            "  here measures how much: there is no ground truth.\n"
            "  Trajectory length is path length, not displacement.\n");

    fprintf(out, "\n");
    rule(out);
}

} // namespace novex
