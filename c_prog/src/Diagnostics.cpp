#include "Diagnostics.hpp"

#include <algorithm>
#include <cmath>

namespace novex
{

namespace
{

constexpr double kRadiansToDegrees = 57.29577951308232;

double rotationAngleDegrees(const Eigen::Matrix3d& rotation)
{
    return Eigen::AngleAxisd(rotation).angle() * kRadiansToDegrees;
}

// Largest |mean| / standard error over three components. With N
// frames of zero-mean noise this stays around 1-2; a real bias grows
// with sqrt(N). Frame-to-frame noise is not perfectly independent, so
// this is read as "clearly biased" only well above 3.
double significance(const Eigen::Vector3d& sum,
                    const Eigen::Vector3d& squares,
                    uint64_t n)
{
    if (n < 2)
    {
        return 0.0;
    }

    const double count = static_cast<double>(n);

    double worst = 0.0;

    for (int k = 0; k < 3; ++k)
    {
        const double mean = sum(k) / count;
        const double variance =
            std::max(0.0, squares(k) / count - mean * mean);

        const double standardError = std::sqrt(variance / count);

        if (standardError > 1e-15)
        {
            worst = std::max(worst, std::abs(mean) / standardError);
        }
    }

    return worst;
}

} // namespace

void StationaryDiagnostic::start(double timestamp,
                                 const Eigen::Matrix3d& rotation,
                                 const Eigen::Vector3d& position)
{
    *this = StationaryDiagnostic();

    active = true;
    everStarted = true;

    startTime = timestamp;
    lastTime = timestamp;

    startRotation = rotation;
    startPosition = position;
    lastRotation = rotation;
    lastPosition = position;

    // Relative to the window start the independent composition begins
    // at identity. Until the first keyframe inside the window, raw
    // estimates are against an older keyframe, so they are NOT used:
    // update() only composes once haveKeyframe is set.
}

void StationaryDiagnostic::stop()
{
    active = false;
}

void StationaryDiagnostic::update(const FrameDiagnostics& frame,
                                  const Eigen::Matrix3d& rotation,
                                  const Eigen::Vector3d& position)
{
    if (!active)
    {
        return;
    }

    // The window's clock is the camera's: the first frame it sees
    // defines its start, whatever clock start() was called with.
    if (frames == 0)
    {
        startTime = frame.timestamp;
    }

    ++frames;

    lastTime = frame.timestamp;
    lastRotation = rotation;
    lastPosition = position;

    flowSum += frame.flowMedianPx;

    if (frame.stereoValid && frame.stereoPoints > 0)
    {
        depthSum += frame.depthMedian;
        stereoResidualSum += frame.stereoResidualMedianPx;
        stereoVerticalSum += frame.stereoVerticalOffsetPx;
        ++depthFrames;
    }

    if (!frame.motionAttempted)
    {
        return;
    }

    if (!frame.motionAccepted)
    {
        ++rejected;
        return;
    }

    ++accepted;

    const bool composable = haveKeyframe;

    const Eigen::Vector3d translationMm(
        frame.relativeTranslation[0] * 1e3,
        frame.relativeTranslation[1] * 1e3,
        frame.relativeTranslation[2] * 1e3
    );

    const Eigen::Vector3d rotationDeg(
        frame.relativeRotationVector[0] * kRadiansToDegrees,
        frame.relativeRotationVector[1] * kRadiansToDegrees,
        frame.relativeRotationVector[2] * kRadiansToDegrees
    );

    const double t = translationMm.norm();
    const double r = rotationDeg.norm();

    translationSum += t;
    translationSquares += t * t;
    translationVectorSum += translationMm;

    rotationSum += r;
    rotationSquares += r * r;
    rotationVectorSum += rotationDeg;

    // Per-component squares ride in the same accumulators' shadows.
    translationComponentSquares += translationMm.cwiseProduct(translationMm);
    rotationComponentSquares += rotationDeg.cwiseProduct(rotationDeg);

    reprojectionSum += frame.reprojectionMedianPx;
    inlierRatioSum += frame.inlierRatio;

    // ---- independent pose composition ----
    //
    // The raw estimate is the camera's motion from its keyframe:
    // rotation Exp(rv), displacement d, in keyframe axes. Composing it
    // onto this class's own keyframe pose must reproduce the
    // estimator's pose. If it does not, integration or reference-frame
    // bookkeeping is wrong - stage D.
    const Eigen::Vector3d rv(
        frame.estimateRotationVector[0],
        frame.estimateRotationVector[1],
        frame.estimateRotationVector[2]
    );

    const Eigen::Vector3d displacement(
        frame.estimateTranslation[0],
        frame.estimateTranslation[1],
        frame.estimateTranslation[2]
    );

    const double angle = rv.norm();

    const Eigen::Matrix3d step = angle > 1e-15
        ? Eigen::AngleAxisd(angle, rv / angle).toRotationMatrix()
        : Eigen::Matrix3d::Identity();

    if (!composable)
    {
        // Before the first in-window keyframe, follow the estimator so
        // the composition starts from a known pose at that keyframe.
        measuredRotation = startRotation.transpose() * rotation;
        measuredPosition = startRotation.transpose() * (position - startPosition);
        return;
    }

    // In start-frame coordinates, like the drift figures.
    measuredPosition = keyframePosition + keyframeRotation * displacement;
    measuredRotation = keyframeRotation * step;
}

void StationaryDiagnostic::noteKeyframe()
{
    if (!active)
    {
        return;
    }

    // The keyframe is wherever the independent composition says the
    // camera is now - never read back from the estimator.
    keyframeRotation = measuredRotation;
    keyframePosition = measuredPosition;
    haveKeyframe = true;
}

StationaryReport StationaryDiagnostic::report() const
{
    StationaryReport out;

    out.active = active;
    out.haveData = everStarted && frames > 0;

    if (!out.haveData)
    {
        return out;
    }

    out.durationSeconds = lastTime - startTime;
    out.frames = frames;
    out.acceptedEstimates = accepted;
    out.rejectedEstimates = rejected;

    const double n = static_cast<double>(std::max<uint64_t>(1, accepted));

    out.translationMeanMm = translationSum / n;
    out.translationStdMm = std::sqrt(std::max(
        0.0, translationSquares / n - out.translationMeanMm * out.translationMeanMm));

    out.rotationMeanDeg = rotationSum / n;
    out.rotationStdDeg = std::sqrt(std::max(
        0.0, rotationSquares / n - out.rotationMeanDeg * out.rotationMeanDeg));

    for (int k = 0; k < 3; ++k)
    {
        out.translationBiasMm[k] = translationVectorSum(k) / n;
        out.rotationBiasDeg[k] = rotationVectorSum(k) / n;
    }

    out.translationBiasSignificance = significance(
        translationVectorSum, translationComponentSquares, accepted);

    out.rotationBiasSignificance = significance(
        rotationVectorSum, rotationComponentSquares, accepted);

    const double allFrames = static_cast<double>(frames);

    out.flowMeanPx = flowSum / allFrames;

    if (depthFrames > 0)
    {
        const double d = static_cast<double>(depthFrames);

        out.depthMedianM = depthSum / d;
        out.stereoResidualPx = stereoResidualSum / d;
        out.stereoVerticalOffsetPx = stereoVerticalSum / d;
    }

    out.reprojectionMedianPx = reprojectionSum / n;
    out.inlierRatio = inlierRatioSum / n;

    // Drift expressed in the START camera frame, so its components mean
    // "right / down / forward of where the camera was".
    const Eigen::Vector3d drift =
        startRotation.transpose() * (lastPosition - startPosition);

    out.positionDriftM = drift.norm();

    for (int k = 0; k < 3; ++k)
    {
        out.positionDrift[k] = drift(k);
    }

    out.orientationDriftDeg =
        rotationAngleDegrees(startRotation.transpose() * lastRotation);

    out.measuredPositionDriftM = measuredPosition.norm();
    out.measuredOrientationDriftDeg = rotationAngleDegrees(measuredRotation);

    // ---- attribution ----
    //
    // Thresholds here only choose which sentence to print; the numbers
    // above are the result. They are deliberately conservative.
    if (frames < 60 || accepted < 30)
    {
        out.indication =
            "not enough data yet (need a few seconds of accepted "
            "estimates)";
    }
    else if (out.flowMeanPx > 0.5)
    {
        out.indication =
            "A (tracking): median optical flow is well above sensor "
            "noise - the camera is moving, or tracks are unstable";
    }
    else if (std::abs(out.positionDriftM - out.measuredPositionDriftM) >
                 std::max(0.01, 0.5 * out.measuredPositionDriftM) ||
             std::abs(out.orientationDriftDeg -
                      out.measuredOrientationDriftDeg) >
                 std::max(0.5, 0.5 * out.measuredOrientationDriftDeg))
    {
        out.indication =
            "D (state integration): the estimator's pose moved "
            "differently from the integral of the measured relative "
            "motions - check reference-frame handling";
    }
    else if (out.rotationBiasSignificance > 6.0 ||
             out.translationBiasSignificance > 6.0)
    {
        out.indication = std::abs(out.stereoVerticalOffsetPx) > 0.3
            ? "C (motion estimation) with a B (stereo) signature: "
              "relative motion is consistently biased and the stereo "
              "rays have a systematic vertical offset - check the "
              "stereo calibration"
            : "C (motion estimation): relative motion is consistently "
              "biased in one direction while the camera is still";
    }
    else
    {
        out.indication =
            "no dominant bias: per-frame motion is zero-mean noise; "
            "remaining drift is its random walk";
    }

    return out;
}

} // namespace novex
