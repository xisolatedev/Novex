// Novex VIO geometry audit.
//
// Verifies the calibration transformation and the stereo/motion
// geometry against synthetic data with KNOWN ground truth. Every
// check here has an exact expected answer, so a failure points at a
// specific piece of maths rather than at "drift".
//
// This is deliberately separate from the live pipeline: it uses the
// same StereoCalibration, StereoMatcher and MotionEstimator code, but
// feeds them data whose correct answer is known in advance.
//
//   novex-geometry-audit [--calibration PATH]

#include "Log.hpp"
#include "MotionEstimator.hpp"
#include "StereoCalibration.hpp"
#include "VIOConfig.hpp"

#include <opencv2/calib3d.hpp>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace novex;

namespace
{

int gPass = 0;
int gFail = 0;

void heading(const char* text)
{
    printf("\n%s\n", text);

    for (size_t i = 0; i < strlen(text); ++i)
    {
        printf("-");
    }

    printf("\n");
}

void report(bool ok, const char* name, const char* detail)
{
    printf("  %s  %-46s %s\n", ok ? "PASS" : "FAIL", name, detail);

    if (ok) ++gPass; else ++gFail;
}

// Percentile of a copy, for reporting error distributions.
double percentile(std::vector<double> values, double fraction)
{
    if (values.empty()) return 0.0;

    std::sort(values.begin(), values.end());

    const size_t index = static_cast<size_t>(
        fraction * (values.size() - 1)
    );

    return values[index];
}

} // namespace

int main(int argc, char** argv)
{
    std::string calibrationPath = "config/stereo_calibration.yaml";

    for (int i = 1; i < argc; ++i)
    {
        if (strcmp(argv[i], "--calibration") == 0 && i + 1 < argc)
        {
            calibrationPath = argv[++i];
        }
    }

    setLogLevel(LogLevel::Warn);

    printf("========================================\n");
    printf("      NOVEX VIO GEOMETRY AUDIT\n");
    printf("========================================\n");

    StereoCalibration calibration;

    if (!calibration.load(calibrationPath))
    {
        printf("cannot load %s\n", calibrationPath.c_str());
        return 1;
    }

    const cv::Size calibrationSize = calibration.calibrationResolution();

    calibration.setCurrentResolution(cv::Size(640, 480));

    const SensorModeMapping& mapping = calibration.mapping();

    printf("\ncalibration : %dx%d per eye, baseline %.3f mm\n",
           calibrationSize.width, calibrationSize.height,
           calibration.baseline() * 1e3);

    printf("current     : %dx%d per eye\n",
           calibration.currentResolution().width,
           calibration.currentResolution().height);

    printf("mapping     : %s\n", mapping.description.c_str());

    // ================================================================
    heading("1. Crop + scale intrinsic transform");
    // ================================================================
    //
    // The claim being tested: projecting a ray through the ORIGINAL
    // calibration and then applying the pixel-space crop+scale must
    // give exactly the same pixel as projecting the same ray through
    // the ADAPTED calibration.
    //
    // If that holds for every ray, the adaptation is exact and cannot
    // be the source of any error. If it fails, the intrinsics are
    // wrong and everything downstream inherits it.

    {
        const double scale = mapping.scale;
        const double cropX = mapping.cropInCalibration.x;
        const double cropY = mapping.cropInCalibration.y;

        for (int side = 0; side < 2; ++side)
        {
            const cv::Matx33d& original = side == 0
                ? calibration.calibrationLeftK()
                : calibration.calibrationRightK();

            const cv::Matx33d& adapted = side == 0
                ? calibration.leftK()
                : calibration.rightK();

            const cv::Vec4d& D = side == 0
                ? calibration.leftDistortion()
                : calibration.rightDistortion();

            // A grid of normalised bearings covering a wide field of
            // view, including well past the crop, so the edges are
            // tested too.
            std::vector<cv::Point2f> normalised;

            for (int gy = -12; gy <= 12; ++gy)
            {
                for (int gx = -12; gx <= 12; ++gx)
                {
                    normalised.push_back(cv::Point2f(
                        static_cast<float>(gx * 0.12),
                        static_cast<float>(gy * 0.12)
                    ));
                }
            }

            std::vector<cv::Point2f> inOriginal;
            std::vector<cv::Point2f> inAdapted;

            cv::fisheye::distortPoints(normalised, inOriginal,
                                       original, D);

            cv::fisheye::distortPoints(normalised, inAdapted,
                                       adapted, D);

            std::vector<double> errors;

            for (size_t i = 0; i < normalised.size(); ++i)
            {
                // Apply the documented pixel-space transform to the
                // original projection.
                const double expectedX =
                    (inOriginal[i].x - cropX) * scale;

                const double expectedY =
                    (inOriginal[i].y - cropY) * scale;

                errors.push_back(std::hypot(
                    inAdapted[i].x - expectedX,
                    inAdapted[i].y - expectedY
                ));
            }

            const double worst =
                *std::max_element(errors.begin(), errors.end());

            char detail[160];

            snprintf(detail, sizeof(detail),
                     "%zu rays, max deviation %.3e px "
                     "(float32 round-off floor is ~1e-4)",
                     normalised.size(), worst);

            // cv::Point2f is float32, so distortPoints cannot resolve
            // better than ~1e-4 px on a 640-wide image. Anything at
            // that level is round-off, not a modelling error; the
            // bar is set an order of magnitude above it and still
            // four orders below anything physically meaningful.
            report(worst < 1e-3,
                   side == 0 ? "left: adapted == crop(scale(original))"
                             : "right: adapted == crop(scale(original))",
                   detail);
        }

        // The distortion coefficients must be untouched. An isotropic
        // scale leaves Kannala-Brandt valid precisely because r_d/f is
        // invariant; scaling k1..k4 would silently break that.
        char detail[160];

        snprintf(detail, sizeof(detail),
                 "k1 %.10f unchanged",
                 calibration.leftDistortion()[0]);

        report(std::abs(calibration.leftDistortion()[0] -
                        0.06137212628357399) < 1e-15,
               "distortion coefficients unmodified", detail);
    }

    // ================================================================
    heading("2. Kannala-Brandt projection / unprojection round trip");
    // ================================================================
    //
    // cv::fisheye::undistortPoints solves the KB radial polynomial
    // iteratively. If it fails to converge - which it can, on a wide
    // lens far from centre - every downstream bearing is wrong, and
    // that error is systematic with image radius. This measures it
    // directly rather than assuming convergence.

    {
        for (int side = 0; side < 2; ++side)
        {
            const cv::Matx33d& K = side == 0
                ? calibration.leftK() : calibration.rightK();

            const cv::Vec4d& D = side == 0
                ? calibration.leftDistortion()
                : calibration.rightDistortion();

            std::vector<cv::Point2f> pixels;

            for (int y = 4; y < 480; y += 8)
            {
                for (int x = 4; x < 640; x += 8)
                {
                    pixels.push_back(cv::Point2f(
                        static_cast<float>(x), static_cast<float>(y)
                    ));
                }
            }

            std::vector<cv::Point2f> bearings;
            std::vector<cv::Point2f> back;

            cv::fisheye::undistortPoints(pixels, bearings, K, D);
            cv::fisheye::distortPoints(bearings, back, K, D);

            std::vector<double> errors;
            std::vector<double> edgeErrors;

            const double cx = K(0, 2);
            const double cy = K(1, 2);

            for (size_t i = 0; i < pixels.size(); ++i)
            {
                const double e = std::hypot(back[i].x - pixels[i].x,
                                            back[i].y - pixels[i].y);

                errors.push_back(e);

                const double radius = std::hypot(pixels[i].x - cx,
                                                 pixels[i].y - cy);

                if (radius > 240.0)
                {
                    edgeErrors.push_back(e);
                }
            }

            const double worst =
                *std::max_element(errors.begin(), errors.end());

            const double edgeWorst = edgeErrors.empty()
                ? 0.0
                : *std::max_element(edgeErrors.begin(),
                                    edgeErrors.end());

            char detail[200];

            snprintf(detail, sizeof(detail),
                     "median %.2e  p99 %.2e  max %.2e px "
                     "(edge max %.2e)",
                     percentile(errors, 0.5),
                     percentile(errors, 0.99),
                     worst, edgeWorst);

            report(worst < 0.01,
                   side == 0 ? "left: pixel -> bearing -> pixel"
                             : "right: pixel -> bearing -> pixel",
                   detail);
        }
    }

    // ================================================================
    heading("3. Stereo extrinsics, disparity and depth sign");
    // ================================================================
    //
    // Places points at known depths in the LEFT camera frame,
    // projects them into both eyes through the real fisheye model,
    // and runs the exact triangulation the pipeline uses. Depth must
    // come back correct, and disparity must have the right sign.

    {
        const cv::Matx33d& R = calibration.rotation();
        const cv::Vec3d& T = calibration.translation();

        const cv::Matx34d P1(1, 0, 0, 0,
                             0, 1, 0, 0,
                             0, 0, 1, 0);

        const cv::Matx34d P2(R(0,0), R(0,1), R(0,2), T[0],
                             R(1,0), R(1,1), R(1,2), T[1],
                             R(2,0), R(2,1), R(2,2), T[2]);

        const double depths[] = { 0.3, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0 };

        std::vector<double> depthErrors;
        std::vector<double> disparities;
        std::vector<double> naiveDisparities;
        std::vector<double> naiveDepths;

        bool signCorrect = true;

        for (double Z : depths)
        {
            for (int gy = -2; gy <= 2; ++gy)
            {
                for (int gx = -2; gx <= 2; ++gx)
                {
                    const cv::Vec3d Pleft(gx * 0.2 * Z / 3.0,
                                          gy * 0.2 * Z / 3.0,
                                          Z);

                    const cv::Vec3d Pright = R * Pleft + T;

                    if (Pright[2] <= 0.0) continue;

                    // Project through each lens.
                    std::vector<cv::Point2f> nl {
                        cv::Point2f(
                            static_cast<float>(Pleft[0] / Pleft[2]),
                            static_cast<float>(Pleft[1] / Pleft[2]))
                    };

                    std::vector<cv::Point2f> nr {
                        cv::Point2f(
                            static_cast<float>(Pright[0] / Pright[2]),
                            static_cast<float>(Pright[1] / Pright[2]))
                    };

                    std::vector<cv::Point2f> pl, pr;

                    cv::fisheye::distortPoints(
                        nl, pl, calibration.leftK(),
                        calibration.leftDistortion());

                    cv::fisheye::distortPoints(
                        nr, pr, calibration.rightK(),
                        calibration.rightDistortion());

                    // Now go back exactly the way the pipeline does.
                    std::vector<cv::Point2f> bl, br;

                    cv::fisheye::undistortPoints(
                        pl, bl, calibration.leftK(),
                        calibration.leftDistortion());

                    cv::fisheye::undistortPoints(
                        pr, br, calibration.rightK(),
                        calibration.rightDistortion());

                    cv::Mat X;

                    cv::triangulatePoints(P1, P2, bl, br, X);

                    const float w = X.at<float>(3, 0);

                    if (std::abs(w) < 1e-12f) continue;

                    const double recovered = X.at<float>(2, 0) / w;

                    depthErrors.push_back(
                        std::abs(recovered - Z) / Z);

                    // Disparity must be measured between bearings
                    // expressed in a COMMON orientation.
                    //
                    // Two corrections are needed before the sign means
                    // anything. Pixel difference is not an invariant
                    // on a fisheye, because KB radial compression maps
                    // equal angles to unequal pixel distances off
                    // axis. And the raw bearing difference is not an
                    // invariant either, because the two lenses are
                    // relatively rotated (~0.7 deg about Y here) - so
                    // the right bearing must first be rotated into the
                    // left camera's orientation with R^T.
                    //
                    // Once both are in the left orientation, the right
                    // eye is simply displaced along +x, and a point at
                    // finite depth must have a strictly positive
                    // disparity at any depth.
                    const cv::Vec3d rightInLeftOrientation =
                        R.t() * cv::Vec3d(br[0].x, br[0].y, 1.0);

                    const double rotatedRightX =
                        rightInLeftOrientation[0] /
                        rightInLeftOrientation[2];

                    const double bearingDisparity =
                        bl[0].x - rotatedRightX;

                    // Also record what the UNrotated difference does,
                    // because that is the quantity a naive
                    // implementation would use.
                    naiveDisparities.push_back(bl[0].x - br[0].x);
                    naiveDepths.push_back(Z);

                    disparities.push_back(bearingDisparity);

                    if (bearingDisparity <= 0.0)
                    {
                        signCorrect = false;
                    }
                }
            }
        }

        const double worstDepth = depthErrors.empty() ? 1.0
            : *std::max_element(depthErrors.begin(), depthErrors.end());

        char detail[200];

        snprintf(detail, sizeof(detail),
                 "%zu points, max relative depth error %.3e",
                 depthErrors.size(), worstDepth);

        report(worstDepth < 1e-4,
               "triangulation recovers known depth", detail);

        const double minDisparity = disparities.empty() ? 0.0
            : *std::min_element(disparities.begin(), disparities.end());

        snprintf(detail, sizeof(detail),
                 "%zu points, min bearing disparity %.6f (must be > 0)",
                 disparities.size(), minDisparity);

        report(signCorrect,
               "disparity sign (common orientation)", detail);

        // Where does the NAIVE (unrotated) bearing difference change
        // sign? Anything relying on that quantity silently breaks
        // beyond this depth.
        double crossover = 0.0;

        for (size_t i = 0; i < naiveDisparities.size(); ++i)
        {
            if (naiveDisparities[i] <= 0.0 &&
                (crossover == 0.0 || naiveDepths[i] < crossover))
            {
                crossover = naiveDepths[i];
            }
        }

        if (crossover > 0.0)
        {
            printf("\n  NOTE: the inter-lens rotation makes the "
                   "UNROTATED bearing difference\n"
                   "        change sign beyond about %.0f m. The "
                   "pipeline does not use that\n"
                   "        quantity, but it is a further reason far "
                   "points are unreliable\n"
                   "        on this rig.\n\n",
                   crossover);
        }

        // Where does the right camera sit in the left frame?
        const cv::Vec3d rightInLeft = -R.t() * T;

        snprintf(detail, sizeof(detail),
                 "right camera at (%.4f, %.4f, %.4f) m in left frame",
                 rightInLeft[0], rightInLeft[1], rightInLeft[2]);

        report(rightInLeft[0] > 0.10 && rightInLeft[0] < 0.12 &&
                   std::abs(rightInLeft[1]) < 0.01 &&
                   std::abs(rightInLeft[2]) < 0.01,
               "baseline direction (right eye is +x)", detail);
    }

    // ================================================================
    heading("4. Depth observability at this baseline");
    // ================================================================
    //
    // Not a pass/fail of the code - a statement about what this
    // hardware can actually measure. A point whose disparity is
    // smaller than the measured matching noise has a depth that is
    // noise, and feeding it to PnP as if it were a measurement is how
    // a well-tracked system still drifts.

    {
        const double fx = calibration.leftK()(0, 0);
        const double baseline = calibration.baseline();

        printf("  fx = %.2f px, baseline = %.4f m\n\n", fx, baseline);
        printf("  %8s  %10s  %14s\n",
               "depth", "disparity", "depth err @1px");

        for (double Z : { 0.5, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0, 20.0, 25.0 })
        {
            const double disparity = fx * baseline / Z;

            // dZ/dd = -Z^2 / (f B), so a one-pixel error maps to:
            const double error = Z * Z / (fx * baseline);

            printf("  %6.1f m  %8.2f px  %10.2f m (%.0f%%)\n",
                   Z, disparity, error, 100.0 * error / Z);
        }

        printf("\n");
    }

    // ================================================================
    heading("5. Motion estimator round trip (perfect data)");
    // ================================================================
    //
    // The estimator is handed exact correspondences for a known
    // motion. If it cannot recover that motion to numerical precision,
    // the bug is in the estimator or its conventions, not in the
    // measurements.

    {
        VIOConfig config;
        config.applyDerived();

        MotionEstimator estimator(config, calibration);
        Profiler profiler;

        struct Case
        {
            const char* name;
            cv::Vec3d rotationAxisAngle;
            cv::Vec3d translation;
        };

        const Case cases[] = {
            { "pure forward translation",  {0, 0, 0},        {0, 0, 0.02} },
            { "pure lateral translation",  {0, 0, 0},        {0.02, 0, 0} },
            { "pure vertical translation", {0, 0, 0},        {0, 0.02, 0} },
            { "pure yaw",                  {0, 0.01, 0},     {0, 0, 0} },
            { "pure pitch",                {0.01, 0, 0},     {0, 0, 0} },
            { "pure roll",                 {0, 0, 0.01},     {0, 0, 0} },
            { "combined",                  {0.008, -0.006, 0.004},
                                                             {0.01, -0.005, 0.02} },
        };

        for (const Case& c : cases)
        {
            cv::Matx33d R;
            cv::Mat rvec = (cv::Mat_<double>(3, 1) <<
                c.rotationAxisAngle[0],
                c.rotationAxisAngle[1],
                c.rotationAxisAngle[2]);

            cv::Mat Rmat;
            cv::Rodrigues(rvec, Rmat);

            for (int r = 0; r < 3; ++r)
                for (int col = 0; col < 3; ++col)
                    R(r, col) = Rmat.at<double>(r, col);

            std::vector<Feature> features;

            // Points spread across depth and image, as the real
            // pipeline would see.
            uint64_t id = 1;

            for (int gy = -4; gy <= 4; ++gy)
            {
                for (int gx = -4; gx <= 4; ++gx)
                {
                    for (double Z : { 0.8, 1.5, 3.0 })
                    {
                        const cv::Vec3d Pprev(
                            gx * 0.09 * Z, gy * 0.09 * Z, Z);

                        const cv::Vec3d Pcur = R * Pprev + c.translation;

                        if (Pcur[2] < 0.1) continue;

                        std::vector<cv::Point2f> normalised {
                            cv::Point2f(
                                static_cast<float>(Pcur[0] / Pcur[2]),
                                static_cast<float>(Pcur[1] / Pcur[2]))
                        };

                        std::vector<cv::Point2f> pixel;

                        cv::fisheye::distortPoints(
                            normalised, pixel,
                            calibration.leftK(),
                            calibration.leftDistortion());

                        if (pixel[0].x < 0 || pixel[0].x > 640 ||
                            pixel[0].y < 0 || pixel[0].y > 480)
                        {
                            continue;
                        }

                        Feature f;

                        f.id = id++;
                        f.hasDepth = true;
                        f.position3D = cv::Point3f(
                            static_cast<float>(Pprev[0]),
                            static_cast<float>(Pprev[1]),
                            static_cast<float>(Pprev[2]));

                        f.point = pixel[0];

                        features.push_back(f);
                    }
                }
            }

            const MotionResult result =
                estimator.estimate(features, 0.033, profiler);

            double rotationError = 999.0;
            double translationError = 999.0;

            if (result.success)
            {
                const cv::Matx33d dR = result.rotation * R.t();

                rotationError = std::acos(std::max(-1.0, std::min(1.0,
                    (cv::trace(dR) - 1.0) * 0.5)));

                translationError =
                    cv::norm(result.translation - c.translation);
            }

            char detail[220];

            snprintf(detail, sizeof(detail),
                     "%3d pts, %3d inliers, dR %.3e rad, dt %.3e m",
                     result.correspondences, result.inliers,
                     rotationError, translationError);

            report(result.success &&
                       rotationError < 1e-5 &&
                       translationError < 1e-5,
                   c.name, detail);
        }
    }

    printf("\n========================================\n");
    printf("passed %d, failed %d\n", gPass, gFail);
    printf("========================================\n");

    return gFail == 0 ? 0 : 1;
}
