#include "StereoCalibration.hpp"

#include "Log.hpp"
#include "Yaml.hpp"

#include <cmath>
#include <sstream>

namespace novex
{

namespace
{

bool readMatrix3x3(const Yaml& yaml,
                   const std::string& key,
                   cv::Matx33d& out,
                   std::string& why)
{
    const std::vector<double> values = yaml.getVector(key);

    if (values.size() != 9)
    {
        why = key + ": expected 9 values, got " +
              std::to_string(values.size());
        return false;
    }

    for (int i = 0; i < 9; ++i)
    {
        out.val[i] = values[static_cast<size_t>(i)];
    }

    return true;
}

} // namespace

bool StereoCalibration::load(const std::string& filePath)
{
    loaded = false;
    adapted = false;

    path = filePath;

    Yaml yaml;

    if (!yaml.loadFile(filePath))
    {
        LOG_ERROR("calibration: %s", yaml.error().c_str());
        return false;
    }

    const std::string modelName = yaml.getString("model", "");

    if (modelName == "fisheye")
    {
        cameraModel = CameraModel::Fisheye;
    }
    else
    {
        // Refusing rather than guessing: the whole stereo geometry
        // below assumes Kannala-Brandt, and a pinhole calibration
        // pushed through it would produce plausible-looking but wrong
        // depth.
        LOG_ERROR(
            "calibration: model '%s' is not supported "
            "(only 'fisheye' / Kannala-Brandt)",
            modelName.c_str()
        );

        return false;
    }

    calibrationSize.width  = yaml.getInt("image_width", 0);
    calibrationSize.height = yaml.getInt("image_height", 0);

    std::string why;

    if (!readMatrix3x3(yaml, "camera1.K", calLeftK, why) ||
        !readMatrix3x3(yaml, "camera2.K", calRightK, why) ||
        !readMatrix3x3(yaml, "R", R, why))
    {
        LOG_ERROR("calibration: %s", why.c_str());
        return false;
    }

    const std::vector<double> leftDistortion  = yaml.getVector("camera1.D");
    const std::vector<double> rightDistortion = yaml.getVector("camera2.D");
    const std::vector<double> translation     = yaml.getVector("T");

    if (leftDistortion.size() != 4 || rightDistortion.size() != 4)
    {
        LOG_ERROR(
            "calibration: Kannala-Brandt needs exactly 4 distortion "
            "coefficients per camera (got %zu / %zu)",
            leftDistortion.size(),
            rightDistortion.size()
        );

        return false;
    }

    if (translation.size() != 3)
    {
        LOG_ERROR(
            "calibration: T must have 3 values, got %zu",
            translation.size()
        );

        return false;
    }

    for (int i = 0; i < 4; ++i)
    {
        leftD[i]  = leftDistortion[static_cast<size_t>(i)];
        rightD[i] = rightDistortion[static_cast<size_t>(i)];
    }

    for (int i = 0; i < 3; ++i)
    {
        T[i] = translation[static_cast<size_t>(i)];
    }

    baselineMeters = yaml.getDouble("baseline_m", cv::norm(T));

    if (!validate())
    {
        return false;
    }

    loaded = true;

    LOG_INFO(
        "calibration: loaded %s (%s, %dx%d per eye, baseline %.2f mm)",
        filePath.c_str(),
        "Kannala-Brandt fisheye",
        calibrationSize.width,
        calibrationSize.height,
        baselineMeters * 1e3
    );

    return true;
}

bool StereoCalibration::validate()
{
    if (calibrationSize.width <= 0 || calibrationSize.height <= 0)
    {
        LOG_ERROR(
            "calibration: image_width/image_height missing or invalid"
        );

        return false;
    }

    // Focal lengths and principal points must at least sit inside a
    // believable range for the declared image size. A calibration that
    // fails this is corrupt, and a corrupt calibration is worse than
    // none because everything downstream still "works".
    const cv::Matx33d* matrices[2] = { &calLeftK, &calRightK };
    const char* names[2] = { "camera1", "camera2" };

    for (int i = 0; i < 2; ++i)
    {
        const cv::Matx33d& K = *matrices[i];

        const double fx = K(0, 0);
        const double fy = K(1, 1);
        const double cx = K(0, 2);
        const double cy = K(1, 2);

        if (!(fx > 1.0) || !(fy > 1.0) ||
            !std::isfinite(fx) || !std::isfinite(fy))
        {
            LOG_ERROR(
                "calibration: %s has implausible focal length "
                "(fx=%.3f fy=%.3f)",
                names[i], fx, fy
            );

            return false;
        }

        if (cx < 0.0 || cx > calibrationSize.width ||
            cy < 0.0 || cy > calibrationSize.height)
        {
            LOG_ERROR(
                "calibration: %s principal point (%.1f, %.1f) lies "
                "outside the declared %dx%d image",
                names[i], cx, cy,
                calibrationSize.width, calibrationSize.height
            );

            return false;
        }
    }

    // R must be a rotation. Checks both orthonormality and handedness;
    // a mirrored R would flip depth sign in a way that is easy to miss.
    const cv::Matx33d shouldBeIdentity = R * R.t();

    double orthonormalityError = 0.0;

    for (int row = 0; row < 3; ++row)
    {
        for (int col = 0; col < 3; ++col)
        {
            const double expected = (row == col) ? 1.0 : 0.0;

            orthonormalityError = std::max(
                orthonormalityError,
                std::abs(shouldBeIdentity(row, col) - expected)
            );
        }
    }

    if (orthonormalityError > 1e-4)
    {
        LOG_ERROR(
            "calibration: R is not orthonormal (max error %.3e)",
            orthonormalityError
        );

        return false;
    }

    if (cv::determinant(R) < 0.0)
    {
        LOG_ERROR("calibration: R has determinant < 0 (reflection)");
        return false;
    }

    // The stated baseline must agree with |T|; if it does not, one of
    // the two was edited by hand and we cannot tell which to trust.
    const double magnitude = cv::norm(T);

    if (magnitude < 1e-4)
    {
        LOG_ERROR(
            "calibration: baseline is essentially zero (%.6f m); "
            "stereo depth is not observable",
            magnitude
        );

        return false;
    }

    if (std::abs(magnitude - baselineMeters) > 1e-4)
    {
        LOG_WARN(
            "calibration: declared baseline_m %.6f disagrees with |T| "
            "%.6f; using |T|",
            baselineMeters,
            magnitude
        );

        baselineMeters = magnitude;
    }

    return true;
}

SensorModeMapping StereoCalibration::deriveMapping(
    const cv::Size& calibration,
    const cv::Size& current)
{
    SensorModeMapping mapping;

    mapping.cropInCalibration = cv::Rect(
        0, 0, calibration.width, calibration.height
    );

    if (calibration == current)
    {
        mapping.identity = true;
        mapping.scale = 1.0;
        mapping.description =
            "identity - the camera is running the mode the "
            "calibration was measured in";

        return mapping;
    }

    mapping.identity = false;

    // The rule: find the largest CENTERED region of the calibrated
    // image that has the current image's aspect ratio, then scale it
    // isotropically onto the current image.
    //
    // Why this rule and not a plain rescale: a plain rescale of
    // 1280x720 onto 640x480 is anisotropic (0.500 horizontally, 0.667
    // vertically). An anisotropic resampling is not expressible in the
    // Kannala-Brandt model at all - that model maps an incidence
    // ANGLE to a radius, which requires the pixel grid to be square -
    // so it would quietly invalidate the distortion coefficients.
    //
    // This rule was not assumed. It was verified against this camera
    // by capturing the same static scene in both modes and fitting a
    // full affine between the left eyes with ORB + RANSAC, then
    // repeating independently for the right eyes:
    //
    //     left  : sx 0.66603  sy 0.66574  origin (159.5, -0.5)
    //     right : sx 0.66708  sy 0.66471  origin (160.2, -0.2)
    //
    // sx == sy to within 0.4%, so the sensor mode is isotropic, and
    // the implied source window is 960x720 at x=160 - exactly the
    // centered 4:3 crop this rule produces. The distortion
    // coefficients therefore carry over untouched and only the
    // principal point and focal length move.
    const double scaleX =
        static_cast<double>(current.width) / calibration.width;

    const double scaleY =
        static_cast<double>(current.height) / calibration.height;

    mapping.scale = std::max(scaleX, scaleY);

    const int cropWidth = static_cast<int>(
        std::lround(current.width / mapping.scale)
    );

    const int cropHeight = static_cast<int>(
        std::lround(current.height / mapping.scale)
    );

    mapping.cropInCalibration = cv::Rect(
        (calibration.width  - cropWidth)  / 2,
        (calibration.height - cropHeight) / 2,
        cropWidth,
        cropHeight
    );

    mapping.horizontalFOVRetained =
        static_cast<double>(cropWidth) / calibration.width;

    mapping.verticalFOVRetained =
        static_cast<double>(cropHeight) / calibration.height;

    mapping.upscaling =
        current.width  > calibration.width ||
        current.height > calibration.height;

    std::ostringstream text;

    text.setf(std::ios::fixed);
    text.precision(4);

    text << "centered crop " << cropWidth << "x" << cropHeight
         << " at (" << mapping.cropInCalibration.x << ", "
         << mapping.cropInCalibration.y << ") of the "
         << calibration.width << "x" << calibration.height
         << " calibrated image, then isotropic scale "
         << mapping.scale;

    mapping.description = text.str();

    return mapping;
}

cv::Matx33d StereoCalibration::adaptIntrinsics(
    const cv::Matx33d& K,
    const SensorModeMapping& mapping)
{
    // Crop moves the principal point; isotropic scale multiplies focal
    // length and principal point alike. The Kannala-Brandt
    // coefficients k1..k4 are functions of incidence angle, not of
    // pixel size, so they are deliberately NOT touched here.
    cv::Matx33d adapted = K;

    adapted(0, 2) = K(0, 2) - mapping.cropInCalibration.x;
    adapted(1, 2) = K(1, 2) - mapping.cropInCalibration.y;

    adapted(0, 0) *= mapping.scale;
    adapted(1, 1) *= mapping.scale;
    adapted(0, 2) *= mapping.scale;
    adapted(1, 2) *= mapping.scale;

    return adapted;
}

bool StereoCalibration::setCurrentResolution(const cv::Size& perEyeSize)
{
    if (!loaded)
    {
        LOG_ERROR("calibration: setCurrentResolution before load()");
        return false;
    }

    if (perEyeSize.width <= 0 || perEyeSize.height <= 0)
    {
        LOG_ERROR(
            "calibration: invalid current resolution %dx%d",
            perEyeSize.width, perEyeSize.height
        );

        return false;
    }

    currentSize = perEyeSize;
    modeMapping = deriveMapping(calibrationSize, currentSize);

    curLeftK  = adaptIntrinsics(calLeftK,  modeMapping);
    curRightK = adaptIntrinsics(calRightK, modeMapping);

    adapted = true;

    if (modeMapping.identity)
    {
        LOG_INFO(
            "calibration: current resolution matches calibration "
            "(%dx%d per eye); intrinsics used unchanged",
            currentSize.width, currentSize.height
        );
    }
    else
    {
        LOG_INFO(
            "calibration: adapting %dx%d -> %dx%d per eye: %s",
            calibrationSize.width, calibrationSize.height,
            currentSize.width, currentSize.height,
            modeMapping.description.c_str()
        );

        LOG_INFO(
            "calibration: field of view retained %.1f%% horizontal, "
            "%.1f%% vertical",
            modeMapping.horizontalFOVRetained * 100.0,
            modeMapping.verticalFOVRetained * 100.0
        );

        if (modeMapping.horizontalFOVRetained < 0.9 ||
            modeMapping.verticalFOVRetained < 0.9)
        {
            LOG_WARN(
                "calibration: this camera mode discards part of the "
                "calibrated field of view. On a fisheye lens the "
                "periphery is where features move fastest under "
                "rotation, so losing it weakens the rotation "
                "estimate. The 2560x720 mode keeps all of it."
            );
        }

        if (modeMapping.upscaling)
        {
            LOG_WARN(
                "calibration: current resolution exceeds the "
                "calibrated one; intrinsics are being extrapolated "
                "beyond what was measured"
            );
        }
    }

    return true;
}

std::string StereoCalibration::describe() const
{
    std::ostringstream text;

    text.setf(std::ios::fixed);
    text.precision(3);

    text << "StereoCalibration from " << path << "\n";

    if (!loaded)
    {
        text << "  NOT LOADED\n";
        return text.str();
    }

    text << "  model              : Kannala-Brandt fisheye\n"
         << "  calibration size   : " << calibrationSize.width
         << "x" << calibrationSize.height << " per eye\n"
         << "  baseline           : " << baselineMeters * 1e3 << " mm\n";

    text << "  calibration coords :\n"
         << "    left  fx " << calLeftK(0, 0)
         << " fy " << calLeftK(1, 1)
         << " cx " << calLeftK(0, 2)
         << " cy " << calLeftK(1, 2) << "\n"
         << "    right fx " << calRightK(0, 0)
         << " fy " << calRightK(1, 1)
         << " cx " << calRightK(0, 2)
         << " cy " << calRightK(1, 2) << "\n";

    if (!adapted)
    {
        text << "  current coords     : not derived yet\n";
        return text.str();
    }

    text << "  current size       : " << currentSize.width
         << "x" << currentSize.height << " per eye\n"
         << "  mapping            : " << modeMapping.description << "\n"
         << "  current coords     :\n"
         << "    left  fx " << curLeftK(0, 0)
         << " fy " << curLeftK(1, 1)
         << " cx " << curLeftK(0, 2)
         << " cy " << curLeftK(1, 2) << "\n"
         << "    right fx " << curRightK(0, 0)
         << " fy " << curRightK(1, 1)
         << " cx " << curRightK(0, 2)
         << " cy " << curRightK(1, 2) << "\n";

    text.precision(8);

    text << "  distortion (unchanged by resolution):\n"
         << "    left  " << leftD[0] << " " << leftD[1] << " "
         << leftD[2] << " " << leftD[3] << "\n"
         << "    right " << rightD[0] << " " << rightD[1] << " "
         << rightD[2] << " " << rightD[3] << "\n";

    return text.str();
}

} // namespace novex
