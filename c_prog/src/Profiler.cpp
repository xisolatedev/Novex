#include "Profiler.hpp"

#include <cstdio>

namespace novex
{

const char* stageName(Stage stage)
{
    switch (stage)
    {
        case Stage::Capture:    return "capture";
        case Stage::Decode:     return "decode";
        case Stage::Preprocess: return "preprocess";
        case Stage::Detect:     return "detect";
        case Stage::Track:      return "track";
        case Stage::Stereo:     return "stereo";
        case Stage::Motion:     return "motion";
        case Stage::State:      return "state";
        case Stage::Imu:        return "imu";
        case Stage::PointCloud: return "pointcloud";
        case Stage::Floor:      return "floor";
        case Stage::Total:      return "total";
        default:                return "?";
    }
}

void Profiler::begin(Stage stage)
{
    startTime[static_cast<int>(stage)] = monotonicSeconds();
}

void Profiler::end(Stage stage)
{
    const int index = static_cast<int>(stage);

    const double elapsed =
        monotonicSeconds() - startTime[index];

    samples[index][cursor[index]] = elapsed;

    cursor[index] = (cursor[index] + 1) % Window;

    if (count[index] < Window)
    {
        ++count[index];
    }
}

void Profiler::endWith(Stage stage, double seconds)
{
    const int index = static_cast<int>(stage);

    samples[index][cursor[index]] = seconds;

    cursor[index] = (cursor[index] + 1) % Window;

    if (count[index] < Window)
    {
        ++count[index];
    }
}

void Profiler::noteCapture(double cameraTimestamp)
{
    if (lastCaptureStamp > 0.0)
    {
        const double dt = cameraTimestamp - lastCaptureStamp;

        if (dt > 1e-6)
        {
            // Exponential smoothing rather than a window, so the
            // reported rate reacts to a stall within a few frames.
            const double instant = 1.0 / dt;

            captureRate = (captureRate <= 0.0)
                ? instant
                : captureRate * 0.9 + instant * 0.1;
        }
    }

    lastCaptureStamp = cameraTimestamp;
}

void Profiler::noteProcessed(double now)
{
    if (lastProcessStamp > 0.0)
    {
        const double dt = now - lastProcessStamp;

        if (dt > 1e-6)
        {
            const double instant = 1.0 / dt;

            processRate = (processRate <= 0.0)
                ? instant
                : processRate * 0.9 + instant * 0.1;
        }
    }

    lastProcessStamp = now;
}

double Profiler::last(Stage stage) const
{
    const int index = static_cast<int>(stage);

    if (count[index] == 0)
    {
        return 0.0;
    }

    const int previous =
        (cursor[index] + Window - 1) % Window;

    return samples[index][previous];
}

double Profiler::average(Stage stage) const
{
    const int index = static_cast<int>(stage);

    if (count[index] == 0)
    {
        return 0.0;
    }

    double sum = 0.0;

    for (int i = 0; i < count[index]; ++i)
    {
        sum += samples[index][i];
    }

    return sum / count[index];
}

double Profiler::captureFPS() const
{
    return captureRate;
}

double Profiler::processingFPS() const
{
    return processRate;
}

double Profiler::latency() const
{
    return latencySeconds;
}

void Profiler::noteLatency(double seconds)
{
    latencySeconds = (latencySeconds <= 0.0)
        ? seconds
        : latencySeconds * 0.9 + seconds * 0.1;
}

void Profiler::formatSummary(char* buffer, size_t size) const
{
    snprintf(
        buffer,
        size,
        "cap %.1f/proc %.1f fps  lat %.1f ms | "
        "capture %.1f (decode %.1f)  pre %.1f  detect %.1f  "
        "track %.1f  stereo %.1f  motion %.1f  state %.1f  "
        "imu %.1f  points %.2f  total %.1f ms",
        captureFPS(),
        processingFPS(),
        latency() * 1e3,
        average(Stage::Capture)    * 1e3,
        average(Stage::Decode)     * 1e3,
        average(Stage::Preprocess) * 1e3,
        average(Stage::Detect)     * 1e3,
        average(Stage::Track)      * 1e3,
        average(Stage::Stereo)     * 1e3,
        average(Stage::Motion)     * 1e3,
        average(Stage::State)      * 1e3,
        average(Stage::Imu)        * 1e3,
        average(Stage::PointCloud) * 1e3,
        average(Stage::Total)      * 1e3
    );
}

} // namespace novex
