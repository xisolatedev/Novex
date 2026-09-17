#pragma once

#include <atomic>
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>

namespace novex
{

enum class CommandType
{
    Reset,             // restart tracking and the estimator
    Recenter,          // keep tracking, redefine the reported origin
    Pause,             // stop processing frames, keep everything alive
    Resume,
    SetStereoEnabled,  // uses Command::flag
    SetImuEnabled,     // uses Command::flag
    StationaryTest,    // flag: start (true) or stop (false) the window
    ClearMap           // drop the accumulated point map, keep tracking
};

struct Command
{
    CommandType type = CommandType::Reset;
    bool flag = false;
};

const char* commandName(CommandType type);

// Parses a command word, as it arrives over IPC. Returns false for
// anything unrecognised rather than guessing.
bool parseCommand(const std::string& word, bool flag, Command& out);

// The one way anything outside the VIO thread is allowed to change
// estimator state.
//
// The IPC server, the GUI and the CLI all run on different threads
// from the pipeline. Letting any of them call reset() directly would
// mean tearing down the tracker's feature list while the tracker is
// halfway through using it. Instead they enqueue, and the VIO thread
// drains the queue at a point where doing the work is safe - between
// frames, never inside one.
//
// The queue is bounded and drops the OLDEST entry when full. A client
// stuck in a loop sending resets must not be able to grow this without
// limit on a 512 MB board, and for control commands the newest
// intent is the one that matters.
class CommandQueue
{
public:

    static constexpr size_t Capacity = 32;

    // Callable from any thread. Never blocks for longer than the
    // copy of one 2-byte struct.
    bool push(const Command& command);

    // VIO thread only. Moves everything pending into `out`, oldest
    // first, and leaves the queue empty.
    size_t drain(std::vector<Command>& out);

    uint64_t accepted() const { return acceptedCount.load(); }
    uint64_t dropped() const { return droppedCount.load(); }

private:

    mutable std::mutex mutex;
    std::vector<Command> pending;

    std::atomic<uint64_t> acceptedCount{0};
    std::atomic<uint64_t> droppedCount{0};
};

} // namespace novex
