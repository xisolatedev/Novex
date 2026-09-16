#pragma once

#include "Camera.hpp"
#include "VIO.hpp"
#include "VIOConfig.hpp"

#include <opencv2/core.hpp>

namespace novex
{

// Development-only visualisation.
//
// The VIO core has no knowledge of this class. The data flow is
// Camera -> VIO -> Gui, so the GUI is a consumer of results and can be
// deleted without touching anything upstream. Nothing here is ever
// constructed in daemon mode, so a headless machine never loads
// highgui's window backend.
class Gui
{
public:

    explicit Gui(const VIOConfig& config);
    ~Gui();

    bool open();
    void close();

    bool isOpen() const { return windowOpen; }

    // Draws one frame. Returns false when the user has asked to quit.
    bool draw(const Camera& camera, const VIO& vio);

private:

    void drawOverlay(cv::Mat& canvas,
                     const Camera& camera,
                     const VIOSnapshot& snapshot);

    const VIOConfig& config;

    bool windowOpen = false;
    bool available = true;

    // Reused canvas, so the GUI does not allocate a new image per
    // frame even in development.
    cv::Mat canvas;
};

} // namespace novex
