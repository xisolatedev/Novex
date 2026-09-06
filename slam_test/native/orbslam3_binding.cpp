// ============================================================
// NOVEX - pybind11 binding for ORB-SLAM3
// ============================================================
// Exposes exactly what the Novex GUI needs and nothing more:
//
//   * stereo tracking on synchronized rectified image pairs
//   * the real ORB-SLAM3 tracking state
//   * the keypoints of the frame that was just tracked,
//     flagged by whether they matched a map point
//   * the current map (map points + keyframe poses)
//
// Design notes:
//
//  - track_stereo() releases the GIL. ORB-SLAM3 spends tens of
//    milliseconds inside this call and the camera capture thread
//    must keep running while it does.
//
//  - The incoming numpy buffers are cloned into cv::Mat. ORB-SLAM3
//    keeps a shallow cv::Mat reference to the left image inside
//    Tracking/FrameDrawer after the call returns; without the clone
//    that would alias a Python-owned buffer that is about to be
//    reused by the capture thread.
//
//  - Poses are returned as plain 4x4 float32 numpy matrices so the
//    Python side never needs Sophus or Eigen.
// ============================================================

#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>

#include <opencv2/core/core.hpp>

#include <string>
#include <vector>
#include <memory>
#include <stdexcept>
#include <cstring>

#include "System.h"
#include "Tracking.h"
#include "Atlas.h"
#include "Map.h"
#include "MapPoint.h"
#include "KeyFrame.h"
#include "Frame.h"

namespace py = pybind11;

// ------------------------------------------------------------
// numpy (H, W) uint8  ->  cv::Mat CV_8UC1   (deep copy)
// ------------------------------------------------------------
static cv::Mat NumpyToGray(const py::array_t<uint8_t, py::array::c_style | py::array::forcecast> &arr,
                           const char *name)
{
    py::buffer_info info = arr.request();

    if (info.ndim != 2) {
        throw std::runtime_error(std::string(name) +
                                 ": expected a 2D grayscale uint8 array, got ndim=" +
                                 std::to_string(info.ndim));
    }

    const int rows = static_cast<int>(info.shape[0]);
    const int cols = static_cast<int>(info.shape[1]);

    cv::Mat wrapper(rows, cols, CV_8UC1, info.ptr, info.strides[0]);

    // Deep copy: ORB-SLAM3 retains a reference to this image.
    return wrapper.clone();
}

// ------------------------------------------------------------
// Sophus::SE3f -> 4x4 float32 numpy matrix
// ------------------------------------------------------------
static py::array_t<float> SE3ToNumpy(const Sophus::SE3f &T)
{
    py::array_t<float> out({4, 4});
    auto m = out.mutable_unchecked<2>();

    const Eigen::Matrix3f R = T.rotationMatrix();
    const Eigen::Vector3f t = T.translation();

    for (int i = 0; i < 3; ++i) {
        for (int j = 0; j < 3; ++j) {
            m(i, j) = R(i, j);
        }
        m(i, 3) = t(i);
    }

    m(3, 0) = 0.0f;
    m(3, 1) = 0.0f;
    m(3, 2) = 0.0f;
    m(3, 3) = 1.0f;

    return out;
}

// ------------------------------------------------------------
class NovexSlam
{
public:
    NovexSlam(const std::string &vocabulary,
              const std::string &settings,
              bool use_viewer,
              int verbosity)
    {
        ORB_SLAM3::Verbose::SetTh(
            static_cast<ORB_SLAM3::Verbose::eLevel>(verbosity));

        // Vocabulary loading takes 10-20 s; do not hold the GIL.
        py::gil_scoped_release release;

        system_ = std::make_unique<ORB_SLAM3::System>(
            vocabulary,
            settings,
            ORB_SLAM3::System::STEREO,
            use_viewer);
    }

    ~NovexSlam()
    {
        if (system_) {
            try {
                py::gil_scoped_release release;
                system_->Shutdown();
            } catch (...) {
                // Never throw from a destructor.
            }
        }
    }

    // --------------------------------------------------------
    // Track one synchronized, rectified stereo pair.
    //
    // Returns a dict; see slam.py for how it is consumed.
    // --------------------------------------------------------
    py::dict TrackStereo(const py::array_t<uint8_t, py::array::c_style | py::array::forcecast> &left,
                         const py::array_t<uint8_t, py::array::c_style | py::array::forcecast> &right,
                         double timestamp)
    {
        cv::Mat imLeft  = NumpyToGray(left,  "left");
        cv::Mat imRight = NumpyToGray(right, "right");

        if (imLeft.size() != imRight.size()) {
            throw std::runtime_error("left and right images must have the same size");
        }

        Sophus::SE3f Tcw;
        int state = -1;

        std::vector<cv::KeyPoint> keypoints;
        std::vector<cv::KeyPoint> keypoints_right;
        std::vector<ORB_SLAM3::MapPoint *> mappoints;
        std::vector<float> uRight;
        std::vector<float> depth;
        bool fisheye_model = false;

        {
            // ORB extraction + stereo matching + optimisation happen
            // here. This is the expensive call, so the GIL is dropped.
            py::gil_scoped_release release;

            Tcw = system_->TrackStereo(imLeft, imRight, timestamp);

            state = system_->GetTrackingState();

            // Read straight from the tracker's current frame rather
            // than System's snapshot, so the keypoints, their stereo
            // matches and their depths are all guaranteed to describe
            // the SAME frame. Safe here because tracking runs on this
            // thread and has already returned.
            ORB_SLAM3::Tracking *tracker = system_->GetTracker();
            if (tracker) {
                ORB_SLAM3::Frame &f = tracker->mCurrentFrame;
                keypoints       = f.mvKeys;
                keypoints_right = f.mvKeysRight;
                mappoints       = f.mvpMapPoints;

                // ORB-SLAM3 records stereo matches in two DIFFERENT
                // ways depending on the camera model, and reading the
                // wrong one silently reports zero stereo:
                //
                //   Rectified/PinHole: Nleft == -1, and mvuRight[i]
                //     holds the matching column in the right image
                //     (-1 when unmatched), with depth in mvDepth[i].
                //
                //   KannalaBrandt8 (fisheye): the frame holds BOTH
                //     images' keypoints, N = Nleft + Nright, and the
                //     match is mvLeftToRightMatch[i] (an index, -1
                //     when unmatched) with the triangulated point in
                //     mvStereo3Dpoints[i].
                //
                // Normalise both into the same uRight/depth arrays so
                // the Python side does not care which model is in use.
                fisheye_model = (f.Nleft != -1);

                if (fisheye_model) {
                    const size_t nleft = static_cast<size_t>(f.Nleft);
                    uRight.assign(nleft, -1.0f);
                    depth.assign(nleft, -1.0f);

                    for (size_t i = 0; i < nleft; ++i) {
                        if (i < f.mvLeftToRightMatch.size() &&
                            f.mvLeftToRightMatch[i] >= 0) {
                            uRight[i] = static_cast<float>(f.mvLeftToRightMatch[i]);
                            if (i < f.mvStereo3Dpoints.size()) {
                                depth[i] = f.mvStereo3Dpoints[i](2);
                            }
                        }
                    }

                    // In this mode mvpMapPoints covers left THEN right
                    // keypoints; only the left half lines up with the
                    // left keypoint list.
                    if (mappoints.size() > nleft) {
                        mappoints.resize(nleft);
                    }
                } else {
                    uRight = f.mvuRight;
                    depth  = f.mvDepth;
                }
            } else {
                keypoints = system_->GetTrackedKeyPointsUn();
                mappoints = system_->GetTrackedMapPoints();
            }
        }

        const size_t n = keypoints.size();

        py::array_t<float> kp({static_cast<py::ssize_t>(n), static_cast<py::ssize_t>(2)});
        py::array_t<bool>  tracked(static_cast<py::ssize_t>(n));
        py::array_t<bool>  has_stereo(static_cast<py::ssize_t>(n));
        py::array_t<float> kp_depth(static_cast<py::ssize_t>(n));

        auto kp_m = kp.mutable_unchecked<2>();
        auto tr_m = tracked.mutable_unchecked<1>();
        auto st_m = has_stereo.mutable_unchecked<1>();
        auto dp_m = kp_depth.mutable_unchecked<1>();

        int n_tracked = 0;
        int n_stereo = 0;
        double depth_sum = 0.0;
        float depth_min = 0.0f, depth_max = 0.0f;
        bool first_depth = true;

        for (size_t i = 0; i < n; ++i) {
            kp_m(i, 0) = keypoints[i].pt.x;
            kp_m(i, 1) = keypoints[i].pt.y;

            // A keypoint counts as tracked when it is associated with
            // a map point that is not flagged bad. This is the same
            // criterion ORB-SLAM3's own FrameDrawer uses.
            bool is_tracked = false;

            if (i < mappoints.size() && mappoints[i]) {
                if (!mappoints[i]->isBad()) {
                    is_tracked = true;
                }
            }

            tr_m(i) = is_tracked;
            if (is_tracked) {
                ++n_tracked;
            }

            // mvuRight holds the matching column in the RIGHT image,
            // or -1 when stereo matching found nothing. This is the
            // honest measure of how much the second camera is
            // contributing: a feature without a stereo match is
            // effectively monocular and carries no depth.
            const bool stereo = (i < uRight.size()) && (uRight[i] >= 0.0f);
            st_m(i) = stereo;

            float d = -1.0f;
            if (i < depth.size()) {
                d = depth[i];
            }
            dp_m(i) = d;

            if (stereo) {
                ++n_stereo;
                if (d > 0.0f) {
                    depth_sum += d;
                    if (first_depth) {
                        depth_min = depth_max = d;
                        first_depth = false;
                    } else {
                        if (d < depth_min) depth_min = d;
                        if (d > depth_max) depth_max = d;
                    }
                }
            }
        }

        const size_t nr = keypoints_right.size();
        py::array_t<float> kpr({static_cast<py::ssize_t>(nr), static_cast<py::ssize_t>(2)});
        auto kpr_m = kpr.mutable_unchecked<2>();
        for (size_t i = 0; i < nr; ++i) {
            kpr_m(i, 0) = keypoints_right[i].pt.x;
            kpr_m(i, 1) = keypoints_right[i].pt.y;
        }

        py::dict out;
        out["Tcw"]                = SE3ToNumpy(Tcw);
        out["state"]              = state;
        out["keypoints"]          = kp;
        out["keypoints_right"]    = kpr;
        out["kp_tracked"]         = tracked;
        out["kp_stereo"]          = has_stereo;
        out["kp_depth"]           = kp_depth;
        out["num_keypoints"]      = static_cast<int>(n);
        out["num_keypoints_right"] = static_cast<int>(nr);
        out["num_tracked"]        = n_tracked;
        out["num_stereo"]         = n_stereo;
        out["fisheye_model"]      = fisheye_model;
        out["mean_depth"]         = n_stereo > 0 ? depth_sum / n_stereo : 0.0;
        out["min_depth"]          = depth_min;
        out["max_depth"]          = depth_max;

        return out;
    }

    // --------------------------------------------------------
    // Current map: Nx3 float32 of map point world positions.
    // --------------------------------------------------------
    py::array_t<float> GetMapPoints()
    {
        std::vector<ORB_SLAM3::MapPoint *> mps;

        {
            py::gil_scoped_release release;
            ORB_SLAM3::Map *map = system_->GetAtlas()->GetCurrentMap();
            if (map) {
                mps = map->GetAllMapPoints();
            }
        }

        std::vector<float> good;
        good.reserve(mps.size() * 3);

        for (ORB_SLAM3::MapPoint *mp : mps) {
            if (!mp || mp->isBad()) {
                continue;
            }
            const Eigen::Vector3f p = mp->GetWorldPos();
            good.push_back(p(0));
            good.push_back(p(1));
            good.push_back(p(2));
        }

        const py::ssize_t n = static_cast<py::ssize_t>(good.size() / 3);

        py::array_t<float> out({n, static_cast<py::ssize_t>(3)});
        if (n > 0) {
            std::memcpy(out.mutable_data(), good.data(), good.size() * sizeof(float));
        }
        return out;
    }

    // --------------------------------------------------------
    // Keyframe camera centres in world frame: Nx3 float32.
    // Used to draw the keyframe positions in the 3D view.
    // --------------------------------------------------------
    py::array_t<float> GetKeyFramePositions()
    {
        std::vector<ORB_SLAM3::KeyFrame *> kfs;

        {
            py::gil_scoped_release release;
            ORB_SLAM3::Map *map = system_->GetAtlas()->GetCurrentMap();
            if (map) {
                kfs = map->GetAllKeyFrames();
            }
        }

        std::vector<float> good;
        good.reserve(kfs.size() * 3);

        for (ORB_SLAM3::KeyFrame *kf : kfs) {
            if (!kf || kf->isBad()) {
                continue;
            }
            const Eigen::Vector3f c = kf->GetCameraCenter();
            good.push_back(c(0));
            good.push_back(c(1));
            good.push_back(c(2));
        }

        const py::ssize_t n = static_cast<py::ssize_t>(good.size() / 3);

        py::array_t<float> out({n, static_cast<py::ssize_t>(3)});
        if (n > 0) {
            std::memcpy(out.mutable_data(), good.data(), good.size() * sizeof(float));
        }
        return out;
    }

    py::dict GetMapStats()
    {
        long unsigned int n_points = 0;
        long unsigned int n_kfs = 0;
        int n_maps = 0;

        {
            py::gil_scoped_release release;
            ORB_SLAM3::Atlas *atlas = system_->GetAtlas();
            ORB_SLAM3::Map *map = atlas->GetCurrentMap();
            if (map) {
                n_points = map->MapPointsInMap();
                n_kfs    = map->KeyFramesInMap();
            }
            n_maps = static_cast<int>(atlas->CountMaps());
        }

        py::dict out;
        out["map_points"] = static_cast<int>(n_points);
        out["keyframes"]  = static_cast<int>(n_kfs);
        out["num_maps"]   = n_maps;
        return out;
    }

    int GetTrackingState()
    {
        return system_->GetTrackingState();
    }

    bool IsLost()
    {
        return system_->isLost();
    }

    void Reset()
    {
        py::gil_scoped_release release;
        system_->Reset();
    }

    void ResetActiveMap()
    {
        py::gil_scoped_release release;
        system_->ResetActiveMap();
    }

    void SaveKeyFrameTrajectory(const std::string &path)
    {
        py::gil_scoped_release release;
        system_->SaveKeyFrameTrajectoryTUM(path);
    }

    void SaveTrajectory(const std::string &path)
    {
        py::gil_scoped_release release;
        system_->SaveTrajectoryTUM(path);
    }

    void Shutdown()
    {
        if (!system_) {
            return;
        }
        py::gil_scoped_release release;
        system_->Shutdown();
    }

private:
    std::unique_ptr<ORB_SLAM3::System> system_;
};

// ------------------------------------------------------------
PYBIND11_MODULE(novex_orbslam3, m)
{
    m.doc() = "Minimal pybind11 binding around ORB-SLAM3 stereo for the Novex test GUI";

    // The real ORB_SLAM3::Tracking::eTrackingState values, so the GUI
    // never invents a state of its own.
    py::enum_<ORB_SLAM3::Tracking::eTrackingState>(m, "TrackingState")
        .value("SYSTEM_NOT_READY", ORB_SLAM3::Tracking::SYSTEM_NOT_READY)
        .value("NO_IMAGES_YET",    ORB_SLAM3::Tracking::NO_IMAGES_YET)
        .value("NOT_INITIALIZED",  ORB_SLAM3::Tracking::NOT_INITIALIZED)
        .value("OK",               ORB_SLAM3::Tracking::OK)
        .value("RECENTLY_LOST",    ORB_SLAM3::Tracking::RECENTLY_LOST)
        .value("LOST",             ORB_SLAM3::Tracking::LOST)
        .value("OK_KLT",           ORB_SLAM3::Tracking::OK_KLT)
        .export_values();

    py::class_<NovexSlam>(m, "StereoSlam")
        .def(py::init<const std::string &, const std::string &, bool, int>(),
             py::arg("vocabulary"),
             py::arg("settings"),
             py::arg("use_viewer") = false,
             py::arg("verbosity") = 1,
             "Create an ORB-SLAM3 stereo system. Blocks while the ORB "
             "vocabulary loads (10-20 s).")
        .def("track_stereo", &NovexSlam::TrackStereo,
             py::arg("left"), py::arg("right"), py::arg("timestamp"),
             "Track one synchronized RECTIFIED grayscale stereo pair.")
        .def("get_map_points", &NovexSlam::GetMapPoints)
        .def("get_keyframe_positions", &NovexSlam::GetKeyFramePositions)
        .def("get_map_stats", &NovexSlam::GetMapStats)
        .def("get_tracking_state", &NovexSlam::GetTrackingState)
        .def("is_lost", &NovexSlam::IsLost)
        .def("reset", &NovexSlam::Reset)
        .def("reset_active_map", &NovexSlam::ResetActiveMap)
        .def("save_trajectory", &NovexSlam::SaveTrajectory, py::arg("path"))
        .def("save_keyframe_trajectory", &NovexSlam::SaveKeyFrameTrajectory, py::arg("path"))
        .def("shutdown", &NovexSlam::Shutdown);
}
