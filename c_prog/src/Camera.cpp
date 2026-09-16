#include "Camera.hpp"

#include "Log.hpp"
#include "Time.hpp"

#include <opencv2/imgcodecs.hpp>
#include <opencv2/imgproc.hpp>

#include <cmath>
#include <sstream>

namespace novex
{

namespace
{

std::string fourccToString(double value)
{
    const int code = static_cast<int>(value);

    if (code == 0)
    {
        return "none";
    }

    char text[5] = {
        static_cast<char>( code        & 0xFF),
        static_cast<char>((code >>  8) & 0xFF),
        static_cast<char>((code >> 16) & 0xFF),
        static_cast<char>((code >> 24) & 0xFF),
        '\0'
    };

    return std::string(text);
}

} // namespace

Camera::Camera(const VIOConfig& config)
    : config(config)
{
}

Camera::~Camera()
{
    close();
}

bool Camera::open()
{
    close();

    state = Status();

    state.requestedWidth  = config.cameraWidth;
    state.requestedHeight = config.cameraHeight;
    state.requestedFPS    = config.cameraFPS;

    // CAP_V4L2 rather than CAP_ANY: this pins the backend to V4L2 so
    // that format negotiation, buffer timestamps and MJPG selection
    // behave the same on the development machine and on the Pi.
    capture.open(config.cameraDevice, cv::CAP_V4L2);

    if (!capture.isOpened())
    {
        LOG_ERROR(
            "camera: cannot open device %d via V4L2",
            config.cameraDevice
        );

        return false;
    }

    if (!applyFormat())
    {
        capture.release();
        return false;
    }

    readBackNegotiatedFormat();

    // Prove the configured decode path actually works on this device
    // before the pipeline starts depending on it. Some UVC drivers
    // accept CONVERT_RGB=0 and then hand back something that is not a
    // JPEG.
    bool captured = false;

    for (int attempt = 0; attempt < 10 && !captured; ++attempt)
    {
        captured = grab();
    }

    if (!captured && state.directGrayDecode)
    {
        LOG_WARN(
            "camera: direct-grayscale MJPG decode failed on this "
            "device; falling back to the colour decode path"
        );

        state.directGrayDecode = false;

        capture.release();
        capture.open(config.cameraDevice, cv::CAP_V4L2);

        if (!capture.isOpened() || !applyFormat())
        {
            return false;
        }

        readBackNegotiatedFormat();

        for (int attempt = 0; attempt < 10 && !captured; ++attempt)
        {
            captured = grab();
        }
    }

    if (!captured)
    {
        LOG_ERROR("camera: opened but produced no usable frame");
        capture.release();
        return false;
    }

    state.open = true;

    // Counters from the probe frames are not interesting.
    state.framesCaptured = 0;
    state.framesFailed = 0;

    LOG_INFO("camera: %s", describe().c_str());

    if (state.negotiatedWidth  != state.requestedWidth ||
        state.negotiatedHeight != state.requestedHeight)
    {
        LOG_WARN(
            "camera: requested %dx%d but the driver negotiated %dx%d; "
            "the calibration will be adapted to what was negotiated",
            state.requestedWidth,
            state.requestedHeight,
            state.negotiatedWidth,
            state.negotiatedHeight
        );
    }

    if (config.cameraMJPEG && !state.mjpegNegotiated)
    {
        LOG_WARN(
            "camera: MJPG was requested but the driver reports '%s'. "
            "Uncompressed formats rarely sustain this resolution over "
            "USB and usually collapse to a few frames per second.",
            state.fourcc.c_str()
        );
    }

    if (!state.driverTimestamps)
    {
        LOG_WARN(
            "camera: the driver did not supply buffer timestamps; "
            "falling back to host clock at decode time, which adds "
            "jitter and a decode-length bias to every timestamp"
        );
    }

    return true;
}

bool Camera::applyFormat()
{
    // Order matters for V4L2: the pixel format has to be chosen before
    // the frame size, because the set of valid sizes depends on it.
    if (config.cameraMJPEG)
    {
        capture.set(
            cv::CAP_PROP_FOURCC,
            cv::VideoWriter::fourcc('M', 'J', 'P', 'G')
        );
    }

    capture.set(cv::CAP_PROP_FRAME_WIDTH,  config.cameraWidth);
    capture.set(cv::CAP_PROP_FRAME_HEIGHT, config.cameraHeight);
    capture.set(cv::CAP_PROP_FPS,          config.cameraFPS);

    // Queue depth is left to the driver by default, and that is a
    // measured decision rather than an oversight.
    //
    // Requesting a depth of 1 looks like the right way to hold latency
    // down, but on this uvcvideo device it HALVES the frame rate:
    // with a single buffer, nothing is queued to the hardware while
    // userspace holds the frame, so every second frame is missed.
    // Measured on the development machine at 1280x480 MJPG:
    //
    //     BUFFERSIZE=1        63.9 ms interval   15.7 fps
    //     driver default      33.4 ms interval   30.0 fps
    //     BUFFERSIZE=4        33.4 ms interval   30.0 fps
    //
    // Latency is controlled instead by dropQueuedFrames(), which
    // discards stale frames explicitly and reports how many - a
    // mechanism that works whether or not a driver honours this
    // property at all.
    if (config.cameraBufferSize > 0)
    {
        capture.set(cv::CAP_PROP_BUFFERSIZE, config.cameraBufferSize);
    }

    state.directGrayDecode = false;

    if (config.cameraMJPEG && config.cameraDirectGray)
    {
        // With colour conversion disabled, retrieve() hands back the
        // raw MJPG bytes. Decoding those straight to grayscale lets
        // libjpeg skip chroma upsampling and the YUV->BGR conversion
        // entirely, and the pipeline only ever wanted luminance.
        if (capture.set(cv::CAP_PROP_CONVERT_RGB, 0))
        {
            state.directGrayDecode = true;
        }
        else
        {
            LOG_INFO(
                "camera: driver will not disable colour conversion; "
                "using the colour decode path"
            );
        }
    }

    return true;
}

void Camera::readBackNegotiatedFormat()
{
    // Everything here is read back from the driver. Assuming the
    // requested mode was accepted is how a pipeline ends up silently
    // running at 640x480 while every calibration constant assumes
    // something else.
    state.negotiatedWidth =
        static_cast<int>(capture.get(cv::CAP_PROP_FRAME_WIDTH));

    state.negotiatedHeight =
        static_cast<int>(capture.get(cv::CAP_PROP_FRAME_HEIGHT));

    state.negotiatedFPS = capture.get(cv::CAP_PROP_FPS);

    state.fourcc = fourccToString(capture.get(cv::CAP_PROP_FOURCC));

    state.mjpegNegotiated = (state.fourcc == "MJPG");
}

void Camera::close()
{
    if (capture.isOpened())
    {
        capture.release();
    }

    state.open = false;
    haveFrame = false;
}

bool Camera::isOpen() const
{
    return capture.isOpened() && state.open;
}

double Camera::readTimestamp()
{
    const double host = monotonicSeconds();

    // CAP_PROP_POS_MSEC on the V4L2 backend is the buffer timestamp,
    // which the kernel takes on CLOCK_MONOTONIC when the frame
    // arrives. That is both earlier and far more stable than reading
    // the clock ourselves after a JPEG decode, and it shares a clock
    // with IIO timestamps from an IMU.
    const double driverMilliseconds = capture.get(cv::CAP_PROP_POS_MSEC);

    if (driverMilliseconds > 0.0 && std::isfinite(driverMilliseconds))
    {
        const double driver = driverMilliseconds * 1e-3;

        // Sanity check against our own clock. A driver that reports
        // milliseconds-since-stream-start rather than monotonic time
        // would fail this and be rejected, rather than quietly
        // desynchronising the IMU.
        const double offset = host - driver;

        if (offset > -0.5 && offset < 2.0)
        {
            state.driverTimestamps = true;
            return driver;
        }
    }

    state.driverTimestamps = false;

    return host;
}

bool Camera::decodeInto(cv::Mat& destination)
{
    if (state.directGrayDecode)
    {
        if (!capture.retrieve(encoded) || encoded.empty())
        {
            return false;
        }

        // imdecode with an explicit destination reuses the existing
        // allocation once the frame size has settled, so the steady
        // state allocates nothing.
        cv::imdecode(encoded, cv::IMREAD_GRAYSCALE, &destination);

        return !destination.empty();
    }

    if (!capture.retrieve(colour) || colour.empty())
    {
        return false;
    }

    if (colour.channels() == 1)
    {
        // Some drivers hand back single-channel data directly.
        colour.copyTo(destination);
    }
    else
    {
        cv::cvtColor(colour, destination, cv::COLOR_BGR2GRAY);
    }

    return !destination.empty();
}

bool Camera::grab()
{
    if (!capture.isOpened())
    {
        return false;
    }

    // grab() and retrieve() are split so the timestamp is read at
    // buffer dequeue rather than after the decode.
    const double beforeWait = monotonicSeconds();

    if (!capture.grab())
    {
        ++state.framesFailed;
        return false;
    }

    const double afterWait = monotonicSeconds();

    state.lastWaitSeconds = afterWait - beforeWait;

    const double timestamp = readTimestamp();

    if (!decodeInto(frames[writeIndex]))
    {
        ++state.framesFailed;
        return false;
    }

    state.lastDecodeSeconds = monotonicSeconds() - afterWait;

    const cv::Mat& frame = frames[writeIndex];

    if (frame.cols != state.negotiatedWidth ||
        frame.rows != state.negotiatedHeight)
    {
        // The decoded size is the authority; the property read-back
        // can lie, the pixels cannot.
        state.negotiatedWidth  = frame.cols;
        state.negotiatedHeight = frame.rows;
    }

    if (frame.cols % 2 != 0)
    {
        LOG_ERROR(
            "camera: frame width %d is odd and cannot be split into "
            "two eyes",
            frame.cols
        );

        return false;
    }

    readIndex = writeIndex;
    writeIndex ^= 1;

    state.lastTimestamp = timestamp;
    ++state.framesCaptured;

    haveFrame = true;

    updateEyeViews();

    return true;
}

void Camera::updateEyeViews()
{
    const cv::Mat& frame = frames[readIndex];

    const int halfWidth = frame.cols / 2;

    const cv::Rect leftHalf(0, 0, halfWidth, frame.rows);
    const cv::Rect rightHalf(halfWidth, 0, halfWidth, frame.rows);

    // These are views, not copies: cv::Mat's ROI constructor shares
    // the parent's pixels and only bumps the reference count.
    if (config.cameraSwapEyes)
    {
        leftView  = frame(rightHalf);
        rightView = frame(leftHalf);
    }
    else
    {
        leftView  = frame(leftHalf);
        rightView = frame(rightHalf);
    }
}

int Camera::dropQueuedFrames(int count)
{
    int dropped = 0;

    for (int i = 0; i < count; ++i)
    {
        if (!capture.grab())
        {
            break;
        }

        ++dropped;
    }

    state.framesDropped += static_cast<uint64_t>(dropped);

    return dropped;
}

const cv::Mat& Camera::getFrame() const
{
    return frames[readIndex];
}

const cv::Mat& Camera::getLeftImage() const
{
    return leftView;
}

const cv::Mat& Camera::getRightImage() const
{
    return rightView;
}

double Camera::getTimestamp() const
{
    return state.lastTimestamp;
}

cv::Size Camera::eyeSize() const
{
    return cv::Size(state.negotiatedWidth / 2, state.negotiatedHeight);
}

std::string Camera::describe() const
{
    std::ostringstream text;

    text.setf(std::ios::fixed);
    text.precision(1);

    text << "device " << config.cameraDevice
         << ": " << state.negotiatedWidth
         << "x" << state.negotiatedHeight
         << " @ " << state.negotiatedFPS << " fps"
         << ", format " << state.fourcc
         << ", eyes " << (state.negotiatedWidth / 2)
         << "x" << state.negotiatedHeight
         << ", decode "
         << (state.directGrayDecode ? "mjpg->gray" : "bgr->gray")
         << ", timestamps "
         << (state.driverTimestamps ? "v4l2 buffer" : "host clock");

    return text.str();
}

} // namespace novex
