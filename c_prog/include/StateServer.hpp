#pragma once

#include "Camera.hpp"
#include "VIO.hpp"
#include "VIOConfig.hpp"

#include <atomic>
#include <string>
#include <thread>
#include <vector>

namespace novex
{

// A line-oriented server on a Unix domain socket, so other local Novex
// processes can ask the daemon for its current state.
//
// A Unix socket rather than HTTP: there is no remote client, no
// routing, no content negotiation and no authentication story to get
// wrong. Filesystem permissions already answer "who may connect", and
// the whole protocol is one word in and one line out. An HTTP server
// would add a dependency and a thread pool to solve problems this
// system does not have.
//
// The server runs on its own thread and never touches the pipeline's
// data structures. It only calls VIO::snapshot(), which copies a small
// struct under a mutex the processing loop holds for a few microseconds
// once per frame. A slow or stalled client therefore cannot delay
// processing: it blocks on its own socket, not on the VIO.
//
// Protocol, one command per line:
//
//   GET_STATE        one line of JSON with the current estimate
//   GET_STATS        one line of JSON with timing and health
//   GET_DEBUG        detailed --debug statistics, or enabled:false
//   GET_STATUS       run mode and subsystem state
//   GET_CAMERA       negotiated camera mode
//   SUBSCRIBE <hz>   push state lines at up to <hz>, newest only
//   UNSUBSCRIBE
//   GET_DIAGNOSTICS  geometry of the latest frame + stationary report
//   SUBSCRIBE_POINTS <hz>
//                    push binary point cloud messages at up to <hz>
//   UNSUBSCRIBE_POINTS
//
// Binary messages share the line protocol: a text line
//
//   BIN <n>\n
//
// is followed by exactly n raw bytes (layout in PointCloud.hpp). A
// line-only client that never subscribes to points never sees one.
//   PING             -> PONG
//   QUIT             closes the connection
//
// Control commands, all of which are ENQUEUED for the VIO thread and
// answered immediately with {"queued":...} rather than waited on:
//
//   RESET            restart tracking and the estimator
//   RECENTER         keep tracking, move the reported origin
//   PAUSE / RESUME
//   SET_STEREO on|off
//   SET_IMU on|off
//   STATIONARY on|off    start / stop the stationary drift window
//   CLEAR_MAP            drop the point map, keep tracking
//
// SUBSCRIBE is what the Node server uses. Pushing beats polling here
// because the daemon already knows when a new state exists, and
// because a push that cannot be delivered is simply dropped: the
// newest state matters, intermediate ones do not.
class StateServer
{
public:

    // Takes VIO by non-const reference only to reach its command
    // queue. The server never touches estimator state directly; it
    // reads snapshots and enqueues commands.
    StateServer(const VIOConfig& config, VIO& vio);

    // Optional, for GET_CAMERA. The server only ever reads status
    // from it.
    void attachCamera(const Camera* camera) { this->camera = camera; }
    ~StateServer();

    StateServer(const StateServer&) = delete;
    StateServer& operator=(const StateServer&) = delete;

    bool start();
    void stop();

    bool isRunning() const { return running.load(); }

    const std::string& socketPath() const { return path; }

    uint64_t connectionsAccepted() const
    {
        return accepted.load();
    }

    uint64_t requestsServed() const { return served.load(); }

private:

    void serveLoop();

    struct Client
    {
        int fd = -1;

        bool subscribed = false;
        double intervalSeconds = 0.05;
        double nextSendTime = 0.0;

        // Point stream. The map is sent as deltas, so the server must
        // know what this client already holds: the map epoch and the
        // generation it has been brought up to.
        bool pointsSubscribed = false;
        double pointsInterval = 0.1;
        double nextPointsTime = 0.0;
        uint64_t liveSequence = 0;
        uint32_t mapEpoch = 0;
        uint32_t mapGeneration = 0;

        // Bytes accepted for this client but not yet taken by the
        // kernel. Non-empty means the client is behind: droppable
        // updates are skipped for it until this drains, and nothing
        // is ever written out of order or cut mid-message.
        std::vector<uint8_t> outbox;
        size_t outboxOffset = 0;

        uint64_t droppedUpdates = 0;
    };

    bool handleCommand(Client& client, const std::string& command);

    void pushSubscriptions(double now);

    void pushPoints(Client& client, double now);

    // Sends `data` to the client without blocking. If the client is
    // already behind, a `droppable` message is discarded and false is
    // returned; anything else is queued after what is pending.
    // Returns false also when the client should be closed.
    bool deliver(Client& client, const uint8_t* data, size_t length,
                 bool droppable, bool& closeClient);

    // Writes as much of the outbox as the socket will take.
    bool flush(Client& client);

    size_t formatState(char* buffer, size_t size) const;
    size_t formatStats(char* buffer, size_t size) const;
    size_t formatDebug(char* buffer, size_t size) const;
    size_t formatStatus(char* buffer, size_t size) const;
    size_t formatCamera(char* buffer, size_t size) const;
    size_t formatDiagnostics(char* buffer, size_t size) const;

    // The message pushed to subscribers: state, performance and
    // debug in one object, so the dashboard parses once per update.
    size_t formatStream(char* buffer, size_t size) const;

    // Command replies. Never dropped: queued behind pending data if
    // the client is slow. Returns false if the client is gone.
    bool sendLine(Client& client, const char* data, size_t length);

    // Server-thread scratch for building point messages, reused.
    std::vector<uint8_t> pointScratch;
    std::vector<uint8_t> pointPayload;

    const VIOConfig& config;
    VIO& vio;

    const Camera* camera = nullptr;

    std::string path;

    int listenFd = -1;

    // Touched only by the server thread.
    std::vector<Client> clients;

    std::thread worker;
    std::atomic<bool> running{false};
    std::atomic<bool> stopRequested{false};

    std::atomic<uint64_t> accepted{0};
    std::atomic<uint64_t> served{0};

public:

    // Point stream accounting, for the dashboard.
    uint64_t pointBytesSent() const { return pointBytes.load(); }
    uint64_t pointMessagesSent() const { return pointMessages.load(); }

private:

    std::atomic<uint64_t> pointBytes{0};
    std::atomic<uint64_t> pointMessages{0};
};

} // namespace novex
