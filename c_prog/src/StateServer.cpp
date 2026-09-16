#include "StateServer.hpp"

#include "Log.hpp"
#include "Time.hpp"

#include <cerrno>
#include <cstdio>
#include <algorithm>
#include <cstdlib>
#include <fcntl.h>
#include <cstring>
#include <poll.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include <vector>

namespace novex
{

StateServer::StateServer(const VIOConfig& config, VIO& vio)
    : config(config), vio(vio), path(config.ipcSocketPath)
{
}

StateServer::~StateServer()
{
    stop();
}

bool StateServer::start()
{
    if (!config.ipcEnabled)
    {
        LOG_INFO("ipc: disabled");
        return true;
    }

    if (path.size() >= sizeof(sockaddr_un::sun_path))
    {
        LOG_ERROR(
            "ipc: socket path is too long (%zu >= %zu)",
            path.size(),
            sizeof(sockaddr_un::sun_path)
        );

        return false;
    }

    // A stale socket file from a previous run that did not shut down
    // cleanly would otherwise make bind() fail forever.
    if (::unlink(path.c_str()) != 0 && errno != ENOENT)
    {
        LOG_WARN(
            "ipc: cannot remove stale socket %s: %s",
            path.c_str(),
            std::strerror(errno)
        );
    }

    listenFd = ::socket(AF_UNIX, SOCK_STREAM, 0);

    if (listenFd < 0)
    {
        LOG_ERROR("ipc: socket(): %s", std::strerror(errno));
        return false;
    }

    sockaddr_un address;

    std::memset(&address, 0, sizeof(address));

    address.sun_family = AF_UNIX;

    std::strncpy(
        address.sun_path,
        path.c_str(),
        sizeof(address.sun_path) - 1
    );

    if (::bind(listenFd,
               reinterpret_cast<sockaddr*>(&address),
               sizeof(address)) != 0)
    {
        LOG_ERROR(
            "ipc: bind(%s): %s",
            path.c_str(),
            std::strerror(errno)
        );

        ::close(listenFd);
        listenFd = -1;

        return false;
    }

    // Owner and group only. The socket exposes the vehicle's pose;
    // there is no reason for it to be world-writable.
    ::chmod(path.c_str(), 0660);

    // Non-blocking, so the accept-drain loop in serveLoop ends with
    // EAGAIN instead of parking the thread on an empty backlog.
    ::fcntl(listenFd, F_SETFL,
            ::fcntl(listenFd, F_GETFL, 0) | O_NONBLOCK);

    // A backlog well above the client limit, so a burst of clients is
    // refused deliberately by us with a log line, rather than being
    // dropped silently by the kernel.
    if (::listen(listenFd, config.ipcMaxClients * 4 + 8) != 0)
    {
        LOG_ERROR("ipc: listen(): %s", std::strerror(errno));

        ::close(listenFd);
        listenFd = -1;
        ::unlink(path.c_str());

        return false;
    }

    stopRequested.store(false);
    running.store(true);

    worker = std::thread(&StateServer::serveLoop, this);

    LOG_INFO("ipc: listening on %s", path.c_str());

    return true;
}

void StateServer::stop()
{
    if (!running.load() && !worker.joinable())
    {
        return;
    }

    stopRequested.store(true);

    if (worker.joinable())
    {
        worker.join();
    }

    if (listenFd >= 0)
    {
        ::close(listenFd);
        listenFd = -1;
    }

    ::unlink(path.c_str());

    running.store(false);
}

void StateServer::serveLoop()
{
    // A client that vanishes mid-write would otherwise kill the whole
    // daemon with SIGPIPE. Handling it as an error return instead is
    // the difference between one dropped client and a dead VIO.
    ::signal(SIGPIPE, SIG_IGN);

    std::vector<pollfd> descriptors;

    descriptors.reserve(
        static_cast<size_t>(config.ipcMaxClients) + 1
    );

    while (!stopRequested.load())
    {
        descriptors.clear();

        pollfd listener;

        listener.fd = listenFd;
        listener.events = POLLIN;
        listener.revents = 0;

        descriptors.push_back(listener);

        bool anySubscribed = false;

        for (const Client& client : clients)
        {
            pollfd entry;

            entry.fd = client.fd;
            entry.events = POLLIN;
            entry.revents = 0;

            descriptors.push_back(entry);

            anySubscribed = anySubscribed || client.subscribed;
        }

        // A bounded timeout is what makes shutdown prompt without
        // needing a self-pipe: the loop wakes twice a second to notice
        // that a stop was requested.
        // With a subscriber attached the loop has to wake often
        // enough to hit its push rate; without one, twice a second is
        // plenty to notice a shutdown.
        const int timeoutMs = anySubscribed ? 5 : 500;

        const int ready = ::poll(
            descriptors.data(),
            static_cast<nfds_t>(descriptors.size()),
            timeoutMs
        );

        if (ready < 0)
        {
            if (errno == EINTR)
            {
                continue;
            }

            LOG_ERROR("ipc: poll(): %s", std::strerror(errno));
            break;
        }

        pushSubscriptions(monotonicSeconds());

        if (ready == 0)
        {
            continue;
        }

        if (descriptors[0].revents & POLLIN)
        {
            // Drain the whole backlog rather than accepting one
            // connection per poll round. A burst of clients starting
            // at once would otherwise sit in the kernel queue waiting
            // for a reply that only arrives one round at a time, and
            // any that overflow the backlog get connection refused.
            for (;;)
            {
                const int clientFd =
                    ::accept(listenFd, nullptr, nullptr);

                if (clientFd < 0)
                {
                    break;
                }

                if (static_cast<int>(clients.size()) >=
                    config.ipcMaxClients)
                {
                    LOG_WARN_EVERY(
                        5.0,
                        "ipc: refusing connection, %d clients already "
                        "attached",
                        config.ipcMaxClients
                    );

                    ::close(clientFd);
                    continue;
                }

                Client client;

                client.fd = clientFd;

                clients.push_back(client);
                accepted.fetch_add(1);
            }
        }

        // Collect closures first, then apply them, so the client list
        // is not modified while the poll results still index into it.
        std::vector<int> closing;

        for (size_t i = 1; i < descriptors.size(); ++i)
        {
            const short events = descriptors[i].revents;

            if (events == 0)
            {
                continue;
            }

            const int clientFd = descriptors[i].fd;

            Client* client = nullptr;

            for (Client& candidate : clients)
            {
                if (candidate.fd == clientFd)
                {
                    client = &candidate;
                    break;
                }
            }

            if (client == nullptr)
            {
                continue;
            }

            bool keep = true;

            if (events & POLLIN)
            {
                char input[128];

                const ssize_t received =
                    ::recv(clientFd, input, sizeof(input) - 1, 0);

                if (received <= 0)
                {
                    // Zero means an orderly disconnect, negative an
                    // error. Either way the client is gone, and that
                    // is a normal event, not a fault.
                    keep = false;
                }
                else
                {
                    input[received] = '\0';

                    std::string command(input);

                    while (!command.empty() &&
                           (command.back() == '\n' ||
                            command.back() == '\r' ||
                            command.back() == ' '))
                    {
                        command.pop_back();
                    }

                    keep = handleCommand(*client, command);
                }
            }

            if ((events & (POLLHUP | POLLERR | POLLNVAL)) != 0)
            {
                keep = false;
            }

            if (!keep)
            {
                closing.push_back(clientFd);
            }
        }

        for (int clientFd : closing)
        {
            ::close(clientFd);

            for (size_t j = 0; j < clients.size(); ++j)
            {
                if (clients[j].fd == clientFd)
                {
                    clients.erase(clients.begin() + static_cast<long>(j));
                    break;
                }
            }
        }
    }

    for (const Client& client : clients)
    {
        ::close(client.fd);
    }

    clients.clear();
}

void StateServer::pushSubscriptions(double now)
{
    char message[4096];

    size_t length = 0;
    bool formatted = false;

    for (Client& client : clients)
    {
        if (!client.subscribed || now < client.nextSendTime)
        {
            continue;
        }

        // Formatted at most once per wake-up, however many
        // subscribers there are.
        if (!formatted)
        {
            length = formatStream(message, sizeof(message));

            if (length >= sizeof(message))
            {
                length = sizeof(message) - 1;
            }

            formatted = true;
        }

        client.nextSendTime = now + client.intervalSeconds;

        // Non-blocking. If the receiver has not drained its socket we
        // simply skip this update: the next one carries newer data
        // anyway, and queueing stale states would only add latency.
        const ssize_t sent = ::send(
            client.fd,
            message,
            length,
            MSG_NOSIGNAL | MSG_DONTWAIT
        );

        if (sent >= 0)
        {
            served.fetch_add(1);
        }
    }
}

bool StateServer::sendLine(int clientFd, const char* data, size_t length)
{
    const ssize_t sent = ::send(
        clientFd,
        data,
        length,
        MSG_NOSIGNAL | MSG_DONTWAIT
    );

    if (sent < 0)
    {
        if (errno == EAGAIN || errno == EWOULDBLOCK)
        {
            LOG_WARN_EVERY(
                5.0,
                "ipc: client is not reading; dropping reply"
            );

            return true;
        }

        return false;
    }

    served.fetch_add(1);

    return true;
}

size_t StateServer::formatState(char* buffer, size_t size) const
{
    const VIOSnapshot snapshot = vio.snapshot();
    const VIOState& state = snapshot.state;

    // Hand-built JSON into a fixed buffer: no allocation, no
    // dependency, and the output is small enough that a client can
    // parse it with anything at all.
    return static_cast<size_t>(snprintf(
        buffer,
        size,
        "{\"timestamp\":%.6f,"
        "\"position\":[%.6f,%.6f,%.6f],"
        "\"velocity\":[%.6f,%.6f,%.6f],"
        "\"orientation\":[%.6f,%.6f,%.6f,%.6f],"
        "\"tracking\":%s,"
        "\"feature_count\":%d,"
        "\"inlier_count\":%d,"
        "\"stereo_count\":%d,"
        "\"imu_enabled\":%s,"
        "\"imu_healthy\":%s,"
        "\"gyro_bias\":[%.6f,%.6f,%.6f],"
        "\"frame_id\":%llu,"
        "\"dropped_frames\":%llu,"
        "\"lost_frames\":%d}\n",
        state.timestamp,
        state.position.x(), state.position.y(), state.position.z(),
        state.velocity.x(), state.velocity.y(), state.velocity.z(),
        state.orientation.x(), state.orientation.y(),
        state.orientation.z(), state.orientation.w(),
        state.tracking ? "true" : "false",
        state.trackedFeatures,
        state.inlierFeatures,
        state.stereoFeatures,
        state.imuEnabled ? "true" : "false",
        state.imuHealthy ? "true" : "false",
        state.gyroBias.x(), state.gyroBias.y(), state.gyroBias.z(),
        static_cast<unsigned long long>(state.frameId),
        static_cast<unsigned long long>(state.droppedFrames),
        state.lostFrames
    ));
}

size_t StateServer::formatStats(char* buffer, size_t size) const
{
    const VIOSnapshot snapshot = vio.snapshot();

    const double* stage = snapshot.stageMilliseconds;

    return static_cast<size_t>(snprintf(
        buffer,
        size,
        "{\"capture_fps\":%.2f,"
        "\"processing_fps\":%.2f,"
        "\"latency_ms\":%.2f,"
        "\"capture_ms\":%.3f,"
        "\"decode_ms\":%.3f,"
        "\"preprocess_ms\":%.3f,"
        "\"detect_ms\":%.3f,"
        "\"track_ms\":%.3f,"
        "\"stereo_ms\":%.3f,"
        "\"motion_ms\":%.3f,"
        "\"state_ms\":%.3f,"
        "\"imu_ms\":%.3f,"
        "\"total_ms\":%.3f,"
        "\"stereo_matched\":%d,"
        "\"stereo_triangulated\":%d,"
        "\"imu_running\":%s,"
        "\"imu_rate_hz\":%.1f,"
        "\"dropped_frames\":%llu}\n",
        snapshot.captureFPS,
        snapshot.processingFPS,
        snapshot.latencySeconds * 1e3,
        stage[static_cast<int>(Stage::Capture)],
        stage[static_cast<int>(Stage::Decode)],
        stage[static_cast<int>(Stage::Preprocess)],
        stage[static_cast<int>(Stage::Detect)],
        stage[static_cast<int>(Stage::Track)],
        stage[static_cast<int>(Stage::Stereo)],
        stage[static_cast<int>(Stage::Motion)],
        stage[static_cast<int>(Stage::State)],
        stage[static_cast<int>(Stage::Imu)],
        stage[static_cast<int>(Stage::Total)],
        snapshot.stereoMatched,
        snapshot.stereoTriangulated,
        snapshot.imuRunning ? "true" : "false",
        snapshot.imuRateHz,
        static_cast<unsigned long long>(
            snapshot.state.droppedFrames)
    ));
}

size_t StateServer::formatDebug(char* buffer, size_t size) const
{
    const DebugStatistics d = vio.debug().snapshot();

    if (!d.enabled)
    {
        // Honest rather than zero-filled: without --debug these
        // numbers were never collected, and reporting 0.00 ms would
        // read as a measurement.
        return static_cast<size_t>(snprintf(
            buffer,
            size,
            "{\"enabled\":false,"
            "\"message\":\"Detailed debug statistics disabled. "
            "Start with --debug for detailed timing information.\"}\n"
        ));
    }

    return static_cast<size_t>(snprintf(
        buffer,
        size,
        "{\"enabled\":true,"
        "\"runtime_s\":%.3f,"
        "\"frames_processed\":%llu,"
        "\"dropped_frames\":%llu,"
        "\"failed_frames\":%llu,"
        "\"avg_frame_ms\":%.3f,"
        "\"min_frame_ms\":%.3f,"
        "\"max_frame_ms\":%.3f,"
        "\"tracking_failures\":%llu,"
        "\"successful_frames\":%llu,"
        "\"avg_features\":%.1f,"
        "\"min_features\":%d,"
        "\"max_features\":%d,"
        "\"stereo_total\":%llu,"
        "\"avg_stereo\":%.1f,"
        "\"frames_without_stereo\":%llu,"
        "\"imu_samples\":%llu,"
        "\"trajectory_m\":%.4f}\n",
        d.runtimeSeconds,
        static_cast<unsigned long long>(d.framesProcessed),
        static_cast<unsigned long long>(d.droppedFrames),
        static_cast<unsigned long long>(d.failedFrames),
        d.averageFrameTimeMs,
        d.minFrameTimeMs,
        d.maxFrameTimeMs,
        static_cast<unsigned long long>(d.trackingFailures),
        static_cast<unsigned long long>(d.successfulFrames),
        d.averageTrackedFeatures,
        d.minTrackedFeatures,
        d.maxTrackedFeatures,
        static_cast<unsigned long long>(d.stereoMatchesTotal),
        d.averageStereoMatches,
        static_cast<unsigned long long>(d.framesWithoutStereo),
        static_cast<unsigned long long>(d.imuSamples),
        d.trajectoryDistanceMeters
    ));
}

size_t StateServer::formatStatus(char* buffer, size_t size) const
{
    const VIOSnapshot s = vio.snapshot();

    return static_cast<size_t>(snprintf(
        buffer,
        size,
        "{\"running\":true,"
        "\"paused\":%s,"
        "\"tracking\":%s,"
        "\"stereo_enabled\":%s,"
        "\"imu_enabled\":%s,"
        "\"imu_running\":%s,"
        "\"debug_enabled\":%s,"
        "\"reset_count\":%llu,"
        "\"recenter_count\":%llu,"
        "\"recentered\":%s,"
        "\"frame_id\":%llu}\n",
        s.paused ? "true" : "false",
        s.state.tracking ? "true" : "false",
        s.stereoEnabled ? "true" : "false",
        s.imuEnabled ? "true" : "false",
        s.imuRunning ? "true" : "false",
        vio.debug().isEnabled() ? "true" : "false",
        static_cast<unsigned long long>(s.resetCount),
        static_cast<unsigned long long>(s.recenterCount),
        s.originRecentered ? "true" : "false",
        static_cast<unsigned long long>(s.state.frameId)
    ));
}

size_t StateServer::formatCamera(char* buffer, size_t size) const
{
    if (camera == nullptr)
    {
        return static_cast<size_t>(snprintf(
            buffer, size, "{\"available\":false}\n"
        ));
    }

    const Camera::Status& c = camera->status();

    return static_cast<size_t>(snprintf(
        buffer,
        size,
        "{\"available\":true,"
        "\"width\":%d,\"height\":%d,"
        "\"eye_width\":%d,\"eye_height\":%d,"
        "\"fps\":%.2f,"
        "\"fourcc\":\"%s\","
        "\"mjpeg\":%s,"
        "\"direct_gray\":%s,"
        "\"driver_timestamps\":%s,"
        "\"frames_captured\":%llu,"
        "\"frames_dropped\":%llu,"
        "\"frames_failed\":%llu}\n",
        c.negotiatedWidth, c.negotiatedHeight,
        c.negotiatedWidth / 2, c.negotiatedHeight,
        c.negotiatedFPS,
        c.fourcc.c_str(),
        c.mjpegNegotiated ? "true" : "false",
        c.directGrayDecode ? "true" : "false",
        c.driverTimestamps ? "true" : "false",
        static_cast<unsigned long long>(c.framesCaptured),
        static_cast<unsigned long long>(c.framesDropped),
        static_cast<unsigned long long>(c.framesFailed)
    ));
}

size_t StateServer::formatStream(char* buffer, size_t size) const
{
    const VIOSnapshot s = vio.snapshot();
    const VIOState& st = s.state;
    const DebugStatistics d = vio.debug().snapshot();

    const double* stage = s.stageMilliseconds;

    // One object carrying everything the dashboard needs, so the
    // browser parses once per update instead of correlating several
    // messages. Position and orientation stay in NOVEX coordinates
    // here; the conversion to Three.js axes happens in the browser,
    // where it is documented alongside the scene setup.
    return static_cast<size_t>(snprintf(
        buffer,
        size,
        "{\"type\":\"vio_state\","
        "\"timestamp\":%.6f,"
        "\"position\":{\"x\":%.6f,\"y\":%.6f,\"z\":%.6f},"
        "\"velocity\":{\"x\":%.6f,\"y\":%.6f,\"z\":%.6f},"
        "\"orientation\":{\"x\":%.6f,\"y\":%.6f,\"z\":%.6f,\"w\":%.6f},"
        "\"tracking\":%s,"
        "\"paused\":%s,"
        "\"trackedFeatures\":%d,"
        "\"inliers\":%d,"
        "\"stereoMatches\":%d,"
        "\"stereoTriangulated\":%d,"
        "\"stereoEnabled\":%s,"
        "\"imuEnabled\":%s,"
        "\"imuHealthy\":%s,"
        "\"fps\":%.2f,"
        "\"cameraFps\":%.2f,"
        "\"latencyMs\":%.2f,"
        "\"frameId\":%llu,"
        "\"droppedFrames\":%llu,"
        "\"lostFrames\":%d,"
        "\"resetCount\":%llu,"
        "\"recenterCount\":%llu,"
        "\"recentered\":%s,"
        "\"timing\":{"
            "\"totalMs\":%.3f,\"captureMs\":%.3f,\"decodeMs\":%.3f,"
            "\"detectMs\":%.3f,\"trackMs\":%.3f,\"stereoMs\":%.3f,"
            "\"motionMs\":%.3f,\"stateMs\":%.3f,\"imuMs\":%.3f},"
        "\"debug\":{\"enabled\":%s,"
            "\"runtimeS\":%.2f,\"framesProcessed\":%llu,"
            "\"avgFrameMs\":%.3f,\"minFrameMs\":%.3f,"
            "\"maxFrameMs\":%.3f,\"trackingFailures\":%llu,"
            "\"avgFeatures\":%.1f,\"imuSamples\":%llu,"
            "\"trajectoryM\":%.4f}}\n",
        st.timestamp,
        st.position.x(), st.position.y(), st.position.z(),
        st.velocity.x(), st.velocity.y(), st.velocity.z(),
        st.orientation.x(), st.orientation.y(),
        st.orientation.z(), st.orientation.w(),
        st.tracking ? "true" : "false",
        s.paused ? "true" : "false",
        st.trackedFeatures,
        st.inlierFeatures,
        s.stereoMatched,
        s.stereoTriangulated,
        s.stereoEnabled ? "true" : "false",
        s.imuEnabled ? "true" : "false",
        st.imuHealthy ? "true" : "false",
        s.processingFPS,
        s.captureFPS,
        s.latencySeconds * 1e3,
        static_cast<unsigned long long>(st.frameId),
        static_cast<unsigned long long>(st.droppedFrames),
        st.lostFrames,
        static_cast<unsigned long long>(s.resetCount),
        static_cast<unsigned long long>(s.recenterCount),
        s.originRecentered ? "true" : "false",
        stage[static_cast<int>(Stage::Total)],
        stage[static_cast<int>(Stage::Capture)],
        stage[static_cast<int>(Stage::Decode)],
        stage[static_cast<int>(Stage::Detect)],
        stage[static_cast<int>(Stage::Track)],
        stage[static_cast<int>(Stage::Stereo)],
        stage[static_cast<int>(Stage::Motion)],
        stage[static_cast<int>(Stage::State)],
        stage[static_cast<int>(Stage::Imu)],
        d.enabled ? "true" : "false",
        d.runtimeSeconds,
        static_cast<unsigned long long>(d.framesProcessed),
        d.averageFrameTimeMs,
        d.minFrameTimeMs,
        d.maxFrameTimeMs,
        static_cast<unsigned long long>(d.trackingFailures),
        d.averageTrackedFeatures,
        static_cast<unsigned long long>(d.imuSamples),
        d.trajectoryDistanceMeters
    ));
}

bool StateServer::handleCommand(Client& client,
                                const std::string& command)
{
    char response[4096];
    size_t length = 0;

    // Split into a verb and an optional argument.
    std::string verb = command;
    std::string argument;

    const size_t space = command.find(' ');

    if (space != std::string::npos)
    {
        verb = command.substr(0, space);
        argument = command.substr(space + 1);

        while (!argument.empty() && argument.front() == ' ')
        {
            argument.erase(argument.begin());
        }
    }

    if (verb == "GET_STATE")
    {
        length = formatState(response, sizeof(response));
    }
    else if (verb == "GET_STATS")
    {
        length = formatStats(response, sizeof(response));
    }
    else if (verb == "GET_DEBUG")
    {
        length = formatDebug(response, sizeof(response));
    }
    else if (verb == "GET_STATUS")
    {
        length = formatStatus(response, sizeof(response));
    }
    else if (verb == "GET_CAMERA")
    {
        length = formatCamera(response, sizeof(response));
    }
    else if (verb == "SUBSCRIBE")
    {
        double hz = config.webUpdateHz;

        if (!argument.empty())
        {
            hz = std::strtod(argument.c_str(), nullptr);
        }

        // Capped: a subscriber cannot make the server spin faster
        // than this no matter what it asks for.
        if (!(hz > 0.0))
        {
            hz = 1.0;
        }

        hz = std::min(hz, 60.0);

        client.subscribed = true;
        client.intervalSeconds = 1.0 / hz;
        client.nextSendTime = 0.0;   // send one immediately

        length = static_cast<size_t>(snprintf(
            response, sizeof(response),
            "{\"subscribed\":true,\"hz\":%.2f}\n", hz
        ));
    }
    else if (verb == "UNSUBSCRIBE")
    {
        client.subscribed = false;

        length = static_cast<size_t>(snprintf(
            response, sizeof(response), "{\"subscribed\":false}\n"
        ));
    }
    else if (verb == "PING")
    {
        length = static_cast<size_t>(
            snprintf(response, sizeof(response), "PONG\n")
        );
    }
    else if (verb == "QUIT" || verb.empty())
    {
        return false;
    }
    else
    {
        Command queued;

        // Control commands take an optional on/off argument; anything
        // that is not "off"/"false"/"0" counts as on.
        const bool flag = !(argument == "off" ||
                            argument == "false" ||
                            argument == "0");

        if (parseCommand(verb, flag, queued))
        {
            // Enqueued, not executed. The reply says so rather than
            // implying the change has already happened - the VIO
            // thread applies it at the next frame boundary.
            vio.commands().push(queued);

            length = static_cast<size_t>(snprintf(
                response, sizeof(response),
                "{\"queued\":\"%s\",\"flag\":%s}\n",
                commandName(queued.type),
                flag ? "true" : "false"
            ));
        }
        else
        {
            length = static_cast<size_t>(snprintf(
                response, sizeof(response),
                "{\"error\":\"unknown command\"}\n"
            ));
        }
    }

    if (length >= sizeof(response))
    {
        length = sizeof(response) - 1;
    }

    return sendLine(client.fd, response, length);
}

} // namespace novex
