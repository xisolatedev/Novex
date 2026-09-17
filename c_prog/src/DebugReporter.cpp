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

void DebugReporter::printStationary(const StationaryReport& r, FILE* out)
{
    heading(out, "Stationary-camera drift test");

    if (!r.haveData)
    {
        fprintf(out, "  No stationary data was collected.\n");
        return;
    }

    fprintf(out, "  %-30s %8.1f s  (%llu frames, %llu accepted, "
                 "%llu rejected)%s\n",
            "Window:", r.durationSeconds,
            static_cast<unsigned long long>(r.frames),
            static_cast<unsigned long long>(r.acceptedEstimates),
            static_cast<unsigned long long>(r.rejectedEstimates),
            r.active ? "" : "  [stopped]");

    fprintf(out, "  %-30s %8.3f mm  (std %.3f)\n",
            "Relative translation / frame:",
            r.translationMeanMm, r.translationStdMm);
    fprintf(out, "  %-30s %+.4f %+.4f %+.4f mm  (%.1f sigma)\n",
            "  mean vector (bias):",
            r.translationBiasMm[0], r.translationBiasMm[1],
            r.translationBiasMm[2], r.translationBiasSignificance);
    fprintf(out, "  %-30s %8.4f deg (std %.4f)\n",
            "Relative rotation / frame:",
            r.rotationMeanDeg, r.rotationStdDeg);
    fprintf(out, "  %-30s %+.5f %+.5f %+.5f deg (%.1f sigma)\n",
            "  mean vector (bias):",
            r.rotationBiasDeg[0], r.rotationBiasDeg[1],
            r.rotationBiasDeg[2], r.rotationBiasSignificance);
    fprintf(out, "  %-30s %8.3f px\n", "Optical flow (median):",
            r.flowMeanPx);
    fprintf(out, "  %-30s %8.2f m\n", "Median depth:", r.depthMedianM);
    fprintf(out, "  %-30s %8.3f px\n", "Reprojection error:",
            r.reprojectionMedianPx);
    fprintf(out, "  %-30s %8.1f %%\n", "Inlier ratio:",
            r.inlierRatio * 100.0);
    fprintf(out, "  %-30s %8.3f px  (vertical %+.3f px)\n",
            "Stereo ray miss:", r.stereoResidualPx,
            r.stereoVerticalOffsetPx);
    fprintf(out, "  %-30s %8.4f m   (%+.4f %+.4f %+.4f, start frame)\n",
            "Accumulated position drift:", r.positionDriftM,
            r.positionDrift[0], r.positionDrift[1], r.positionDrift[2]);
    fprintf(out, "  %-30s %8.3f deg\n", "Accumulated orientation drift:",
            r.orientationDriftDeg);
    fprintf(out, "  %-30s %8.4f m / %.3f deg\n",
            "Integrated measured motion:",
            r.measuredPositionDriftM, r.measuredOrientationDriftDeg);

    if (r.durationSeconds > 1.0)
    {
        fprintf(out, "  %-30s %8.4f m/min, %.3f deg/min\n",
                "Drift rate:",
                r.positionDriftM * 60.0 / r.durationSeconds,
                r.orientationDriftDeg * 60.0 / r.durationSeconds);
    }

    fprintf(out, "\n  Indication: %s\n",
            r.indication ? r.indication : "n/a");
    fprintf(out,
            "  (Only meaningful if the camera really was stationary.)\n");
}

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

    heading(out, "Geometry");

    if (s.geometryFrames == 0)
    {
        fprintf(out, "  No stereo geometry was measured.\n");
    }
    else
    {
        fprintf(out, "  %-30s %8.2f px\n", "Average disparity:",
                s.averageDisparityPx);
        fprintf(out, "  %-30s %8.2f px\n", "Median disparity:",
                s.medianDisparityPx);
        fprintf(out, "  %-30s %8.2f m\n", "Average median depth:",
                s.averageDepthM);
        fprintf(out, "  %-30s %8.3f px\n", "Average stereo ray miss:",
                s.averageStereoResidualPx);
        fprintf(out, "  %-30s %+8.3f px\n", "Average stereo vertical offset:",
                s.averageStereoVerticalOffsetPx);
    }

    if (s.motionFrames == 0)
    {
        fprintf(out, "  No motion estimate was accepted.\n");
    }
    else
    {
        fprintf(out, "  %-30s %8.3f px\n", "Average reprojection error:",
                s.averageReprojectionPx);
        fprintf(out, "  %-30s %8.3f px\n", "Median reprojection error:",
                s.medianReprojectionPx);
        fprintf(out, "  %-30s %8.1f %%\n", "Average RANSAC inlier ratio:",
                s.averageInlierRatio * 100.0);
        fprintf(out, "  %-30s %8.1f\n", "Average inliers:",
                s.averageInliers);
        fprintf(out, "  %-30s %8.4f deg\n", "Average relative rotation:",
                s.averageRelativeRotationDeg);
        fprintf(out, "  %-30s %8.3f mm\n", "Average relative translation:",
                s.averageRelativeTranslationMm);
        fprintf(out, "  %-30s %8.4f deg\n", "Average rotation 1-sigma:",
                s.averageRotationSigmaDeg);
        fprintf(out, "  %-30s %8.3f mm\n", "Average translation 1-sigma:",
                s.averageTranslationSigmaMm);
    }

    fprintf(out, "  %-30s %8.3f px\n", "Average optical flow (median):",
            s.averageFlowPx);
    fprintf(out, "  %-30s %8llu\n", "Motion estimates rejected:",
            static_cast<unsigned long long>(s.motionRejected));
    fprintf(out, "  %-30s %8llu\n", "Reference re-anchors (lost):",
            static_cast<unsigned long long>(s.referenceResets));
    fprintf(out, "  %-30s %8llu\n", "Stereo matches rejected:",
            static_cast<unsigned long long>(s.stereoRejected));
    fprintf(out, "  %-30s %8llu\n", "Correspondences rejected:",
            static_cast<unsigned long long>(s.correspondencesRejected));

    heading(out, "Drift diagnostics");
    fprintf(out, "  %-30s %8.3f m\n", "Accumulated visual translation:",
            s.accumulatedTranslationM);
    fprintf(out, "  %-30s %8.2f deg\n", "Accumulated visual rotation:",
            s.accumulatedRotationDeg);
    fprintf(out, "  %-30s %8.3f m\n", "Net translation from origin:",
            s.netTranslationM);
    fprintf(out, "  %-30s %8.2f deg\n", "Net rotation from origin:",
            s.netRotationDeg);
    fprintf(out,
            "\n  Accumulated = sum of per-frame measured motion magnitudes\n"
            "  (path length). Net = where the internal pose ended up.\n"
            "  Relative to the internal frame, i.e. since start or reset.\n");

    if (s.stationary.haveData)
    {
        printStationary(s.stationary, out);
    }
    else
    {
        fprintf(out,
                "\n  Stationary drift: not measured (run with\n"
                "  --stationary-test, or start it from the dashboard).\n");
    }

    heading(out, "Point cloud");

    if (!s.pointCloudEnabled)
    {
        fprintf(out, "  Disabled (--no-pointcloud).\n");
    }
    else
    {
        const PointCloudCounters& c = s.pointCounters;

        fprintf(out, "  %-30s %8llu\n", "Total 3D points generated:",
                static_cast<unsigned long long>(c.generated));
        fprintf(out, "  %-30s %8llu\n", "Valid (passed map gates):",
                static_cast<unsigned long long>(c.accepted));
        fprintf(out, "  %-30s %8llu\n", "Rejected:",
                static_cast<unsigned long long>(c.rejected()));
        fprintf(out, "    %-28s %8llu\n", "depth > limit",
                static_cast<unsigned long long>(c.rejectedDepth));
        fprintf(out, "    %-28s %8llu\n", "depth uncertainty",
                static_cast<unsigned long long>(c.rejectedUncertainty));
        fprintf(out, "    %-28s %8llu\n", "stereo ray miss",
                static_cast<unsigned long long>(c.rejectedResidual));
        fprintf(out, "    %-28s %8llu\n", "track too young",
                static_cast<unsigned long long>(c.rejectedTrackAge));
        fprintf(out, "    %-28s %8llu\n", "not a motion inlier",
                static_cast<unsigned long long>(c.rejectedNotInlier));
        fprintf(out, "    %-28s %8llu\n", "no accepted pose",
                static_cast<unsigned long long>(c.rejectedNoPose));

        if (s.pointDepthSamples > 0)
        {
            fprintf(out, "  %-30s %8.2f m\n", "Average depth:",
                    s.averagePointDepthM);
            fprintf(out, "  %-30s %8.2f m\n", "Median depth:",
                    s.medianPointDepthM);
            fprintf(out, "  %-30s %8.2f m\n", "Maximum depth:",
                    s.maxPointDepthM);
        }

        if (s.pointMapEnabled)
        {
            fprintf(out, "  %-30s %8zu\n", "Current map size:", s.mapPoints);
            fprintf(out, "  %-30s %8zu\n", "Peak map size:", s.mapPeakPoints);
            fprintf(out, "  %-30s %8zu\n", "Maximum map size:", s.mapCapacity);

            if (s.voxelSize > 0.0)
            {
                fprintf(out, "  %-30s %8.3f m\n", "Voxel size:", s.voxelSize);
            }
            else
            {
                fprintf(out, "  %-30s %8s\n", "Voxel size:", "off");
            }

            fprintf(out, "  %-30s %8llu new / %llu merged / %llu refined / "
                         "%llu evicted\n",
                    "Map updates:",
                    static_cast<unsigned long long>(c.mapInserted),
                    static_cast<unsigned long long>(c.mapMerged),
                    static_cast<unsigned long long>(c.mapRefined),
                    static_cast<unsigned long long>(c.mapEvicted));

            if (s.innovationFrames > 0)
            {
                fprintf(out, "  %-30s %8.2f %% of range\n",
                        "Median track innovation:",
                        s.averageInnovationPct);
            }
        }
        else
        {
            fprintf(out, "  Map accumulation disabled.\n");
        }
    }

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
