'use strict';

// A minimal RFC 6455 WebSocket server, built on node:http and
// node:crypto only.
//
// Why not `ws`: this dashboard has to run on a Raspberry Pi Zero 2 W
// that may have no network access at all, which makes `npm install` a
// deployment step that can simply fail in the field. What we actually
// need is a small subset - accept an upgrade, send text frames, honour
// ping/pong and close - and that subset is short enough to own.
//
// Binary frames are sent for the point cloud stream (see
// lib/pointcloud.js); incoming binary frames are ignored.
//
// Deliberately NOT implemented, because nothing here uses it:
//   * permessage-deflate (state updates are small and frequent;
//     compressing them would cost more CPU than it saves on loopback)
//   * fragmentation of outgoing messages (every message is one frame)
//   * subprotocol negotiation
//
// Incoming frames ARE handled, because browsers mask their traffic and
// send pings: text, ping, pong and close are all parsed.

const crypto = require('node:crypto');

const GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

const OPCODE = {
    CONTINUATION: 0x0,
    TEXT: 0x1,
    BINARY: 0x2,
    CLOSE: 0x8,
    PING: 0x9,
    PONG: 0xa,
};

function acceptKey(key)
{
    return crypto
        .createHash('sha1')
        .update(key + GUID)
        .digest('base64');
}

// Builds a single unfragmented server frame. Servers must not mask.
function encodeFrame(opcode, payload)
{
    const body = Buffer.isBuffer(payload)
        ? payload
        : Buffer.from(payload ?? '', 'utf8');

    const length = body.length;

    let header;

    if (length < 126)
    {
        header = Buffer.alloc(2);
        header[1] = length;
    }
    else if (length < 65536)
    {
        header = Buffer.alloc(4);
        header[1] = 126;
        header.writeUInt16BE(length, 2);
    }
    else
    {
        header = Buffer.alloc(10);
        header[1] = 127;
        // Node cannot write a 64-bit length as a plain number, and a
        // frame this large is not something this server produces.
        header.writeUInt32BE(0, 2);
        header.writeUInt32BE(length, 6);
    }

    header[0] = 0x80 | opcode;   // FIN + opcode

    return Buffer.concat([header, body]);
}

class Connection
{
    constructor(socket, server)
    {
        this.socket = socket;
        this.server = server;
        this.buffer = Buffer.alloc(0);
        this.closed = false;

        socket.on('data', (chunk) => this._onData(chunk));
        socket.on('error', () => this.close());
        socket.on('close', () => this._onClosed());
    }

    send(text)
    {
        return this._write(OPCODE.TEXT, text, 1 << 20);
    }

    // Binary frames carry point cloud messages. The default limit is
    // tighter than for text: a point message is large, and a browser
    // that has not drained the last one gains nothing from a second.
    sendBinary(buffer, limit = 256 << 10)
    {
        return this._write(OPCODE.BINARY, buffer, limit);
    }

    // Bytes accepted but not yet written to the network.
    get pending()
    {
        return this.socket.destroyed ? Infinity : this.socket.writableLength;
    }

    _write(opcode, payload, limit)
    {
        if (this.closed || this.socket.destroyed)
        {
            return false;
        }

        // Back-pressure guard. If the client is not draining - a
        // backgrounded tab, a stalled browser - we drop the update
        // rather than letting Node buffer it without limit. The next
        // state is more useful than a queue of stale ones, which is
        // the same rule the C++ side applies.
        if (this.socket.writableLength > limit)
        {
            return false;
        }

        try
        {
            this.socket.write(encodeFrame(opcode, payload));
            return true;
        }
        catch
        {
            this.close();
            return false;
        }
    }

    close(code = 1000)
    {
        if (this.closed)
        {
            return;
        }

        this.closed = true;

        try
        {
            const payload = Buffer.alloc(2);
            payload.writeUInt16BE(code, 0);

            this.socket.write(encodeFrame(OPCODE.CLOSE, payload));
            this.socket.end();
        }
        catch
        {
            this.socket.destroy();
        }
    }

    _onClosed()
    {
        this.closed = true;
        this.server._remove(this);
    }

    _onData(chunk)
    {
        this.buffer = Buffer.concat([this.buffer, chunk]);

        // A client that never completes a frame must not be able to
        // grow this without bound.
        if (this.buffer.length > 1 << 20)
        {
            this.close(1009);
            return;
        }

        for (;;)
        {
            const frame = this._readFrame();

            if (frame === null)
            {
                return;
            }

            this._handleFrame(frame);

            if (this.closed)
            {
                return;
            }
        }
    }

    // Returns null when a complete frame is not yet buffered.
    _readFrame()
    {
        const data = this.buffer;

        if (data.length < 2)
        {
            return null;
        }

        const opcode = data[0] & 0x0f;
        const masked = (data[1] & 0x80) !== 0;

        let length = data[1] & 0x7f;
        let offset = 2;

        if (length === 126)
        {
            if (data.length < offset + 2) return null;
            length = data.readUInt16BE(offset);
            offset += 2;
        }
        else if (length === 127)
        {
            if (data.length < offset + 8) return null;

            const high = data.readUInt32BE(offset);
            const low = data.readUInt32BE(offset + 4);

            if (high !== 0)
            {
                this.close(1009);
                return null;
            }

            length = low;
            offset += 8;
        }

        let mask = null;

        if (masked)
        {
            if (data.length < offset + 4) return null;
            mask = data.subarray(offset, offset + 4);
            offset += 4;
        }

        if (data.length < offset + length)
        {
            return null;
        }

        const payload = Buffer.from(
            data.subarray(offset, offset + length)
        );

        if (mask)
        {
            for (let i = 0; i < payload.length; ++i)
            {
                payload[i] ^= mask[i & 3];
            }
        }

        this.buffer = data.subarray(offset + length);

        return { opcode, payload };
    }

    _handleFrame(frame)
    {
        switch (frame.opcode)
        {
            case OPCODE.TEXT:
            case OPCODE.CONTINUATION:
                this.server._message(this, frame.payload.toString('utf8'));
                break;

            case OPCODE.PING:
                this.socket.write(encodeFrame(OPCODE.PONG, frame.payload));
                break;

            case OPCODE.PONG:
            case OPCODE.BINARY:
                break;

            case OPCODE.CLOSE:
                this.close();
                break;

            default:
                this.close(1003);
                break;
        }
    }
}

class WebSocketServer
{
    constructor(httpServer, { onConnect, onMessage, onClose } = {})
    {
        this.connections = new Set();
        this.onConnect = onConnect;
        this.onMessage = onMessage;
        this.onClose = onClose;

        httpServer.on('upgrade', (request, socket, head) =>
        {
            this._upgrade(request, socket, head);
        });
    }

    get size()
    {
        return this.connections.size;
    }

    broadcast(text)
    {
        let delivered = 0;

        for (const connection of this.connections)
        {
            if (connection.send(text))
            {
                ++delivered;
            }
        }

        return delivered;
    }

    closeAll()
    {
        for (const connection of [...this.connections])
        {
            connection.close(1001);   // going away
        }
    }

    _upgrade(request, socket, head)
    {
        const key = request.headers['sec-websocket-key'];

        if (request.headers.upgrade?.toLowerCase() !== 'websocket' || !key)
        {
            socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
            return;
        }

        socket.write(
            'HTTP/1.1 101 Switching Protocols\r\n' +
            'Upgrade: websocket\r\n' +
            'Connection: Upgrade\r\n' +
            `Sec-WebSocket-Accept: ${acceptKey(key)}\r\n` +
            '\r\n'
        );

        // Nagle would add latency to the small, frequent state frames
        // this server exists to deliver.
        socket.setNoDelay(true);

        const connection = new Connection(socket, this);

        this.connections.add(connection);

        if (head && head.length)
        {
            connection._onData(head);
        }

        this.onConnect?.(connection);
    }

    _remove(connection)
    {
        if (this.connections.delete(connection))
        {
            this.onClose?.(connection);
        }
    }

    _message(connection, text)
    {
        this.onMessage?.(connection, text);
    }
}

module.exports = { WebSocketServer };
