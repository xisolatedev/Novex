#include "Log.hpp"
#include "Time.hpp"

#include <cstdarg>
#include <cstdio>
#include <mutex>

namespace novex
{

namespace
{

LogLevel gLevel = LogLevel::Info;
std::mutex gMutex;

const char* levelName(LogLevel level)
{
    switch (level)
    {
        case LogLevel::Debug: return "DEBUG";
        case LogLevel::Info:  return "INFO ";
        case LogLevel::Warn:  return "WARN ";
        case LogLevel::Error: return "ERROR";
        default:              return "?????";
    }
}

} // namespace

void setLogLevel(LogLevel level)
{
    gLevel = level;
}

LogLevel logLevel()
{
    return gLevel;
}

void logWrite(LogLevel level, const char* fmt, ...)
{
    // Timestamped against process start rather than the raw monotonic
    // value, which is machine uptime and unreadable in a log.
    static const double start = monotonicSeconds();

    char message[512];

    va_list args;
    va_start(args, fmt);
    vsnprintf(message, sizeof(message), fmt, args);
    va_end(args);

    std::lock_guard<std::mutex> lock(gMutex);

    fprintf(
        stderr,
        "[%8.3f] %s  %s\n",
        monotonicSeconds() - start,
        levelName(level),
        message
    );

    fflush(stderr);
}

} // namespace novex
