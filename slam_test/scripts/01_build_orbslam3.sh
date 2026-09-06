#!/usr/bin/env bash
# ============================================================
# NOVEX - build ORB-SLAM3 and its dependencies
# ============================================================
# Run as your NORMAL USER (no sudo). Everything is built inside
# slam_test/third_party/ and installed into
# slam_test/third_party/install - nothing touches the system.
#
#   bash scripts/01_build_orbslam3.sh
#
# Expect 20-45 minutes on a 4-core machine.
# ============================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TP="$HERE/third_party"
PREFIX="$TP/install"
ORB="$TP/ORB_SLAM3"
PANGO="$TP/Pangolin"

# ------------------------------------------------------------
# Parallelism
#
# ORB-SLAM3 and g2o have translation units that need well over
# 1 GB of RAM each. Over-parallelising on a low-memory machine
# makes the OOM killer stop the build halfway through, which
# looks like a random compiler crash. So jobs are derived from
# free memory, not just core count.
# ------------------------------------------------------------
CORES="$(nproc)"
MEM_AVAIL_GB="$(awk '/MemAvailable/ {printf "%d", $2/1024/1024}' /proc/meminfo)"
JOBS="$CORES"
MEM_JOBS=$(( MEM_AVAIL_GB > 0 ? MEM_AVAIL_GB : 1 ))
if [ "$MEM_JOBS" -lt "$JOBS" ]; then JOBS="$MEM_JOBS"; fi
if [ "$JOBS" -lt 1 ]; then JOBS=1; fi
export MAKEFLAGS="-j${JOBS}"

echo "=============================================="
echo " NOVEX - building ORB-SLAM3"
echo "=============================================="
echo "cores          : $CORES"
echo "available RAM  : ${MEM_AVAIL_GB} GB"
echo "parallel jobs  : $JOBS"
echo "install prefix : $PREFIX"
echo

# ------------------------------------------------------------
# Dependency check - fail loudly and specifically
# ------------------------------------------------------------
missing=0
check_pkg() {
    if ! pkg-config --exists "$1" 2>/dev/null; then
        echo "MISSING: $1  ($2)"
        missing=1
    else
        echo "found  : $1 $(pkg-config --modversion "$1")"
    fi
}
check_hdr() {
    if [ ! -e "$1" ]; then
        echo "MISSING: $1  ($2)"
        missing=1
    else
        echo "found  : $1"
    fi
}

command -v cmake >/dev/null || { echo "MISSING: cmake"; missing=1; }
command -v g++   >/dev/null || { echo "MISSING: g++";   missing=1; }
check_pkg opencv4 "libopencv-dev"
check_hdr /usr/include/eigen3/Eigen/Core "libeigen3-dev"
check_hdr /usr/include/boost/serialization/serialization.hpp "libboost-serialization-dev"
check_hdr /usr/include/openssl/ssl.h "libssl-dev"
check_hdr /usr/include/GL/glew.h "libglew-dev"

if [ "$missing" -ne 0 ]; then
    echo
    echo "=============================================="
    echo " DEPENDENCIES MISSING"
    echo "=============================================="
    echo "Run this first:"
    echo "    sudo bash scripts/00_install_system_deps.sh"
    exit 1
fi
echo

# ------------------------------------------------------------
# 0. Patch ORB-SLAM3 for the modern toolchain
# ------------------------------------------------------------
python3 "$HERE/scripts/patch_orbslam3.py" "$ORB"

# ------------------------------------------------------------
# 1. Free the ~1.3 GB of dataset timestamp files and prebuilt
#    example data we will never use. Purely a disk saving.
# ------------------------------------------------------------
if [ -d "$ORB/Examples_old" ]; then
    echo "Removing ORB_SLAM3/Examples_old (unused, ~700 MB)..."
    rm -rf "$ORB/Examples_old"
fi
find "$ORB/Examples" -type d \( -name "TUM_IMU" -o -name "EuRoC_TimeStamps" -o -name "TUM_TimeStamps" \) \
     -exec rm -rf {} + 2>/dev/null || true

# ------------------------------------------------------------
# 2. Pangolin
#
# ORB-SLAM3's library includes Viewer.cc / MapDrawer.cc, which
# link against Pangolin, so it is a hard build dependency even
# though the Novex GUI runs with the viewer disabled.
# ------------------------------------------------------------
if [ -f "$PREFIX/lib/cmake/Pangolin/PangolinConfig.cmake" ]; then
    echo "Pangolin already installed in prefix, skipping."
else
    echo "----------------------------------------------"
    echo " Building Pangolin"
    echo "----------------------------------------------"
    # CMAKE_INSTALL_RPATH=$ORIGIN is essential.
    #
    # Pangolin is split into a dozen libraries that depend on each
    # other (libpango_display needs libpango_windowing, and so on).
    # Since it is installed into a local prefix rather than a system
    # directory, those siblings are not on the loader's search path.
    #
    # A parent's RUNPATH is NOT inherited by transitive dependencies,
    # so libORB_SLAM3.so knowing where the prefix is does not help the
    # loader resolve libpango_display's own dependencies. $ORIGIN makes
    # each library look next to itself, which is both correct and
    # relocatable - the whole prefix can be moved and still work.
    cmake -S "$PANGO" -B "$PANGO/build" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX="$PREFIX" \
        -DCMAKE_INSTALL_RPATH='$ORIGIN' \
        -DCMAKE_INSTALL_RPATH_USE_LINK_PATH=ON \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_TESTS=OFF \
        -DBUILD_TOOLS=OFF \
        -DBUILD_PANGOLIN_PYTHON=OFF
    cmake --build "$PANGO/build" -j"$JOBS"
    cmake --install "$PANGO/build"
fi

# ------------------------------------------------------------
# 3. ORB vocabulary
#
# ORB-SLAM3 needs the ~145 MB DBoW2 vocabulary at runtime. It
# ships compressed; loading the .txt takes ~10-20 s at startup.
# ------------------------------------------------------------
if [ ! -f "$ORB/Vocabulary/ORBvoc.txt" ]; then
    echo "Uncompressing ORB vocabulary..."
    tar -xf "$ORB/Vocabulary/ORBvoc.txt.tar.gz" -C "$ORB/Vocabulary"
fi
echo "Vocabulary: $(du -h "$ORB/Vocabulary/ORBvoc.txt" | cut -f1)"

# ------------------------------------------------------------
# 4. DBoW2
#
# Built separately because ORB-SLAM3 links it by hard-coded
# path (Thirdparty/DBoW2/lib/libDBoW2.so) rather than as a
# CMake subproject.
# ------------------------------------------------------------
echo "----------------------------------------------"
echo " Building DBoW2"
echo "----------------------------------------------"
cmake -S "$ORB/Thirdparty/DBoW2" -B "$ORB/Thirdparty/DBoW2/build" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build "$ORB/Thirdparty/DBoW2/build" -j"$JOBS"

# ------------------------------------------------------------
# 5. ORB-SLAM3 itself (g2o is pulled in via add_subdirectory)
#
# Sophus is header-only here and is included straight from
# Thirdparty/Sophus, so upstream's build.sh step for it is
# skipped - it only built Sophus' own tests.
# ------------------------------------------------------------
echo "----------------------------------------------"
echo " Building ORB-SLAM3 (library only)"
echo "----------------------------------------------"
cmake -S "$ORB" -B "$ORB/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH="$PREFIX" \
    -DCMAKE_CXX_STANDARD=14
cmake --build "$ORB/build" -j"$JOBS"

echo
echo "=============================================="
echo " ORB-SLAM3 BUILD COMPLETE"
echo "=============================================="
ls -lh "$ORB/lib/"*.so
echo
echo "Next:"
echo "    bash scripts/02_build_binding.sh"
