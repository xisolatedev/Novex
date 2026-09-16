#pragma once

#include "VIOConfig.hpp"

#include <Eigen/Core>

#include <atomic>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace novex
{

struct IMUSample
{
    // CLOCK_MONOTONIC seconds - the same clock the camera timestamps
    // use, so no offset estimation is needed between the two.
    double timestamp = 0.0;

    Eigen::Vector3d acceleration = Eigen::Vector3d::Zero();  // m/s^2
    Eigen::Vector3d gyroscope = Eigen::Vector3d::Zero();     // rad/s
};

// A source of IMU samples. One implementation talks to a real device;
// the other exists so the rest of the system has something to hold
// when there is no IMU.
//
// No implementation ever synthesises a sample. An unavailable IMU
// produces nothing at all, and the pipeline runs as pure stereo visual
// odometry.
class IMUBackend
{
public:

    virtual ~IMUBackend() = default;

    virtual bool open() = 0;
    virtual void close() = 0;

    // Reads one sample. Returns false if none is available; the caller
    // treats that as a transient condition, not an error.
    virtual bool read(IMUSample& sample) = 0;

    virtual const char* name() const = 0;

    const std::string& lastError() const { return errorText; }

protected:

    std::string errorText;
};

class IMU
{
public:

    struct Health
    {
        bool enabled = false;
        bool available = false;
        bool running = false;

        uint64_t samplesRead = 0;
        uint64_t samplesOverwritten = 0;
        uint64_t readFailures = 0;

        double lastSampleTime = 0.0;
        double measuredRateHz = 0.0;

        std::string backend = "none";
        std::string detail;
    };

    explicit IMU(const VIOConfig& config);
    ~IMU();

    IMU(const IMU&) = delete;
    IMU& operator=(const IMU&) = delete;

    // Returns false only if the IMU was requested and could not be
    // brought up. A disabled IMU starts successfully and does nothing,
    // which is what lets the caller treat the IMU as genuinely
    // optional with no special cases.
    bool start();
    void stop();

    bool isEnabled() const { return enabled; }
    bool isRunning() const { return running.load(); }

    // Copies every buffered sample with begin < timestamp <= end into
    // `out`, oldest first. Returns the number copied. Samples older
    // than `begin` are discarded from the buffer.
    size_t samplesBetween(double begin,
                          double end,
                          std::vector<IMUSample>& out);

    Health health() const;

private:

    void samplingLoop();

    void push(const IMUSample& sample);

    const VIOConfig& config;

    bool enabled = false;

    std::unique_ptr<IMUBackend> backend;

    std::thread worker;
    std::atomic<bool> running{false};
    std::atomic<bool> stopRequested{false};

    // Fixed-capacity ring buffer, sized once at start-up. An IMU that
    // outruns the consumer must overwrite its oldest data rather than
    // grow without bound on a 512 MB machine.
    mutable std::mutex bufferMutex;
    std::vector<IMUSample> buffer;
    size_t head = 0;
    size_t used = 0;

    mutable std::mutex healthMutex;
    Health status;
};

// Creates the backend named in the config. Returns nullptr for
// "none" or an unrecognised name.
std::unique_ptr<IMUBackend> createIMUBackend(const VIOConfig& config);

} // namespace novex
