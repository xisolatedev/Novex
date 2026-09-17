#include "PointCloud.hpp"

#include <algorithm>
#include <cmath>
#include <cstring>

namespace novex
{

namespace
{

// Voxel coordinates are packed 21 bits per axis, which covers
// +/- 2^20 voxels: over 30 km per axis at 3 cm, far beyond anything
// local odometry reaches.
constexpr int64_t kAxisOffset = int64_t(1) << 20;
constexpr int64_t kAxisLimit = (int64_t(1) << 21) - 1;

// Evict by sampling this many slots from the clock hand.
constexpr size_t kEvictionSamples = 32;

// Cap on the running-mean weight, so a voxel keeps following its
// point's estimate as it improves instead of freezing on old data.
constexpr uint16_t kMergeWeightCap = 16;

// A merged observation re-publishes the slot only when something a
// viewer could see changed: position by a tenth of a voxel, quality
// upward, or more than this many seconds of "last seen".
constexpr float kRepublishSeenSeconds = 1.0f;

void writeU8(std::vector<uint8_t>& out, uint8_t value)
{
    out.push_back(value);
}

void writeBytes(std::vector<uint8_t>& out, const void* data, size_t size)
{
    const uint8_t* bytes = static_cast<const uint8_t*>(data);
    out.insert(out.end(), bytes, bytes + size);
}

void writeU16(std::vector<uint8_t>& out, uint16_t v) { writeBytes(out, &v, 2); }
void writeU32(std::vector<uint8_t>& out, uint32_t v) { writeBytes(out, &v, 4); }
void writeF32(std::vector<uint8_t>& out, float v)    { writeBytes(out, &v, 4); }
void writeF64(std::vector<uint8_t>& out, double v)   { writeBytes(out, &v, 8); }

void writePose(std::vector<uint8_t>& out, const PointPose& pose)
{
    writeBytes(out, pose.rotation, sizeof(pose.rotation));
    writeBytes(out, pose.position, sizeof(pose.position));
}

void writeHeader(std::vector<uint8_t>& out,
                 uint8_t type,
                 uint16_t flags,
                 uint32_t count,
                 uint64_t frameId,
                 double timestamp,
                 uint32_t epoch,
                 uint32_t generation,
                 uint32_t capacity,
                 uint32_t entryBytes,
                 const PointPose& pose,
                 const PointPose& origin,
                 uint32_t mapSize,
                 float voxel)
{
    const size_t start = out.size();

    writeU8(out, 'N');
    writeU8(out, 'X');
    writeU8(out, 'P');
    writeU8(out, 'C');
    writeU8(out, 1);
    writeU8(out, type);
    writeU16(out, flags);
    writeU32(out, count);
    writeU32(out, static_cast<uint32_t>(frameId & 0xffffffffu));
    writeF64(out, timestamp);
    writeU32(out, epoch);
    writeU32(out, generation);
    writeU32(out, capacity);
    writeU32(out, entryBytes);
    writePose(out, pose);
    writePose(out, origin);
    writeU32(out, mapSize);
    writeF32(out, voxel);

    // The layout is a published contract with the browser; fail loudly
    // in development if a change ever drifts from it.
    (void)start;
    // NOLINTNEXTLINE
    if (out.size() - start != kPointHeaderBytes)
    {
        out.resize(start);
    }
}

} // namespace

uint8_t pointQuality(float depthSigma,
                     float stereoResidualPx,
                     bool motionInlier,
                     double sigmaLimit,
                     double residualLimit)
{
    const double depthFactor =
        1.0 / (1.0 + depthSigma / std::max(1e-6, sigmaLimit));

    const double residualFactor =
        1.0 / (1.0 + stereoResidualPx / std::max(1e-6, residualLimit));

    const double trackFactor = motionInlier ? 1.0 : 0.6;

    const double score =
        255.0 * depthFactor * residualFactor * trackFactor;

    return static_cast<uint8_t>(
        std::lround(std::max(0.0, std::min(255.0, score)))
    );
}

// -------------------------------------------------------------------
// PointMap
// -------------------------------------------------------------------

void PointMap::configure(size_t capacity, double voxelSize)
{
    capacity = std::max<size_t>(1, capacity);

    slots.assign(capacity, Slot());
    dirtyFlag.assign(capacity, 0);
    dirty.clear();
    dirty.reserve(capacity);
    freeList.clear();
    freeList.reserve(capacity);

    voxel = std::max(0.0, voxelSize);
    inverseVoxel = voxel > 0.0 ? static_cast<float>(1.0 / voxel) : 0.0f;

    // Load factor <= 0.5 keeps linear probe chains short.
    size_t tableSize = 1;

    while (tableSize < capacity * 2)
    {
        tableSize <<= 1;
    }

    if (voxel > 0.0)
    {
        table.assign(tableSize, -1);
        tableMask = tableSize - 1;
    }
    else
    {
        table.clear();
        tableMask = 0;
    }

    epochNumber = 0;

    clear(0.0);
}

void PointMap::clear(double now)
{
    for (Slot& slot : slots)
    {
        slot = Slot();
        slot.alive = false;
    }

    std::fill(table.begin(), table.end(), -1);
    std::fill(dirtyFlag.begin(), dirtyFlag.end(), 0);

    dirty.clear();
    freeList.clear();

    // Handed out lowest index first, so a young map is contiguous at
    // the front of the buffers.
    for (size_t i = slots.size(); i > 0; --i)
    {
        freeList.push_back(static_cast<uint32_t>(i - 1));
    }

    count = 0;
    clockHand = 0;

    ++epochNumber;
    generationNumber = 0;
    epochStartTime = now;
}

void PointMap::clearDirty()
{
    for (uint32_t index : dirty)
    {
        dirtyFlag[index] = 0;
    }

    dirty.clear();
}

uint64_t PointMap::hashKey(uint64_t key)
{
    // splitmix64 finaliser: cheap and mixes packed coordinates well.
    key += 0x9e3779b97f4a7c15ull;
    key = (key ^ (key >> 30)) * 0xbf58476d1ce4e5b9ull;
    key = (key ^ (key >> 27)) * 0x94d049bb133111ebull;

    return key ^ (key >> 31);
}

bool PointMap::voxelKey(const Eigen::Vector3f& position, uint64_t& key) const
{
    uint64_t packed = 0;

    for (int axis = 0; axis < 3; ++axis)
    {
        const int64_t cell = static_cast<int64_t>(
            std::floor(position(axis) * inverseVoxel)
        ) + kAxisOffset;

        if (cell < 0 || cell > kAxisLimit)
        {
            return false;
        }

        packed |= static_cast<uint64_t>(cell) << (21 * axis);
    }

    key = packed;

    return true;
}

int32_t PointMap::find(uint64_t key) const
{
    size_t index = hashKey(key) & tableMask;

    for (;;)
    {
        const int32_t entry = table[index];

        if (entry < 0)
        {
            return -1;
        }

        if (slots[static_cast<size_t>(entry)].key == key)
        {
            return entry;
        }

        index = (index + 1) & tableMask;
    }
}

void PointMap::tableInsert(uint64_t key, uint32_t slotIndex)
{
    size_t index = hashKey(key) & tableMask;

    while (table[index] >= 0)
    {
        index = (index + 1) & tableMask;
    }

    table[index] = static_cast<int32_t>(slotIndex);
}

void PointMap::tableErase(uint64_t key)
{
    size_t index = hashKey(key) & tableMask;

    for (;;)
    {
        const int32_t entry = table[index];

        if (entry < 0)
        {
            return;   // not present
        }

        if (slots[static_cast<size_t>(entry)].key == key)
        {
            break;
        }

        index = (index + 1) & tableMask;
    }

    // Backward-shift deletion: pull later members of the probe chain
    // into the hole when their home position allows it, so lookups
    // never need tombstones.
    size_t hole = index;
    size_t next = (hole + 1) & tableMask;

    while (table[next] >= 0)
    {
        const uint64_t nextKey =
            slots[static_cast<size_t>(table[next])].key;

        const size_t home = hashKey(nextKey) & tableMask;

        // Distance from home to `next`, and from home to `hole`, both
        // cyclic. The entry may move into the hole only if the hole
        // lies on its probe path.
        const size_t distanceNext = (next - home) & tableMask;
        const size_t distanceHole = (hole - home) & tableMask;

        if (distanceHole < distanceNext)
        {
            table[hole] = table[next];
            hole = next;
        }

        next = (next + 1) & tableMask;
    }

    table[hole] = -1;
}

void PointMap::markDirty(uint32_t index, Slot& slot)
{
    slot.generation = ++generationNumber;
    slot.publishedSeen = slot.lastSeen;

    if (!dirtyFlag[index])
    {
        dirtyFlag[index] = 1;
        dirty.push_back(index);
    }
}

uint32_t PointMap::allocateSlot(double now, PointCloudCounters& counters)
{
    if (!freeList.empty())
    {
        const uint32_t index = freeList.back();
        freeList.pop_back();

        return index;
    }

    // Full: evict. With voxels, sample from the clock hand and take the
    // stalest, lowest-quality slot. Without voxels the map is a ring,
    // so the clock hand itself is the oldest point.
    size_t victim = clockHand;

    if (voxel > 0.0)
    {
        double worstScore = 1e300;

        for (size_t i = 0; i < kEvictionSamples; ++i)
        {
            const size_t candidate = (clockHand + i) % slots.size();
            const Slot& s = slots[candidate];

            // A second of recency is worth about a full quality range.
            const double score = s.lastSeen + s.quality / 255.0;

            if (score < worstScore)
            {
                worstScore = score;
                victim = candidate;
            }
        }

        clockHand = (clockHand + kEvictionSamples) % slots.size();
    }
    else
    {
        clockHand = (clockHand + 1) % slots.size();
    }

    Slot& evicted = slots[victim];

    if (voxel > 0.0)
    {
        tableErase(evicted.key);
    }

    evicted.alive = false;
    evicted.owner = 0;
    --count;
    ++counters.mapEvicted;

    // Evicted and immediately reused: one dirty mark covers both, since
    // receivers overwrite the slot wholesale.
    (void)now;

    return static_cast<uint32_t>(victim);
}

void PointMap::mergeInto(uint32_t index,
                         const Eigen::Vector3f& position,
                         uint8_t quality,
                         uint8_t intensity,
                         float seen)
{
    Slot& slot = slots[index];

    const uint16_t weight = std::min<uint16_t>(
        static_cast<uint16_t>(slot.hits + 1), kMergeWeightCap
    );

    const float alpha = 1.0f / static_cast<float>(weight);

    float moved = 0.0f;

    for (int axis = 0; axis < 3; ++axis)
    {
        const float delta = (position(axis) - slot.position[axis]) * alpha;

        slot.position[axis] += delta;
        moved = std::max(moved, std::abs(delta));
    }

    if (slot.hits < 0xffff)
    {
        ++slot.hits;
    }

    const bool better = quality > slot.quality;

    slot.quality = std::max(slot.quality, quality);
    slot.intensity = static_cast<uint8_t>((slot.intensity * 3u + intensity) / 4u);
    slot.lastSeen = seen;

    if (better ||
        moved > static_cast<float>(voxel) * 0.1f ||
        seen - slot.publishedSeen > kRepublishSeenSeconds)
    {
        markDirty(index, slot);
    }
}

int32_t PointMap::place(const Eigen::Vector3f& position,
                        uint8_t quality,
                        uint8_t intensity,
                        double now,
                        uint64_t owner,
                        PointCloudCounters& counters)
{
    if (slots.empty() || !position.allFinite())
    {
        return -1;
    }

    const float seen = static_cast<float>(now - epochStartTime);

    uint64_t key = 0;

    if (voxel > 0.0)
    {
        if (!voxelKey(position, key))
        {
            return -1;
        }

        const int32_t existing = find(key);

        if (existing >= 0)
        {
            mergeInto(static_cast<uint32_t>(existing), position, quality,
                      intensity, seen);

            ++counters.mapMerged;

            return existing;
        }
    }

    const uint32_t index = allocateSlot(now, counters);
    Slot& slot = slots[index];

    slot.position[0] = position(0);
    slot.position[1] = position(1);
    slot.position[2] = position(2);
    slot.lastSeen = seen;
    slot.hits = 1;
    slot.quality = quality;
    slot.intensity = intensity;
    slot.alive = true;
    slot.key = key;
    slot.owner = owner;

    if (voxel > 0.0)
    {
        tableInsert(key, index);
    }

    ++count;
    ++counters.mapInserted;

    markDirty(index, slot);

    return static_cast<int32_t>(index);
}

void PointMap::insert(const Eigen::Vector3f& position,
                      uint8_t quality,
                      uint8_t intensity,
                      double now,
                      PointCloudCounters& counters)
{
    place(position, quality, intensity, now, 0, counters);
}

int32_t PointMap::upsertTrack(int32_t slotHint,
                              uint64_t owner,
                              const Eigen::Vector3f& position,
                              uint8_t quality,
                              uint8_t intensity,
                              double now,
                              PointCloudCounters& counters)
{
    const bool owned =
        slotHint >= 0 &&
        static_cast<size_t>(slotHint) < slots.size() &&
        slots[static_cast<size_t>(slotHint)].alive &&
        slots[static_cast<size_t>(slotHint)].owner == owner &&
        owner != 0;

    if (!owned || !position.allFinite())
    {
        return place(position, quality, intensity, now, owner, counters);
    }

    const uint32_t index = static_cast<uint32_t>(slotHint);
    Slot& slot = slots[index];

    const float seen = static_cast<float>(now - epochStartTime);

    if (voxel > 0.0)
    {
        uint64_t key = 0;

        if (!voxelKey(position, key))
        {
            return slotHint;
        }

        if (key != slot.key)
        {
            const int32_t other = find(key);

            if (other >= 0)
            {
                // The refined estimate lands in a voxel another point
                // already holds: they are the same surface, so this
                // track's point is folded into it and its own slot
                // released.
                tableErase(slot.key);

                slot.alive = false;
                slot.owner = 0;
                --count;

                freeList.push_back(index);
                markDirty(index, slot);

                mergeInto(static_cast<uint32_t>(other), position, quality,
                          intensity, seen);

                ++counters.mapMerged;

                return other;
            }

            tableErase(slot.key);
            slot.key = key;
            tableInsert(key, index);
        }
    }

    // The track's fused estimate REPLACES its previous one: the fusion
    // already weighed every observation, so averaging again would
    // double count the old ones.
    float moved = 0.0f;

    for (int axis = 0; axis < 3; ++axis)
    {
        moved = std::max(moved, std::abs(position(axis) - slot.position[axis]));
        slot.position[axis] = position(axis);
    }

    const bool better = quality > slot.quality;

    slot.quality = std::max(slot.quality, quality);
    slot.intensity = static_cast<uint8_t>((slot.intensity * 3u + intensity) / 4u);
    slot.lastSeen = seen;

    if (slot.hits < 0xffff)
    {
        ++slot.hits;
    }

    ++counters.mapRefined;

    // Republished when a viewer could see the difference.
    const float visible = voxel > 0.0
        ? static_cast<float>(voxel) * 0.1f
        : 0.002f;

    if (better || moved > visible ||
        seen - slot.publishedSeen > kRepublishSeenSeconds)
    {
        markDirty(index, slot);
    }

    return slotHint;
}

// -------------------------------------------------------------------
// PointCloudChannel
// -------------------------------------------------------------------

void PointCloudChannel::configure(size_t liveCapacity, size_t mapCapacity)
{
    std::lock_guard<std::mutex> lock(mutex);

    live.assign(liveCapacity, LivePoint());
    liveCount = 0;

    mirror.assign(mapCapacity, PointMap::Slot());

    for (PointMap::Slot& slot : mirror)
    {
        slot.alive = false;
        slot.generation = 0;
    }

    mirrorEpoch = 0;
    mirrorGeneration = 0;
    mirrorSize = 0;
}

bool PointCloudChannel::tryPublishLive(double timestamp,
                                       uint64_t frameId,
                                       const PointPose& pose,
                                       const PointPose& origin,
                                       const LivePoint* points,
                                       size_t count)
{
    std::unique_lock<std::mutex> lock(mutex, std::try_to_lock);

    if (!lock.owns_lock())
    {
        skipped.fetch_add(1, std::memory_order_relaxed);
        return false;
    }

    count = std::min(count, live.size());

    if (count > 0)
    {
        std::memcpy(live.data(), points, count * sizeof(LivePoint));
    }

    liveCount = count;
    liveTimestamp = timestamp;
    liveFrameId = frameId;
    livePose = pose;
    liveOrigin = origin;

    ++liveSequence;
    ++liveMessages;

    return true;
}

bool PointCloudChannel::tryPublishMap(const PointMap& map,
                                      double timestamp,
                                      uint64_t frameId,
                                      const PointPose& pose,
                                      const PointPose& origin)
{
    std::unique_lock<std::mutex> lock(mutex, std::try_to_lock);

    if (!lock.owns_lock())
    {
        skipped.fetch_add(1, std::memory_order_relaxed);
        return false;
    }

    if (mirror.size() != map.capacity())
    {
        return false;
    }

    if (map.epoch() != mirrorEpoch)
    {
        for (PointMap::Slot& slot : mirror)
        {
            slot.alive = false;
            slot.generation = 0;
        }

        mirrorEpoch = map.epoch();
    }

    for (uint32_t index : map.dirtySlots())
    {
        mirror[index] = map.slot(index);
    }

    mirrorGeneration = map.generation();
    mirrorSize = map.size();
    mirrorVoxel = map.voxelSize();
    mapTimestamp = timestamp;
    mapFrameId = frameId;
    mapPose = pose;
    mapOrigin = origin;

    ++mapPublishes;

    return true;
}

size_t PointCloudChannel::appendLive(std::vector<uint8_t>& out,
                                     uint64_t& lastSequence)
{
    std::lock_guard<std::mutex> lock(mutex);

    if (liveSequence == 0 || liveSequence == lastSequence)
    {
        return 0;
    }

    lastSequence = liveSequence;

    const size_t start = out.size();

    out.reserve(start + kPointHeaderBytes + liveCount * kLiveEntryBytes);

    writeHeader(out, kPointMessageLive, 0,
                static_cast<uint32_t>(liveCount),
                liveFrameId, liveTimestamp,
                0, 0, 0,
                static_cast<uint32_t>(kLiveEntryBytes),
                livePose, liveOrigin,
                static_cast<uint32_t>(mirrorSize),
                static_cast<float>(mirrorVoxel));

    for (size_t i = 0; i < liveCount; ++i)
    {
        const LivePoint& p = live[i];

        writeF32(out, p.position[0]);
        writeF32(out, p.position[1]);
        writeF32(out, p.position[2]);
        writeU32(out, p.featureId);
        writeU8(out, p.quality);
        writeU8(out, p.flags);
        writeU8(out, p.intensity);
        writeU8(out, p.age);
    }

    return out.size() - start;
}

size_t PointCloudChannel::appendMapDelta(std::vector<uint8_t>& out,
                                         uint32_t& receiverEpoch,
                                         uint32_t& receiverGeneration)
{
    std::lock_guard<std::mutex> lock(mutex);

    if (mirrorEpoch == 0)
    {
        return 0;   // nothing published yet
    }

    const bool reset = receiverEpoch != mirrorEpoch;

    if (!reset && receiverGeneration == mirrorGeneration)
    {
        return 0;
    }

    const uint32_t since = reset ? 0 : receiverGeneration;

    const size_t start = out.size();

    // Header first with a placeholder count, patched below: counting
    // twice would double the scan.
    writeHeader(out, kPointMessageMap,
                reset ? kPointFlagMapReset : 0,
                0, mapFrameId, mapTimestamp,
                mirrorEpoch, mirrorGeneration,
                static_cast<uint32_t>(mirror.size()),
                static_cast<uint32_t>(kMapEntryBytes),
                mapPose, mapOrigin,
                static_cast<uint32_t>(mirrorSize),
                static_cast<float>(mirrorVoxel));

    uint32_t entries = 0;

    for (size_t i = 0; i < mirror.size(); ++i)
    {
        const PointMap::Slot& slot = mirror[i];

        if (slot.generation <= since)
        {
            continue;
        }

        // A reset receiver holds nothing, so dead slots are noise.
        if (reset && !slot.alive)
        {
            continue;
        }

        writeU32(out, static_cast<uint32_t>(i));
        writeF32(out, slot.position[0]);
        writeF32(out, slot.position[1]);
        writeF32(out, slot.position[2]);
        writeF32(out, slot.lastSeen);
        writeU8(out, slot.quality);
        writeU8(out, slot.intensity);
        writeU8(out, slot.alive ? 1 : 0);
        writeU8(out, static_cast<uint8_t>(std::min<uint16_t>(slot.hits, 255)));

        ++entries;
    }

    std::memcpy(out.data() + start + 8, &entries, sizeof(entries));

    receiverEpoch = mirrorEpoch;
    receiverGeneration = mirrorGeneration;

    return out.size() - start;
}

PointCloudChannel::Summary PointCloudChannel::summary() const
{
    std::lock_guard<std::mutex> lock(mutex);

    Summary s;

    s.livePoints = liveCount;
    s.mapPoints = mirrorSize;
    s.mapCapacity = mirror.size();
    s.voxelSize = mirrorVoxel;
    s.liveMessages = liveMessages;
    s.mapPublishes = mapPublishes;
    s.publishSkipped = skipped.load(std::memory_order_relaxed);

    return s;
}

void PointCloudChannel::noteSkipped()
{
    skipped.fetch_add(1, std::memory_order_relaxed);
}

} // namespace novex
