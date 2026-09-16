'use strict';

// Talks to the novex-vio daemon over its Unix domain socket.
//
// The protocol is newline-delimited: one command per line out, one
// JSON object per line back. SUBSCRIBE puts the daemon into push mode
// so this process does not poll.
//
// This client holds NO authoritative state. It caches the last message
// purely so a browser that connects late gets something immediately
// instead of waiting for the next push.

const net = require('node:net');
const { EventEmitter } = require('node:events');

class NovexClient extends EventEmitter
{
    constructor({ socketPath, updateHz })
    {
        super();

        this.socketPath = socketPath;
        this.updateHz = updateHz;

        this.socket = null;
        this.connected = false;
        this.stopped = false;
        this.pending = '';

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
            this.pending = '';

            socket.write(`SUBSCRIBE ${this.updateHz}\n`);

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

    _onData(chunk)
    {
        this.pending += chunk.toString('utf8');

        // Guard against a partial line growing without bound if the
        // daemon ever stopped emitting newlines.
        if (this.pending.length > 1 << 20)
        {
            this.pending = '';
            return;
        }

        let index;

        while ((index = this.pending.indexOf('\n')) >= 0)
        {
            const line = this.pending.slice(0, index).trim();

            this.pending = this.pending.slice(index + 1);

            if (line.length === 0)
            {
                continue;
            }

            this._onLine(line);
        }
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
