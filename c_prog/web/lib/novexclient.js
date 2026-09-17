'use strict';

// Talks to the novex-vio daemon over its Unix domain socket.
//
// The protocol is newline-delimited: one command per line out, one
// JSON object per line back. SUBSCRIBE puts the daemon into push mode
// so this process does not poll.
//
// SUBSCRIBE_POINTS adds binary point cloud messages to the same
// stream, each framed as a text line "BIN <n>" followed by exactly n
// raw bytes. Parsing therefore works on Buffers, never on decoded
// strings: a binary payload is not valid UTF-8.
//
// This client holds NO authoritative state. It caches the last message
// purely so a browser that connects late gets something immediately
// instead of waiting for the next push.

const net = require('node:net');
const { EventEmitter } = require('node:events');

class NovexClient extends EventEmitter
{
    constructor({ socketPath, updateHz, pointsHz = 0 })
    {
        super();

        this.socketPath = socketPath;
        this.updateHz = updateHz;

        // 0 = not subscribed. Changed at run time with setPointsHz, so
        // the daemon only serialises points while someone is watching.
        this.pointsHz = pointsHz;

        this.socket = null;
        this.connected = false;
        this.stopped = false;
        this.pending = Buffer.alloc(0);

        // Bytes still owed to the current BIN payload, or -1 when the
        // next thing in the stream is a text line.
        this.binaryRemaining = -1;

        this.latest = null;
        this.latestAt = 0;

        // Requests waiting for a one-shot reply, oldest first. The
        // daemon answers in order on a single connection, so a queue
        // is enough to match replies to requests.
        this.waiting = [];

        this.reconnectDelay = 250;
    }

    start()
    {
        this._connect();
    }

    stop()
    {
        this.stopped = true;

        if (this.reconnectTimer)
        {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (this.socket)
        {
            try { this.socket.end(); } catch { /* already gone */ }
            this.socket.destroy();
            this.socket = null;
        }
    }

    // Sends a command and resolves with the daemon's reply. Used for
    // the REST endpoints; the live stream does not go through here.
    request(line, timeoutMs = 1000)
    {
        return new Promise((resolve, reject) =>
        {
            if (!this.connected || !this.socket)
            {
                reject(new Error('not connected to novex-vio'));
                return;
            }

            const entry = { resolve, reject };

            entry.timer = setTimeout(() =>
            {
                const index = this.waiting.indexOf(entry);
                if (index >= 0) this.waiting.splice(index, 1);
                reject(new Error('timed out waiting for novex-vio'));
            }, timeoutMs);

            this.waiting.push(entry);

            this.socket.write(line + '\n');
        });
    }

    _connect()
    {
        if (this.stopped)
        {
            return;
        }

        const socket = net.createConnection({ path: this.socketPath });

        this.socket = socket;

        socket.setNoDelay(true);

        socket.on('connect', () =>
        {
            this.connected = true;
            this.reconnectDelay = 250;
            this.pending = Buffer.alloc(0);
            this.binaryRemaining = -1;

            socket.write(`SUBSCRIBE ${this.updateHz}\n`);

            if (this.pointsHz > 0)
            {
                // Replies to subscription verbs are recognised by
                // shape in _onLine, not queued as request replies.
                socket.write(`SUBSCRIBE_POINTS ${this.pointsHz}\n`);
            }

            this.emit('status', { connected: true });
        });

        socket.on('data', (chunk) => this._onData(chunk));

        socket.on('error', () => { /* handled by close */ });

        socket.on('close', () =>
        {
            const wasConnected = this.connected;

            this.connected = false;
            this.socket = null;

            for (const entry of this.waiting)
            {
                clearTimeout(entry.timer);
                entry.reject(new Error('connection closed'));
            }

            this.waiting.length = 0;

            if (wasConnected)
            {
                this.emit('status', { connected: false });
            }

            this._scheduleReconnect();
        });
    }

    _scheduleReconnect()
    {
        if (this.stopped)
        {
            return;
        }

        // Backing off matters: novex-vio may not have created its
        // socket yet, or may have exited. Retrying in a tight loop
        // would burn CPU on a board that has none to spare.
        this.reconnectTimer = setTimeout(() =>
        {
            this.reconnectTimer = null;
            this._connect();
        }, this.reconnectDelay);

        this.reconnectDelay = Math.min(this.reconnectDelay * 2, 4000);
    }

    // Starts, retunes or (with 0) stops the point stream.
    setPointsHz(hz)
    {
        if (hz === this.pointsHz)
        {
            return;
        }

        this.pointsHz = hz;

        if (this.connected && this.socket)
        {
            this.socket.write(hz > 0
                ? `SUBSCRIBE_POINTS ${hz}\n`
                : 'UNSUBSCRIBE_POINTS\n');
        }
    }

    _onData(chunk)
    {
        this.pending = this.pending.length
            ? Buffer.concat([this.pending, chunk])
            : chunk;

        // A full map resynchronisation is the largest legitimate
        // message (500000 slots x 24 bytes); anything beyond a margin
        // over that is a broken stream.
        if (this.pending.length > 32 << 20)
        {
            this.pending = Buffer.alloc(0);
            this.binaryRemaining = -1;
            this.socket?.destroy();
            return;
        }

        let offset = 0;

        for (;;)
        {
            if (this.binaryRemaining >= 0)
            {
                if (this.pending.length - offset < this.binaryRemaining)
                {
                    break;
                }

                const payload = this.pending.subarray(
                    offset, offset + this.binaryRemaining
                );

                offset += this.binaryRemaining;
                this.binaryRemaining = -1;

                this.emit('points', payload);
                continue;
            }

            const newline = this.pending.indexOf(0x0a, offset);

            if (newline < 0)
            {
                break;
            }

            const line = this.pending.toString('utf8', offset, newline).trim();

            offset = newline + 1;

            if (line.startsWith('BIN '))
            {
                const length = Number(line.slice(4));

                if (!Number.isInteger(length) || length < 0)
                {
                    this.socket?.destroy();
                    return;
                }

                this.binaryRemaining = length;
                continue;
            }

            if (line.length > 0)
            {
                this._onLine(line);
            }
        }

        // Keep only the unconsumed tail. Copied, so the large buffer
        // it came from can be collected.
        this.pending = offset >= this.pending.length
            ? Buffer.alloc(0)
            : Buffer.from(this.pending.subarray(offset));
    }

    _onLine(line)
    {
        let message;

        try
        {
            message = JSON.parse(line);
        }
        catch
        {
            // PONG and other non-JSON replies land here.
            const entry = this.waiting.shift();

            if (entry)
            {
                clearTimeout(entry.timer);
                entry.resolve({ raw: line });
            }

            return;
        }

        if (message.type === 'vio_state')
        {
            this.latest = message;
            this.latestAt = Date.now();

            this.emit('state', message);
            return;
        }

        // Acknowledgements of the subscription verbs this client sends
        // on its own; they must not be mistaken for request replies.
        if ('pointsSubscribed' in message || 'subscribed' in message)
        {
            this.emit('subscription', message);
            return;
        }

        // Anything else is the reply to a request we made.
        const entry = this.waiting.shift();

        if (entry)
        {
            clearTimeout(entry.timer);
            entry.resolve(message);
        }
    }
}

module.exports = { NovexClient };
