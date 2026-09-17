// Connects as a browser would, collects the binary point cloud stream
// for a few seconds, rebuilds the map from the deltas, and prints one
// line of JSON describing what it received. test_web.sh compares that
// against the daemon's own counters.
//
//   node tests/points_client.js PORT [SECONDS]
const net = require('node:net'), crypto = require('node:crypto');
const port = Number(process.argv[2] || 8087);
const seconds = Number(process.argv[3] || 4);
const key = crypto.randomBytes(16).toString('base64');

const result = {
    liveMessages: 0, mapMessages: 0, badHeaders: 0,
    livePointsLast: 0, mapResets: 0, mirrorSize: 0,
    reportedMapSize: 0, maxLiveDepth: 0, minLiveDepth: Infinity,
    kbytes: 0,
};

const mirror = new Map();
const sock = net.createConnection({ host: '127.0.0.1', port });
let buf = Buffer.alloc(0), shook = false;

sock.on('connect', () => sock.write(
    `GET / HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\nUpgrade: websocket\r\n` +
    `Connection: Upgrade\r\nSec-WebSocket-Key: ${key}\r\n` +
    `Sec-WebSocket-Version: 13\r\n\r\n`));

function onBinary(p)
{
    result.kbytes += p.length / 1024;

    if (p.length < 144 || p.toString('latin1', 0, 4) !== 'NXPC') {
        ++result.badHeaders; return;
    }

    const type = p.readUInt8(5), flags = p.readUInt16LE(6);
    const count = p.readUInt32LE(8), entry = p.readUInt32LE(36);

    if (p.length !== 144 + count * entry) { ++result.badHeaders; return; }

    if (type === 1) {
        ++result.liveMessages;
        result.livePointsLast = count;
        for (let i = 0; i < count; ++i) {
            const z = p.readFloatLE(144 + i * 20 + 8);
            result.maxLiveDepth = Math.max(result.maxLiveDepth, z);
            result.minLiveDepth = Math.min(result.minLiveDepth, z);
        }
    } else if (type === 2) {
        ++result.mapMessages;
        if (flags & 1) { mirror.clear(); ++result.mapResets; }
        for (let i = 0; i < count; ++i) {
            const o = 144 + i * 24;
            const slot = p.readUInt32LE(o);
            if (p.readUInt8(o + 22)) mirror.set(slot, true); else mirror.delete(slot);
        }
        result.mirrorSize = mirror.size;
        result.reportedMapSize = p.readUInt32LE(136);
    }
}

sock.on('data', (c) => {
    buf = Buffer.concat([buf, c]);
    if (!shook) {
        const i = buf.indexOf('\r\n\r\n');
        if (i < 0) return;
        shook = true;
        buf = buf.subarray(i + 4);
    }
    for (;;) {
        if (buf.length < 2) return;
        const op = buf[0] & 0x0f;
        let len = buf[1] & 0x7f, off = 2;
        if (len === 126) { if (buf.length < 4) return; len = buf.readUInt16BE(2); off = 4; }
        else if (len === 127) { if (buf.length < 10) return; len = buf.readUInt32BE(6); off = 10; }
        if (buf.length < off + len) return;
        const payload = buf.subarray(off, off + len);
        buf = buf.subarray(off + len);
        if (op === 2) onBinary(Buffer.from(payload));
    }
});

sock.on('error', (e) => { console.log(JSON.stringify({ error: e.message })); process.exit(1); });

setTimeout(() => {
    if (!Number.isFinite(result.minLiveDepth)) result.minLiveDepth = 0;
    console.log(JSON.stringify(result));
    process.exit(0);
}, seconds * 1000);
