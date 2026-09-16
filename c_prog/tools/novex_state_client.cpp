// Minimal example client for the novex-vio IPC socket.
//
// Deliberately depends on nothing but libc, to show how little a
// consumer needs: connect, write a word, read a line.
//
//   novex-state                    one GET_STATE, print, exit
//   novex-state --stats            one GET_STATS
//   novex-state --watch 10         poll GET_STATE ten times a second
//   novex-state --socket PATH      non-default socket

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <csignal>
#include <cstring>
#include <sys/socket.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

namespace
{

int connectTo(const char* path)
{
    const int fd = socket(AF_UNIX, SOCK_STREAM, 0);

    if (fd < 0)
    {
        fprintf(stderr, "socket(): %s\n", strerror(errno));
        return -1;
    }

    sockaddr_un address;

    memset(&address, 0, sizeof(address));

    address.sun_family = AF_UNIX;

    strncpy(address.sun_path, path, sizeof(address.sun_path) - 1);

    if (connect(fd,
                reinterpret_cast<sockaddr*>(&address),
                sizeof(address)) != 0)
    {
        fprintf(stderr,
                "connect(%s): %s\n"
                "Is novex-vio running with IPC enabled?\n",
                path, strerror(errno));

        close(fd);
        return -1;
    }

    return fd;
}

bool request(int fd, const char* command)
{
    char line[128];

    const int length = snprintf(line, sizeof(line), "%s\n", command);

    if (send(fd, line, static_cast<size_t>(length),
             MSG_NOSIGNAL) < 0)
    {
        fprintf(stderr, "send(): %s\n", strerror(errno));
        return false;
    }

    char response[2048];

    const ssize_t received =
        recv(fd, response, sizeof(response) - 1, 0);

    if (received <= 0)
    {
        fprintf(stderr, "the daemon closed the connection\n");
        return false;
    }

    response[received] = '\0';

    fputs(response, stdout);
    fflush(stdout);

    return true;
}

} // namespace

int main(int argc, char** argv)
{
    // Writing to a socket the daemon has already closed - which is
    // exactly what happens when it refuses a connection because it
    // already has its maximum number of clients - would otherwise
    // kill this process with SIGPIPE instead of letting it report the
    // condition and exit.
    signal(SIGPIPE, SIG_IGN);

    const char* socketPath = "/tmp/novex-vio.sock";
    const char* command = "GET_STATE";

    double watchHz = 0.0;

    for (int i = 1; i < argc; ++i)
    {
        if (strcmp(argv[i], "--socket") == 0 && i + 1 < argc)
        {
            socketPath = argv[++i];
        }
        else if (strcmp(argv[i], "--stats") == 0)
        {
            command = "GET_STATS";
        }
        else if (strcmp(argv[i], "--ping") == 0)
        {
            command = "PING";
        }
        else if (strcmp(argv[i], "--watch") == 0 && i + 1 < argc)
        {
            watchHz = atof(argv[++i]);
        }
        else
        {
            fprintf(stderr,
                    "usage: %s [--socket PATH] [--stats|--ping] "
                    "[--watch HZ]\n",
                    argv[0]);

            return 2;
        }
    }

    const int fd = connectTo(socketPath);

    if (fd < 0)
    {
        return 1;
    }

    int status = 0;

    if (watchHz <= 0.0)
    {
        status = request(fd, command) ? 0 : 1;
    }
    else
    {
        // The connection is held open across polls, which is what the
        // daemon expects: it keeps clients attached until they send
        // QUIT or disconnect.
        const double period = 1.0 / watchHz;

        timespec interval;

        interval.tv_sec = static_cast<time_t>(period);

        interval.tv_nsec =
            static_cast<long>((period - interval.tv_sec) * 1e9);

        while (request(fd, command))
        {
            nanosleep(&interval, nullptr);
        }

        status = 1;
    }

    send(fd, "QUIT\n", 5, MSG_NOSIGNAL);

    close(fd);

    return status;
}
