#include "StateServer.hpp"

#include "Log.hpp"
#include "Time.hpp"

#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <algorithm>
#include <cstdlib>
#include <fcntl.h>
#include <cstring>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <unistd.h>

#include <vector>

namespace novex
{

namespace
{

// A client more than this far behind is not a slow reader any more but
// a stuck one, and holding megabytes for it on a 512 MB board helps
// nobody. It is disconnected; it can reconnect and resynchronise.
constexpr size_t kMaxOutboxBytes = 16u << 20;

// Appends formatted text to a fixed buffer, tracking the offset and
// never overrunning. Hand-built JSON, like everything else here: no
// allocation and no dependency.
class JsonWriter
{
public:

    JsonWriter(char* buffer, size_t size) : buffer(buffer), size(size) {}

    __attribute__((format(printf, 2, 3)))
    void add(const char* format, ...)
    {
        if (used >= size)
        {
            return;
        }

        va_list arguments;
        va_start(arguments, format);

        const int written =
            vsnprintf(buffer + used, size - used, format, arguments);

        va_end(arguments);

        if (written > 0)
        {
            used += static_cast<size_t>(written);
        }

        // vsnprintf reports what it WOULD have written, so this
        // catches the overflow even though nothing was scribbled past
        // the end.
        if (used >= size)
        {
            overflow = true;
        }
    }

    size_t length() const { return std::min(used, size); }

    // True when the object was cut short. A truncated JSON object is
    // not valid JSON, so a caller must report it rather than send it.
    bool truncated() const { return overflow; }

private:

    char* buffer;
    size_t size;
    size_t used = 0;
    bool overflow = false;
};

// Static strings only (failure reasons, indications); they contain no
// characters needing escapes, but null must still become JSON null.
void addString(JsonWriter& json, const char* key, const char* value)
{
    if (value == nullptr)
    {
        json.add("\"%s\":null", key);
    }
    else
    {
        json.add("\"%s\":\"%s\"", key, value);
    }
}

// The geometry / drift / stationary / point cloud objects, shared by
// the push stream and GET_DIAGNOSTICS so the two can never disagree.
void addDiagnostics(JsonWriter& json, const VIOConfig& config,
                    const VIOSnapshot& s,
                    const PointCloudChannel::Summary& points,
                    uint64_t pointBytes, uint64_t pointMessages)
{
    const FrameDiagnostics& g = s.diagnostics;

    json.add("\"geometry\":{"
             "\"frameId\":%llu,"
             "\"flowMedianPx\":%.4f,\"flowMeanPx\":%.4f,"
             "\"trackRejected\":%d,\"detected\":%d,"
             "\"stereoValid\":%s,\"stereoAttempted\":%d,"
             "\"stereoPoints\":%d,\"stereoRejected\":%d,"
             "\"stereoRejectedMatch\":%d,\"stereoRejectedEpipolar\":%d,"
             "\"stereoRejectedDepth\":%d,"
             "\"disparityMedianPx\":%.3f,\"disparityStdPx\":%.3f,"
             "\"depthMedian\":%.4f,\"depthMin\":%.4f,\"depthMax\":%.4f,"
             "\"depthStd\":%.4f,"
             "\"stereoResidualPx\":%.4f,\"stereoVerticalOffsetPx\":%.4f,",
             static_cast<unsigned long long>(g.frameId),
             g.flowMedianPx, g.flowMeanPx,
             g.trackRejected, g.detectedFeatures,
             g.stereoValid ? "true" : "false", g.stereoAttempted,
             g.stereoPoints, g.stereoRejected,
             g.stereoRejectedMatch, g.stereoRejectedEpipolar,
             g.stereoRejectedDepth,
             g.disparityMedianPx, g.disparityStdPx,
             g.depthMedian, g.depthMin, g.depthMax, g.depthStd,
             g.stereoResidualMedianPx, g.stereoVerticalOffsetPx);

    json.add("\"motionAttempted\":%s,\"motionAccepted\":%s,",
             g.motionAttempted ? "true" : "false",
             g.motionAccepted ? "true" : "false");

    addString(json, "motionRejectReason", g.motionRejectReason);

    json.add(",\"correspondences\":%d,\"inliers\":%d,"
             "\"rejectedCorrespondences\":%d,\"inlierRatio\":%.4f,"
             "\"reprojectionMedianPx\":%.4f,\"reprojectionMaxPx\":%.4f,"
             "\"rotationSigmaDeg\":%.5f,\"translationSigmaMm\":%.4f,"
             "\"conditioning\":%.3e,\"referenceSpan\":%d,"
             "\"relativeRotationDeg\":%.5f,\"relativeTranslationMm\":%.4f,"
             "\"relativeRotationVectorDeg\":[%.5f,%.5f,%.5f],"
             "\"relativeTranslationVectorMm\":[%.4f,%.4f,%.4f],"
             "\"speed\":%.4f,\"poseDeltaMm\":%.4f,\"poseDeltaDeg\":%.5f,"
             "\"motionRejectedTotal\":%llu,\"referenceResetsTotal\":%llu,"
             "\"stereoRejectedTotal\":%llu,"
             "\"correspondencesRejectedTotal\":%llu},",
             g.correspondences, g.inliers,
             g.rejectedCorrespondences, g.inlierRatio,
             g.reprojectionMedianPx, g.reprojectionMaxPx,
             g.rotationSigmaDeg, g.translationSigmaMm,
             g.conditioning, g.referenceSpanFrames,
             g.relativeRotationDeg, g.relativeTranslationM * 1e3,
             g.relativeRotationVector[0] * 57.29577951308232,
             g.relativeRotationVector[1] * 57.29577951308232,
             g.relativeRotationVector[2] * 57.29577951308232,
             g.relativeTranslation[0] * 1e3,
             g.relativeTranslation[1] * 1e3,
             g.relativeTranslation[2] * 1e3,
             g.speed, g.poseDeltaM * 1e3, g.poseDeltaDeg,
             static_cast<unsigned long long>(g.motionRejectedTotal),
             static_cast<unsigned long long>(g.referenceResetsTotal),
             static_cast<unsigned long long>(g.stereoRejectedTotal),
             static_cast<unsigned long long>(g.correspondencesRejectedTotal));

    json.add("\"drift\":{\"accumulatedRotationDeg\":%.4f,"
             "\"accumulatedTranslationM\":%.5f,"
             "\"netRotationDeg\":%.4f,\"netTranslationM\":%.5f},",
             g.accumulatedRotationDeg, g.accumulatedTranslationM,
             g.netRotationDeg, g.netTranslationM);

    const StationaryReport& r = s.stationary;

    json.add("\"stationary\":{\"active\":%s,\"haveData\":%s,"
             "\"durationS\":%.2f,\"frames\":%llu,\"accepted\":%llu,"
             "\"rejected\":%llu,"
             "\"translationMeanMm\":%.4f,\"translationStdMm\":%.4f,"
             "\"translationBiasMm\":[%.5f,%.5f,%.5f],"
             "\"translationBiasSigma\":%.2f,"
             "\"rotationMeanDeg\":%.5f,\"rotationStdDeg\":%.5f,"
             "\"rotationBiasDeg\":[%.6f,%.6f,%.6f],"
             "\"rotationBiasSigma\":%.2f,"
             "\"flowPx\":%.4f,\"depthMedianM\":%.3f,"
             "\"reprojectionPx\":%.4f,\"inlierRatio\":%.4f,"
             "\"stereoResidualPx\":%.4f,\"stereoVerticalOffsetPx\":%.4f,"
             "\"positionDriftM\":%.5f,"
             "\"positionDrift\":[%.5f,%.5f,%.5f],"
             "\"orientationDriftDeg\":%.4f,"
             "\"measuredPositionDriftM\":%.5f,"
             "\"measuredOrientationDriftDeg\":%.4f,",
             r.active ? "true" : "false", r.haveData ? "true" : "false",
             r.durationSeconds,
             static_cast<unsigned long long>(r.frames),
             static_cast<unsigned long long>(r.acceptedEstimates),
             static_cast<unsigned long long>(r.rejectedEstimates),
             r.translationMeanMm, r.translationStdMm,
             r.translationBiasMm[0], r.translationBiasMm[1],
             r.translationBiasMm[2], r.translationBiasSignificance,
             r.rotationMeanDeg, r.rotationStdDeg,
             r.rotationBiasDeg[0], r.rotationBiasDeg[1],
             r.rotationBiasDeg[2], r.rotationBiasSignificance,
             r.flowMeanPx, r.depthMedianM,
             r.reprojectionMedianPx, r.inlierRatio,
             r.stereoResidualPx, r.stereoVerticalOffsetPx,
             r.positionDriftM,
             r.positionDrift[0], r.positionDrift[1], r.positionDrift[2],
             r.orientationDriftDeg,
             r.measuredPositionDriftM, r.measuredOrientationDriftDeg);

    addString(json, "indication", r.indication);

    const PointCloudCounters& c = s.pointCounters;

    json.add("},\"pointCloud\":{\"enabled\":%s,\"mapEnabled\":%s,"
             "\"livePoints\":%zu,\"mapPoints\":%zu,\"mapCapacity\":%zu,"
             "\"voxelSize\":%.4f,\"mapEpoch\":%u,"
             "\"generated\":%llu,\"accepted\":%llu,\"rejected\":%llu,"
             "\"rejectedDepth\":%llu,\"rejectedUncertainty\":%llu,"
             "\"rejectedResidual\":%llu,\"rejectedTrackAge\":%llu,"
             "\"rejectedNotInlier\":%llu,\"rejectedNoPose\":%llu,"
             "\"mapInserted\":%llu,\"mapMerged\":%llu,\"mapRefined\":%llu,"
             "\"mapEvicted\":%llu,\"innovationPct\":%.3f,"
             "\"innovationSamples\":%d,"
             "\"publishSkipped\":%llu,\"bytesSent\":%llu,"
             "\"messagesSent\":%llu},",
             s.pointCloudEnabled ? "true" : "false",
             s.pointMapEnabled ? "true" : "false",
             s.livePoints, s.mapPoints, s.mapCapacity,
             s.voxelSize, s.mapEpoch,
             static_cast<unsigned long long>(c.generated),
             static_cast<unsigned long long>(c.accepted),
             static_cast<unsigned long long>(c.rejected()),
             static_cast<unsigned long long>(c.rejectedDepth),
             static_cast<unsigned long long>(c.rejectedUncertainty),
             static_cast<unsigned long long>(c.rejectedResidual),
             static_cast<unsigned long long>(c.rejectedTrackAge),
             static_cast<unsigned long long>(c.rejectedNotInlier),
             static_cast<unsigned long long>(c.rejectedNoPose),
             static_cast<unsigned long long>(c.mapInserted),
             static_cast<unsigned long long>(c.mapMerged),
             static_cast<unsigned long long>(c.mapRefined),
             static_cast<unsigned long long>(c.mapEvicted),
             g.mapInnovationMedianPct, g.mapInnovationSamples,
             static_cast<unsigned long long>(points.publishSkipped),
             static_cast<unsigned long long>(pointBytes),
             static_cast<unsigned long long>(pointMessages));

    json.add("\"origin\":{\"orientation\":{\"x\":%.9f,\"y\":%.9f,"
             "\"z\":%.9f,\"w\":%.9f},"
             "\"position\":{\"x\":%.6f,\"y\":%.6f,\"z\":%.6f}}",
             s.originOrientation.x(), s.originOrientation.y(),
             s.originOrientation.z(), s.originOrientation.w(),
             s.originPosition.x(), s.originPosition.y(),
             s.originPosition.z());

    // ---- floor ----
    //
    // The plane is given in the REPORTED frame, like every other
    // position the dashboard receives, so the browser can draw it
    // without knowing that an internal frame exists. Normal and
    // point stay in Novex axes; the browser flips to Three.js
    // alongside the rest of the scene.
    const FloorEstimate& f = s.floor;

    const Eigen::Matrix3d originRotation =
        s.originOrientation.toRotationMatrix();

    const Plane reportedPlane =
        planeInFrame(f.worldPlane, originRotation, s.originPosition);

    const Eigen::Vector3d reportedPoint = f.worldPlane.valid()
        ? Eigen::Vector3d(originRotation.transpose() *
                          (f.floorPointWorld - s.originPosition))
        : Eigen::Vector3d::Zero();

    json.add(",\"floor\":{\"enabled\":%s,\"valid\":%s,",
             config.floorEnabled ? "true" : "false",
             f.valid ? "true" : "false");

    addString(json, "status", floorStatusName(f.status));
    json.add(",");
    addString(json, "downSource", floorDownSourceName(f.downSource));
    json.add(",");
    addString(json, "detail", f.detail);

    json.add(",\"confidence\":%.4f,\"ageS\":%.3f,"
             "\"heightM\":%.4f,\"distanceM\":%.4f,"
             "\"normal\":{\"x\":%.6f,\"y\":%.6f,\"z\":%.6f},"
             "\"normalCamera\":{\"x\":%.6f,\"y\":%.6f,\"z\":%.6f},"
             "\"offset\":%.6f,"
             "\"point\":{\"x\":%.4f,\"y\":%.4f,\"z\":%.4f},"
             "\"tiltDeg\":%.3f,\"pitchDeg\":%.3f,\"rollDeg\":%.3f,"
             "\"gravityDeg\":%.3f,"
             "\"candidates\":%d,\"inliers\":%d,"
             "\"inlierFraction\":%.4f,\"rmsResidualM\":%.5f,"
             "\"spanM\":%.4f,\"aboveFraction\":%.4f}",
             f.confidence, f.ageSeconds,
             f.cameraHeight, f.distanceToCamera,
             reportedPlane.normal.x(), reportedPlane.normal.y(),
             reportedPlane.normal.z(),
             f.normalCamera.x(), f.normalCamera.y(), f.normalCamera.z(),
             reportedPlane.offset,
             reportedPoint.x(), reportedPoint.y(), reportedPoint.z(),
             f.tiltDegrees, f.pitchDegrees, f.rollDegrees,
             f.gravityAngleDegrees,
             f.candidateCount, f.inlierCount,
             f.inlierFraction, f.rmsResidualM,
             f.spanMeters, f.aboveFraction);
}

} // namespace

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

    // Named so its CPU cost - which is the whole daemon-side cost of
    // serving the dashboard - can be read per thread in top or /proc.
    ::pthread_setname_np(::pthread_self(), "novex-ipc");

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

            // Only ask to be woken for writability while something is
            // actually waiting to go out; otherwise poll would return
            // immediately forever.
            if (client.outboxOffset < client.outbox.size())
            {
                entry.events |= POLLOUT;
            }

            descriptors.push_back(entry);

            anySubscribed = anySubscribed || client.subscribed ||
                            client.pointsSubscribed;
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

            if (events & POLLOUT)
            {
                keep = flush(*client);
            }

            if (keep && (events & POLLIN))
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
    // Sized for the full stream object, which carries geometry and
    // point cloud diagnostics as well as the state.
    char message[16384];

    size_t length = 0;
    bool formatted = false;

    for (Client& client : clients)
    {
        if (client.pointsSubscribed)
        {
            pushPoints(client, now);
        }

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

        // Droppable. If the receiver has not drained what it already
        // has, this update is skipped: the next one carries newer data
        // anyway, and queueing stale states would only add latency.
        bool closeClient = false;

        if (deliver(client, reinterpret_cast<const uint8_t*>(message),
                    length, true, closeClient))
        {
            served.fetch_add(1);
        }

        if (closeClient)
        {
            // Not closed here: the poll round still holds this fd.
            // Shutting it down makes the next poll report a hang-up,
            // and the normal path closes and removes it.
            ::shutdown(client.fd, SHUT_RDWR);
        }
    }
}

void StateServer::pushPoints(Client& client, double now)
{
    if (now < client.nextPointsTime)
    {
        return;
    }

    client.nextPointsTime = now + client.pointsInterval;

    // Behind: skip this round entirely. The live points are superseded
    // by the next ones, and the map delta is not lost - the client's
    // generation has not advanced, so the next delta covers it.
    if (client.outboxOffset < client.outbox.size())
    {
        ++client.droppedUpdates;
        return;
    }

    PointCloudChannel& channel = vio.pointChannel();

    // Each message is framed as "BIN <n>\n" + n bytes, and both kinds go
    // out in one write so the whole round is delivered or skipped as a
    // unit. Payloads are built into a reused scratch buffer.
    std::vector<uint8_t>& out = pointScratch;
    std::vector<uint8_t>& payload = pointPayload;

    out.clear();

    size_t messages = 0;

    auto append = [&]()
    {
        char line[32];

        const int lineLength =
            snprintf(line, sizeof(line), "BIN %zu\n", payload.size());

        out.insert(out.end(), line, line + lineLength);
        out.insert(out.end(), payload.begin(), payload.end());

        ++messages;
    };

    payload.clear();

    if (channel.appendLive(payload, client.liveSequence) > 0)
    {
        append();
    }

    payload.clear();

    if (channel.appendMapDelta(payload, client.mapEpoch,
                               client.mapGeneration) > 0)
    {
        append();
    }

    if (messages == 0)
    {
        return;
    }

    // Not droppable: the map delta has already advanced this client's
    // generation, so it must arrive complete.
    bool closeClient = false;

    deliver(client, out.data(), out.size(), false, closeClient);

    if (closeClient)
    {
        LOG_WARN_EVERY(
            5.0,
            "ipc: point subscriber fell more than %zu MB behind; "
            "disconnecting it",
            kMaxOutboxBytes >> 20
        );

        // Closed on the next poll round, which sees the hang-up.
        ::shutdown(client.fd, SHUT_RDWR);
        return;
    }

    pointBytes.fetch_add(out.size());
    pointMessages.fetch_add(messages);
}

bool StateServer::deliver(Client& client,
                          const uint8_t* data,
                          size_t length,
                          bool droppable,
                          bool& closeClient)
{
    closeClient = false;

    if (client.outboxOffset < client.outbox.size())
    {
        if (droppable)
        {
            ++client.droppedUpdates;
            return false;
        }

        if (client.outbox.size() - client.outboxOffset + length >
            kMaxOutboxBytes)
        {
            closeClient = true;
            return false;
        }

        const size_t held = client.outbox.size();

        client.outbox.resize(held + length);
        std::memcpy(client.outbox.data() + held, data, length);

        return true;
    }

    client.outbox.clear();
    client.outboxOffset = 0;

    ssize_t sent = ::send(
        client.fd,
        data,
        length,
        MSG_NOSIGNAL | MSG_DONTWAIT
    );

    if (sent < 0)
    {
        if (errno != EAGAIN && errno != EWOULDBLOCK)
        {
            closeClient = true;
            return false;
        }

        if (droppable)
        {
            ++client.droppedUpdates;
            return false;
        }

        sent = 0;
    }

    // A partial write cannot be dropped any more - the receiver has
    // the first half of a message - so the rest is queued, droppable
    // or not.
    if (static_cast<size_t>(sent) < length)
    {
        const size_t remaining = length - static_cast<size_t>(sent);

        client.outbox.resize(remaining);
        std::memcpy(client.outbox.data(), data + sent, remaining);
    }

    return true;
}

bool StateServer::flush(Client& client)
{
    while (client.outboxOffset < client.outbox.size())
    {
        const ssize_t sent = ::send(
            client.fd,
            client.outbox.data() + client.outboxOffset,
            client.outbox.size() - client.outboxOffset,
            MSG_NOSIGNAL | MSG_DONTWAIT
        );

        if (sent < 0)
        {
            return errno == EAGAIN || errno == EWOULDBLOCK;
        }

        client.outboxOffset += static_cast<size_t>(sent);
    }

    client.outbox.clear();
    client.outboxOffset = 0;

    return true;
}

bool StateServer::sendLine(Client& client, const char* data, size_t length)
{
    bool closeClient = false;

    deliver(client, reinterpret_cast<const uint8_t*>(data), length, false,
            closeClient);

    if (closeClient)
    {
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
        "\"lost_frames\":%d,"
        "\"floor_valid\":%s,"
        "\"floor_status\":\"%s\","
        "\"floor_height\":%.4f,"
        "\"floor_confidence\":%.3f}\n",
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
        state.lostFrames,
        snapshot.floor.valid ? "true" : "false",
        floorStatusName(snapshot.floor.status),
        snapshot.floor.cameraHeight,
        snapshot.floor.confidence
    ));
}

// The full ground estimate, in both frames plus the reported one.
//
// A consumer that only wants "how high am I" reads floor_height from
// GET_STATE. A consumer placing a virtual floor wants the world plane
// from here, because that is the one that stays put while the head
// turns.
size_t StateServer::formatFloor(char* buffer, size_t size) const
{
    const VIOSnapshot snapshot = vio.snapshot();
    const FloorEstimate& floor = snapshot.floor;

    // The world plane lives in the INTERNAL frame. Everything else the
    // server reports is in the RECENTERED frame, so convert it rather
    // than handing out two different conventions under one roof.
    const Eigen::Matrix3d originRotation =
        snapshot.originOrientation.toRotationMatrix();

    const Plane reported = planeInFrame(floor.worldPlane,
                                        originRotation,
                                        snapshot.originPosition);

    const Eigen::Vector3d reportedPoint = floor.worldPlane.valid()
        ? Eigen::Vector3d(originRotation.transpose() *
                          (floor.floorPointWorld - snapshot.originPosition))
        : Eigen::Vector3d::Zero();

    return static_cast<size_t>(snprintf(
        buffer,
        size,
        "{\"valid\":%s,"
        "\"status\":\"%s\","
        "\"down_source\":\"%s\","
        "\"confidence\":%.4f,"
        "\"timestamp\":%.6f,"
        "\"frame_id\":%llu,"
        "\"age_s\":%.3f,"
        "\"camera_plane\":[%.6f,%.6f,%.6f,%.6f],"
        "\"world_plane\":[%.6f,%.6f,%.6f,%.6f],"
        "\"reported_plane\":[%.6f,%.6f,%.6f,%.6f],"
        "\"normal_camera\":[%.6f,%.6f,%.6f],"
        "\"normal_world\":[%.6f,%.6f,%.6f],"
        "\"distance_m\":%.4f,"
        "\"height_m\":%.4f,"
        "\"floor_point_camera\":[%.4f,%.4f,%.4f],"
        "\"floor_point_world\":[%.4f,%.4f,%.4f],"
        "\"floor_point_reported\":[%.4f,%.4f,%.4f],"
        "\"tilt_deg\":%.3f,"
        "\"pitch_deg\":%.3f,"
        "\"roll_deg\":%.3f,"
        "\"gravity_deg\":%.3f,"
        "\"candidates\":%d,"
        "\"inliers\":%d,"
        "\"inlier_fraction\":%.4f,"
        "\"rms_residual_m\":%.5f,"
        "\"span_m\":%.4f,"
        "\"above_fraction\":%.4f,"
        "\"detail\":\"%s\"}\n",
        floor.valid ? "true" : "false",
        floorStatusName(floor.status),
        floorDownSourceName(floor.downSource),
        floor.confidence,
        floor.timestamp,
        static_cast<unsigned long long>(floor.frameId),
        floor.ageSeconds,
        floor.cameraPlane.normal.x(), floor.cameraPlane.normal.y(),
        floor.cameraPlane.normal.z(), floor.cameraPlane.offset,
        floor.worldPlane.normal.x(), floor.worldPlane.normal.y(),
        floor.worldPlane.normal.z(), floor.worldPlane.offset,
        reported.normal.x(), reported.normal.y(),
        reported.normal.z(), reported.offset,
        floor.normalCamera.x(), floor.normalCamera.y(),
        floor.normalCamera.z(),
        floor.normalWorld.x(), floor.normalWorld.y(),
        floor.normalWorld.z(),
        floor.distanceToCamera,
        floor.cameraHeight,
        floor.floorPointCamera.x(), floor.floorPointCamera.y(),
        floor.floorPointCamera.z(),
        floor.floorPointWorld.x(), floor.floorPointWorld.y(),
        floor.floorPointWorld.z(),
        reportedPoint.x(), reportedPoint.y(), reportedPoint.z(),
        floor.tiltDegrees,
        floor.pitchDegrees,
        floor.rollDegrees,
        floor.gravityAngleDegrees,
        floor.candidateCount,
        floor.inlierCount,
        floor.inlierFraction,
        floor.rmsResidualM,
        floor.spanMeters,
        floor.aboveFraction,
        floor.detail ? floor.detail : ""
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

size_t StateServer::formatDiagnostics(char* buffer, size_t size) const
{
    const VIOSnapshot s = vio.snapshot();

    JsonWriter json(buffer, size);

    json.add("{");
    addDiagnostics(json, config, s, vio.pointChannel().summary(),
                   pointBytes.load(), pointMessages.load());
    json.add("}\n");

    if (json.truncated())
    {
        LOG_WARN_EVERY(5.0,
                       "ipc: the diagnostics object does not fit in "
                       "%zu bytes and was truncated", size);

        return static_cast<size_t>(snprintf(
            buffer, size,
            "{\"error\":\"diagnostics exceeded the response buffer\"}\n"
        ));
    }

    return json.length();
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
    const int head = snprintf(
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
            "\"motionMs\":%.3f,\"stateMs\":%.3f,\"imuMs\":%.3f,"
            "\"pointsMs\":%.3f},"
        "\"debug\":{\"enabled\":%s,"
            "\"runtimeS\":%.2f,\"framesProcessed\":%llu,"
            "\"avgFrameMs\":%.3f,\"minFrameMs\":%.3f,"
            "\"maxFrameMs\":%.3f,\"trackingFailures\":%llu,"
            "\"avgFeatures\":%.1f,\"imuSamples\":%llu,"
            "\"trajectoryM\":%.4f},",
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
        stage[static_cast<int>(Stage::PointCloud)],
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
    );

    if (head <= 0 || static_cast<size_t>(head) >= size)
    {
        return static_cast<size_t>(std::max(head, 0));
    }

    JsonWriter json(buffer + head, size - static_cast<size_t>(head));

    addDiagnostics(json, config, s, vio.pointChannel().summary(),
                   pointBytes.load(), pointMessages.load());

    json.add("}\n");

    if (json.truncated())
    {
        // Dropping the update is the only safe move: half an object
        // would desynchronise every subscriber's parser.
        LOG_WARN_EVERY(5.0,
                       "ipc: the state stream object does not fit in "
                       "%zu bytes and was dropped", size);

        return 0;
    }

    return static_cast<size_t>(head) + json.length();
}

bool StateServer::handleCommand(Client& client,
                                const std::string& command)
{
    // Sized for the largest reply, which is GET_DIAGNOSTICS: the
    // geometry, drift, stationary, point cloud and floor objects in
    // one message. Matches the push stream's buffer.
    char response[16384];
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
    else if (verb == "GET_FLOOR")
    {
        length = formatFloor(response, sizeof(response));
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
    else if (verb == "GET_DIAGNOSTICS")
    {
        length = formatDiagnostics(response, sizeof(response));
    }
    else if (verb == "SUBSCRIBE_POINTS")
    {
        double hz = 10.0;

        if (!argument.empty())
        {
            hz = std::strtod(argument.c_str(), nullptr);
        }

        if (!(hz > 0.0))
        {
            hz = 1.0;
        }

        hz = std::min(hz, 30.0);

        client.pointsSubscribed = true;
        client.pointsInterval = 1.0 / hz;
        client.nextPointsTime = 0.0;

        length = static_cast<size_t>(snprintf(
            response, sizeof(response),
            "{\"pointsSubscribed\":true,\"hz\":%.2f,"
            "\"enabled\":%s}\n",
            hz, config.pointCloudEnabled ? "true" : "false"
        ));
    }
    else if (verb == "UNSUBSCRIBE_POINTS")
    {
        // The client's map epoch / generation are kept: a later
        // SUBSCRIBE_POINTS continues with deltas from where it was.
        client.pointsSubscribed = false;

        length = static_cast<size_t>(snprintf(
            response, sizeof(response), "{\"pointsSubscribed\":false}\n"
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

    return sendLine(client, response, length);
}

} // namespace novex
