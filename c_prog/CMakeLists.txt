cmake_minimum_required(VERSION 3.16)

project(NovexVIO LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE)
    # Release by default. A Debug build of this pipeline is roughly an
    # order of magnitude slower, which on a Pi Zero 2 W is the
    # difference between running and not.
    set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

# -----------------------------------------------------------------
# Dependencies
#
# OpenCV and Eigen only. Every candidate beyond these was rejected:
# a YAML library (the two files we read use a subset small enough to
# parse in 200 lines), a JSON library (we emit one flat object with
# snprintf), and a logging library.
# -----------------------------------------------------------------
find_package(OpenCV REQUIRED
    COMPONENTS core imgproc imgcodecs videoio calib3d video)

# highgui is only needed for GUI mode. Its absence is not fatal.
find_package(OpenCV QUIET COMPONENTS highgui)

find_package(Eigen3 3.3 REQUIRED NO_MODULE)

find_package(Threads REQUIRED)

# -----------------------------------------------------------------
# Optimisation
#
# The deployment target is an ARM Cortex-A53. -O2 plus the vectoriser
# lets GCC emit NEON for the pixel loops on its own; A53 has NEON
# unconditionally as part of AArch64, so no -mfpu flag is needed or
# wanted. Nothing here assumes hardware the target may not have.
# -----------------------------------------------------------------
set(NOVEX_FLAGS -O2 -ffast-math -fno-finite-math-only)

include(CheckCXXCompilerFlag)

check_cxx_compiler_flag(-ftree-vectorize NOVEX_HAS_VECTORIZE)

if(NOVEX_HAS_VECTORIZE)
    list(APPEND NOVEX_FLAGS -ftree-vectorize)
endif()

option(NOVEX_NATIVE_ARCH
    "Tune for the building machine. Leave OFF when cross-building or \
producing a binary to copy to another board." OFF)

if(NOVEX_NATIVE_ARCH)
    check_cxx_compiler_flag(-mcpu=native NOVEX_HAS_MCPU_NATIVE)

    if(NOVEX_HAS_MCPU_NATIVE)
        list(APPEND NOVEX_FLAGS -mcpu=native)
    else()
        check_cxx_compiler_flag(-march=native NOVEX_HAS_MARCH_NATIVE)

        if(NOVEX_HAS_MARCH_NATIVE)
            list(APPEND NOVEX_FLAGS -march=native)
        endif()
    endif()
endif()

# -----------------------------------------------------------------
# Core library
#
# The pipeline is a library so that the daemon, the GUI and the test
# suite all link the same code. Gui.cpp is the only file that touches
# highgui, and nothing in the core includes it.
# -----------------------------------------------------------------
set(NOVEX_CORE_SOURCES
    src/Log.cpp
    src/Profiler.cpp
    src/Yaml.cpp
    src/VIOConfig.cpp
    src/CommandQueue.cpp
    src/DebugStatistics.cpp
    src/DebugReporter.cpp
    src/StereoCalibration.cpp
    src/Camera.cpp
    src/FeatureTracker.cpp
    src/StereoMatcher.cpp
    src/MotionEstimator.cpp
    src/Diagnostics.cpp
    src/PointCloud.cpp
    src/FloorEstimator.cpp
    src/IMU.cpp
    src/StateEstimator.cpp
    src/VIO.cpp
    src/StateServer.cpp
    src/WebServer.cpp
)

add_library(novex-core STATIC ${NOVEX_CORE_SOURCES})

target_include_directories(novex-core
    PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(novex-core
    PUBLIC
    opencv_core
    opencv_imgproc
    opencv_imgcodecs
    opencv_videoio
    opencv_calib3d
    opencv_video
    Eigen3::Eigen
    Threads::Threads
)

target_compile_options(novex-core PRIVATE ${NOVEX_FLAGS})

target_compile_options(novex-core PRIVATE
    -Wall -Wextra -Wno-unused-parameter)

# -----------------------------------------------------------------
# GUI (development only)
# -----------------------------------------------------------------
add_library(novex-gui STATIC src/Gui.cpp)

target_link_libraries(novex-gui PUBLIC novex-core)

if(TARGET opencv_highgui)
    target_link_libraries(novex-gui PUBLIC opencv_highgui)
else()
    message(WARNING
        "OpenCV highgui was not found. novex-vio will build and run in "
        "daemon mode; --mode gui will report that it cannot open a "
        "window.")
endif()

target_compile_options(novex-gui PRIVATE ${NOVEX_FLAGS})

# -----------------------------------------------------------------
# Executables
# -----------------------------------------------------------------
add_executable(novex-vio src/main.cpp)

target_link_libraries(novex-vio PRIVATE novex-core novex-gui)

target_compile_options(novex-vio PRIVATE ${NOVEX_FLAGS})

# Example IPC client. Depends on libc alone, on purpose.
add_executable(novex-state tools/novex_state_client.cpp)

# Geometry audit: verifies the calibration transform and the stereo /
# motion maths against synthetic data with known ground truth.
add_executable(novex-geometry-audit tools/geometry_audit.cpp)

target_link_libraries(novex-geometry-audit PRIVATE novex-core)

target_compile_options(novex-geometry-audit PRIVATE ${NOVEX_FLAGS})

# Record raw stereo frames, and replay them through the real pipeline,
# so estimator changes can be compared on identical input.
add_executable(novex-record tools/novex_record.cpp)
target_link_libraries(novex-record PRIVATE novex-core)
target_compile_options(novex-record PRIVATE ${NOVEX_FLAGS})

add_executable(novex-replay tools/novex_replay.cpp)
target_link_libraries(novex-replay PRIVATE novex-core)
target_compile_options(novex-replay PRIVATE ${NOVEX_FLAGS})

# Floor / ground estimator: synthetic scenes with known ground truth,
# plus a benchmark of the three cost paths.
add_executable(novex-floor-test tools/floor_test.cpp)
target_link_libraries(novex-floor-test PRIVATE novex-core)
target_compile_options(novex-floor-test PRIVATE ${NOVEX_FLAGS})

add_executable(novex-vio-test tests/test_novex.cpp)

target_link_libraries(novex-vio-test PRIVATE novex-core novex-gui)

target_compile_options(novex-vio-test PRIVATE ${NOVEX_FLAGS})

enable_testing()

add_test(NAME novex-validation COMMAND novex-vio-test)

add_test(NAME novex-floor COMMAND novex-floor-test)

set_tests_properties(novex-validation novex-floor PROPERTIES
    WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

# -----------------------------------------------------------------
# Install
# -----------------------------------------------------------------
install(TARGETS novex-vio novex-state RUNTIME DESTINATION bin)

install(FILES
    config/novex_vio.yaml
    config/stereo_calibration.yaml
    DESTINATION share/novex-vio/config)

message(STATUS "Novex VIO")
message(STATUS "  build type : ${CMAKE_BUILD_TYPE}")
message(STATUS "  OpenCV     : ${OpenCV_VERSION}")
message(STATUS "  flags      : ${NOVEX_FLAGS}")
