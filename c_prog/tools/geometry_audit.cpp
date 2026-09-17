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
//   novex-geometry-audit [--calibration PATH] [--recording DIR]
//
// With --recording (a novex-record directory) it also checks the stereo
// extrinsic convention and the calibration's consistency on REAL
// frames, where synthetic data cannot help.

#include "Log.hpp"
#include "FisheyeGeometry.hpp"
#include "MotionEstimator.hpp"
#include "StereoCalibration.hpp"
#include "StereoMatcher.hpp"
#include "VIOConfig.hpp"

#include <opencv2/calib3d.hpp>
#include <opencv2/imgcodecs.hpp>
#include <opencv2/video/tracking.hpp>

#include <algorithm>
#include <cmath>
#include <random>
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
    std::string recordingPath;
    int recordingFrames = 60;

    for (int i = 1; i < argc; ++i)
    {
        if (strcmp(argv[i], "--calibration") == 0 && i + 1 < argc)
        {
            calibrationPath = argv[++i];
        }
        else if (strcmp(argv[i], "--recording") == 0 && i + 1 < argc)
        {
            recordingPath = argv[++i];
        }
        else if (strcmp(argv[i], "--frames") == 0 && i + 1 < argc)
        {
            recordingFrames = atoi(argv[++i]);
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
    heading("1b. Pixel-centre convention of the crop + scale");
    // ================================================================
    //
    // Test 1 proves the code applies u' = s (u - crop). That formula
    // aligns pixel CENTRES at the crop origin. A resampler that aligns
    // pixel AREAS (as cv::resize and typical ISP scalers do) instead
    // gives u' = s (u - crop + 0.5) - 0.5, which differs by a constant
    // 0.5 (1 - s) = 0.167 px at s = 2/3.
    //
    // The measurement that established the mapping (ORB affine fits)
    // found the crop origin at (159.5, -0.5) left and (160.2, -0.2)
    // right. Centre alignment predicts (160, 0); area alignment
    // predicts (160.25, 0.25). The fit's ~0.5 px scatter cannot tell
    // them apart, so the existing, measured formula is kept - and the
    // CONSEQUENCE of being wrong is bounded here instead.
    //
    // A common principal-point shift moves both eyes' rays by the same
    // small angle. That is a fixed rotation of the rig's reported
    // frame: it cannot create frame-to-frame motion, and it barely
    // changes stereo range.

    {
        const double shift = 0.5 * (1.0 - mapping.scale);
        const double fx = calibration.leftK()(0, 0);

        const double angleDeg = std::atan(shift / fx) * 57.29577951308232;

        // Range change at 2 m from shifting both principal points by
        // `shift` along x, computed with the real triangulation.
        const cv::Matx33d& R = calibration.rotation();
        const cv::Vec3d C = -(R.t() * calibration.translation());

        const cv::Vec3d P(0.3, 0.1, 2.0);
        const cv::Vec3d Pr = R * P + calibration.translation();

        auto rangeWithShift = [&](double dx)
        {
            cv::Matx33d KL = calibration.leftK();
            cv::Matx33d KR = calibration.rightK();

            cv::Point2d pl;
            cv::Point2d pr;

            projectFisheye(KL, calibration.leftDistortion(), P, pl);
            projectFisheye(KR, calibration.rightDistortion(), Pr, pr);

            KL(0, 2) += dx;
            KR(0, 2) += dx;

            std::vector<cv::Point2f> l { cv::Point2f(pl) };
            std::vector<cv::Point2f> r { cv::Point2f(pr) };
            std::vector<cv::Point2f> nl;
            std::vector<cv::Point2f> nr;

            cv::fisheye::undistortPoints(l, nl, KL, calibration.leftDistortion());
            cv::fisheye::undistortPoints(r, nr, KR, calibration.rightDistortion());

            StereoMatcher::RayIntersection ray;

            StereoMatcher::intersectOnLeftRay(
                bearingFromNormalised(nl[0]),
                R.t() * bearingFromNormalised(nr[0]),
                C, ray);

            return ray.point[2];
        };

        const double base = rangeWithShift(0.0);
        const double shifted = rangeWithShift(shift);

        char detail[200];

        snprintf(detail, sizeof(detail),
                 "%.3f px = %.4f deg common rotation; depth at 2 m "
                 "changes %.2f mm",
                 shift, angleDeg, (shifted - base) * 1e3);

        report(angleDeg < 0.05 && std::abs(shifted - base) < 0.005,
               "convention ambiguity is geometrically negligible",
               detail);
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

                    // The exact triangulation the pipeline uses.
                    StereoMatcher::RayIntersection ray;

                    if (!StereoMatcher::intersectOnLeftRay(
                            bearingFromNormalised(bl[0]),
                            R.t() * bearingFromNormalised(br[0]),
                            -(R.t() * T),
                            ray))
                    {
                        depthErrors.push_back(1.0);
                        continue;
                    }

                    const double recovered = ray.point[2];

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

        // float32 image coordinates limit this: at 20 m a 1e-7
        // normalised error is ~1e-5 relative depth.
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
                        f.hasReference = true;
                        f.reference3D = cv::Point3f(
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

    // ================================================================
    heading("6. Stereo inconsistency must not manufacture motion");
    // ================================================================
    //
    // The regression test for the dominant drift source found on this
    // rig. A real calibration is never perfect: the live pair shows a
    // systematic vertical miss between the rays. Simulate exactly that
    // - the right-eye observations sit 0.5 px low - with a camera that
    // does NOT move, and feed the motion estimator:
    //
    //   (a) points from linear DLT, which splits the inconsistency
    //       between both views, so the 3D point misses its own left
    //       pixel - what the pipeline used to do
    //   (b) points on the left ray, what it does now
    //
    // (b) must report zero motion. (a) is printed to show the size of
    // the error it used to integrate every frame.

    {
        VIOConfig config;
        config.applyDerived();

        MotionEstimator estimator(config, calibration);
        Profiler profiler;

        const cv::Matx33d& R = calibration.rotation();
        const cv::Vec3d& T = calibration.translation();
        const cv::Vec3d C = -(R.t() * T);

        const cv::Matx34d P1(1, 0, 0, 0,  0, 1, 0, 0,  0, 0, 1, 0);
        const cv::Matx34d P2(R(0,0), R(0,1), R(0,2), T[0],
                             R(1,0), R(1,1), R(1,2), T[1],
                             R(2,0), R(2,1), R(2,2), T[2]);

        std::vector<Feature> dlt;
        std::vector<Feature> leftRay;

        uint64_t id = 1;

        for (int gy = -4; gy <= 4; ++gy)
        {
            for (int gx = -5; gx <= 5; ++gx)
            {
                const double Z = 1.0 + 0.15 * ((gx + gy + 20) % 7);
                const cv::Vec3d P(gx * 0.13 * Z, gy * 0.12 * Z, Z);
                const cv::Vec3d Pr = R * P + T;

                cv::Point2d pl;
                cv::Point2d pr;

                if (!projectFisheye(calibration.leftK(),
                                    calibration.leftDistortion(), P, pl) ||
                    !projectFisheye(calibration.rightK(),
                                    calibration.rightDistortion(), Pr, pr))
                {
                    continue;
                }

                if (pl.x < 10 || pl.x > 630 || pl.y < 10 || pl.y > 470)
                {
                    continue;
                }

                // The calibration error under test.
                pr.y += 0.5;

                std::vector<cv::Point2f> l { cv::Point2f(pl) };
                std::vector<cv::Point2f> r { cv::Point2f(pr) };
                std::vector<cv::Point2f> nl;
                std::vector<cv::Point2f> nr;

                cv::fisheye::undistortPoints(l, nl, calibration.leftK(),
                                             calibration.leftDistortion());
                cv::fisheye::undistortPoints(r, nr, calibration.rightK(),
                                             calibration.rightDistortion());

                cv::Mat X;
                cv::triangulatePoints(P1, P2, nl, nr, X);

                StereoMatcher::RayIntersection ray;

                if (!StereoMatcher::intersectOnLeftRay(
                        bearingFromNormalised(nl[0]),
                        R.t() * bearingFromNormalised(nr[0]), C, ray))
                {
                    continue;
                }

                Feature f;

                f.id = id++;
                f.point = l[0];
                f.hasReference = true;

                const float w = X.at<float>(3, 0);

                f.reference3D = cv::Point3f(X.at<float>(0, 0) / w,
                                            X.at<float>(1, 0) / w,
                                            X.at<float>(2, 0) / w);
                dlt.push_back(f);

                f.reference3D = cv::Point3f(
                    static_cast<float>(ray.point[0]),
                    static_cast<float>(ray.point[1]),
                    static_cast<float>(ray.point[2]));
                leftRay.push_back(f);
            }
        }

        auto measure = [&](std::vector<Feature>& features,
                           double& rotationDeg, double& translationMm)
        {
            const MotionResult m =
                estimator.estimate(features, 1.0 / 30.0, profiler);

            if (!m.success)
            {
                rotationDeg = 999.0;
                translationMm = 999.0;
                return;
            }

            rotationDeg = std::acos(std::max(-1.0, std::min(1.0,
                (cv::trace(m.rotation) - 1.0) * 0.5))) * 57.29577951308232;
            translationMm = cv::norm(m.translation) * 1e3;
        };

        double dltRotation = 0.0;
        double dltTranslation = 0.0;
        double rayRotation = 0.0;
        double rayTranslation = 0.0;

        measure(dlt, dltRotation, dltTranslation);
        measure(leftRay, rayRotation, rayTranslation);

        char detail[220];

        snprintf(detail, sizeof(detail),
                 "%zu pts: left ray %.2e deg %.2e mm per frame",
                 leftRay.size(), rayRotation, rayTranslation);

        report(rayRotation < 1e-3 && rayTranslation < 1e-2,
               "stationary + 0.5 px stereo error -> no motion", detail);

        printf("        for comparison, DLT points: %.4f deg, %.3f mm per "
               "frame\n"
               "        = %.1f deg/s of fake rotation at 30 fps if integrated\n",
               dltRotation, dltTranslation, dltRotation * 30.0);
    }

    // ================================================================
    heading("7. Motion estimator under noise and outliers");
    // ================================================================
    //
    // Known motion, 0.5 px Gaussian noise on every observation and 25%
    // gross outliers. Reported against the estimator's own 1-sigma so
    // the uncertainty figures it publishes are checked, not assumed.

    {
        VIOConfig config;
        config.applyDerived();

        MotionEstimator estimator(config, calibration);
        Profiler profiler;

        std::mt19937 random(12345);
        std::normal_distribution<double> noise(0.0, 0.5);
        std::uniform_real_distribution<double> uniform(0.0, 1.0);

        cv::Matx33d R;
        cv::Rodrigues(cv::Vec3d(0.004, -0.006, 0.002), R);
        const cv::Vec3d t(0.004, -0.002, 0.011);

        double worstRotation = 0.0;
        double worstTranslation = 0.0;
        double sumRotationSigma = 0.0;
        double sumTranslationSigma = 0.0;
        double sumRotationError = 0.0;
        double sumTranslationError = 0.0;
        int trials = 0;
        int failures = 0;

        for (int trial = 0; trial < 50; ++trial)
        {
            std::vector<Feature> features;
            uint64_t id = 1;

            for (int k = 0; k < 250; ++k)
            {
                const double Z = 0.6 + 4.0 * uniform(random);
                const double x = (uniform(random) - 0.5) * 3.0 * Z;
                const double y = (uniform(random) - 0.5) * 2.2 * Z;

                const cv::Vec3d P(x, y, Z);
                const cv::Vec3d Pc = R * P + t;

                cv::Point2d px;

                if (!projectFisheye(calibration.leftK(),
                                    calibration.leftDistortion(), Pc, px) ||
                    px.x < 12 || px.x > 628 || px.y < 12 || px.y > 468)
                {
                    continue;
                }

                if (uniform(random) < 0.25)
                {
                    px.x += 8.0 + 30.0 * uniform(random);
                    px.y -= 5.0 + 20.0 * uniform(random);
                }
                else
                {
                    px.x += noise(random);
                    px.y += noise(random);
                }

                Feature f;
                f.id = id++;
                f.point = cv::Point2f(px);
                f.hasReference = true;
                f.reference3D = cv::Point3f(P);
                features.push_back(f);
            }

            const MotionResult m =
                estimator.estimate(features, 1.0 / 30.0, profiler);

            ++trials;

            if (!m.success)
            {
                ++failures;
                continue;
            }

            const cv::Matx33d dR = m.rotation * R.t();

            const double rotationError = std::acos(std::max(-1.0,
                std::min(1.0, (cv::trace(dR) - 1.0) * 0.5))) *
                57.29577951308232;

            const double translationError = cv::norm(m.translation - t) * 1e3;

            worstRotation = std::max(worstRotation, rotationError);
            worstTranslation = std::max(worstTranslation, translationError);
            sumRotationError += rotationError;
            sumTranslationError += translationError;
            sumRotationSigma += m.rotationSigmaDeg;
            sumTranslationSigma += m.translationSigmaMm;
        }

        const int good = trials - failures;

        char detail[240];

        snprintf(detail, sizeof(detail),
                 "%d/%d solved; mean err %.4f deg %.2f mm, worst %.4f deg "
                 "%.2f mm",
                 good, trials,
                 good ? sumRotationError / good : 0.0,
                 good ? sumTranslationError / good : 0.0,
                 worstRotation, worstTranslation);

        report(failures == 0 && worstRotation < 0.1 && worstTranslation < 3.0,
               "25% outliers + 0.5 px noise", detail);

        // The reported 1-sigma is a worst-axis figure; the mean error
        // over all axes should not exceed a few of them.
        snprintf(detail, sizeof(detail),
                 "mean reported 1-sigma %.4f deg %.2f mm",
                 good ? sumRotationSigma / good : 0.0,
                 good ? sumTranslationSigma / good : 0.0);

        report(good > 0 &&
                   sumRotationError / good < 4.0 * sumRotationSigma / good &&
                   sumTranslationError / good <
                       4.0 * sumTranslationSigma / good,
               "published uncertainty is consistent with error", detail);
    }

    // ================================================================
    if (!recordingPath.empty())
    {
        heading("8. Real frames: stereo extrinsic convention and consistency");
    // ================================================================
    //
    // Synthetic tests use the calibration's own convention, so they
    // cannot catch the convention itself being inverted. Real frames
    // can: under the right convention the left and right rays of true
    // matches nearly intersect, and points land in front of both
    // cameras. Each hypothesis is scored on the same matches.

        VIOConfig config;
        config.applyDerived();

        const cv::Matx33d& R = calibration.rotation();
        const cv::Vec3d& T = calibration.translation();

        struct Hypothesis
        {
            const char* name;
            cv::Matx33d rotation;     // X_right = rotation X_left + translation
            cv::Vec3d translation;
            std::vector<double> miss;
            std::vector<double> vertical;
            int behind = 0;
            int total = 0;
        };

        Hypothesis hypotheses[] = {
            { "X_right = R X_left + T  (calibration file)", R, T, {}, {}, 0, 0 },
            { "X_left = R X_right + T  (inverted)", R.t(), -(R.t() * T), {}, {}, 0, 0 },
            { "rotation ignored, T only", cv::Matx33d::eye(), T, {}, {}, 0, 0 },
        };

        // Vertical miss by distance from the left principal point, for
        // the calibration's own convention.
        constexpr int kBins = 4;
        std::vector<double> binMiss[kBins];
        std::vector<double> binVertical[kBins];

        int framesUsed = 0;

        for (int i = 0; i < recordingFrames; ++i)
        {
            char name[1024];
            snprintf(name, sizeof(name), "%s/%05d.png",
                     recordingPath.c_str(), i * 5);

            const cv::Mat frame = cv::imread(name, cv::IMREAD_GRAYSCALE);

            if (frame.empty() || frame.cols != 1280 || frame.rows != 480)
            {
                break;
            }

            ++framesUsed;

            const cv::Mat left = frame(cv::Rect(0, 0, 640, 480));
            const cv::Mat right = frame(cv::Rect(640, 0, 640, 480));

            std::vector<cv::Point2f> corners;
            cv::goodFeaturesToTrack(left, corners, 400, 0.01, 12);

            if (corners.empty())
            {
                continue;
            }

            // Seed at infinity through the calibration, as the pipeline
            // does, then KLT with a forward-backward check.
            std::vector<cv::Point2f> normalised;
            cv::fisheye::undistortPoints(corners, normalised,
                                         calibration.leftK(),
                                         calibration.leftDistortion());

            std::vector<cv::Point2f> seeds;

            for (const cv::Point2f& n : normalised)
            {
                const cv::Vec3d b = R * cv::Vec3d(n.x, n.y, 1.0);
                seeds.push_back(cv::Point2f(
                    static_cast<float>(b[0] / b[2]),
                    static_cast<float>(b[1] / b[2])));
            }

            std::vector<cv::Point2f> matched;
            cv::fisheye::distortPoints(seeds, matched, calibration.rightK(),
                                       calibration.rightDistortion());

            std::vector<uchar> forward;
            std::vector<uchar> backward;
            std::vector<float> error;
            std::vector<cv::Point2f> back;

            cv::calcOpticalFlowPyrLK(left, right, corners, matched, forward,
                                     error, cv::Size(21, 21), 3,
                                     cv::TermCriteria(3, 20, 0.03),
                                     cv::OPTFLOW_USE_INITIAL_FLOW);
            cv::calcOpticalFlowPyrLK(right, left, matched, back, backward,
                                     error, cv::Size(21, 21), 3);

            std::vector<cv::Point2f> leftKept;
            std::vector<cv::Point2f> rightKept;

            for (size_t k = 0; k < corners.size(); ++k)
            {
                if (forward[k] && backward[k] &&
                    cv::norm(back[k] - corners[k]) < 1.0 &&
                    matched[k].x >= 0 && matched[k].x < 640 &&
                    matched[k].y >= 0 && matched[k].y < 480)
                {
                    leftKept.push_back(corners[k]);
                    rightKept.push_back(matched[k]);
                }
            }

            if (leftKept.empty())
            {
                continue;
            }

            std::vector<cv::Point2f> nl;
            std::vector<cv::Point2f> nr;

            cv::fisheye::undistortPoints(leftKept, nl, calibration.leftK(),
                                         calibration.leftDistortion());
            cv::fisheye::undistortPoints(rightKept, nr, calibration.rightK(),
                                         calibration.rightDistortion());

            const double pixel =
                0.5 * (calibration.leftK()(0, 0) + calibration.leftK()(1, 1));

            for (Hypothesis& h : hypotheses)
            {
                const cv::Vec3d centre = -(h.rotation.t() * h.translation);

                for (size_t k = 0; k < nl.size(); ++k)
                {
                    ++h.total;

                    StereoMatcher::RayIntersection ray;

                    if (!StereoMatcher::intersectOnLeftRay(
                            bearingFromNormalised(nl[k]),
                            h.rotation.t() * bearingFromNormalised(nr[k]),
                            centre, ray))
                    {
                        ++h.behind;
                        continue;
                    }

                    h.miss.push_back(ray.missRadians * pixel);
                    h.vertical.push_back(ray.miss[1] / ray.range * pixel);

                    if (&h == &hypotheses[0])
                    {
                        const double radius = std::hypot(
                            leftKept[k].x - calibration.leftK()(0, 2),
                            leftKept[k].y - calibration.leftK()(1, 2));

                        const int bin = std::min(kBins - 1,
                            static_cast<int>(radius / 80.0));

                        binMiss[bin].push_back(ray.missRadians * pixel);
                        binVertical[bin].push_back(
                            ray.miss[1] / ray.range * pixel);
                    }
                }
            }
        }

        printf("  %d frames, matches scored under each convention:\n\n",
               framesUsed);
        printf("  %-44s %8s %9s %11s\n",
               "hypothesis", "matches", "behind", "median miss");

        double best = 1e9;
        int bestIndex = -1;

        for (int k = 0; k < 3; ++k)
        {
            Hypothesis& h = hypotheses[k];

            const double median = percentile(h.miss, 0.5);

            printf("  %-44s %8d %8.1f%% %9.3f px\n",
                   h.name, h.total,
                   h.total ? 100.0 * h.behind / h.total : 0.0, median);

            if (!h.miss.empty() && median < best)
            {
                best = median;
                bestIndex = k;
            }
        }

        printf("\n");

        char detail[200];

        snprintf(detail, sizeof(detail),
                 "calibration convention has the smallest ray miss "
                 "(%.3f px)", percentile(hypotheses[0].miss, 0.5));

        report(bestIndex == 0, "extrinsic convention matches real data",
               detail);

        // Medians throughout: a handful of false matches would drag a
        // mean anywhere.
        const double verticalMedian = percentile(hypotheses[0].vertical, 0.5);

        printf("\n  Calibration consistency on real frames (not a code "
               "check):\n");
        printf("  %-12s %8s %12s %16s\n",
               "radius", "matches", "median miss", "median vertical");

        for (int b = 0; b < kBins; ++b)
        {
            printf("  %3d-%-3d px   %8zu %9.3f px %+13.3f px\n",
                   b * 80, (b + 1) * 80, binMiss[b].size(),
                   percentile(binMiss[b], 0.5),
                   percentile(binVertical[b], 0.5));
        }

        printf("\n  Median vertical miss %+.3f px. A consistent non-zero value "
               "is a\n"
               "  stereo calibration error. Since section 6's fix it only "
               "affects\n"
               "  range along each ray, never rotation - but it does bias "
               "depth,\n"
               "  and the proper remedy is a stereo recalibration.\n",
               verticalMedian);
    }

    printf("\n========================================\n");
    printf("passed %d, failed %d\n", gPass, gFail);
    printf("========================================\n");

    return gFail == 0 ? 0 : 1;
}
