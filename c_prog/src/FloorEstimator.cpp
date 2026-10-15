#include "FloorEstimator.hpp"

#include "Log.hpp"

#include <Eigen/Eigenvalues>

#include <opencv2/calib3d.hpp>
#include <opencv2/imgproc.hpp>

#include <algorithm>
#include <cmath>
#include <cstdio>

namespace novex
{

namespace
{

constexpr double kDegrees = 57.295779513082320876;
constexpr double kStandardGravity = 9.80665;

// Cap on the height histogram, so a wild depth outlier cannot make
// the acquisition allocate or scan an unbounded number of bins.
constexpr int kMaxHistogramBins = 1024;

// Gravity older than this is not used; the platform may have been
// rotating ever since.
constexpr double kGravityStaleSeconds = 0.5;

double clampDouble(double value, double low, double high)
{
    return value < low ? low : (value > high ? high : value);
}

// Both factors are 1 for a perfect measurement and exactly 0.5 at the
// configured limit, the same shape pointQuality() uses.
double rising(double value, double limit)
{
    if (!(limit > 0.0))
    {
        return 1.0;
    }

    const double v = std::max(0.0, value);

    return v / (v + limit);
}

double falling(double value, double limit)
{
    if (!(limit > 0.0))
    {
        return 1.0;
    }

    return limit / (limit + std::max(0.0, value));
}

double angleBetweenDegrees(const Eigen::Vector3d& a,
                           const Eigen::Vector3d& b)
{
    const double na = a.norm();
    const double nb = b.norm();

    if (!(na > 0.0) || !(nb > 0.0))
    {
        return 180.0;
    }

    return std::acos(clampDouble(a.dot(b) / (na * nb), -1.0, 1.0)) *
           kDegrees;
}

// Any unit vector perpendicular to `n`. Picks the axis `n` is least
// aligned with, so the cross product never degenerates.
Eigen::Vector3d perpendicular(const Eigen::Vector3d& n)
{
    Eigen::Vector3d axis = Eigen::Vector3d::UnitX();

    if (std::abs(n.x()) > std::abs(n.y()))
    {
        axis = std::abs(n.y()) > std::abs(n.z())
            ? Eigen::Vector3d::UnitZ()
            : Eigen::Vector3d::UnitY();
    }
    else if (std::abs(n.y()) > std::abs(n.z()))
    {
        axis = Eigen::Vector3d::UnitZ();
    }

    return n.cross(axis).normalized();
}

} // namespace

// ===================================================================

Plane planeInFrame(const Plane& plane,
                   const Eigen::Matrix3d& rotation,
                   const Eigen::Vector3d& translation)
{
    Plane out;

    if (!plane.valid())
    {
        return out;
    }

    out.normal = rotation.transpose() * plane.normal;
    out.offset = plane.offset + plane.normal.dot(translation);

    return out;
}

const char* floorStatusName(FloorStatus status)
{
    switch (status)
    {
        case FloorStatus::Unknown:      return "UNKNOWN";
        case FloorStatus::Initializing: return "INITIALIZING";
        case FloorStatus::Tracking:     return "TRACKING";
        case FloorStatus::Predicting:   return "PREDICTING";
        case FloorStatus::Lost:         return "LOST";
        default:                        return "?";
    }
}

const char* floorDownSourceName(FloorDownSource source)
{
    switch (source)
    {
        case FloorDownSource::None:    return "none";
        case FloorDownSource::Nominal: return "nominal";
        case FloorDownSource::Tracked: return "tracked";
        case FloorDownSource::Imu:     return "imu";
        default:                       return "?";
    }
}

// ===================================================================

FloorEstimator::FloorEstimator(const VIOConfig& config)
    : config(config)
{
    configure(static_cast<size_t>(std::max(1, config.maxFeatures)));
}

void FloorEstimator::configure(size_t maxFeatures)
{
    const size_t capacity = std::max<size_t>(maxFeatures, 64);

    candidates.resize(capacity);

    selection.reserve(capacity);
    inliers.reserve(capacity);
    scratchScalars.reserve(capacity);

    histogram.assign(kMaxHistogramBins, 0);

    debugInlierPixels.reserve(capacity);
    debugRejectedPixels.reserve(capacity);
    debugInlierIds.reserve(capacity);
    hullScratch.reserve(capacity);
}

void FloorEstimator::reset()
{
    tracked = Plane();
    haveTracked = false;
    trackedConfidence = 0.0;
    status = FloorStatus::Unknown;
    lastSource = FloorDownSource::None;

    lastMeasurementTime = 0.0;
    lastAcceptedTime = 0.0;
    goodObservations = 0;
    disagreements = 0;

    gravityUpWorld.setZero();
    haveGravity = false;
    lastGravityTime = 0.0;

    candidateCount = 0;
    lastAccepted = Measurement();

    debugInlierPixels.clear();
    debugRejectedPixels.clear();
    debugInlierIds.clear();

    published = FloorEstimate();
    published.detail = "reset";

    randomState = 0x9e3779b9u;
}

// ===================================================================
// gravity
// ===================================================================
//
// The accelerometer measures SPECIFIC FORCE. A device at rest reads
// +1 g along its own up axis, which is why `up` is +a and not -a. An
// IMU whose driver reports the gravity vector instead of the reaction
// needs floor.accel_sign = -1; there is no way to detect which one a
// given board does, so it is a config value rather than a guess.
//
// Samples are used only when the platform is not obviously
// accelerating (|a| within a tolerance of 1 g) and not spinning
// (gyro below a threshold). Everything else is thrown away: a wrong
// gravity direction is far worse than no gravity direction, because
// it would confidently tilt the floor.

void FloorEstimator::updateGravity(const FloorInput& input)
{
    if (!config.floorUseGravity || input.imu == nullptr ||
        input.imu->empty())
    {
        if (haveGravity &&
            input.timestamp - lastGravityTime > kGravityStaleSeconds)
        {
            haveGravity = false;
        }

        return;
    }

    Eigen::Matrix3d cameraFromBody;

    for (int row = 0; row < 3; ++row)
    {
        for (int col = 0; col < 3; ++col)
        {
            cameraFromBody(row, col) =
                config.imuRotationCameraFromBody[
                    static_cast<size_t>(row * 3 + col)];
        }
    }

    const double tolerance =
        kStandardGravity * config.floorGravityToleranceRatio;

    int used = 0;

    for (const IMUSample& sample : *input.imu)
    {
        const double magnitude = sample.acceleration.norm();

        if (std::abs(magnitude - kStandardGravity) > tolerance)
        {
            continue;
        }

        if (sample.gyroscope.norm() > config.floorStaticGyroThreshold)
        {
            continue;
        }

        // Body -> camera -> world. Expressing it in the world frame is
        // what makes the low-pass legitimate: gravity is constant
        // there while the camera rotates underneath it.
        const Eigen::Vector3d inCamera =
            cameraFromBody * sample.acceleration;

        const Eigen::Vector3d inWorld =
            input.worldFromCamera * inCamera;

        const Eigen::Vector3d up =
            (config.floorAccelSign * inWorld).normalized();

        if (!haveGravity)
        {
            gravityUpWorld = up;
            haveGravity = true;
        }
        else
        {
            const double alpha = config.floorGravityAlpha;

            gravityUpWorld =
                ((1.0 - alpha) * gravityUpWorld + alpha * up).normalized();
        }

        ++used;
    }

    if (used > 0)
    {
        lastGravityTime = input.timestamp;
    }
    else if (haveGravity &&
             input.timestamp - lastGravityTime > kGravityStaleSeconds)
    {
        haveGravity = false;
    }
}

bool FloorEstimator::resolveUp(Eigen::Vector3d& up,
                               FloorDownSource& source) const
{
    if (config.floorUseGravity && haveGravity)
    {
        up = gravityUpWorld;
        source = FloorDownSource::Imu;
        return true;
    }

    if (haveTracked && trackedConfidence >= config.floorLostConfidence)
    {
        up = tracked.normal;
        source = FloorDownSource::Tracked;
        return true;
    }

    if (config.floorAssumeUprightStart)
    {
        // The internal world frame IS the first tracked camera pose,
        // so "down" at start-up is the camera's +Y. This is an
        // ASSUMPTION about how the device was held, not a
        // measurement, and it is reported as such through
        // downSource so a consumer can weigh it.
        const Eigen::Vector3d down(config.floorNominalDownWorld[0],
                                   config.floorNominalDownWorld[1],
                                   config.floorNominalDownWorld[2]);

        if (down.squaredNorm() > 0.0)
        {
            up = -down.normalized();
            source = FloorDownSource::Nominal;
            return true;
        }
    }

    up.setZero();
    source = FloorDownSource::None;

    return false;
}

// ===================================================================
// candidate selection
// ===================================================================
//
// Not every stereo point. The gates below are the cheap, physical
// ones: a point has to be a trustworthy stereo measurement at a
// plausible range before it is allowed to vote on where the floor is.
// Geometric selection - which points lie on a plane, and which plane
// is the ground rather than a wall or a table - happens afterwards.

size_t FloorEstimator::selectCandidates(const FloorInput& input)
{
    candidateCount = 0;

    if (input.features == nullptr)
    {
        return 0;
    }

    const size_t capacity = candidates.size();

    for (const Feature& feature : *input.features)
    {
        if (candidateCount >= capacity)
        {
            break;
        }

        if (!feature.hasDepth)
        {
            continue;
        }

        const double depth = feature.position3D.z;

        if (depth < config.floorMinDepth || depth > config.floorMaxDepth)
        {
            continue;
        }

        if (feature.depthSigma > config.floorMaxDepthSigma)
        {
            continue;
        }

        if (feature.stereoResidualPx > config.floorMaxStereoResidualPx)
        {
            continue;
        }

        if (feature.age < config.floorMinTrackAge)
        {
            continue;
        }

        if (config.floorRequireMotionInlier && !feature.motionInlier)
        {
            continue;
        }

        Candidate& c = candidates[candidateCount++];

        c.camera = Eigen::Vector3d(feature.position3D.x,
                                   feature.position3D.y,
                                   feature.position3D.z);

        c.world = input.worldFromCamera * c.camera + input.cameraInWorld;

        c.pixel = feature.point;
        c.featureId = static_cast<uint32_t>(feature.id & 0xffffffffu);

        // Range noise is what actually limits a stereo point, and it
        // grows with range. Weighting by its inverse variance stops
        // distant, uncertain points from dragging the plane.
        const double range = c.camera.norm();

        const double sigma =
            std::max(1e-3, feature.depthSigma * std::max(range, 1e-3));

        c.weight = 1.0 / (sigma * sigma);
        c.height = 0.0;
    }

    // Deterministic decimation - never a random subsample, so two runs
    // over the same input give the same answer. Keeps the Pi's cost
    // bounded no matter how many features are tracked.
    const size_t budget =
        static_cast<size_t>(std::max(16, config.floorMaxPoints));

    if (candidateCount > budget)
    {
        const size_t stride = (candidateCount + budget - 1) / budget;

        size_t kept = 0;

        for (size_t i = 0; i < candidateCount; i += stride)
        {
            candidates[kept++] = candidates[i];
        }

        candidateCount = kept;
    }

    return candidateCount;
}

// ===================================================================
// plane fitting
// ===================================================================
//
// IRLS with a Huber weight on top of the per-point inverse range
// variance. The plane itself is the eigenvector of the weighted
// scatter matrix with the smallest eigenvalue - a total least squares
// fit, which is the right one here because the error is perpendicular
// to the plane rather than along one axis.
//
// This is what replaces "fit least squares and hope": a handful of
// furniture points that survived candidate selection get their weight
// driven towards zero in two or three iterations instead of tilting
// the answer.

bool FloorEstimator::fitPlane(const std::vector<uint32_t>& sel,
                              const Eigen::Vector3d& towards,
                              Plane& plane) const
{
    const size_t n = sel.size();

    if (n < 3)
    {
        return false;
    }

    scratchScalars.clear();
    scratchScalars.resize(n);

    for (size_t i = 0; i < n; ++i)
    {
        scratchScalars[i] = candidates[sel[i]].weight;
    }

    // Normalise the weights once, so the eigen decomposition works on
    // numbers of order one whatever the range scale is.
    {
        double maxWeight = 0.0;

        for (double w : scratchScalars)
        {
            maxWeight = std::max(maxWeight, w);
        }

        if (!(maxWeight > 0.0))
        {
            return false;
        }

        for (double& w : scratchScalars)
        {
            w /= maxWeight;
        }
    }

    Eigen::Vector3d normal = Eigen::Vector3d::Zero();
    Eigen::Vector3d centroid = Eigen::Vector3d::Zero();

    const int iterations = std::max(1, config.floorIrlsIterations);

    for (int iteration = 0; iteration < iterations; ++iteration)
    {
        double total = 0.0;

        centroid.setZero();

        for (size_t i = 0; i < n; ++i)
        {
            centroid += scratchScalars[i] * candidates[sel[i]].world;
            total += scratchScalars[i];
        }

        if (!(total > 1e-9))
        {
            return false;
        }

        centroid /= total;

        Eigen::Matrix3d scatter = Eigen::Matrix3d::Zero();

        for (size_t i = 0; i < n; ++i)
        {
            const Eigen::Vector3d d = candidates[sel[i]].world - centroid;

            scatter += scratchScalars[i] * (d * d.transpose());
        }

        scatter /= total;

        Eigen::SelfAdjointEigenSolver<Eigen::Matrix3d> solver;

        // computeDirect is the closed-form 3x3 path: no iteration, no
        // allocation, which is the whole reason this is affordable
        // several times per measurement on a Pi.
        solver.computeDirect(scatter);

        const Eigen::Vector3d values = solver.eigenvalues();

        // Ascending order. values(1) is the smaller IN-plane spread;
        // if it is zero the support is a line and the normal about it
        // is arbitrary.
        if (!(values(1) > 1e-8))
        {
            return false;
        }

        normal = solver.eigenvectors().col(0);

        const double length = normal.norm();

        if (!(length > 0.0) || !std::isfinite(length))
        {
            return false;
        }

        normal /= length;

        if (normal.dot(towards - centroid) < 0.0)
        {
            normal = -normal;
        }

        if (iteration + 1 == iterations)
        {
            break;
        }

        // ---- reweight ----
        const double offset = -normal.dot(centroid);

        double medianAbs = 0.0;

        {
            std::vector<double>& residuals = hullScratchResiduals;

            residuals.clear();
            residuals.reserve(n);

            for (size_t i = 0; i < n; ++i)
            {
                residuals.push_back(std::abs(
                    normal.dot(candidates[sel[i]].world) + offset));
            }

            const size_t middle = residuals.size() / 2;

            std::nth_element(residuals.begin(),
                             residuals.begin() +
                                 static_cast<long>(middle),
                             residuals.end());

            medianAbs = residuals[middle];
        }

        // 1.4826 * MAD-about-zero, floored by the configured Huber
        // width so a perfectly flat synthetic plane cannot drive the
        // scale to zero and start rejecting its own inliers.
        const double scale =
            std::max(config.floorHuberM, 1.4826 * medianAbs);

        for (size_t i = 0; i < n; ++i)
        {
            const double r = std::abs(
                normal.dot(candidates[sel[i]].world) + offset);

            const double huber = (r <= scale) ? 1.0 : (scale / r);

            scratchScalars[i] =
                (candidates[sel[i]].weight) * huber;
        }

        double maxWeight = 0.0;

        for (double w : scratchScalars)
        {
            maxWeight = std::max(maxWeight, w);
        }

        if (!(maxWeight > 0.0))
        {
            return false;
        }

        for (double& w : scratchScalars)
        {
            w /= maxWeight;
        }
    }

    plane.normal = normal;
    plane.offset = -normal.dot(centroid);

    return true;
}

void FloorEstimator::scorePlane(const Plane& plane,
                                const Eigen::Vector3d& cameraInWorld,
                                Measurement& out)
{
    inliers.clear();

    const double band = config.floorInlierBandM;

    double sumSquared = 0.0;
    int above = 0;

    for (size_t i = 0; i < candidateCount; ++i)
    {
        const double r = plane.signedDistance(candidates[i].world);

        if (r >= -band)
        {
            ++above;
        }

        if (std::abs(r) <= band)
        {
            inliers.push_back(static_cast<uint32_t>(i));
            sumSquared += r * r;
        }
    }

    out.worldPlane = plane;
    out.candidates = static_cast<int>(candidateCount);
    out.inliers = static_cast<int>(inliers.size());

    out.inlierFraction = candidateCount > 0
        ? static_cast<double>(out.inliers) /
          static_cast<double>(candidateCount)
        : 0.0;

    out.aboveFraction = candidateCount > 0
        ? static_cast<double>(above) /
          static_cast<double>(candidateCount)
        : 0.0;

    out.rmsResidual = out.inliers > 0
        ? std::sqrt(sumSquared / static_cast<double>(out.inliers))
        : 0.0;

    // ---- in-plane extent ----
    //
    // Twice the square root of the SMALLER in-plane variance. A patch
    // of floor scores high; the seam where a wall meets the floor, or
    // any other near-collinear support, scores near zero, and that is
    // the cheapest available test for "this plane is pinned down in
    // both directions".
    out.span = 0.0;

    if (out.inliers >= 3)
    {
        Eigen::Vector3d centroid = Eigen::Vector3d::Zero();

        for (uint32_t index : inliers)
        {
            centroid += candidates[index].world;
        }

        centroid /= static_cast<double>(inliers.size());

        Eigen::Matrix3d scatter = Eigen::Matrix3d::Zero();

        for (uint32_t index : inliers)
        {
            const Eigen::Vector3d d = candidates[index].world - centroid;

            scatter += d * d.transpose();
        }

        scatter /= static_cast<double>(inliers.size());

        Eigen::SelfAdjointEigenSolver<Eigen::Matrix3d> solver;
        solver.computeDirect(scatter);

        out.span = 2.0 * std::sqrt(std::max(0.0, solver.eigenvalues()(1)));
    }

    (void)cameraInWorld;
}

bool FloorEstimator::validate(const Eigen::Vector3d& up,
                              FloorDownSource source,
                              const Eigen::Vector3d& cameraInWorld,
                              Measurement& out)
{
    out.accepted = false;

    if (out.inliers < config.floorMinInliers)
    {
        ++totals.rejectedSupport;
        out.detail = "too few points on the plane";
        return false;
    }

    if (out.inlierFraction < config.floorMinInlierFraction)
    {
        ++totals.rejectedSupport;
        out.detail = "plane explains too little of the scene";
        return false;
    }

    if (out.rmsResidual > config.floorMaxResidualM)
    {
        ++totals.rejectedResidual;
        out.detail = "surface too rough to be a floor";
        return false;
    }

    if (out.span < config.floorMinSpanM)
    {
        ++totals.rejectedSpan;
        out.detail = "support is near-collinear";
        return false;
    }

    // A floor has the scene ON it. A ceiling has the scene below it,
    // and this is the test that separates the two when there is no
    // gravity at all to appeal to.
    if (out.aboveFraction < config.floorMinAboveFraction)
    {
        ++totals.rejectedAbove;
        out.detail = "scene is on the wrong side of the plane";
        return false;
    }

    const double height = out.worldPlane.signedDistance(cameraInWorld);

    if (height < config.floorMinHeightM || height > config.floorMaxHeightM)
    {
        ++totals.rejectedHeight;
        out.detail = "implausible camera height";
        return false;
    }

    double tiltDegrees = 0.0;

    const bool haveUp = (source == FloorDownSource::Imu) ||
                        (source == FloorDownSource::Nominal);

    if (haveUp)
    {
        tiltDegrees = angleBetweenDegrees(out.worldPlane.normal, up);

        if (tiltDegrees > config.floorMaxTiltDeg)
        {
            ++totals.rejectedTilt;
            out.detail = "plane is not perpendicular to gravity";
            return false;
        }
    }

    // ---- confidence ----
    //
    // Geometric mean of factors that are each exactly 0.5 at their
    // configured limit, so a measurement sitting on every threshold
    // scores 0.5 and one comfortably inside every threshold
    // approaches 1. The gravity factor is the honest penalty for
    // having had to assume an up direction rather than measure one.
    const double gravityFactor =
        (source == FloorDownSource::Imu)
            ? falling(tiltDegrees, config.floorMaxTiltDeg)
            : (source == FloorDownSource::Nominal ? 0.55
                                                  : 0.45);

    const double product =
        rising(out.inliers, config.floorMinInliers) *
        rising(out.inlierFraction, config.floorMinInlierFraction) *
        falling(out.rmsResidual, config.floorMaxResidualM) *
        rising(out.span, config.floorMinSpanM) *
        gravityFactor;

    out.confidence = clampDouble(std::pow(std::max(product, 1e-9), 0.2),
                                 0.0, 1.0);

    out.accepted = true;
    out.detail = "measured";

    return true;
}

// ===================================================================
// the three fit paths
// ===================================================================

bool FloorEstimator::refineFromPrior(const FloorInput& input,
                                     const Eigen::Vector3d& up,
                                     Measurement& out)
{
    if (!haveTracked)
    {
        return false;
    }

    selection.clear();

    const double band = config.floorPriorBandM;

    for (size_t i = 0; i < candidateCount; ++i)
    {
        if (std::abs(tracked.signedDistance(candidates[i].world)) <= band)
        {
            selection.push_back(static_cast<uint32_t>(i));
        }
    }

    if (selection.size() < static_cast<size_t>(config.floorMinInliers))
    {
        return false;
    }

    Plane plane;

    if (!fitPlane(selection, input.cameraInWorld, plane))
    {
        return false;
    }

    scorePlane(plane, input.cameraInWorld, out);

    // One re-fit on the re-selected inliers. Two rounds is enough:
    // the prior was already close, and a third costs time for a
    // change smaller than the stereo noise.
    if (out.inliers >= 3)
    {
        selection = inliers;

        Plane refined;

        if (fitPlane(selection, input.cameraInWorld, refined))
        {
            scorePlane(refined, input.cameraInWorld, out);
        }
    }

    return validate(up, lastSource, input.cameraInWorld, out);
}

bool FloorEstimator::acquireWithUp(const FloorInput& input,
                                   const Eigen::Vector3d& up,
                                   Measurement& out)
{
    // ---- 1-DOF acquisition ----
    //
    // With the normal fixed by gravity, the only unknown left is the
    // offset, and a plane's offset is just a height. So instead of
    // sampling triples of points and hoping one lands on the floor,
    // project every candidate onto the up axis and look for the
    // LOWEST significant cluster. This is deterministic, O(n), and it
    // cannot pick a table top over the floor the way a plain
    // support-maximising RANSAC routinely does, because the floor is
    // always the lower of the two.

    if (candidateCount == 0)
    {
        return false;
    }

    double lowest = 0.0;
    double highest = 0.0;

    for (size_t i = 0; i < candidateCount; ++i)
    {
        candidates[i].height = up.dot(candidates[i].world);

        if (i == 0)
        {
            lowest = highest = candidates[i].height;
        }
        else
        {
            lowest = std::min(lowest, candidates[i].height);
            highest = std::max(highest, candidates[i].height);
        }
    }

    const double binWidth = std::max(0.01, config.floorHeightBinM);

    int bins = static_cast<int>((highest - lowest) / binWidth) + 1;

    bins = std::min(bins, kMaxHistogramBins);

    if (bins < 1)
    {
        return false;
    }

    std::fill(histogram.begin(), histogram.begin() + bins, 0);

    for (size_t i = 0; i < candidateCount; ++i)
    {
        int bin = static_cast<int>((candidates[i].height - lowest) /
                                   binWidth);

        bin = std::min(bins - 1, std::max(0, bin));

        ++histogram[static_cast<size_t>(bin)];
    }

    // Peak of the 3-bin window, used only as a scale for "significant".
    int peak = 0;

    for (int bin = 0; bin < bins; ++bin)
    {
        int window = histogram[static_cast<size_t>(bin)];

        if (bin > 0)
        {
            window += histogram[static_cast<size_t>(bin - 1)];
        }

        if (bin + 1 < bins)
        {
            window += histogram[static_cast<size_t>(bin + 1)];
        }

        peak = std::max(peak, window);
    }

    const int threshold = std::max(
        config.floorMinInliers,
        static_cast<int>(config.floorClusterPeakFraction *
                         static_cast<double>(peak))
    );

    int chosen = -1;

    for (int bin = 0; bin < bins; ++bin)
    {
        int window = histogram[static_cast<size_t>(bin)];

        if (bin > 0)
        {
            window += histogram[static_cast<size_t>(bin - 1)];
        }

        if (bin + 1 < bins)
        {
            window += histogram[static_cast<size_t>(bin + 1)];
        }

        if (window >= threshold)
        {
            chosen = bin;
            break;
        }
    }

    if (chosen < 0)
    {
        ++totals.rejectedSupport;
        out.detail = "no significant height cluster";
        return false;
    }

    // Mean height of the cluster, which is a much better centre than
    // the bin edge.
    const double centreLow = lowest + (chosen - 1) * binWidth;
    const double centreHigh = lowest + (chosen + 2) * binWidth;

    double sum = 0.0;
    int count = 0;

    for (size_t i = 0; i < candidateCount; ++i)
    {
        if (candidates[i].height >= centreLow &&
            candidates[i].height <= centreHigh)
        {
            sum += candidates[i].height;
            ++count;
        }
    }

    if (count < 3)
    {
        return false;
    }

    const double centre = sum / static_cast<double>(count);

    selection.clear();

    for (size_t i = 0; i < candidateCount; ++i)
    {
        if (std::abs(candidates[i].height - centre) <=
            config.floorClusterBandM)
        {
            selection.push_back(static_cast<uint32_t>(i));
        }
    }

    if (selection.size() < 3)
    {
        return false;
    }

    Plane plane;

    if (!fitPlane(selection, input.cameraInWorld, plane))
    {
        // The cluster is real but too flat to orient a normal from.
        // Fall back to the gravity normal itself, which is exactly
        // what the constraint says it should be.
        plane.normal = up;
        plane.offset = -centre;
    }

    scorePlane(plane, input.cameraInWorld, out);

    if (out.inliers >= 3)
    {
        selection = inliers;

        Plane refined;

        if (fitPlane(selection, input.cameraInWorld, refined))
        {
            scorePlane(refined, input.cameraInWorld, out);
        }
    }

    return validate(up, lastSource, input.cameraInWorld, out);
}

bool FloorEstimator::acquireUnconstrained(const FloorInput& input,
                                          Measurement& out)
{
    // No gravity, no prior, no upright assumption. This is the weakest
    // mode and its confidence is penalised for it in validate().
    //
    // Even here the sampling is not generic: a hypothesis must put the
    // camera at a plausible height above the plane and must have the
    // scene on one side of it, so most of the walls and ceilings are
    // never scored at all.

    if (candidateCount < 3)
    {
        return false;
    }

    const int iterations = std::max(8, config.floorRansacIterations);
    const double band = config.floorInlierBandM;

    int bestSupport = 0;
    Plane bestPlane;

    for (int iteration = 0; iteration < iterations; ++iteration)
    {
        const size_t a = static_cast<size_t>(
            deterministicRandom() * static_cast<double>(candidateCount));
        const size_t b = static_cast<size_t>(
            deterministicRandom() * static_cast<double>(candidateCount));
        const size_t c = static_cast<size_t>(
            deterministicRandom() * static_cast<double>(candidateCount));

        if (a == b || b == c || a == c ||
            a >= candidateCount || b >= candidateCount ||
            c >= candidateCount)
        {
            continue;
        }

        const Eigen::Vector3d& p0 = candidates[a].world;
        const Eigen::Vector3d& p1 = candidates[b].world;
        const Eigen::Vector3d& p2 = candidates[c].world;

        const Eigen::Vector3d e1 = p1 - p0;
        const Eigen::Vector3d e2 = p2 - p0;

        // Spread requirement: three points a few centimetres apart
        // define a plane whose normal is pure stereo noise.
        if (e1.norm() < config.floorMinSpanM ||
            e2.norm() < config.floorMinSpanM)
        {
            continue;
        }

        Eigen::Vector3d normal = e1.cross(e2);

        const double area = normal.norm();

        if (!(area > 1e-4))
        {
            continue;
        }

        normal /= area;

        if (normal.dot(input.cameraInWorld - p0) < 0.0)
        {
            normal = -normal;
        }

        Plane plane;
        plane.normal = normal;
        plane.offset = -normal.dot(p0);

        const double height = plane.signedDistance(input.cameraInWorld);

        if (height < config.floorMinHeightM ||
            height > config.floorMaxHeightM)
        {
            continue;
        }

        int support = 0;
        int above = 0;

        for (size_t i = 0; i < candidateCount; ++i)
        {
            const double r = plane.signedDistance(candidates[i].world);

            if (std::abs(r) <= band)
            {
                ++support;
            }

            if (r >= -band)
            {
                ++above;
            }
        }

        const double aboveFraction =
            static_cast<double>(above) /
            static_cast<double>(candidateCount);

        if (aboveFraction < config.floorMinAboveFraction)
        {
            continue;
        }

        if (support > bestSupport)
        {
            bestSupport = support;
            bestPlane = plane;
        }
    }

    if (bestSupport < 3 || !bestPlane.valid())
    {
        ++totals.rejectedSupport;
        out.detail = "no plane hypothesis found support";
        return false;
    }

    scorePlane(bestPlane, input.cameraInWorld, out);

    if (out.inliers >= 3)
    {
        selection = inliers;

        Plane refined;

        if (fitPlane(selection, input.cameraInWorld, refined))
        {
            scorePlane(refined, input.cameraInWorld, out);
        }
    }

    return validate(Eigen::Vector3d::Zero(), FloorDownSource::None,
                    input.cameraInWorld, out);
}

double FloorEstimator::deterministicRandom() const
{
    // Plain LCG. Deterministic on purpose: the same recording must
    // produce the same floor every time it is replayed, which rules
    // out anything seeded from a clock.
    randomState = randomState * 1664525u + 1013904223u;

    return static_cast<double>(randomState >> 8) /
           static_cast<double>(1u << 24);
}

// ===================================================================
// measurement cycle
// ===================================================================

void FloorEstimator::measure(const FloorInput& input, Measurement& out)
{
    ++totals.measurements;

    out = Measurement();

    if (selectCandidates(input) <
        static_cast<size_t>(config.floorMinInliers))
    {
        ++totals.rejectedCandidates;
        out.detail = "too few stereo points with usable depth";
        return;
    }

    Eigen::Vector3d up = Eigen::Vector3d::Zero();
    FloorDownSource source = FloorDownSource::None;

    resolveUp(up, source);

    lastSource = source;

    bool got = false;

    // Prior first: cheapest, and the only path that cannot make the
    // floor jump. Acquisition runs only when it fails.
    if (haveTracked && trackedConfidence >= config.floorLostConfidence)
    {
        got = refineFromPrior(input, up, out);
    }

    if (!got)
    {
        if (source != FloorDownSource::None)
        {
            got = acquireWithUp(input, up, out);
        }
        else
        {
            got = acquireUnconstrained(input, out);
        }
    }

    if (!got)
    {
        return;
    }

    // ---- agreement with what is already tracked ----
    //
    // A measurement that disagrees with the tracked floor is not
    // automatically right and not automatically wrong. One is noise;
    // several in a row means the world changed - a different floor
    // level, a lift, or SLAM drift - and the tracked plane has to be
    // abandoned rather than defended forever.
    if (haveTracked && status != FloorStatus::Unknown)
    {
        const double turn = angleBetweenDegrees(out.worldPlane.normal,
                                                tracked.normal);

        const double shift = std::abs(
            out.worldPlane.signedDistance(input.cameraInWorld) -
            tracked.signedDistance(input.cameraInWorld));

        if (turn > config.floorMaxJumpDeg || shift > config.floorMaxJumpM)
        {
            ++disagreements;

            if (disagreements < config.floorReacquireAfter)
            {
                out.accepted = false;
                out.detail = "disagrees with the tracked floor";
                return;
            }

            // Persistent disagreement wins. Throw the old plane away
            // and adopt this one outright rather than blending
            // towards it for the next second.
            ++totals.reacquisitions;

            haveTracked = false;
            goodObservations = 0;
            trackedConfidence = 0.0;

            LOG_INFO("floor: re-acquiring, %.1f deg / %.2f m from the "
                     "tracked plane over %d measurements",
                     turn, shift, disagreements);
        }
    }

    disagreements = 0;

    ++totals.accepted;
}

void FloorEstimator::integrate(const Measurement& measurement,
                               const FloorInput& input)
{
    if (!haveTracked)
    {
        tracked = measurement.worldPlane;
        haveTracked = true;
        trackedConfidence = 0.5 * measurement.confidence;
        goodObservations = 1;
    }
    else
    {
        // Gain rises with how good the measurement is. A weak
        // measurement nudges; a strong one moves.
        const double alpha = clampDouble(
            config.floorBlendAlpha * measurement.confidence, 0.05, 0.8);

        Eigen::Vector3d normal =
            (1.0 - alpha) * tracked.normal +
            alpha * measurement.worldPlane.normal;

        const double length = normal.norm();

        if (length > 1e-6)
        {
            normal /= length;

            // The offset is blended THROUGH the camera height, not
            // directly. Two planes with slightly different normals
            // have offsets that are not comparable - blending the raw
            // d makes the floor lurch whenever the normal moves. The
            // height under the camera is the quantity a consumer
            // actually cares about, and it is comparable.
            const double previousHeight =
                tracked.signedDistance(input.cameraInWorld);

            const double measuredHeight =
                measurement.worldPlane.signedDistance(input.cameraInWorld);

            const double height =
                (1.0 - alpha) * previousHeight + alpha * measuredHeight;

            tracked.normal = normal;
            tracked.offset = height - normal.dot(input.cameraInWorld);
        }

        trackedConfidence +=
            alpha * (measurement.confidence - trackedConfidence);

        ++goodObservations;
    }

    trackedConfidence = clampDouble(trackedConfidence, 0.0, 1.0);

    lastAcceptedTime = input.timestamp;
    lastAccepted = measurement;

    if (goodObservations >= config.floorMinInitObservations &&
        trackedConfidence >= config.floorTrackingConfidence)
    {
        status = FloorStatus::Tracking;
    }
    else
    {
        status = FloorStatus::Initializing;
    }

    // ---- debug point lists ----
    debugInlierPixels.clear();
    debugInlierIds.clear();
    debugRejectedPixels.clear();

    const double band = config.floorInlierBandM;

    for (size_t i = 0; i < candidateCount; ++i)
    {
        if (std::abs(tracked.signedDistance(candidates[i].world)) <= band)
        {
            debugInlierPixels.push_back(candidates[i].pixel);
            debugInlierIds.push_back(candidates[i].featureId);
        }
        else
        {
            debugRejectedPixels.push_back(candidates[i].pixel);
        }
    }
}

void FloorEstimator::decay(const FloorInput& input)
{
    if (!haveTracked)
    {
        status = FloorStatus::Unknown;
        trackedConfidence = 0.0;
        return;
    }

    const double elapsed = std::max(0.0,
                                    input.timestamp - lastAcceptedTime);

    const double tau = std::max(0.05, config.floorDecayTauSeconds);

    // Confidence is a function of the AGE of the last accepted
    // measurement, not a repeated multiplication. That makes it
    // independent of how often update() happens to be called and
    // impossible to decay twice for one frame.
    const double aged = lastAccepted.confidence * std::exp(-elapsed / tau);

    trackedConfidence = std::min(trackedConfidence, std::max(aged, 0.0));

    if (trackedConfidence < config.floorUnknownConfidence)
    {
        if (status != FloorStatus::Unknown)
        {
            ++totals.lostEvents;

            LOG_INFO("floor: lost after %.1f s without a measurement",
                     elapsed);
        }

        haveTracked = false;
        tracked = Plane();
        goodObservations = 0;
        status = FloorStatus::Unknown;
    }
    else if (trackedConfidence < config.floorLostConfidence)
    {
        status = FloorStatus::Lost;
    }
    else if (status == FloorStatus::Tracking ||
             status == FloorStatus::Predicting ||
             status == FloorStatus::Lost)
    {
        status = FloorStatus::Predicting;
    }
}

// ===================================================================
// publication (the per-frame prediction)
// ===================================================================

void FloorEstimator::publishFrom(const FloorInput& input)
{
    FloorEstimate& e = published;

    const char* detail = e.detail;

    e = FloorEstimate();

    e.detail = detail;
    e.timestamp = input.timestamp;
    e.frameId = input.frameId;
    e.status = status;
    e.confidence = trackedConfidence;
    e.downSource = lastSource;

    e.candidateCount = lastAccepted.candidates;
    e.inlierCount = lastAccepted.inliers;
    e.inlierFraction = lastAccepted.inlierFraction;
    e.rmsResidualM = lastAccepted.rmsResidual;
    e.spanMeters = lastAccepted.span;
    e.aboveFraction = lastAccepted.aboveFraction;

    e.ageSeconds = (lastAcceptedTime > 0.0)
        ? std::max(0.0, input.timestamp - lastAcceptedTime)
        : 0.0;

    if (!haveTracked || !tracked.valid())
    {
        e.valid = false;
        return;
    }

    e.worldPlane = tracked;
    e.normalWorld = tracked.normal;

    // Everything below is the prediction: the world plane, expressed
    // in the camera frame this frame's pose defines. Rotating the
    // head does not change the floor - it changes this transform.
    e.cameraPlane = planeInFrame(tracked, input.worldFromCamera,
                                 input.cameraInWorld);

    e.normalCamera = e.cameraPlane.normal;

    e.cameraHeight = tracked.signedDistance(input.cameraInWorld);
    e.distanceToCamera = std::abs(e.cameraHeight);

    e.floorPointWorld =
        input.cameraInWorld - e.cameraHeight * tracked.normal;

    // In the camera frame the optical centre is the origin, so the
    // foot of the perpendicular is simply -d * n.
    e.floorPointCamera = -e.cameraPlane.offset * e.normalCamera;

    // Camera up in the camera frame is -Y: the convention is Y down.
    const Eigen::Vector3d cameraUp(0.0, -1.0, 0.0);

    e.tiltDegrees = angleBetweenDegrees(e.normalCamera, cameraUp);

    e.pitchDegrees = std::atan2(e.normalCamera.z(),
                                -e.normalCamera.y()) * kDegrees;

    e.rollDegrees = std::atan2(e.normalCamera.x(),
                               -e.normalCamera.y()) * kDegrees;

    e.gravityAngleDegrees = haveGravity
        ? angleBetweenDegrees(tracked.normal, gravityUpWorld)
        : -1.0;

    e.valid = (status == FloorStatus::Tracking ||
               status == FloorStatus::Predicting) &&
              trackedConfidence >= config.floorLostConfidence;
}

// ===================================================================

const FloorEstimate& FloorEstimator::update(const FloorInput& input,
                                            Profiler& profiler)
{
    ++totals.updates;

    if (!config.floorEnabled)
    {
        published.valid = false;
        published.status = FloorStatus::Unknown;
        published.detail = "disabled";
        return published;
    }

    ScopedStage timing(profiler, Stage::Floor);

    updateGravity(input);

    const double interval = (config.floorUpdateHz > 0.0)
        ? 1.0 / config.floorUpdateHz
        : 0.0;

    // Measure on the configured schedule, and always while there is
    // no floor to predict from - an unknown floor is worth spending
    // the time to find.
    const bool due =
        (lastMeasurementTime <= 0.0) ||
        (input.timestamp - lastMeasurementTime >= interval) ||
        (status == FloorStatus::Unknown) ||
        (status == FloorStatus::Lost);

    bool measured = false;

    // A pose that was carried forward rather than measured would place
    // every world point with a stale transform, which is exactly how a
    // floor estimate ends up confidently wrong. Predict instead.
    if (due && input.poseValid)
    {
        lastMeasurementTime = input.timestamp;

        Measurement measurement;

        measure(input, measurement);

        if (measurement.accepted)
        {
            integrate(measurement, input);
            measured = true;
        }

        published.detail = measurement.detail;
    }
    else if (!input.poseValid)
    {
        published.detail = "pose not measured this frame";
    }

    if (!measured)
    {
        decay(input);
    }

    publishFrom(input);

    return published;
}

// ===================================================================
// debug output
// ===================================================================

bool FloorEstimator::buildMask(const cv::Size& size, cv::Mat& mask) const
{
    if (size.width <= 0 || size.height <= 0 ||
        debugInlierPixels.size() < 3)
    {
        return false;
    }

    if (mask.size() != size || mask.type() != CV_8UC1)
    {
        mask.create(size, CV_8UC1);
    }

    mask.setTo(0);

    // The stereo support is SPARSE, so this is the region the floor
    // points span, not a per-pixel segmentation. Named a mask because
    // that is what a consumer wants to intersect against; documented
    // as coarse because pretending otherwise would be a lie.
    hullScratch.clear();

    cv::convexHull(debugInlierPixels, hullScratch);

    if (hullScratch.size() < 3)
    {
        return false;
    }

    std::vector<cv::Point> polygon;

    polygon.reserve(hullScratch.size());

    for (const cv::Point2f& p : hullScratch)
    {
        polygon.emplace_back(cvRound(p.x), cvRound(p.y));
    }

    const cv::Point* points = polygon.data();
    const int count = static_cast<int>(polygon.size());

    cv::fillPoly(mask, &points, &count, 1, cv::Scalar(255));

    return true;
}

void FloorEstimator::drawDebug(cv::Mat& bgr,
                               const cv::Matx33d& cameraMatrix,
                               const cv::Vec4d& distortion) const
{
    if (bgr.empty() || bgr.type() != CV_8UC3)
    {
        return;
    }

    const cv::Scalar green(80, 220, 80);
    const cv::Scalar red(70, 70, 240);
    const cv::Scalar cyan(230, 230, 60);
    const cv::Scalar white(240, 240, 240);

    for (const cv::Point2f& p : debugRejectedPixels)
    {
        cv::circle(bgr, p, 2, red, 1, cv::LINE_AA);
    }

    for (const cv::Point2f& p : debugInlierPixels)
    {
        cv::circle(bgr, p, 3, green, -1, cv::LINE_AA);
    }

    if (published.valid)
    {
        // A grid on the plane, drawn around the point under the
        // camera. Projected with the fisheye model, because a pinhole
        // projection of a wide-angle ray lands in the wrong place and
        // a debug overlay that lies is worse than none.
        const Eigen::Vector3d n = published.normalCamera;
        const Eigen::Vector3d origin = published.floorPointCamera;

        const Eigen::Vector3d u = perpendicular(n);
        const Eigen::Vector3d v = n.cross(u);

        std::vector<cv::Point3f> object;
        std::vector<cv::Point2f> image;

        const int half = 3;
        const double step = 0.5;

        auto push = [&](int i, int j)
        {
            const Eigen::Vector3d p =
                origin + (i * step) * u + (j * step) * v;

            object.emplace_back(static_cast<float>(p.x()),
                                static_cast<float>(p.y()),
                                static_cast<float>(p.z()));
        };

        for (int i = -half; i <= half; ++i)
        {
            for (int j = -half; j <= half; ++j)
            {
                push(i, j);
            }
        }

        // The normal arrow, as the last two points.
        object.emplace_back(static_cast<float>(origin.x()),
                            static_cast<float>(origin.y()),
                            static_cast<float>(origin.z()));

        const Eigen::Vector3d tip = origin + 0.5 * n;

        object.emplace_back(static_cast<float>(tip.x()),
                            static_cast<float>(tip.y()),
                            static_cast<float>(tip.z()));

        cv::fisheye::projectPoints(object, image,
                                   cv::Vec3d(0, 0, 0),
                                   cv::Vec3d(0, 0, 0),
                                   cameraMatrix, distortion);

        const int side = 2 * half + 1;

        auto visible = [&](size_t index)
        {
            return object[index].z > 0.05f &&
                   std::isfinite(image[index].x) &&
                   std::isfinite(image[index].y);
        };

        for (int i = 0; i < side; ++i)
        {
            for (int j = 0; j < side; ++j)
            {
                const size_t here = static_cast<size_t>(i * side + j);

                if (j + 1 < side)
                {
                    const size_t next = here + 1;

                    if (visible(here) && visible(next))
                    {
                        cv::line(bgr, image[here], image[next], cyan, 1,
                                 cv::LINE_AA);
                    }
                }

                if (i + 1 < side)
                {
                    const size_t next =
                        here + static_cast<size_t>(side);

                    if (visible(here) && visible(next))
                    {
                        cv::line(bgr, image[here], image[next], cyan, 1,
                                 cv::LINE_AA);
                    }
                }
            }
        }

        const size_t base = image.size() - 2;

        if (visible(base) && visible(base + 1))
        {
            cv::arrowedLine(bgr, image[base], image[base + 1], white, 2,
                            cv::LINE_AA);
        }
    }

    // ---- text block ----
    char line[192];

    int y = bgr.rows - 74;

    auto label = [&](const char* text, const cv::Scalar& colour)
    {
        cv::putText(bgr, text, cv::Point(9, y + 1),
                    cv::FONT_HERSHEY_SIMPLEX, 0.42,
                    cv::Scalar(20, 20, 20), 2, cv::LINE_AA);

        cv::putText(bgr, text, cv::Point(8, y),
                    cv::FONT_HERSHEY_SIMPLEX, 0.42, colour, 1,
                    cv::LINE_AA);

        y += 16;
    };

    snprintf(line, sizeof(line), "FLOOR  %s  (%s)",
             floorStatusName(published.status),
             floorDownSourceName(published.downSource));

    label(line, published.valid ? green : red);

    if (published.valid)
    {
        snprintf(line, sizeof(line),
                 "height %.3f m   dist %.3f m   conf %.2f   age %.1f s",
                 published.cameraHeight, published.distanceToCamera,
                 published.confidence, published.ageSeconds);

        label(line, white);

        snprintf(line, sizeof(line),
                 "normal cam % .3f % .3f % .3f   tilt %.1f deg",
                 published.normalCamera.x(), published.normalCamera.y(),
                 published.normalCamera.z(), published.tiltDegrees);

        label(line, white);

        snprintf(line, sizeof(line),
                 "inliers %d/%d   rms %.3f m   span %.2f m",
                 published.inlierCount, published.candidateCount,
                 published.rmsResidualM, published.spanMeters);

        label(line, white);
    }
    else
    {
        snprintf(line, sizeof(line), "GROUND UNKNOWN : %s",
                 published.detail);

        label(line, red);
    }
}

} // namespace novex
