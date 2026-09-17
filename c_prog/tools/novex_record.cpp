// novex-record: capture raw stereo frames for exact replay.
//
//   novex-record DIR FRAMES [novex-vio camera flags...]
//
// Writes DIR/00000.png ... (the combined grayscale side-by-side frame,
// PNG = lossless) and DIR/times.txt with the camera timestamp of each.
// novex-replay feeds them through the unmodified pipeline, so two
// estimator versions can be compared on IDENTICAL input instead of on
// two runs that happened to see different motion.

#include "Camera.hpp"
#include "Log.hpp"
#include "VIOConfig.hpp"

#include <opencv2/imgcodecs.hpp>

#include <sys/stat.h>

#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

int main(int argc, char** argv)
{
    using namespace novex;

    if (argc < 3)
    {
        fprintf(stderr,
                "usage: novex-record DIR FRAMES [camera flags]\n"
                "  e.g. novex-record /tmp/loop 1800 --device 0\n");
        return 1;
    }

    const std::string directory = argv[1];
    const int frames = std::atoi(argv[2]);

    ::mkdir(directory.c_str(), 0755);

    // Remaining flags go through the normal parser, so --device,
    // --width and friends mean exactly what they mean for novex-vio.
    std::vector<char*> forwarded = { argv[0] };

    for (int i = 3; i < argc; ++i)
    {
        forwarded.push_back(argv[i]);
    }

    VIOConfig config;

    // The daemon's config file is not what a recording wants, but the
    // camera section must match what novex-vio will use; read it.
    bool shouldExit = false;

    if (!config.parseCommandLine(static_cast<int>(forwarded.size()),
                                 forwarded.data(), shouldExit) ||
        shouldExit)
    {
        return 1;
    }

    setLogLevel(LogLevel::Warn);

    Camera camera(config);

    if (!camera.open())
    {
        return 1;
    }

    const std::string timesPath = directory + "/times.txt";

    FILE* times = std::fopen(timesPath.c_str(), "w");

    if (times == nullptr)
    {
        fprintf(stderr, "cannot write %s\n", timesPath.c_str());
        return 1;
    }

    // Let auto-exposure settle before anything is kept.
    for (int i = 0; i < 30; ++i)
    {
        camera.grab();
    }

    fprintf(stderr, "recording %d frames to %s ...\n",
            frames, directory.c_str());

    int written = 0;

    while (written < frames)
    {
        if (!camera.grab())
        {
            continue;
        }

        char name[1024];

        snprintf(name, sizeof(name), "%s/%05d.png",
                 directory.c_str(), written);

        // Compression level 1 keeps up with 30 fps on the development
        // machine; the file is still lossless.
        cv::imwrite(name, camera.getFrame(),
                    { cv::IMWRITE_PNG_COMPRESSION, 1 });

        fprintf(times, "%d %.6f\n", written, camera.getTimestamp());

        ++written;
    }

    std::fclose(times);

    fprintf(stderr, "recorded %d frames, %llu dropped by the camera\n",
            written,
            static_cast<unsigned long long>(camera.status().framesDropped));

    return 0;
}
