#!/usr/bin/env python3
"""
Patch upstream ORB-SLAM3 so it compiles on a modern toolchain
(CMake >= 3.28, gcc 13, Eigen 3.4, Pangolin 0.9) and so it exposes
the few accessors the Novex pybind11 binding needs.

Every patch is listed explicitly below with the reason it exists.
Re-running is safe: each patch checks whether it is already applied.

    python3 scripts/patch_orbslam3.py third_party/ORB_SLAM3
"""

import sys
import os
import re

APPLIED = []
SKIPPED = []


def patch(path, old, new, why, count=1):
    """Literal string replacement."""
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()

    # Idempotency: the replacement text is the marker. If it is already
    # there the patch has been applied, even when `old` is a substring of
    # `new` (which is the case for the pure-insertion patches below).
    if new in text:
        SKIPPED.append(f"{os.path.basename(path)}: {why} (already applied)")
        return

    if old not in text:
        SKIPPED.append(f"!! {os.path.basename(path)}: PATTERN NOT FOUND for: {why}")
        return

    text = text.replace(old, new, count)

    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(text)

    APPLIED.append(f"{os.path.basename(path)}: {why}")


def patch_regex(path, pattern, repl, why, flags=0, guard=None):
    """`guard`: if this string is already in the file, the patch is a no-op."""
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        text = f.read()

    if guard is not None and guard in text:
        SKIPPED.append(f"{os.path.basename(path)}: {why} (already applied)")
        return

    new_text, n = re.subn(pattern, repl, text, count=1, flags=flags)

    if n == 0:
        SKIPPED.append(f"{os.path.basename(path)}: {why} (no match / already applied)")
        return

    with open(path, "w", encoding="utf-8", errors="surrogateescape") as f:
        f.write(new_text)

    APPLIED.append(f"{os.path.basename(path)}: {why}")


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "third_party/ORB_SLAM3")

    if not os.path.isdir(root):
        print(f"ERROR: {root} does not exist. Clone ORB-SLAM3 first.")
        return 1

    def p(*parts):
        return os.path.join(root, *parts)

    # ------------------------------------------------------------------
    # 1. cmake_minimum_required
    #
    # Upstream asks for CMake 2.8. CMake >= 3.27 refuses outright:
    # "Compatibility with CMake < 3.5 has been removed".
    # Bump every CMakeLists in the tree we build.
    # ------------------------------------------------------------------
    for f in [
        p("CMakeLists.txt"),
        p("Thirdparty", "DBoW2", "CMakeLists.txt"),
        p("Thirdparty", "g2o", "CMakeLists.txt"),
    ]:
        if os.path.exists(f):
            patch_regex(
                f,
                r"cmake_minimum_required\s*\(\s*VERSION\s+[0-9.]+\s*\)",
                "cmake_minimum_required(VERSION 3.16)",
                "cmake_minimum_required -> 3.16 (CMake 3.28 dropped <3.5 compat)",
                flags=re.I,
                guard="cmake_minimum_required(VERSION 3.16)",
            )

    # ------------------------------------------------------------------
    # 2. C++14
    #
    # Upstream forces -std=c++11. The bundled Sophus and g2o both need
    # C++14 (they use auto return type deduction / std::make_unique).
    # ------------------------------------------------------------------
    patch(
        p("CMakeLists.txt"),
        'CHECK_CXX_COMPILER_FLAG("-std=c++11" COMPILER_SUPPORTS_CXX11)',
        'CHECK_CXX_COMPILER_FLAG("-std=c++14" COMPILER_SUPPORTS_CXX11)',
        "probe for -std=c++14 instead of c++11",
    )
    patch(
        p("CMakeLists.txt"),
        'set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++11")',
        'set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -std=c++14")',
        "compile the library as C++14",
    )

    for f in [
        p("Thirdparty", "DBoW2", "CMakeLists.txt"),
        p("Thirdparty", "g2o", "CMakeLists.txt"),
    ]:
        if os.path.exists(f):
            patch_regex(
                f,
                r"-std=c\+\+11",
                "-std=c++14",
                "third-party C++14",
                guard="-std=c++14",
            )

    # ------------------------------------------------------------------
    # 3. Position independent code
    #
    # The Novex pybind11 module is a shared object that links these
    # libraries. Everything it pulls in must be -fPIC.
    # ------------------------------------------------------------------
    for f in [
        p("CMakeLists.txt"),
        p("Thirdparty", "DBoW2", "CMakeLists.txt"),
        p("Thirdparty", "g2o", "CMakeLists.txt"),
    ]:
        if os.path.exists(f):
            patch_regex(
                f,
                r"(cmake_minimum_required\(VERSION 3\.16\)\n)",
                r"\1set(CMAKE_POSITION_INDEPENDENT_CODE ON)\n",
                "force -fPIC (needed to link into a Python extension module)",
                guard="set(CMAKE_POSITION_INDEPENDENT_CODE ON)",
            )

    # ------------------------------------------------------------------
    # 4. Do not build the 70+ example executables
    #
    # We only need libORB_SLAM3.so. Building the examples costs a large
    # amount of compile time and pulls in dataset-specific code we
    # never run. Everything from the "# Build examples" comment down is
    # example targets, so the file is truncated there.
    # ------------------------------------------------------------------
    cml = p("CMakeLists.txt")
    with open(cml) as f:
        text = f.read()

    marker = "# Build examples"
    if marker in text and "NOVEX: examples intentionally not built" not in text:
        text = text.split(marker)[0]
        text += (
            "# ------------------------------------------------------------\n"
            "# NOVEX: examples intentionally not built.\n"
            "# The Novex GUI links libORB_SLAM3.so through its own pybind11\n"
            "# module (see native/), so the upstream dataset example\n"
            "# executables are unnecessary and only cost build time.\n"
            "# ------------------------------------------------------------\n"
        )
        with open(cml, "w") as f:
            f.write(text)
        APPLIED.append("CMakeLists.txt: dropped example executables (library only)")
    else:
        SKIPPED.append("CMakeLists.txt: example targets already removed")

    # ------------------------------------------------------------------
    # 5. Eigen alignment in LoopClosing.h
    #
    # KeyFrameAndPose stores fixed-size vectorizable Eigen types
    # (g2o::Sim3) in a std::map. With Eigen 3.4 + gcc 13 this trips a
    # static assertion unless the map uses Eigen's aligned allocator.
    # ------------------------------------------------------------------
    lc = p("include", "LoopClosing.h")
    with open(lc) as fh:
        lc_text = fh.read()
    if "aligned_allocator<std::pair<KeyFrame* const" in lc_text.replace(" *const", "* const"):
        SKIPPED.append("LoopClosing.h: aligned_allocator already correct upstream")
    else:
        SKIPPED.append("!! LoopClosing.h: unexpected KeyFrameAndPose typedef, check Eigen alignment")

    # ------------------------------------------------------------------
    # 6. Accessors for the Novex binding
    #
    # System keeps mpAtlas / mpTracker private. The GUI needs the map
    # points, keyframe poses and the live tracking internals, so two
    # trivial const-free getters are added to the public section.
    # This is the only behavioural change made to ORB-SLAM3.
    # ------------------------------------------------------------------
    sysh = p("include", "System.h")
    patch(
        sysh,
        "    float GetImageScale();",
        "    float GetImageScale();\n"
        "\n"
        "    // ---- Added for Novex -------------------------------------\n"
        "    // The GUI renders the map itself instead of using Pangolin,\n"
        "    // so it needs read access to the Atlas and the Tracker.\n"
        "    Atlas* GetAtlas() { return mpAtlas; }\n"
        "    Tracking* GetTracker() { return mpTracker; }\n"
        "    // ----------------------------------------------------------\n",
        "expose GetAtlas()/GetTracker() for the Novex binding",
    )

    # ------------------------------------------------------------------
    # 7. Upstream bug: Camera.type "Rectified" + STEREO segfaults
    #
    # readCamera2() only allocates a camera model for the PinHole and
    # KannalaBrandt types. For "Rectified" it does nothing, because a
    # rectified pair shares one set of intrinsics plus a baseline.
    #
    # But Settings' operator<< dereferences originalCalib2_
    # unconditionally whenever the sensor is STEREO, and the Settings
    # constructor never initialises those pointers, so they hold
    # indeterminate values. System's constructor prints the settings,
    # so ORB-SLAM3 crashes on start-up for every rectified stereo
    # configuration - including upstream's own KITTI example.
    #
    # Two changes: initialise the pointers, then guard the print.
    # ------------------------------------------------------------------
    settings_cc = p("src", "Settings.cc")

    patch(
        settings_cc,
        "    Settings::Settings(const std::string &configFile, const int& sensor) :\n"
        "    bNeedToUndistort_(false), bNeedToRectify_(false), bNeedToResize1_(false), bNeedToResize2_(false) {",
        "    Settings::Settings(const std::string &configFile, const int& sensor) :\n"
        "    calibration1_(nullptr), calibration2_(nullptr),\n"
        "    originalCalib1_(nullptr), originalCalib2_(nullptr),\n"
        "    bNeedToUndistort_(false), bNeedToRectify_(false), bNeedToResize1_(false), bNeedToResize2_(false) {",
        "initialise the camera model pointers (they were indeterminate)",
    )

    patch(
        settings_cc,
        "            for(size_t i = 0; i < settings.originalCalib2_->size(); i++){",
        "            for(size_t i = 0; settings.originalCalib2_ && i < settings.originalCalib2_->size(); i++){",
        "do not dereference a null camera 2 model (Rectified stereo)",
    )

    # ------------------------------------------------------------------
    # 8. Upstream bug: fisheye stereo uses the WRONG distortion for the
    #    right camera.
    #
    # Settings::readCamera2() reads camera 2's intrinsics from
    # Camera2.fx/fy/cx/cy, but then reads its Kannala-Brandt distortion
    # from Camera1.k1..k4 - a copy-paste slip. The right lens is
    # therefore modelled with the LEFT lens's distortion, which biases
    # every right-image projection and quietly degrades stereo
    # matching. It matters most exactly where fisheye stereo is worth
    # using: wide lenses, where the two lenses differ measurably.
    # ------------------------------------------------------------------
    patch(
        settings_cc,
        """            float k0 = readParameter<float>(fSettings,"Camera1.k1",found);
            float k1 = readParameter<float>(fSettings,"Camera1.k2",found);
            float k2 = readParameter<float>(fSettings,"Camera1.k3",found);
            float k3 = readParameter<float>(fSettings,"Camera1.k4",found);


            vCalibration = {fx,fy,cx,cy,k0,k1,k2,k3};

            calibration2_ = new KannalaBrandt8(vCalibration);""",
        """            float k0 = readParameter<float>(fSettings,"Camera2.k1",found);
            float k1 = readParameter<float>(fSettings,"Camera2.k2",found);
            float k2 = readParameter<float>(fSettings,"Camera2.k3",found);
            float k3 = readParameter<float>(fSettings,"Camera2.k4",found);


            vCalibration = {fx,fy,cx,cy,k0,k1,k2,k3};

            calibration2_ = new KannalaBrandt8(vCalibration);""",
        "right camera must use Camera2.k1..k4, not Camera1's",
    )

    # ------------------------------------------------------------------
    # 9. Upstream bug: fisheye relocalisation reads out of bounds.
    #
    # In the KannalaBrandt8 (fisheye) path a Frame holds BOTH images'
    # keypoints: N = Nleft + Nright, with mvKeys holding the left set
    # and mvKeysRight the right. mvKeysUn, however, is only ever
    # assigned from mvKeys, so it has Nleft entries.
    #
    # GetFeaturesInArea searches both grids and can therefore return an
    # index >= Nleft. Most of ORBmatcher accounts for this with the
    # idiom at line ~1781:
    #
    #   (Nleft == -1) ? mvKeysUn[i] : (i < Nleft) ? mvKeys[i]
    #                                             : mvKeysRight[i-Nleft]
    #
    # but the relocalisation overload of SearchByProjection was never
    # updated and indexes mvKeysUn directly. That is an out-of-bounds
    # read, and it is exactly where this crashed:
    #
    #   ORBmatcher::SearchByProjection(Frame&, KeyFrame*, set<MapPoint*>...)
    #     <- Tracking::Relocalization() <- Track() <- GrabImageStereo
    #
    # Reproduced roughly one run in three with fisheye stereo, always
    # after tracking was lost and relocalisation began. Harmless in the
    # rectified path (Nleft == -1), fatal in the fisheye one.
    # ------------------------------------------------------------------
    orbmatcher = p("src", "ORBmatcher.cc")
    patch(
        orbmatcher,
        "                            float rot = pKF->mvKeysUn[i].angle-CurrentFrame.mvKeysUn[bestIdx2].angle;",
        "                            // NOVEX: fisheye-safe indexing. In the\n"
        "                            // KannalaBrandt8 path bestIdx2 may exceed\n"
        "                            // Nleft, while mvKeysUn only has Nleft\n"
        "                            // entries. Same idiom as line ~1781.\n"
        "                            const cv::KeyPoint &kpKF = (pKF->NLeft == -1) ? pKF->mvKeysUn[i]\n"
        "                                                     : (i < pKF->NLeft) ? pKF->mvKeys[i]\n"
        "                                                                        : pKF->mvKeysRight[i - pKF->NLeft];\n"
        "                            const cv::KeyPoint &kpCF = (CurrentFrame.Nleft == -1) ? CurrentFrame.mvKeysUn[bestIdx2]\n"
        "                                                     : (bestIdx2 < CurrentFrame.Nleft) ? CurrentFrame.mvKeys[bestIdx2]\n"
        "                                                                                       : CurrentFrame.mvKeysRight[bestIdx2 - CurrentFrame.Nleft];\n"
        "                            float rot = kpKF.angle-kpCF.angle;",
        "fisheye-safe keypoint indexing in relocalisation",
    )

    # ------------------------------------------------------------------
    # 10. gcc 13 header hygiene
    #
    # gcc 13 no longer transitively includes <cstdint> from other
    # standard headers, so files using uint*_t fail to compile.
    # ------------------------------------------------------------------
    for rel in [
        ("Thirdparty", "DBoW2", "DBoW2", "FORB.h"),
        ("Thirdparty", "DBoW2", "DBoW2", "BowVector.h"),
        ("Thirdparty", "DBoW2", "DBoW2", "FeatureVector.h"),
        ("include", "ORBextractor.h"),
        ("include", "SerializationUtils.h"),
    ]:
        f = p(*rel)
        if not os.path.exists(f):
            continue
        with open(f) as fh:
            t = fh.read()
        if "#include <cstdint>" in t:
            SKIPPED.append(f"{rel[-1]}: <cstdint> already included")
            continue
        # insert after the include guard's first #define, else at top
        m = re.search(r"^#define .*$", t, re.M)
        if m:
            t = t[: m.end()] + "\n\n#include <cstdint>   // gcc 13: uint*_t no longer transitively included" + t[m.end():]
        else:
            t = "#include <cstdint>\n" + t
        with open(f, "w") as fh:
            fh.write(t)
        APPLIED.append(f"{rel[-1]}: added <cstdint> for gcc 13")

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print("=" * 62)
    print(" ORB-SLAM3 PATCHES")
    print("=" * 62)
    for line in APPLIED:
        print("  APPLIED  " + line)
    for line in SKIPPED:
        print("  skipped  " + line)
    print("=" * 62)

    missing = [s for s in SKIPPED if s.startswith("!!")]
    if missing:
        print("WARNING: some patches did not match. Upstream may have changed.")
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
