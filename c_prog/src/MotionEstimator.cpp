#include "MotionEstimator.hpp"

#include "FisheyeGeometry.hpp"
#include "Log.hpp"

#include <opencv2/calib3d.hpp>

#include <Eigen/Core>
#include <Eigen/Eigenvalues>
#include <Eigen/LU>

#include <algorithm>
#include <cmath>

namespace novex
{

namespace
{

// Motion limits used only to reject a solution that is physically
// impossible for a handheld or vehicle-mounted camera over one frame
// interval. These catch the degenerate PnP solutions that occasionally
// survive RANSAC on a nearly planar scene, which would otherwise be
// integrated into the pose and never recovered from.
constexpr double kMaxSpeed = 15.0;              // metres per second
constexpr double kMaxAngularRate = 12.0;        // radians per second

constexpr double kRadiansToDegrees = 57.29577951308232;

// A normal matrix whose smallest eigenvalue is this small relative to
// its largest is numerically singular: some motion direction is simply
// not constrained by the data, and the "solution" along it is noise.
constexpr double kSingularConditioning = 1e-12;

// Rodrigues exponential for a small rotation vector.
cv::Matx33d exponential(const cv::Vec3d& omega)
{
    const double angle = cv::norm(omega);

    if (angle < 1e-12)
    {
        return cv::Matx33d(
                  1.0, -omega[2],  omega[1],
             omega[2],       1.0, -omega[0],
            -omega[1],  omega[0],       1.0
        );
    }

    cv::Matx33d result;
    cv::Rodrigues(omega, result);

    return result;
}

// Two unit vectors orthogonal to `direction` and to each other.
void tangentBasis(const cv::Vec3d& direction, cv::Vec3d& e1, cv::Vec3d& e2)
{
    const cv::Vec3d helper = std::abs(direction[0]) < 0.9
        ? cv::Vec3d(1.0, 0.0, 0.0)
        : cv::Vec3d(0.0, 1.0, 0.0);

    e1 = direction.cross(helper);
    e1 /= cv::norm(e1);

    e2 = direction.cross(e1);
}

} // namespace

MotionEstimator::MotionEstimator(const VIOConfig& config,
                                 const StereoCalibration& calibration)
    : config(config), calibration(calibration)
{
    const size_t capacity = static_cast<size_t>(config.maxFeatures) + 32;

    objectPoints.reserve(capacity);
    imagePoints.reserve(capacity);
    normalisedPoints.reserve(capacity);
    featureIndex.reserve(capacity);
    ransacInliers.reserve(capacity);
    bearings.reserve(capacity);
    inlier.reserve(capacity);
    residualScratch.reserve(capacity);

    rvec = cv::Mat::zeros(3, 1, CV_64F);
    tvec = cv::Mat::zeros(3, 1, CV_64F);
}

int MotionEstimator::classify(double thresholdRadians)
{
    int count = 0;

    for (size_t i = 0; i < objectPoints.size(); ++i)
    {
        const cv::Point3f& p = objectPoints[i];

        const cv::Vec3d X =
            rotation * cv::Vec3d(p.x, p.y, p.z) + translation;

        const double range = cv::norm(X);

        bool accepted = false;

        if (range > 1e-9 && X[2] > -range)
        {
            const double angle =
                angleBetweenUnit(X / range, bearings[i]);

            accepted = angle <= thresholdRadians;
        }

        inlier[i] = accepted ? 1 : 0;
        count += accepted ? 1 : 0;
    }

    return count;
}

bool MotionEstimator::refine(double huberRadians,
                             double hessian[36],
                             double& weightedSquares)
{
    // Iteratively reweighted Gauss-Newton on the angle between each
    // predicted bearing and its observed bearing.
    //
    // Residual: the predicted unit bearing u = X / |X| expressed in a
    // tangent basis (e1, e2) of the observed bearing o. At the solution
    // u ~ o, so the two components are the angular error in radians.
    //
    // Perturbation: X' = Exp(w) X + v, i.e. the whole transform is
    // perturbed on the left, so
    //   dX/dw = -[X]x,  dX/dv = I,  du/dX = (I - u u^T) / |X|.
    //
    // Update: R <- Exp(w) R,  t <- Exp(w) t + v.
    const int maxIterations = std::max(1, config.motionRefineIterations);

    Eigen::Matrix<double, 6, 6> H;
    Eigen::Matrix<double, 6, 1> g;

    for (int iteration = 0; iteration < maxIterations; ++iteration)
    {
        H.setZero();
        g.setZero();

        weightedSquares = 0.0;

        int used = 0;

        for (size_t i = 0; i < objectPoints.size(); ++i)
        {
            if (!inlier[i])
            {
                continue;
            }

            const cv::Point3f& p = objectPoints[i];

            const cv::Vec3d X =
                rotation * cv::Vec3d(p.x, p.y, p.z) + translation;

            const double range = cv::norm(X);

            if (range < 1e-9)
            {
                continue;
            }

            const cv::Vec3d u = X / range;
            const cv::Vec3d& o = bearings[i];

            cv::Vec3d e1;
            cv::Vec3d e2;

            tangentBasis(o, e1, e2);

            const double r1 = e1.dot(u);
            const double r2 = e2.dot(u);

            const double magnitude = std::sqrt(r1 * r1 + r2 * r2);

            // Huber: quadratic inside the radius, linear outside, so
            // an inlier that is merely a bit noisy still counts fully
            // and one near the threshold cannot drag the solution.
            const double weight = magnitude <= huberRadians
                ? 1.0
                : huberRadians / magnitude;

            // Rows of the 2x3 d(residual)/dX: e_k^T (I - u u^T) / |X|.
            const cv::Vec3d a1 = (e1 - u * e1.dot(u)) / range;
            const cv::Vec3d a2 = (e2 - u * e2.dot(u)) / range;

            // d(residual)/dw = a^T (-[X]x) = (X x a)^T.
            const cv::Vec3d b1 = X.cross(a1);
            const cv::Vec3d b2 = X.cross(a2);

            const double J1[6] = { b1[0], b1[1], b1[2],
                                   a1[0], a1[1], a1[2] };
            const double J2[6] = { b2[0], b2[1], b2[2],
                                   a2[0], a2[1], a2[2] };

            for (int row = 0; row < 6; ++row)
            {
                g(row) += weight * (J1[row] * r1 + J2[row] * r2);

                for (int col = row; col < 6; ++col)
                {
                    H(row, col) += weight *
                        (J1[row] * J1[col] + J2[row] * J2[col]);
                }
            }

            weightedSquares += weight * (r1 * r1 + r2 * r2);

            ++used;
        }

        if (used < 3)
        {
            return false;
        }

        for (int row = 1; row < 6; ++row)
        {
            for (int col = 0; col < row; ++col)
            {
                H(row, col) = H(col, row);
            }
        }

        const Eigen::Matrix<double, 6, 1> delta =
            H.ldlt().solve(-g);

        if (!delta.allFinite())
        {
            return false;
        }

        const cv::Vec3d omega(delta(0), delta(1), delta(2));
        const cv::Vec3d shift(delta(3), delta(4), delta(5));

        const cv::Matx33d step = exponential(omega);

        rotation = step * rotation;
        translation = step * translation + shift;

        // Converged once the update is far below a pixel in angle and
        // a tenth of a millimetre in position.
        if (cv::norm(omega) < 1e-7 && cv::norm(shift) < 1e-7)
        {
            break;
        }
    }

    for (int i = 0; i < 36; ++i)
    {
        hessian[i] = H(i / 6, i % 6);
    }

    return true;
}

MotionResult MotionEstimator::estimate(
    std::vector<Feature>& features,
    double deltaTime,
    Profiler& profiler)
{
    MotionResult result;

    objectPoints.clear();
    imagePoints.clear();
    featureIndex.clear();

    for (size_t i = 0; i < features.size(); ++i)
    {
        Feature& feature = features[i];

        feature.motionInlier = false;

        // reference3D is expressed in the reference left camera frame,
        // while point is the observation in the current image. That is
        // exactly the pairing PnP needs.
        if (!feature.hasReference)
        {
            continue;
        }

        objectPoints.push_back(feature.reference3D);
        imagePoints.push_back(feature.point);
        featureIndex.push_back(static_cast<int>(i));
    }

    result.correspondences = static_cast<int>(objectPoints.size());

    // AP3P needs four points for a minimal solution; asking RANSAC to
    // work with barely more than that produces poses that are
    // technically consistent and practically meaningless.
    if (result.correspondences < std::max(6, config.minInliersForTracking))
    {
        result.failureReason = "too few features with depth";
        return result;
    }

    result.attempted = true;

    ScopedStage timing(profiler, Stage::Motion);

    cv::fisheye::undistortPoints(
        imagePoints,
        normalisedPoints,
        calibration.leftK(),
        calibration.leftDistortion()
    );

    const cv::Matx33d identityIntrinsics = cv::Matx33d::eye();
    const cv::Vec4d noDistortion = cv::Vec4d::all(0.0);

    ransacInliers.clear();

    bool solved = false;

    try
    {
        solved = cv::solvePnPRansac(
            objectPoints,
            normalisedPoints,
            identityIntrinsics,
            noDistortion,
            rvec,
            tvec,
            false,
            config.ransacIterations,
            static_cast<float>(config.ransacReprojectionError),
            config.ransacConfidence,
            ransacInliers,
            cv::SOLVEPNP_AP3P
        );
    }
    catch (const cv::Exception& error)
    {
        LOG_WARN("motion: solvePnPRansac threw: %s", error.what());
        result.failureReason = "solver error";
        return result;
    }

    if (!solved || static_cast<int>(ransacInliers.size()) <
                       config.minInliersForTracking)
    {
        result.inliers = static_cast<int>(ransacInliers.size());
        result.inlierRatio =
            static_cast<double>(result.inliers) / result.correspondences;
        result.failureReason = "not enough RANSAC inliers";
        return result;
    }

    cv::Rodrigues(rvec, rotation);

    translation = cv::Vec3d(
        tvec.at<double>(0), tvec.at<double>(1), tvec.at<double>(2)
    );

    bearings.clear();
    inlier.assign(objectPoints.size(), 0);

    for (const cv::Point2f& normalised : normalisedPoints)
    {
        bearings.push_back(bearingFromNormalised(normalised));
    }

    const cv::Matx33d& K = calibration.leftK();

    const double radiansPerPixel = 2.0 / (K(0, 0) + K(1, 1));

    const double threshold =
        config.motionInlierThresholdPx * radiansPerPixel;

    // Huber radius of one pixel: the order of KLT matching noise, so
    // ordinary noise is weighted fully and only genuinely poor
    // correspondences are down-weighted.
    const double huber = std::min(threshold, radiansPerPixel);

    double hessian[36] = {};
    double weightedSquares = 0.0;

    // Two rounds: refine on the angular inlier set, then re-select
    // inliers against the refined pose and refine once more. The first
    // selection uses the RANSAC pose, which is only a hypothesis.
    int inlierCount = classify(threshold);

    for (int round = 0; round < 2; ++round)
    {
        if (inlierCount < config.minInliersForTracking)
        {
            break;
        }

        if (!refine(huber, hessian, weightedSquares))
        {
            result.failureReason = "degenerate geometry";
            result.inliers = inlierCount;
            result.inlierRatio =
                static_cast<double>(inlierCount) / result.correspondences;
            return result;
        }

        inlierCount = classify(threshold);
    }

    result.inliers = inlierCount;
    result.inlierRatio =
        static_cast<double>(inlierCount) / result.correspondences;

    if (inlierCount < config.minInliersForTracking)
    {
        result.failureReason = "not enough angular inliers";
        return result;
    }

    // Final normal matrix on the final inlier set, for conditioning
    // and uncertainty. One more pass - converged, so it barely moves.
    if (!refine(huber, hessian, weightedSquares))
    {
        result.failureReason = "degenerate geometry";
        return result;
    }

    // ---- residuals, measured in real pixels through the lens ----

    const cv::Vec4d& D = calibration.leftDistortion();

    residualScratch.clear();

    double worst = 0.0;

    for (size_t i = 0; i < objectPoints.size(); ++i)
    {
        if (!inlier[i])
        {
            continue;
        }

        const cv::Point3f& p = objectPoints[i];

        const cv::Vec3d X =
            rotation * cv::Vec3d(p.x, p.y, p.z) + translation;

        cv::Point2d projected;

        if (!projectFisheye(K, D, X, projected))
        {
            continue;
        }

        const double error = std::hypot(
            projected.x - imagePoints[i].x,
            projected.y - imagePoints[i].y
        );

        residualScratch.push_back(error);
        worst = std::max(worst, error);
    }

    if (!residualScratch.empty())
    {
        const size_t middle = residualScratch.size() / 2;

        std::nth_element(residualScratch.begin(),
                         residualScratch.begin() + static_cast<long>(middle),
                         residualScratch.end());

        result.reprojectionMedianPx = residualScratch[middle];
        result.reprojectionMaxPx = worst;
    }

    // ---- conditioning and uncertainty ----

    Eigen::Matrix<double, 6, 6> H;

    for (int i = 0; i < 36; ++i)
    {
        H(i / 6, i % 6) = hessian[i];
    }

    const Eigen::SelfAdjointEigenSolver<Eigen::Matrix<double, 6, 6>>
        eigen(H, Eigen::EigenvaluesOnly);

    const double largest = eigen.eigenvalues().maxCoeff();
    const double smallest = eigen.eigenvalues().minCoeff();

    result.conditioning = largest > 0.0 ? smallest / largest : 0.0;

    if (!(largest > 0.0) || result.conditioning < kSingularConditioning)
    {
        result.failureReason = "degenerate geometry";
        return result;
    }

    // Covariance = s^2 H^-1, with s^2 the residual variance per
    // residual component estimated from this frame's own data.
    const int degreesOfFreedom = 2 * inlierCount - 6;

    if (degreesOfFreedom > 0)
    {
        const double variance = weightedSquares / degreesOfFreedom;

        const Eigen::Matrix<double, 6, 6> covariance =
            H.inverse() * variance;

        const Eigen::SelfAdjointEigenSolver<Eigen::Matrix3d>
            rotationEigen(covariance.topLeftCorner<3, 3>(),
                          Eigen::EigenvaluesOnly);

        const Eigen::SelfAdjointEigenSolver<Eigen::Matrix3d>
            translationEigen(covariance.bottomRightCorner<3, 3>(),
                             Eigen::EigenvaluesOnly);

        result.rotationSigmaDeg = std::sqrt(std::max(
            0.0, rotationEigen.eigenvalues().maxCoeff())) *
            kRadiansToDegrees;

        result.translationSigmaMm = std::sqrt(std::max(
            0.0, translationEigen.eigenvalues().maxCoeff())) * 1e3;
    }

    result.rotation = rotation;
    result.translation = translation;

    for (int i = 0; i < 3; ++i)
    {
        if (!std::isfinite(result.translation[i]))
        {
            result.failureReason = "non-finite solution";
            return result;
        }
    }

    if (deltaTime > 1e-6)
    {
        const double speed = cv::norm(result.translation) / deltaTime;

        const double angle = std::acos(
            std::max(-1.0, std::min(1.0,
                (cv::trace(result.rotation) - 1.0) * 0.5))
        );

        const double angularRate = angle / deltaTime;

        if (speed > kMaxSpeed || angularRate > kMaxAngularRate)
        {
            LOG_DEBUG(
                "motion: rejecting implausible solution "
                "(%.1f m/s, %.1f rad/s over %.4f s)",
                speed, angularRate, deltaTime
            );

            result.failureReason = "implausible motion";
            return result;
        }
    }

    // Only an ACCEPTED estimate marks its inliers; the point map uses
    // the flag as evidence that a point is consistent with the motion.
    for (size_t i = 0; i < objectPoints.size(); ++i)
    {
        if (inlier[i])
        {
            features[static_cast<size_t>(featureIndex[i])].motionInlier =
                true;
        }
    }

    result.success = true;

    return result;
}

} // namespace novex
