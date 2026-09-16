#pragma once

#include "VIOConfig.hpp"

#include <string>
#include <sys/types.h>

namespace novex
{

// Starts and supervises the Node.js visualisation server as a managed
// child process.
//
// Why a child process rather than an HTTP/WebSocket stack inside C++:
//
//   * The dashboard is Three.js, which means the frontend is
//     JavaScript regardless. Node is already the natural host for it.
//   * Embedding an HTTP and WebSocket server in the daemon would add a
//     dependency to a project whose rule is that every dependency
//     needs a reason, and would put TLS-shaped attack surface inside
//     the process that drives the camera.
//   * Keeping it out-of-process means a crash, a hang, or a wedged
//     browser in the visualisation layer cannot take the estimator
//     with it. The worst case is that the dashboard goes blank.
//
// The cost is a process boundary, paid via the Unix socket the daemon
// already exposes. The Node server is a relay: it subscribes to the
// socket and rebroadcasts over WebSocket. It holds no state of its own
// and is not authoritative for anything.
//
// Lifecycle is bound to the daemon: the child is started after the
// pipeline is up and terminated on shutdown, and it is asked to die
// with its parent so an abrupt exit cannot leave it orphaned.
class WebServer
{
public:

    explicit WebServer(const VIOConfig& config);
    ~WebServer();

    WebServer(const WebServer&) = delete;
    WebServer& operator=(const WebServer&) = delete;

    // Returns false only for a configuration problem worth stopping
    // for. A missing Node runtime is reported and tolerated: the
    // estimator does not need a dashboard.
    bool start();

    void stop();

    // Reaps the child if it has exited, so a crashed dashboard is
    // noticed and reported once rather than lingering as a zombie.
    // Safe to call every loop iteration; does not block.
    void poll();

    bool isRunning() const { return childPid > 0; }

    const std::string& url() const { return dashboardUrl; }

private:

    std::string resolveRoot() const;

    const VIOConfig& config;

    pid_t childPid = -1;

    bool reported = false;

    std::string dashboardUrl;
    std::string root;
};

} // namespace novex
