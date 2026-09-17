#include "CommandQueue.hpp"

#include <string>

namespace novex
{

const char* commandName(CommandType type)
{
    switch (type)
    {
        case CommandType::Reset:            return "reset";
        case CommandType::Recenter:         return "recenter";
        case CommandType::Pause:            return "pause";
        case CommandType::Resume:           return "resume";
        case CommandType::SetStereoEnabled: return "set-stereo";
        case CommandType::SetImuEnabled:    return "set-imu";
        case CommandType::StationaryTest:   return "stationary-test";
        case CommandType::ClearMap:         return "clear-map";
        default:                            return "?";
    }
}

bool parseCommand(const std::string& word, bool flag, Command& out)
{
    out.flag = flag;

    if (word == "RESET")     { out.type = CommandType::Reset;    return true; }
    if (word == "RECENTER")  { out.type = CommandType::Recenter; return true; }
    if (word == "PAUSE")     { out.type = CommandType::Pause;    return true; }
    if (word == "RESUME")    { out.type = CommandType::Resume;   return true; }

    if (word == "SET_STEREO")
    {
        out.type = CommandType::SetStereoEnabled;
        return true;
    }

    if (word == "STATIONARY")
    {
        out.type = CommandType::StationaryTest;
        return true;
    }

    if (word == "CLEAR_MAP")
    {
        out.type = CommandType::ClearMap;
        return true;
    }

    if (word == "SET_IMU")
    {
        out.type = CommandType::SetImuEnabled;
        return true;
    }

    return false;
}

bool CommandQueue::push(const Command& command)
{
    std::lock_guard<std::mutex> lock(mutex);

    if (pending.size() >= Capacity)
    {
        // Drop the oldest. For control commands the most recent
        // intent is what matters, and an unbounded queue is not an
        // option on this hardware.
        pending.erase(pending.begin());
        droppedCount.fetch_add(1);
    }

    pending.push_back(command);
    acceptedCount.fetch_add(1);

    return true;
}

size_t CommandQueue::drain(std::vector<Command>& out)
{
    out.clear();

    std::lock_guard<std::mutex> lock(mutex);

    if (pending.empty())
    {
        return 0;
    }

    out.swap(pending);

    return out.size();
}

} // namespace novex
