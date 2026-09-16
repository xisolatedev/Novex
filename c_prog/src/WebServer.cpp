#include "WebServer.hpp"

#include "Log.hpp"

#include <cerrno>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

namespace novex
{

namespace
{

bool directoryExists(const std::string& path)
{
    struct stat info;

    return ::stat(path.c_str(), &info) == 0 && S_ISDIR(info.st_mode);
}

bool fileExists(const std::string& path)
{
    struct stat info;

    return ::stat(path.c_str(), &info) == 0 && S_ISREG(info.st_mode);
}

} // namespace

WebServer::WebServer(const VIOConfig& config)
    : config(config)
{
    dashboardUrl = "http://" + config.webHost + ":" +
                   std::to_string(config.webPort);
}

WebServer::~WebServer()
{
    stop();
}

std::string WebServer::resolveRoot() const
{
    if (!config.webRoot.empty() && config.webRoot.front() == '/')
    {
        return config.webRoot;
    }

    char buffer[4096];

    if (::getcwd(buffer, sizeof(buffer)) == nullptr)
    {
        return config.webRoot;
    }

    return std::string(buffer) + "/" + config.webRoot;
}

bool WebServer::start()
{
    if (!config.webEnabled)
    {
        return true;
    }

    root = resolveRoot();

    LOG_INFO("[WEB] Visualization server starting...");

    if (!config.webAutoStart)
    {
        LOG_INFO(
            "[WEB] auto-start disabled; run it yourself with: "
            "cd %s && NOVEX_SOCKET=%s PORT=%d node server.js",
            root.c_str(),
            config.ipcSocketPath.c_str(),
            config.webPort
        );

        return true;
    }

    const std::string entry = root + "/server.js";

    if (!directoryExists(root) || !fileExists(entry))
    {
        LOG_ERROR(
            "[WEB] no web server found at %s. Expected %s. "
            "Continuing without the dashboard.",
            root.c_str(),
            entry.c_str()
        );

        return true;
    }

    // No node_modules check, deliberately: the dashboard has zero npm
    // dependencies. Its WebSocket server is in web/lib/websocket.js
    // and Three.js is vendored under web/public/vendor, so there is
    // nothing to install and nothing that can fail on a board with no
    // network.

    const std::string node = config.webNodePath.empty()
        ? std::string("node")
        : config.webNodePath;

    const pid_t pid = ::fork();

    if (pid < 0)
    {
        LOG_ERROR("[WEB] fork(): %s", std::strerror(errno));
        return true;
    }

    if (pid == 0)
    {
        // ---- child ----

        // If the daemon dies for any reason - including SIGKILL,
        // which it cannot handle - the kernel signals this process
        // too. Without it a crashed novex-vio would leave an orphaned
        // Node server holding the port.
        ::prctl(PR_SET_PDEATHSIG, SIGTERM);

        // The parent ignores SIGINT handling for the child's sake;
        // restore the default so Ctrl-C in a shared terminal behaves.
        ::signal(SIGINT, SIG_DFL);
        ::signal(SIGTERM, SIG_DFL);

        if (::chdir(root.c_str()) != 0)
        {
            ::_exit(127);
        }

        // Configuration is passed by environment rather than argv so
        // the Node server has one obvious source of truth and can be
        // run by hand the same way.
        ::setenv("NOVEX_SOCKET", config.ipcSocketPath.c_str(), 1);
        ::setenv("NOVEX_HOST", config.webHost.c_str(), 1);
        ::setenv("PORT", std::to_string(config.webPort).c_str(), 1);

        ::setenv(
            "NOVEX_UPDATE_HZ",
            std::to_string(config.webUpdateHz).c_str(),
            1
        );

        ::setenv(
            "NOVEX_DEBUG",
            config.debugEnabled ? "1" : "0",
            1
        );

        ::execlp(node.c_str(), node.c_str(), "server.js",
                 static_cast<char*>(nullptr));

        // Only reached if exec failed.
        ::_exit(127);
    }

    // ---- parent ----

    childPid = pid;
    reported = false;

    LOG_INFO(
        "[WEB] Listening on %s  (open it in a browser)",
        dashboardUrl.c_str()
    );

    LOG_INFO(
        "[WEB] node pid %d, relaying from %s at %.0f Hz",
        static_cast<int>(childPid),
        config.ipcSocketPath.c_str(),
        config.webUpdateHz
    );

    return true;
}

void WebServer::poll()
{
    if (childPid <= 0)
    {
        return;
    }

    int status = 0;

    const pid_t result = ::waitpid(childPid, &status, WNOHANG);

    if (result == 0)
    {
        return;   // still running
    }

    if (result < 0 && errno == ECHILD)
    {
        childPid = -1;
        return;
    }

    if (result == childPid && !reported)
    {
        reported = true;

        if (WIFEXITED(status) && WEXITSTATUS(status) == 127)
        {
            LOG_ERROR(
                "[WEB] could not start node. Is Node.js installed and "
                "on PATH? The estimator is unaffected."
            );
        }
        else
        {
            LOG_WARN(
                "[WEB] the dashboard server exited (status %d). "
                "VIO continues normally.",
                WIFEXITED(status) ? WEXITSTATUS(status) : -1
            );
        }

        childPid = -1;
    }
}

void WebServer::stop()
{
    if (childPid <= 0)
    {
        return;
    }

    LOG_INFO("[WEB] stopping dashboard server");

    ::kill(childPid, SIGTERM);

    // Give it a moment to close its WebSocket connections and release
    // the port, then insist.
    for (int i = 0; i < 50; ++i)
    {
        int status = 0;

        const pid_t result = ::waitpid(childPid, &status, WNOHANG);

        if (result == childPid || (result < 0 && errno == ECHILD))
        {
            childPid = -1;
            return;
        }

        struct timespec pause;

        pause.tv_sec = 0;
        pause.tv_nsec = 20 * 1000 * 1000;   // 20 ms

        nanosleep(&pause, nullptr);
    }

    LOG_WARN("[WEB] server did not exit; sending SIGKILL");

    ::kill(childPid, SIGKILL);
    ::waitpid(childPid, nullptr, 0);

    childPid = -1;
}

} // namespace novex
