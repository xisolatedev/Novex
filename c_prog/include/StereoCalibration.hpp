#pragma once

#include <opencv2/core.hpp>

#include <string>

namespace novex
{

enum class CameraModel
{
    Fisheye,   // Kannala-Brandt, 4 coefficients
    Pinhole    // not produced by our calibrator; rejected on load
};

// How the image the camera is currently delivering relates to the
// image the calibration was measured on.
//
// This exists because the two are NOT the same on this hardware, and
// pretending otherwise silently corrupts every geometric result. The
// calibration was captured in the camera's 2560x720 stereo mode
// (1280x720 per eye). The mode this system runs in is 1280x480 stereo
// (640x480 per eye), which the sensor produces by cropping
// horizontally and then downscaling - not by squashing the full frame
// into a new aspect ratio.
//
// See StereoCalibration::deriveMapping for how this is computed and
// for the measurement that established it.
struct SensorModeMapping
{
    // The region of the CALIBRATED image that the current image shows,
    // in calibration pixels.
    cv::Rect cropInCalibration;

    // Isotropic scale from cropped calibration pixels to current
    // pixels. Applied after the crop.
    double scale = 1.0;

    // True when the current resolution equals the calibration
    // resolution and no adaptation is needed at all.
    bool identity = true;

    // Fraction of the calibrated horizontal / vertical field of view
    // that survives the crop, as a blunt reminder of what is lost.
    double horizontalFOVRetained = 1.0;
    double verticalFOVRetained = 1.0;

    // True when the current resolution is larger than the calibrated
    // one in some axis, which means intrinsics are being extrapolated
    // rather than reduced.
    bool upscaling = false;

    std::string description;
};

// Loads the existing measured stereo calibration and makes it usable
// at whatever resolution the camera is actually running.
//
// This class never invents, rescales in place, or writes calibration
// values. The numbers loaded from disk are kept verbatim and exposed
// as the "calibration" set; a separate, explicitly derived "current"
// set is what the rest of the pipeline consumes.
class StereoCalibration
{
public:

    bool load(const std::string& path);

    // Derives the current-resolution intrinsics for a given per-eye
    // image size. Must be called before any current* accessor is used.
    // Returns false only if the size is nonsensical; a size that
    // requires an unusual adaptation is accepted but reported through
    // mapping() and logged.
    bool setCurrentResolution(const cv::Size& perEyeSize);

    bool isLoaded() const { return loaded; }
    bool isAdapted() const { return adapted; }

    // ---- calibration-native values, exactly as measured ----

    const cv::Matx33d& calibrationLeftK()  const { return calLeftK; }
    const cv::Matx33d& calibrationRightK() const { return calRightK; }

    const cv::Vec4d& leftDistortion()  const { return leftD; }
    const cv::Vec4d& rightDistortion() const { return rightD; }

    // Rotation and translation such that X_right = R * X_left + T.
    // These are rigid-body extrinsics between the two lenses and are
    // therefore independent of image resolution: they are the same in
    // both coordinate sets.
    const cv::Matx33d& rotation()    const { return R; }
    const cv::Vec3d&   translation() const { return T; }

    double baseline() const { return baselineMeters; }

    cv::Size calibrationResolution() const { return calibrationSize; }
    CameraModel model() const { return cameraModel; }

    const std::string& sourcePath() const { return path; }

    // ---- values adapted to the resolution actually in use ----

    const cv::Matx33d& leftK()  const { return curLeftK; }
    const cv::Matx33d& rightK() const { return curRightK; }

    cv::Size currentResolution() const { return currentSize; }

    const SensorModeMapping& mapping() const { return modeMapping; }

    // Human-readable dump of both coordinate sets, for start-up logs
    // and the self-test.
    std::string describe() const;

private:

    static SensorModeMapping deriveMapping(const cv::Size& calibration,
                                           const cv::Size& current);

    static cv::Matx33d adaptIntrinsics(const cv::Matx33d& K,
                                       const SensorModeMapping& mapping);

    bool validate();

    std::string path;

    bool loaded = false;
    bool adapted = false;

    CameraModel cameraModel = CameraModel::Fisheye;

    cv::Size calibrationSize;
    cv::Size currentSize;

    cv::Matx33d calLeftK  = cv::Matx33d::eye();
    cv::Matx33d calRightK = cv::Matx33d::eye();

    cv::Vec4d leftD  = cv::Vec4d::all(0.0);
    cv::Vec4d rightD = cv::Vec4d::all(0.0);

    cv::Matx33d R = cv::Matx33d::eye();
    cv::Vec3d   T = cv::Vec3d::all(0.0);

    double baselineMeters = 0.0;

    cv::Matx33d curLeftK  = cv::Matx33d::eye();
    cv::Matx33d curRightK = cv::Matx33d::eye();

    SensorModeMapping modeMapping;
};

} // namespace novex
