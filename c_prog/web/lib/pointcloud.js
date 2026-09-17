'use strict';

// Point cloud messages from novex-vio, and the relay's copy of the map.
//
// Wire format (little-endian), identical to include/PointCloud.hpp:
//
//   offset size
//     0     4   magic 'NXPC'
//     4     1   version (1)
//     5     1   type: 1 = LIVE, 2 = MAP
//     6     2   flags: bit0 MAP_RESET
//     8     4   entry count
//    12     4   frame id (low 32 bits)
//    16     8   timestamp f64
//    24     4   map epoch
//    28     4   map generation after this message
//    32     4   map capacity
//    36     4   entry size
//    40    36   R_wc f32 row-major
//    76    12   p_wc f32
//    88    36   R_o  f32 row-major (recenter origin)
//   124    12   p_o  f32
//   136     4   map size
//   140     4   voxel size f32
//   144   ...   entries (LIVE 20 bytes, MAP 24 bytes)
//
// LIVE messages are relayed to browsers byte for byte.
//
// MAP messages are deltas: they only make sense applied on top of the
// previous ones. The daemon tracks what THIS relay holds; the relay in
// turn tracks what each BROWSER holds, using the same epoch/generation
// scheme. So a browser that connects late, or whose socket was too
// backed up to take the last few deltas, is simply sent everything
// newer than what it has - nothing is ever lost, and nothing is ever
// sent twice to a browser that kept up.

const HEADER_BYTES = 144;
const LIVE_ENTRY_BYTES = 20;
const MAP_ENTRY_BYTES = 24;

const TYPE_LIVE = 1;
const TYPE_MAP = 2;

const FLAG_MAP_RESET = 1;

function parseHeader(buffer)
{
    if (buffer.length < HEADER_BYTES ||
        buffer.toString('latin1', 0, 4) !== 'NXPC' ||
        buffer.readUInt8(4) !== 1)
    {
        return null;
    }

    const header = {
        type: buffer.readUInt8(5),
        flags: buffer.readUInt16LE(6),
        count: buffer.readUInt32LE(8),
        frameId: buffer.readUInt32LE(12),
        timestamp: buffer.readDoubleLE(16),
        epoch: buffer.readUInt32LE(24),
        generation: buffer.readUInt32LE(28),
        capacity: buffer.readUInt32LE(32),
        entryBytes: buffer.readUInt32LE(36),
        mapSize: buffer.readUInt32LE(136),
        voxelSize: buffer.readFloatLE(140),
    };

    if (buffer.length !== HEADER_BYTES + header.count * header.entryBytes)
    {
        return null;
    }

    return header;
}

class MapMirror
{
    constructor()
    {
        this.capacity = 0;
        this.epoch = 0;
        this.generation = 0;
        this.mapSize = 0;
        this.voxelSize = 0;

        // Header bytes 12..144 of the latest MAP message (timestamp,
        // poses...), reused when encoding for browsers.
        this.headerTail = Buffer.alloc(HEADER_BYTES);

        this._allocate(0);
    }

    _allocate(capacity)
    {
        this.capacity = capacity;

        // One typed array per field, slot-parallel. Entries are copied
        // in as raw bytes, so a slot is exactly one 24-byte record.
        this.records = Buffer.alloc(capacity * MAP_ENTRY_BYTES);
        this.slotGeneration = new Uint32Array(capacity);
        this.alive = new Uint8Array(capacity);
    }

    // Applies a MAP message from the daemon.
    apply(buffer, header)
    {
        if (header.capacity !== this.capacity)
        {
            this._allocate(header.capacity);
        }

        if ((header.flags & FLAG_MAP_RESET) || header.epoch !== this.epoch)
        {
            this.slotGeneration.fill(0);
            this.alive.fill(0);
            this.epoch = header.epoch;
        }

        for (let i = 0; i < header.count; ++i)
        {
            const offset = HEADER_BYTES + i * MAP_ENTRY_BYTES;
            const slot = buffer.readUInt32LE(offset);

            if (slot >= this.capacity)
            {
                continue;
            }

            buffer.copy(this.records, slot * MAP_ENTRY_BYTES,
                        offset, offset + MAP_ENTRY_BYTES);

            this.slotGeneration[slot] = header.generation;
            this.alive[slot] = buffer.readUInt8(offset + 22);
        }

        this.generation = header.generation;
        this.mapSize = header.mapSize;
        this.voxelSize = header.voxelSize;

        buffer.copy(this.headerTail, 0, 0, HEADER_BYTES);
    }

    // Builds the MAP message that brings a receiver from its
    // (epoch, generation) up to date, or null if it already is.
    // Updates the receiver state only via the returned `next` values,
    // so the caller commits them only once the message is accepted.
    encodeFor(receiverEpoch, receiverGeneration)
    {
        if (this.epoch === 0)
        {
            return null;
        }

        const reset = receiverEpoch !== this.epoch;

        if (!reset && receiverGeneration === this.generation)
        {
            return null;
        }

        const since = reset ? 0 : receiverGeneration;

        let count = 0;

        for (let slot = 0; slot < this.capacity; ++slot)
        {
            if (this.slotGeneration[slot] > since &&
                (!reset || this.alive[slot]))
            {
                ++count;
            }
        }

        const out = Buffer.allocUnsafe(HEADER_BYTES + count * MAP_ENTRY_BYTES);

        this.headerTail.copy(out, 0, 0, HEADER_BYTES);

        out.writeUInt16LE(reset ? FLAG_MAP_RESET : 0, 6);
        out.writeUInt32LE(count, 8);
        out.writeUInt32LE(this.epoch, 24);
        out.writeUInt32LE(this.generation, 28);
        out.writeUInt32LE(this.capacity, 32);
        out.writeUInt32LE(MAP_ENTRY_BYTES, 36);

        let offset = HEADER_BYTES;

        for (let slot = 0; slot < this.capacity; ++slot)
        {
            if (this.slotGeneration[slot] > since &&
                (!reset || this.alive[slot]))
            {
                this.records.copy(out, offset, slot * MAP_ENTRY_BYTES,
                                  (slot + 1) * MAP_ENTRY_BYTES);
                offset += MAP_ENTRY_BYTES;
            }
        }

        return {
            buffer: out,
            next: { epoch: this.epoch, generation: this.generation },
        };
    }
}

module.exports = {
    HEADER_BYTES,
    LIVE_ENTRY_BYTES,
    MAP_ENTRY_BYTES,
    TYPE_LIVE,
    TYPE_MAP,
    FLAG_MAP_RESET,
    parseHeader,
    MapMirror,
};
