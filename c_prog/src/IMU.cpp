#include "IMU.hpp"

#include "Log.hpp"
#include "Time.hpp"

#include <dirent.h>
#include <cerrno>
#include <cstring>
#include <fstream>
#include <sstream>

namespace novex
{

namespace
{

bool readSysfsDouble(const std::string& path, double& out)
{
    std::ifstream file(path);

    if (!file.is_open())
    {
        return false;
    }

    file >> out;

    return static_cast<bool>(file);
}

// Reads an IMU exposed through the Linux Industrial I/O subsystem.
//
// This is the interface a kernel driver presents for the usual
// MEMS parts (MPU6050, ICM20948, LSM6DSx and so on) once their driver
// is loaded, which on a Raspberry Pi means a device-tree overlay
// rather than any userspace protocol. Reading it means reading sysfs
// files, so there is nothing here specific to any one chip and no
// assumed serial protocol.
//
// This uses the simple polled interface (the *_raw attributes) rather
// than the triggered buffer interface. Polling is enough for the
// loosely coupled use the estimator makes of the IMU, and it avoids
// the device-specific trigger setup that the buffered path needs.
//
// STATUS: implemented but NOT tested against hardware - no IMU is
// present on the current bench setup. It is written to fail cleanly
// and report why, so that an absent or unexpected device disables the
// IMU rather than breaking the pipeline.
class IIOBackend : public IMUBackend
{
public:

    explicit IIOBackend(const VIOConfig& config)
        : configuredPath(config.imuDevicePath)
    {
    }

    const char* name() const override { return "iio"; }

    bool open() override
    {
        devicePath = configuredPath.empty()
            ? discoverDevice()
            : configuredPath;

        if (devicePath.empty())
        {
            errorText =
                "no Linux IIO device exposing both in_accel_*_raw and "
                "in_anglvel_*_raw was found under "
                "/sys/bus/iio/devices";

            return false;
        }

        // Scale factors convert the raw integers to SI units. IIO
        // reports acceleration in m/s^2 and angular velocity in rad/s
        // once the scale is applied, which is exactly what the
        // estimator wants.
        if (!readSysfsDouble(devicePath + "/in_accel_scale", accelScale))
        {
            errorText = devicePath + ": missing in_accel_scale";
            return false;
        }

        if (!readSysfsDouble(devicePath + "/in_anglvel_scale", gyroScale))
        {
            errorText = devicePath + ": missing in_anglvel_scale";
            return false;
        }

        const char* axes[3] = { "x", "y", "z" };

        for (int i = 0; i < 3; ++i)
        {
            accelFiles[i].open(
                devicePath + "/in_accel_" + axes[i] + "_raw"
            );

            gyroFiles[i].open(
                devicePath + "/in_anglvel_" + axes[i] + "_raw"
            );

            if (!accelFiles[i].is_open() || !gyroFiles[i].is_open())
            {
                errorText = devicePath + ": cannot open axis " +
                            axes[i];

                return false;
            }
        }

        return true;
    }

    void close() override
    {
        for (int i = 0; i < 3; ++i)
        {
            accelFiles[i].close();
            gyroFiles[i].close();
        }
    }

    bool read(IMUSample& sample) override
    {
        double raw[6];

        for (int i = 0; i < 3; ++i)
        {
            if (!rewindRead(accelFiles[i], raw[i]) ||
                !rewindRead(gyroFiles[i], raw[i + 3]))
            {
                return false;
            }
        }

        // The timestamp is taken after the reads rather than before,
        // because the sysfs reads themselves trigger the conversion on
        // a polled device. It is still the same clock the camera uses.
        sample.timestamp = monotonicSeconds();

        sample.acceleration = Eigen::Vector3d(
            raw[0] * accelScale,
            raw[1] * accelScale,
            raw[2] * accelScale
        );

        sample.gyroscope = Eigen::Vector3d(
            raw[3] * gyroScale,
            raw[4] * gyroScale,
            raw[5] * gyroScale
        );

        return true;
    }

    const std::string& path() const { return devicePath; }

private:

    static bool rewindRead(std::ifstream& file, double& out)
    {
        file.clear();
        file.seekg(0);

        file >> out;

        return static_cast<bool>(file);
    }

    static std::string discoverDevice()
    {
        DIR* directory = opendir("/sys/bus/iio/devices");

        if (directory == nullptr)
        {
            return "";
        }

        std::string found;

        while (const dirent* entry = readdir(directory))
        {
            const std::string entryName = entry->d_name;

            if (entryName.rfind("iio:device", 0) != 0)
            {
                continue;
            }

            const std::string candidate =
                std::string("/sys/bus/iio/devices/") + entryName;

            std::ifstream accel(candidate + "/in_accel_x_raw");
            std::ifstream gyro(candidate + "/in_anglvel_x_raw");

            if (accel.is_open() && gyro.is_open())
            {
                found = candidate;
                break;
            }
        }

        closedir(directory);

        return found;
    }

    std::string configuredPath;
    std::string devicePath;

    double accelScale = 1.0;
    double gyroScale = 1.0;

    std::ifstream accelFiles[3];
    std::ifstream gyroFiles[3];
};

} // namespace

std::unique_ptr<IMUBackend> createIMUBackend(const VIOConfig& config)
{
    if (config.imuBackend == "none" || config.imuBackend.empty())
    {
        return nullptr;
    }

    if (config.imuBackend == "iio")
    {
        return std::unique_ptr<IMUBackend>(new IIOBackend(config));
    }

    LOG_ERROR(
        "imu: unknown backend '%s' (known: none, iio)",
        config.imuBackend.c_str()
    );

    return nullptr;
}

IMU::IMU(const VIOConfig& config)
    : config(config)
{
    enabled = config.imuEnabled;

    status.enabled = enabled;
    status.backend = config.imuBackend;
}

IMU::~IMU()
{
    stop();
}

bool IMU::start()
{
    if (!enabled)
    {
        LOG_INFO(
            "imu: disabled; running as stereo visual odometry"
        );

        return true;
    }

    backend = createIMUBackend(config);

    if (!backend)
    {
        LOG_WARN(
            "imu: no usable backend for '%s'; continuing without an "
            "IMU",
            config.imuBackend.c_str()
        );

        enabled = false;

        std::lock_guard<std::mutex> lock(healthMutex);
        status.enabled = false;
        status.detail = "no backend";

        return true;
    }

    if (!backend->open())
    {
        // An absent IMU is a supported configuration, not a failure.
        // The system degrades to visual odometry and says so once.
        LOG_WARN(
            "imu: backend '%s' unavailable (%s); continuing as stereo "
            "visual odometry",
            backend->name(),
            backend->lastError().c_str()
        );

        {
            std::lock_guard<std::mutex> lock(healthMutex);
            status.available = false;
            status.detail = backend->lastError();
        }

        backend.reset();
        enabled = false;

        return true;
    }

    buffer.assign(
        static_cast<size_t>(std::max(64, config.imuBufferSize)),
        IMUSample()
    );

    head = 0;
    used = 0;

    {
        std::lock_guard<std::mutex> lock(healthMutex);
        status.available = true;
        status.detail = "ok";
    }

    stopRequested.store(false);
    running.store(true);

    // The IMU gets its own thread for a concrete reason: it must be
    // sampled at a rate unrelated to, and much higher than, the frame
    // rate, and it must keep sampling while the pipeline is busy with
    // a frame. Polling it from the vision loop would alias it to the
    // frame rate and lose exactly the high-rate motion the IMU is
    // there to provide.
    worker = std::thread(&IMU::samplingLoop, this);

    LOG_INFO(
        "imu: started, backend '%s' at ~%d Hz",
        backend->name(),
        config.imuRateHz
    );

    return true;
}

void IMU::stop()
{
    stopRequested.store(true);

    if (worker.joinable())
    {
        worker.join();
    }

    running.store(false);

    if (backend)
    {
        backend->close();
        backend.reset();
    }
}

void IMU::samplingLoop()
{
    const double period =
        1.0 / std::max(1, config.imuRateHz);

    double nextSampleTime = monotonicSeconds();

    double rateWindowStart = nextSampleTime;
    uint64_t rateWindowCount = 0;

    while (!stopRequested.load())
    {
        const double now = monotonicSeconds();

        if (now < nextSampleTime)
        {
            const double waitSeconds = nextSampleTime - now;

            struct timespec request;

            request.tv_sec =
                static_cast<time_t>(waitSeconds);

            request.tv_nsec = static_cast<long>(
                (waitSeconds - request.tv_sec) * 1e9
            );

            nanosleep(&request, nullptr);
            continue;
        }

        nextSampleTime += period;

        // If we have fallen far behind, resynchronise rather than
        // trying to catch up with a burst of reads.
        if (nextSampleTime < now - period)
        {
            nextSampleTime = now + period;
        }

        IMUSample sample;

        if (!backend->read(sample))
        {
            std::lock_guard<std::mutex> lock(healthMutex);
            ++status.readFailures;
            continue;
        }

        push(sample);

        ++rateWindowCount;

        const double elapsed = sample.timestamp - rateWindowStart;

        if (elapsed >= 1.0)
        {
            std::lock_guard<std::mutex> lock(healthMutex);

            status.measuredRateHz = rateWindowCount / elapsed;

            rateWindowStart = sample.timestamp;
            rateWindowCount = 0;
        }
    }
}

void IMU::push(const IMUSample& sample)
{
    {
        std::lock_guard<std::mutex> lock(bufferMutex);

        buffer[head] = sample;

        head = (head + 1) % buffer.size();

        if (used < buffer.size())
        {
            ++used;
        }
        else
        {
            std::lock_guard<std::mutex> healthLock(healthMutex);
            ++status.samplesOverwritten;
        }
    }

    std::lock_guard<std::mutex> lock(healthMutex);

    ++status.samplesRead;
    status.lastSampleTime = sample.timestamp;
}

size_t IMU::samplesBetween(double begin,
                           double end,
                           std::vector<IMUSample>& out)
{
    out.clear();

    if (!enabled)
    {
        return 0;
    }

    std::lock_guard<std::mutex> lock(bufferMutex);

    if (used == 0)
    {
        return 0;
    }

    const size_t capacity = buffer.size();
    const size_t oldest = (head + capacity - used) % capacity;

    for (size_t i = 0; i < used; ++i)
    {
        const IMUSample& sample = buffer[(oldest + i) % capacity];

        if (sample.timestamp > begin && sample.timestamp <= end)
        {
            out.push_back(sample);
        }
    }

    return out.size();
}

IMU::Health IMU::health() const
{
    std::lock_guard<std::mutex> lock(healthMutex);

    Health copy = status;

    copy.enabled = enabled;
    copy.running = running.load();

    return copy;
}

} // namespace novex
