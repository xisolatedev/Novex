// Opens a WebSocket, subscribes, and then deliberately never reads.
// Used to prove the daemon drops undeliverable updates instead of
// blocking the VIO loop behind a wedged browser.
const net = require('node:net'), crypto = require('node:crypto');
const port = process.argv[2] || 8087;
const key = crypto.randomBytes(16).toString('base64');
const sock = net.createConnection({ host: '127.0.0.1', port: Number(port) });
sock.on('connect', () => {
    sock.write(`GET / HTTP/1.1\r\nHost: 127.0.0.1:${port}\r\n` +
        `Upgrade: websocket\r\nConnection: Upgrade\r\n` +
        `Sec-WebSocket-Key: ${key}\r\nSec-WebSocket-Version: 13\r\n\r\n`);
    // Stop reading entirely. The kernel receive buffer fills, then the
    // server's non-blocking send starts failing with EAGAIN.
    sock.pause();
});
sock.on('error', () => {});
setTimeout(() => process.exit(0), 30000);
