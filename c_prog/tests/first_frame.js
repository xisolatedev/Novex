// Connects fresh and reports how quickly it receives a state frame,
// proving a late or reconnecting browser is served immediately.
const net = require('node:net'), crypto = require('node:crypto');
const port = Number(process.argv[2] || 8087);
const key = crypto.randomBytes(16).toString('base64');
const started = Date.now();
const sock = net.createConnection({ host: '127.0.0.1', port });
let buf = Buffer.alloc(0), shook = false;
sock.on('connect', () => sock.write(
    `GET / HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\nUpgrade: websocket\r\n` +
    `Connection: Upgrade\r\nSec-WebSocket-Key: ${key}\r\n` +
    `Sec-WebSocket-Version: 13\r\n\r\n`));
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
        const text = buf.subarray(off, off + len).toString();
        buf = buf.subarray(off + len);
        if (op !== 1) continue;
        let m; try { m = JSON.parse(text); } catch { continue; }
        if (m.type === 'vio_state') {
            console.log(`GOT_STATE after ${Date.now() - started} ms, ` +
                `frameId=${m.frameId} tracking=${m.tracking} ` +
                `features=${m.trackedFeatures}`);
            process.exit(0);
        }
    }
});
sock.on('error', (e) => { console.log('ERROR ' + e.message); process.exit(1); });
setTimeout(() => { console.log('TIMEOUT'); process.exit(1); }, 5000);
