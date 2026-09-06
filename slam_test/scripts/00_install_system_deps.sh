#!/usr/bin/env bash
# ============================================================
# NOVEX ORB-SLAM3 TEST - system dependency installer
# ============================================================
# This is the ONLY step that needs root. Everything else
# (cloning, building, running) happens in this project folder
# as your normal user.
#
#   sudo bash scripts/00_install_system_deps.sh
# ============================================================
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run this with sudo:"
    echo "    sudo bash scripts/00_install_system_deps.sh"
    exit 1
fi

echo "=============================================="
echo " NOVEX - installing ORB-SLAM3 build dependencies"
echo "=============================================="

apt-get update

# ------------------------------------------------------------
# Toolchain
#   build-essential : g++/make, ORB-SLAM3 is C++14
#   cmake, git      : build system + fetching sources
#   pkg-config      : how CMake locates OpenCV/Eigen
# ------------------------------------------------------------
TOOLCHAIN="build-essential cmake git pkg-config"

# ------------------------------------------------------------
# ORB-SLAM3 core dependencies
#   libopencv-dev             : image handling, ORB extraction, calibration
#   libeigen3-dev             : all linear algebra (header only)
#   libboost-serialization-dev: ORB-SLAM3 map save/load
#   libssl-dev                : required by ORB-SLAM3's CMake (map hashing)
# ------------------------------------------------------------
ORBSLAM="libopencv-dev libeigen3-dev libboost-serialization-dev libssl-dev"

# ------------------------------------------------------------
# Pangolin dependencies
# ORB-SLAM3 will not compile without Pangolin because its
# Viewer/MapDrawer classes are part of the library. We build
# Pangolin, but the Novex GUI creates the System with
# use_viewer=false, so Pangolin never opens a window unless
# you explicitly ask for it with --orbslam-viewer.
#   libglew-dev / libepoxy-dev : OpenGL loaders Pangolin uses
#   mesa/GL + X11/Wayland dev  : window + context creation
# ------------------------------------------------------------
PANGOLIN="libglew-dev libepoxy-dev libgl1-mesa-dev libegl1-mesa-dev \
          libwayland-dev libxkbcommon-dev wayland-protocols \
          libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev"

# ------------------------------------------------------------
# Python side
#   python3-dev : headers for the pybind11 extension module
#   python3-venv: the project uses a virtualenv
# ------------------------------------------------------------
PYTHON="python3-dev python3-venv"

# ------------------------------------------------------------
# Camera introspection
#   v4l-utils : v4l2-ctl, used to print the ACTUAL negotiated
#               camera mode instead of trusting the request
# ------------------------------------------------------------
CAMERA="v4l-utils"

apt-get install -y $TOOLCHAIN $ORBSLAM $PANGOLIN $PYTHON $CAMERA

echo
echo "=============================================="
echo " DONE"
echo "=============================================="
echo "OpenCV : $(pkg-config --modversion opencv4 2>/dev/null || echo '??')"
echo "Eigen  : $(pkg-config --modversion eigen3 2>/dev/null || echo '??')"
echo "cmake  : $(cmake --version | head -1)"
echo "g++    : $(g++ --version | head -1)"
echo
echo "Next (as your normal user, NOT root):"
echo "    bash scripts/01_build_orbslam3.sh"
