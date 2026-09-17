#pragma once

#include <opencv2/core.hpp>

#include <cmath>

namespace novex
{

// Small, allocation-free Kannala-Brandt helpers for single points.
//
// cv::fisheye works on vectors, which is right for batches but means a
// heap round trip for every one-off projection. These are used where
// the pipeline needs a handful of exact per-point values in the hot
// loop - reprojection errors, bearings - and they implement exactly
// the model cv::fisheye uses (and the calibration was fitted with):
//
//   theta   = atan2(sqrt(x^2 + y^2), z)
//   theta_d = theta (1 + k1 theta^2 + k2 theta^4 + k3 theta^6 + k4 theta^8)
//   u = fx * theta_d * x / r + cx,   v = fy * theta_d * y / r + cy
//
// with zero skew, which is what our calibrator produces.
//
// ANGLES, NOT THE NORMALISED PLANE
// --------------------------------
// Residuals in this pipeline are measured as angles between unit
// bearing vectors. On a pinhole camera the normalised image plane
// z = 1 is a fine place to measure error, but on this fisheye it is
// not: a one-pixel error at incidence theta is sec^2(theta) times
// larger on that plane than at the centre. At the corner of the
// 640x480 image theta reaches ~74 degrees, where that factor is ~13,
// so a least-squares fit on the plane lets the least reliable pixels
// in the image (the calibration is worst at the edge) dominate the
// solution. For a Kannala-Brandt lens, one pixel is close to a
// constant ANGLE everywhere (radially exactly 1/f at k = 0), which is
// why angles are the honest error measure here.

// Projects a point in the camera frame to pixels. Returns false for
// points at or behind the optical centre.
inline bool projectFisheye(const cv::Matx33d& K,
                           const cv::Vec4d& D,
                           const cv::Vec3d& point,
                           cv::Point2d& pixel)
{
    const double r = std::sqrt(point[0] * point[0] + point[1] * point[1]);

    if (!std::isfinite(r) || !std::isfinite(point[2]) ||
        (r < 1e-12 && point[2] <= 0.0))
    {
        return false;
    }

    const double theta = std::atan2(r, point[2]);

    // Beyond ~90 degrees the calibration was never measured and the
    // polynomial is extrapolating.
    if (theta > 1.5707963267948966)
    {
        return false;
    }

    const double t2 = theta * theta;
    const double t4 = t2 * t2;
    const double t6 = t4 * t2;
    const double t8 = t4 * t4;

    const double thetaD =
        theta * (1.0 + D[0] * t2 + D[1] * t4 + D[2] * t6 + D[3] * t8);

    double scale = 1.0;

    if (r > 1e-12)
    {
        scale = thetaD / r;
    }
    else
    {
        // On the axis thetaD / r -> 1 / z.
        scale = 1.0 / point[2];
    }

    pixel.x = K(0, 0) * point[0] * scale + K(0, 2);
    pixel.y = K(1, 1) * point[1] * scale + K(1, 2);

    return true;
}

// Unit bearing from a normalised image coordinate as returned by
// cv::fisheye::undistortPoints (x/z, y/z).
inline cv::Vec3d bearingFromNormalised(const cv::Point2f& normalised)
{
    const cv::Vec3d ray(normalised.x, normalised.y, 1.0);

    return ray / cv::norm(ray);
}

inline double angleBetweenUnit(const cv::Vec3d& a, const cv::Vec3d& b)
{
    // atan2 of |cross| and dot is accurate for tiny angles, where
    // acos(dot) loses almost all precision - and tiny angles are
    // exactly the regime of pixel-level residuals.
    return std::atan2(cv::norm(a.cross(b)), a.dot(b));
}

// Radians to "pixels at the centre of the image", for reporting
// angular quantities in a unit people have intuition for.
inline double anglePixels(double radians, const cv::Matx33d& K)
{
    return radians * 0.5 * (K(0, 0) + K(1, 1));
}

} // namespace novex
