#pragma once

#include <Eigen/Core>

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <vector>

namespace novex
{

// ===================================================================
// 3D feature points and the accumulated point map
// ===================================================================
//
// COORDINATE FRAMES
// -----------------
// Everything here uses the Novex / OpenCV camera convention, right
// handed:
//
//     X right,  Y DOWN,  Z forward (the optical axis of the LEFT lens)
//
//   CAMERA-LOCAL point   P_camera, in the current left camera frame,
//                        exactly as stereo measured it.
//
//   INTERNAL WORLD point P_world = R_wc * P_camera + p_wc, where
//                        (R_wc, p_wc) is the estimator's INTERNAL pose
//                        for the frame the point was measured in. The
//                        internal world is the first tracked camera
//                        pose after start-up or reset. The map is
//                        stored in this frame.
//
//   REPORTED point       P_reported = R_o^T (P_world - p_o), where
//                        (R_o, p_o) is the recenter origin. Identity
//                        until RECENTER. Recenter never rewrites the
//                        map: it changes one transform, which is sent
//                        alongside every point message, so the whole
//                        map moves with the reported frame for free.
//
// The browser converts to Three.js (Y up, Z toward the viewer) with
// the proper rotation diag(1, -1, -1); see web/public/app.js.
//
// Nothing in this file invents points. Every point is a stereo
// measurement of a tracked feature.

// One stereo point as observed in the current frame.
struct LivePoint
{
    float position[3];      // camera-local, metres
    uint32_t featureId;
    float depth;            // z, metres
    float depthSigma;       // relative range uncertainty at 1 px
    float stereoResidualPx;
    uint8_t quality;        // 0..255 ranking score, see pointQuality()
    uint8_t intensity;      // left image grey level at the feature
    uint8_t age;            // track age in frames, clamped to 255
    uint8_t flags;          // LiveFlag bits
};

enum LiveFlag : uint8_t
{
    LiveFlagMotionInlier = 1 << 0,   // inlier of the accepted estimate
    LiveFlagMapEligible  = 1 << 1    // passed every map quality gate
};

// Ranking score for a stereo point, 0..255. NOT a probability. Each
// factor is 1 for a perfect measurement and exactly 0.5 at the
// configured map limit, so the score degrades smoothly rather than
// flipping at a threshold:
//
//   q = 255 * 1/(1 + sigma/sigmaLimit) * 1/(1 + residual/residualLimit)
//           * (motion inlier ? 1 : 0.6)
uint8_t pointQuality(float depthSigma,
                     float stereoResidualPx,
                     bool motionInlier,
                     double sigmaLimit,
                     double residualLimit);

// Counters for everything the point pipeline decided, run totals.
struct PointCloudCounters
{
    uint64_t generated = 0;         // stereo points seen
    uint64_t accepted = 0;          // passed every map gate
    uint64_t rejectedDepth = 0;
    uint64_t rejectedUncertainty = 0;
    uint64_t rejectedResidual = 0;
    uint64_t rejectedTrackAge = 0;
    uint64_t rejectedNotInlier = 0;
    uint64_t rejectedNoPose = 0;    // motion not accepted this frame
    uint64_t mapInserted = 0;       // new voxel / new slot
    uint64_t mapMerged = 0;         // fell into an occupied voxel
    uint64_t mapRefined = 0;        // track's own point moved to its
                                    // improved fused estimate
    uint64_t mapEvicted = 0;

    uint64_t rejected() const
    {
        return rejectedDepth + rejectedUncertainty + rejectedResidual +
               rejectedTrackAge + rejectedNotInlier + rejectedNoPose;
    }
};

// Fixed-budget world point map with optional voxel deduplication.
//
// Memory is allocated once, in configure(). Inserting never allocates.
//
// With voxelSize > 0, space is bucketed into cubes of that edge and
// each occupied cube holds ONE representative point: a running mean
// of the observations that fell in it (the mean's weight is capped so
// it keeps following a point whose estimate improves). Lookup is an
// open-addressing hash table with linear probing and backward-shift
// deletion - no tombstones, no rehash, O(1) per point.
//
// With voxelSize == 0 there is no deduplication and the map is a ring
// of the most recent accepted points.
//
// When the budget is reached, a clock hand samples a few slots and
// evicts the one that is stalest and lowest quality.
//
// Every change bumps a generation counter on the slot and records the
// slot as dirty, so publishers can send only what changed.
class PointMap
{
public:

    struct Slot
    {
        float position[3];
        float lastSeen;      // seconds since the map epoch began
        uint32_t generation; // map generation of the last visible change
        uint16_t hits;
        uint8_t quality;
        uint8_t intensity;
        bool alive;
        uint64_t key;
        float publishedSeen; // lastSeen when last marked dirty
        uint64_t owner;      // feature id that maintains it, 0 = none
    };

    void configure(size_t capacity, double voxelSize);

    // Drops every point and starts a new epoch. Receivers holding a
    // copy of the map must discard it when the epoch changes.
    void clear(double now);

    // `now` is the frame timestamp (seconds, monotonic).
    void insert(const Eigen::Vector3f& position,
                uint8_t quality,
                uint8_t intensity,
                double now,
                PointCloudCounters& counters);

    // Places or MOVES the point maintained by one feature track.
    //
    // `slotHint` is where this track's point was last placed. If that
    // slot is still alive and owned by `owner`, the point is moved to
    // `position` (the track's fused estimate) - re-bucketed if it
    // crossed into another voxel, or merged into that voxel's point if
    // the other voxel is already occupied. Otherwise it is inserted
    // like any other point. Returns the slot now holding it.
    int32_t upsertTrack(int32_t slotHint,
                        uint64_t owner,
                        const Eigen::Vector3f& position,
                        uint8_t quality,
                        uint8_t intensity,
                        double now,
                        PointCloudCounters& counters);

    size_t size() const { return count; }
    size_t capacity() const { return slots.size(); }
    double voxelSize() const { return voxel; }

    uint32_t epoch() const { return epochNumber; }
    uint32_t generation() const { return generationNumber; }
    double epochStart() const { return epochStartTime; }

    const Slot& slot(size_t index) const { return slots[index]; }

    // Slots changed since the last clearDirty(), each listed once.
    const std::vector<uint32_t>& dirtySlots() const { return dirty; }
    void clearDirty();

private:

    static uint64_t hashKey(uint64_t key);

    bool voxelKey(const Eigen::Vector3f& position, uint64_t& key) const;

    int32_t find(uint64_t key) const;
    void tableInsert(uint64_t key, uint32_t slotIndex);
    void tableErase(uint64_t key);

    uint32_t allocateSlot(double now, PointCloudCounters& counters);
    void markDirty(uint32_t index, Slot& slot);

    // Shared by insert and upsertTrack; returns the slot used.
    int32_t place(const Eigen::Vector3f& position, uint8_t quality,
                  uint8_t intensity, double now, uint64_t owner,
                  PointCloudCounters& counters);

    void mergeInto(uint32_t index, const Eigen::Vector3f& position,
                   uint8_t quality, uint8_t intensity, float seen);

    std::vector<Slot> slots;
    std::vector<uint32_t> freeList;
    std::vector<int32_t> table;       // slot index or -1
    size_t tableMask = 0;

    std::vector<uint32_t> dirty;
    std::vector<uint8_t> dirtyFlag;

    double voxel = 0.0;
    float inverseVoxel = 0.0f;

    size_t count = 0;
    size_t clockHand = 0;

    uint32_t epochNumber = 1;
    uint32_t generationNumber = 0;
    double epochStartTime = 0.0;
};

// ===================================================================
// Wire format
// ===================================================================
//
// Little-endian binary, identical on the daemon's Unix socket and on
// the browser WebSocket (the Node relay re-encodes map deltas per
// browser but keeps the format).
//
//   offset size
//     0     4   magic 'N','X','P','C'
//     4     1   version (1)
//     5     1   type: 1 = LIVE, 2 = MAP
//     6     2   flags: bit0 MAP_RESET - discard held map first
//     8     4   entry count
//    12     4   frame id (low 32 bits)
//    16     8   timestamp, f64 seconds (CLOCK_MONOTONIC)
//    24     4   map epoch
//    28     4   map generation reached after applying this message
//    32     4   map capacity (slots)
//    36     4   entry size in bytes
//    40    36   R_wc, f32 row-major  (LIVE: pose of these points;
//                                     MAP: latest pose)
//    76    12   p_wc, f32
//    88    36   R_o recenter origin rotation, f32 row-major
//   124    12   p_o, f32
//   136     4   map size (alive slots)
//   140     4   voxel size, f32 metres (0 = no voxels)
//   144   ...   entries
//
// LIVE entry, 20 bytes, camera-local:
//     f32 x, f32 y, f32 z, u32 feature id,
//     u8 quality, u8 flags, u8 intensity, u8 age
//
// MAP entry, 24 bytes, internal world frame:
//     u32 slot, f32 x, f32 y, f32 z, f32 lastSeen (s since epoch),
//     u8 quality, u8 intensity, u8 alive, u8 hits (clamped)

constexpr size_t kPointHeaderBytes = 144;
constexpr size_t kLiveEntryBytes = 20;
constexpr size_t kMapEntryBytes = 24;

constexpr uint8_t kPointMessageLive = 1;
constexpr uint8_t kPointMessageMap = 2;

constexpr uint16_t kPointFlagMapReset = 1;

// A pose as it travels with point data.
struct PointPose
{
    float rotation[9] = {1, 0, 0, 0, 1, 0, 0, 0, 1};
    float position[3] = {0, 0, 0};
};

// Shared between the VIO thread (writer) and the IPC server thread
// (reader).
//
// The VIO thread NEVER waits here. Both publish calls use try_lock and
// simply report failure when the server happens to be reading; the
// caller keeps its data and tries again on a later frame. The server
// holds the lock only while copying out what one message needs.
class PointCloudChannel
{
public:

    void configure(size_t liveCapacity, size_t mapCapacity);

    // ---- VIO thread ----

    bool tryPublishLive(double timestamp,
                        uint64_t frameId,
                        const PointPose& pose,
                        const PointPose& origin,
                        const LivePoint* points,
                        size_t count);

    // Copies the map's dirty slots into the shared mirror. On success
    // the caller clears the map's dirty list.
    bool tryPublishMap(const PointMap& map,
                       double timestamp,
                       uint64_t frameId,
                       const PointPose& pose,
                       const PointPose& origin);

    // ---- server thread ----

    // Appends a LIVE message to `out` if there is one newer than
    // `lastSequence`. Returns the bytes appended (0 = nothing new).
    size_t appendLive(std::vector<uint8_t>& out, uint64_t& lastSequence);

    // Appends a MAP message holding every slot newer than the
    // receiver's generation - or everything, with MAP_RESET, when the
    // receiver's epoch is stale. Updates epoch/generation to what the
    // message brings the receiver to. Returns bytes appended.
    size_t appendMapDelta(std::vector<uint8_t>& out,
                          uint32_t& receiverEpoch,
                          uint32_t& receiverGeneration);

    // Counters for the dashboard, copied under the lock.
    struct Summary
    {
        size_t livePoints = 0;
        size_t mapPoints = 0;
        size_t mapCapacity = 0;
        double voxelSize = 0.0;
        uint64_t liveMessages = 0;
        uint64_t mapPublishes = 0;
        uint64_t publishSkipped = 0;   // try_lock lost to a reader
    };

    Summary summary() const;

    void noteSkipped();

private:

    mutable std::mutex mutex;

    // Live: fixed arrays, count, sequence.
    std::vector<LivePoint> live;
    size_t liveCount = 0;
    uint64_t liveSequence = 0;
    double liveTimestamp = 0.0;
    uint64_t liveFrameId = 0;
    PointPose livePose;
    PointPose liveOrigin;

    // Map mirror, slot-parallel.
    std::vector<PointMap::Slot> mirror;
    uint32_t mirrorEpoch = 0;
    uint32_t mirrorGeneration = 0;
    size_t mirrorSize = 0;
    double mirrorVoxel = 0.0;
    double mapTimestamp = 0.0;
    uint64_t mapFrameId = 0;
    PointPose mapPose;
    PointPose mapOrigin;

    uint64_t liveMessages = 0;
    uint64_t mapPublishes = 0;

    // Counted without the lock, which is exactly the case it records.
    std::atomic<uint64_t> skipped{0};
};

} // namespace novex
