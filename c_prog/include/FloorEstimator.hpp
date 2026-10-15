#pragma once

#include "FeatureTracker.hpp"
#include "IMU.hpp"
#include "Profiler.hpp"
#include "VIOConfig.hpp"

#include <Eigen/Core>
#include <Eigen/Geometry>

#include <opencv2/core.hpp>

#include <cstdint>
#include <vector>

namespace novex
{

// ===================================================================
// Floor / ground plane estimation
// ===================================================================
//
// COORDINATE FRAMES - stated explicitly, because every sign below
// depends on them and none of them is a convention borrowed from
// somewhere else.
//
//   CAMERA frame   Novex / OpenCV: X right, Y DOWN, Z forward along
//                  the optical axis of the LEFT lens. This is the
//                  frame Feature::position3D is measured in.
//
//   WORLD frame    The estimator's INTERNAL world, i.e. the first
//                  tracked camera pose. X_world = R_wc * X_camera +
//                  p_wc with (R_wc, p_wc) = StateEstimator::
//                  internalRotation() / internalPosition().
//
//                  It is NOT gravity aligned. It is only "Y down" to
//                  the extent that the camera happened to be level at
//                  start-up, which is exactly why this class never
//                  assumes it without saying so (see DownSource).
//
//   REPORTED frame The recenter frame. Nothing here works in it; use
//                  planeInFrame() with the recenter origin to express
//                  a result there.
//
// PLANE CONVENTION
//
//   n . X + d = 0, with |n| = 1, and n ALWAYS oriented to point from
//   the floor towards the camera - i.e. n is "up". That makes
//
//       height = n . C + d
//
//   the SIGNED height of a point C above the floor, positive above.
//   Nothing here reads a Y coordinate to get a height.
//
// The estimator is a geometric sensor-fusion component. It consumes
// the sparse stereo points the pipeline already produces, the pose
// the pipeline already integrates and, when it is trustworthy, the
// IMU's gravity direction. It contains no learned model, and no
// image-space assumption such as "the floor is the bottom of the
// frame": a headset can look up and a drone can look backwards.

// A plane in whatever frame the holder says it is in.
struct Plane
{
    Eigen::Vector3d normal = Eigen::Vector3d::Zero();
    double offset = 0.0;

    bool valid() const { return normal.squaredNorm() > 0.5; }

    // Signed distance, positive on the side the normal points to.
    double signedDistance(const Eigen::Vector3d& point) const
    {
        return normal.dot(point) + offset;
    }

    // Foot of the perpendicular from `point`.
    Eigen::Vector3d project(const Eigen::Vector3d& point) const
    {
        return point - signedDistance(point) * normal;
    }
};

// Re-expresses a plane given in frame A in frame B, where
// X_A = R * X_B + t.
//
//   n_B = R^T n_A,   d_B = d_A + n_A . t
//
// Used both for world -> camera (R_wc, p_wc) and for internal ->
// reported (R_origin, p_origin), which are the same operation.
Plane planeInFrame(const Plane& plane,
                   const Eigen::Matrix3d& rotation,
                   const Eigen::Vector3d& translation);

enum class FloorStatus
{
    Unknown = 0,    // nothing is known; no plane is published
    Initializing,   // a plane exists but has not been confirmed enough
    Tracking,       // confirmed and being measured
    Predicting,     // no measurement this cycle, prediction is carried
    Lost            // held far too long; confidence nearly gone
};

const char* floorStatusName(FloorStatus status);

// Where the "down" direction used to constrain the fit came from.
// This is reported because it is the single biggest determinant of
// how much the result can be trusted.
enum class FloorDownSource
{
    None = 0,   // unconstrained robust fit; weakest case
    Nominal,    // world -Y, i.e. the camera was assumed upright at
                // start-up (config: floor.assume_upright_start)
    Tracked,    // the floor normal this estimator already holds
    Imu         // measured gravity, low-passed
};

const char* floorDownSourceName(FloorDownSource source);

// The estimator's output. Deliberately plain, fixed size and
// copyable, for the same reason VIOState is: the IPC server snapshots
// it under a mutex.
struct FloorEstimate
{
    bool valid = false;
    FloorStatus status = FloorStatus::Unknown;

    // 0..1. NOT a probability - a smoothly degrading ranking score,
    // built the same way pointQuality() is.
    double confidence = 0.0;

    double timestamp = 0.0;
    uint64_t frameId = 0;

    // n . X + d = 0 in each frame. Only meaningful while `valid`.
    Plane cameraPlane;
    Plane worldPlane;

    // Same normals, spelled out because most consumers want only
    // these two vectors.
    Eigen::Vector3d normalCamera = Eigen::Vector3d::Zero();
    Eigen::Vector3d normalWorld = Eigen::Vector3d::Zero();

    // Perpendicular distance from the left optical centre to the
    // plane, metres. Always non-negative.
    double distanceToCamera = 0.0;

    // Signed height of the optical centre above the floor, along the
    // floor normal. Positive above. This is NOT a world Y coordinate.
    double cameraHeight = 0.0;

    // Foot of the perpendicular from the optical centre, in each
    // frame. The point on the floor directly "under" the camera.
    Eigen::Vector3d floorPointCamera = Eigen::Vector3d::Zero();
    Eigen::Vector3d floorPointWorld = Eigen::Vector3d::Zero();

    // ---- camera / floor relative orientation ----
    //
    // Yaw about the floor normal is NOT observable from a plane and
    // is deliberately absent.

    // Angle between the camera's own up axis (0, -1, 0) and the floor
    // normal. 0 = camera level with the floor.
    double tiltDegrees = 0.0;

    // Decomposition of that tilt. Positive pitch = the camera is
    // nosed DOWN, towards the floor. Positive roll = the camera is
    // rolled so the floor normal leans towards +X in the image.
    double pitchDegrees = 0.0;
    double rollDegrees = 0.0;

    // Angle between the floor normal and measured gravity-up.
    // Negative when no gravity measurement was available.
    double gravityAngleDegrees = -1.0;

    FloorDownSource downSource = FloorDownSource::None;

    // ---- measurement quality of the last ACCEPTED observation ----

    int candidateCount = 0;     // stereo points that passed the gates
    int inlierCount = 0;        // of those, on the plane
    double inlierFraction = 0.0;
    double rmsResidualM = 0.0;

    // Extent of the inliers across the plane, metres: twice the
    // square root of the SMALLER in-plane variance. A wall/floor
    // seam, or any other near-collinear support, has a small value
    // here and is rejected on it.
    double spanMeters = 0.0;

    // Fraction of all candidate points lying on or above the plane.
    // A ceiling scores near zero here and is rejected on it.
    double aboveFraction = 0.0;

    // Seconds since the last accepted measurement. Grows while
    // PREDICTING.
    double ageSeconds = 0.0;

    // Why the last cycle ended as it did. Static string, never null.
    const char* detail = "no data";

    EIGEN_MAKE_ALIGNED_OPERATOR_NEW
};

// Everything one update needs. Passing a struct keeps the call site
// readable and lets fields be added without touching every caller.
struct FloorInput
{
    // Current frame's tracked features, with live stereo depth in the
    // CAMERA frame. Never modified.
    const std::vector<Feature>* features = nullptr;

    // Internal world pose of this frame: X_world = R * X_camera + p.
    Eigen::Matrix3d worldFromCamera = Eigen::Matrix3d::Identity();
    Eigen::Vector3d cameraInWorld = Eigen::Vector3d::Zero();

    // False when motion estimation failed this frame and the pose is
    // being carried forward. Measurement is suppressed; prediction
    // still runs.
    bool poseValid = false;

    // IMU samples covering this frame interval, or null. Used only
    // for gravity.
    const std::vector<IMUSample>* imu = nullptr;

    double timestamp = 0.0;
    uint64_t frameId = 0;

    EIGEN_MAKE_ALIGNED_OPERATOR_NEW
};

// Run totals, for the dashboard and the debug report.
struct FloorCounters
{
    uint64_t updates = 0;          // update() calls
    uint64_t measurements = 0;     // full measurement cycles run
    uint64_t accepted = 0;         // measurements that passed
    uint64_t rejectedCandidates = 0;   // too few candidate points
    uint64_t rejectedSupport = 0;      // too few inliers / fraction
    uint64_t rejectedResidual = 0;     // plane too rough
    uint64_t rejectedSpan = 0;         // support near-collinear
    uint64_t rejectedHeight = 0;       // implausible camera height
    uint64_t rejectedTilt = 0;         // too far from gravity
    uint64_t rejectedAbove = 0;        // scene on the wrong side
    uint64_t reacquisitions = 0;       // tracked plane thrown away
    uint64_t lostEvents = 0;
};

// ===================================================================
// FloorEstimator
// ===================================================================
//
// Two rates, on purpose:
//
//   every frame          prediction. The tracked WORLD plane is
//                        re-expressed in the current camera frame and
//                        the height recomputed. About twenty flops;
//                        it is what keeps the floor stable under
//                        rotation without measuring anything.
//
//   floor.update_hz      measurement. Candidate selection, plane
//                        fitting, validation, temporal update.
//
// Nothing here allocates after configure().
class FloorEstimator
{
public:

    explicit FloorEstimator(const VIOConfig& config);

    // Sizes the scratch buffers. Safe to call again.
    void configure(size_t maxFeatures);

    // Back to Unknown; the tracked plane and the gravity filter are
    // discarded. Called on estimator reset, because the world frame
    // the plane is expressed in has just been redefined.
    void reset();

    // One frame. Always cheap; runs a full measurement only when the
    // configured interval has elapsed or the floor is not tracked.
    const FloorEstimate& update(const FloorInput& input,
                                Profiler& profiler);

    const FloorEstimate& estimate() const { return published; }

    const FloorCounters& counters() const { return totals; }

    // ---- debug, VIO thread only ----
    //
    // Image points of the accepted and rejected candidates of the
    // last MEASUREMENT cycle. Empty in the frames between cycles.

    const std::vector<cv::Point2f>& inlierPixels() const
    {
        return debugInlierPixels;
    }

    const std::vector<cv::Point2f>& rejectedPixels() const
    {
        return debugRejectedPixels;
    }

    const std::vector<uint32_t>& inlierFeatureIds() const
    {
        return debugInlierIds;
    }

    // Coarse floor mask: the convex hull of the inlier image points,
    // filled with 255 in an 8-bit single channel image of `size`.
    //
    // Honest about what it is - the stereo support is sparse, so this
    // is the region the floor points span, not a per-pixel
    // segmentation. Returns false when there is nothing to draw.
    bool buildMask(const cv::Size& size, cv::Mat& mask) const;

    // Draws the estimate over a BGR image: inliers, rejected points,
    // a plane grid around the point under the camera, the normal, and
    // a text block. Does nothing when the image is not 3-channel.
    void drawDebug(cv::Mat& bgr,
                   const cv::Matx33d& cameraMatrix,
                   const cv::Vec4d& distortion) const;

private:

    // One candidate stereo point, camera frame, kept flat.
    struct Candidate
    {
        Eigen::Vector3d camera;
        Eigen::Vector3d world;
        cv::Point2f pixel;
        uint32_t featureId;
        double weight;       // 1 / sigma^2 of the range measurement
        double height;       // along the current up direction
    };

    // Result of one fit, before the temporal filter sees it.
    struct Measurement
    {
        Plane worldPlane;
        double confidence = 0.0;
        int inliers = 0;
        int candidates = 0;
        double inlierFraction = 0.0;
        double rmsResidual = 0.0;
        double span = 0.0;
        double aboveFraction = 0.0;
        bool accepted = false;
        const char* detail = "";
    };

    void updateGravity(const FloorInput& input);

    // Resolves the up direction in the WORLD frame and reports where
    // it came from. Returns false only for DownSource::None.
    bool resolveUp(Eigen::Vector3d& up, FloorDownSource& source) const;

    // Fills `candidates` from the features. Returns the count.
    size_t selectCandidates(const FloorInput& input);

    // Full measurement cycle.
    void measure(const FloorInput& input, Measurement& out);

    // Prior-guided path: refine the plane this estimator already
    // holds against the new points. Cheapest and most stable.
    bool refineFromPrior(const FloorInput& input,
                         const Eigen::Vector3d& up,
                         Measurement& out);

    // Acquisition with a known up direction: a 1-DOF search over
    // height. The normal is given, so only the offset is unknown, and
    // a histogram finds it with no random sampling at all.
    bool acquireWithUp(const FloorInput& input,
                       const Eigen::Vector3d& up,
                       Measurement& out);

    // Acquisition with no up direction: constrained 3-point RANSAC.
    bool acquireUnconstrained(const FloorInput& input,
                              Measurement& out);

    // Iteratively reweighted least squares plane fit over the
    // candidates whose index is in `selection`. Writes the fitted
    // world plane, oriented towards `towards`. Returns false if the
    // support is degenerate.
    bool fitPlane(const std::vector<uint32_t>& selection,
                  const Eigen::Vector3d& towards,
                  Plane& plane) const;

    // Re-selects inliers of `plane` from every candidate and measures
    // the fit. Fills everything in `out` except accepted/detail.
    void scorePlane(const Plane& plane,
                    const Eigen::Vector3d& cameraInWorld,
                    Measurement& out);

    // Applies every acceptance gate to a scored measurement.
    bool validate(const Eigen::Vector3d& up,
                  FloorDownSource source,
                  const Eigen::Vector3d& cameraInWorld,
                  Measurement& out);

    // Blends an accepted measurement into the tracked plane.
    void integrate(const Measurement& measurement,
                   const FloorInput& input);

    // No measurement this cycle: decay and re-classify.
    void decay(const FloorInput& input);

    // Recomputes every published field from the tracked world plane
    // and the current pose. This is the per-frame prediction.
    void publishFrom(const FloorInput& input);

    double deterministicRandom() const;

    const VIOConfig& config;

    // ---- tracked state, WORLD frame ----
    Plane tracked;
    bool haveTracked = false;
    double trackedConfidence = 0.0;
    FloorStatus status = FloorStatus::Unknown;
    FloorDownSource lastSource = FloorDownSource::None;

    double lastMeasurementTime = 0.0;
    double lastAcceptedTime = 0.0;
    int goodObservations = 0;
    int disagreements = 0;

    // ---- gravity ----
    //
    // Low-passed UP direction in the world frame, from the
    // accelerometer. Updated only from samples that look like a
    // platform in free-ish rotation at 1 g.
    Eigen::Vector3d gravityUpWorld = Eigen::Vector3d::Zero();
    bool haveGravity = false;
    double lastGravityTime = 0.0;

    // ---- scratch, allocated once ----
    std::vector<Candidate> candidates;
    size_t candidateCount = 0;

    std::vector<uint32_t> selection;
    std::vector<uint32_t> inliers;
    std::vector<int32_t> histogram;

    // Written by fitPlane(), which is const because it does not touch
    // the estimate - only these buffers, which exist so it never
    // allocates.
    mutable std::vector<double> scratchScalars;
    mutable std::vector<double> hullScratchResiduals;

    // The last measurement that was actually integrated. Its quality
    // figures are what the published estimate reports, and its
    // confidence is what the decay is measured down from.
    Measurement lastAccepted;

    std::vector<cv::Point2f> debugInlierPixels;
    std::vector<cv::Point2f> debugRejectedPixels;
    std::vector<uint32_t> debugInlierIds;
    mutable std::vector<cv::Point2f> hullScratch;

    mutable uint32_t randomState = 0x9e3779b9u;

    FloorEstimate published;
    FloorCounters totals;

public:

    EIGEN_MAKE_ALIGNED_OPERATOR_NEW
};

} // namespace novex
