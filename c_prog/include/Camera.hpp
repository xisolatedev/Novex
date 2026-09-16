#pragma once

#include "VIOConfig.hpp"

#include <opencv2/core.hpp>
#include <opencv2/videoio.hpp>

#include <cstdint>
#include <string>

namespace novex
{

// Stereo camera acquisition and configuration. Nothing else.
//
// This class never opens a window, never draws, and does not know that
// a GUI exists. All display lives in Gui.cpp.
class Camera
{
public:

    struct Status
    {
        bool open = false;

        int requestedWidth  = 0;
        int requestedHeight = 0;
        int requestedFPS    = 0;

        // What the driver actually agreed to, read back from V4L2
        // rather than assumed from the request.
        int negotiatedWidth  = 0;
        int negotiatedHeight = 0;
        double negotiatedFPS = 0.0;

        std::string fourcc;

        bool mjpegNegotiated = false;
        bool directGrayDecode = false;

        // True when frame timestamps come from the V4L2 buffer, which
        // is when the sensor delivered the frame. False means we fell
        // back to reading the clock after the decode, which is later
        // and jittery.
        bool driverTimestamps = false;

        uint64_t framesCaptured = 0;
        uint64_t framesDropped  = 0;
        uint64_t framesFailed   = 0;

        double lastTimestamp = 0.0;

        // Time spent blocked in grab() waiting for the sensor to
        // deliver, and time spent decoding it. Only the second is CPU
        // work; keeping them apart is the difference between a
        // meaningful benchmark and one that just reports the frame
        // period back at you.
        double lastWaitSeconds = 0.0;
        double lastDecodeSeconds = 0.0;
    };

    explicit Camera(const VIOConfig& config);
    ~Camera();

    Camera(const Camera&) = delete;
    Camera& operator=(const Camera&) = delete;

    bool open();
    void close();

    bool isOpen() const;

    // Captures and decodes one frame. Returns false on a failed or
    // empty frame; the caller decides whether that is fatal.
    bool grab();

    // Discards up to `count` queued frames without decoding them.
    // This is the overload strategy: when processing has fallen
    // behind, the buffered frames are stale and working through them
    // only increases latency. Returns how many were discarded.
    int dropQueuedFrames(int count);

    // Views onto the most recent frame. No copy is made: the eye
    // images are ROIs into the full frame's buffer.
    //
    // Two frame buffers are used in turn, so the images returned for
    // frame N stay valid while frame N+1 is captured. They are
    // invalidated by the capture after that.
    const cv::Mat& getFrame() const;
    const cv::Mat& getLeftImage() const;
    const cv::Mat& getRightImage() const;

    // CLOCK_MONOTONIC seconds; see Time.hpp.
    double getTimestamp() const;

    cv::Size eyeSize() const;

    int getWidth() const  { return state.negotiatedWidth; }
    int getHeight() const { return state.negotiatedHeight; }
    double getFPS() const { return state.negotiatedFPS; }

    const Status& status() const { return state; }

    std::string describe() const;

private:

    bool applyFormat();
    void readBackNegotiatedFormat();

    bool decodeInto(cv::Mat& destination);
    void updateEyeViews();

    double readTimestamp();

    const VIOConfig& config;

    cv::VideoCapture capture;

    // Ping-pong grayscale frame buffers. Allocated once by the first
    // decode and reused for the life of the process.
    cv::Mat frames[2];
    int writeIndex = 0;
    int readIndex = 1;

    // Raw MJPG bytes, when decoding straight to grayscale.
    cv::Mat encoded;

    // Colour frame, only when the direct-grayscale path is unavailable.
    cv::Mat colour;

    cv::Mat leftView;
    cv::Mat rightView;

    Status state;

    bool haveFrame = false;
};

} // namespace novex
