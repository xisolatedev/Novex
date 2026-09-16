#pragma once

namespace novex
{

enum class LogLevel
{
    Debug = 0,
    Info,
    Warn,
    Error,
    None
};

void setLogLevel(LogLevel level);
LogLevel logLevel();

// Writes to stderr so that stdout stays clean for anything a caller
// might want to pipe.
void logWrite(LogLevel level, const char* fmt, ...)
    __attribute__((format(printf, 2, 3)));

} // namespace novex

#define NOVEX_LOG(lvl, ...)                                  \
    do                                                       \
    {                                                        \
        if (novex::logLevel() <= (lvl))                      \
        {                                                    \
            novex::logWrite((lvl), __VA_ARGS__);             \
        }                                                    \
    } while (0)

#define LOG_DEBUG(...) NOVEX_LOG(novex::LogLevel::Debug, __VA_ARGS__)
#define LOG_INFO(...)  NOVEX_LOG(novex::LogLevel::Info,  __VA_ARGS__)
#define LOG_WARN(...)  NOVEX_LOG(novex::LogLevel::Warn,  __VA_ARGS__)
#define LOG_ERROR(...) NOVEX_LOG(novex::LogLevel::Error, __VA_ARGS__)

// Rate-limited logging. Daemon mode must not print per frame, but some
// messages are still worth seeing periodically. Each call site keeps
// its own timer.
#define LOG_EVERY(lvl, seconds, ...)                         \
    do                                                       \
    {                                                        \
        static double novexLogLast = -1e9;                   \
        const double novexLogNow = novex::monotonicSeconds();\
        if (novexLogNow - novexLogLast >= (seconds))         \
        {                                                    \
            novexLogLast = novexLogNow;                      \
            NOVEX_LOG(lvl, __VA_ARGS__);                     \
        }                                                    \
    } while (0)

#define LOG_INFO_EVERY(seconds, ...) \
    LOG_EVERY(novex::LogLevel::Info, seconds, __VA_ARGS__)

#define LOG_WARN_EVERY(seconds, ...) \
    LOG_EVERY(novex::LogLevel::Warn, seconds, __VA_ARGS__)
