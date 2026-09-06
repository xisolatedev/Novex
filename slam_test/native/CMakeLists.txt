# ============================================================
# NOVEX - pybind11 extension module wrapping ORB-SLAM3
# ============================================================
cmake_minimum_required(VERSION 3.16)
project(novex_orbslam3 LANGUAGES CXX)

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# ------------------------------------------------------------
# IMPORTANT: match ORB-SLAM3's own release flags.
#
# ORB-SLAM3 is compiled with -O3 -march=native. Eigen changes
# its vectorisation and alignment behaviour with the target ISA,
# so a module compiled with different flags that passes Eigen
# types across the boundary can crash at runtime. Keep these
# identical to ORB_SLAM3/CMakeLists.txt.
# ------------------------------------------------------------
set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} -O3 -march=native")

set(ORB_SLAM3_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../third_party/ORB_SLAM3"
    CACHE PATH "Path to the patched ORB-SLAM3 source tree")

if(NOT EXISTS "${ORB_SLAM3_DIR}/lib/libORB_SLAM3.so")
    message(FATAL_ERROR
        "libORB_SLAM3.so not found in ${ORB_SLAM3_DIR}/lib.\n"
        "Build ORB-SLAM3 first:  bash scripts/01_build_orbslam3.sh")
endif()

find_package(OpenCV 4.4 REQUIRED)
find_package(Eigen3 3.1.0 REQUIRED)
find_package(Pangolin REQUIRED)
find_package(pybind11 REQUIRED)

pybind11_add_module(novex_orbslam3 orbslam3_binding.cpp)

target_include_directories(novex_orbslam3 PRIVATE
    ${ORB_SLAM3_DIR}
    ${ORB_SLAM3_DIR}/include
    ${ORB_SLAM3_DIR}/include/CameraModels
    ${ORB_SLAM3_DIR}/Thirdparty/Sophus
    ${EIGEN3_INCLUDE_DIR}
    ${OpenCV_INCLUDE_DIRS}
    ${Pangolin_INCLUDE_DIRS}
)

target_link_libraries(novex_orbslam3 PRIVATE
    ${ORB_SLAM3_DIR}/lib/libORB_SLAM3.so
    ${ORB_SLAM3_DIR}/Thirdparty/DBoW2/lib/libDBoW2.so
    ${ORB_SLAM3_DIR}/Thirdparty/g2o/lib/libg2o.so
    ${OpenCV_LIBS}
    ${Pangolin_LIBRARIES}
)

# ------------------------------------------------------------
# Bake the ORB-SLAM3 library locations into the module so it can
# be imported without the caller having to set LD_LIBRARY_PATH.
# ------------------------------------------------------------
set_target_properties(novex_orbslam3 PROPERTIES
    BUILD_RPATH "${ORB_SLAM3_DIR}/lib;${ORB_SLAM3_DIR}/Thirdparty/DBoW2/lib;${ORB_SLAM3_DIR}/Thirdparty/g2o/lib"
    INSTALL_RPATH "${ORB_SLAM3_DIR}/lib;${ORB_SLAM3_DIR}/Thirdparty/DBoW2/lib;${ORB_SLAM3_DIR}/Thirdparty/g2o/lib"
)
