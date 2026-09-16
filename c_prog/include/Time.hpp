#pragma once

#include <time.h>

namespace novex
{

// Every timestamp in Novex VIO is CLOCK_MONOTONIC seconds.
//
// This is not an arbitrary choice. The V4L2 buffer timestamps the
// camera gives us (exposed by OpenCV as CAP_PROP_POS_MSEC) are on
// CLOCK_MONOTONIC, and so are the Linux IIO timestamps an IMU would
// deliver. Using the same clock everywhere means camera and IMU
// samples can be compared directly, with no offset estimation and no
// wall-clock jumps from NTP.
inline double monotonicSeconds()
{
    struct timespec ts;

    clock_gettime(CLOCK_MONOTONIC, &ts);

    return static_cast<double>(ts.tv_sec) +
           static_cast<double>(ts.tv_nsec) * 1e-9;
}

} // namespace novex
