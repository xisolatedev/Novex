'use strict';

// Novex VIO development dashboard server.
//
//   novex-vio  --(Unix socket, SUBSCRIBE)-->  this process
//                                                  |
//                                            WebSocket + HTTP
//                                                  |
//                                              browser (Three.js)
//
// This is a RELAY. It owns no VIO state, it cannot compute anything,
// and if it dies the estimator does not notice. Everything it serves
// came from the daemon.
//
// Zero npm dependencies, on purpose: this has to be deployable to a
// Raspberry Pi that may have no network, where `npm install` is a step
// that can fail in the field.
//
// Configuration comes from the environment, which is how novex-vio
// passes it when it spawns this process:
//
//   NOVEX_SOCKET     daemon socket path   (default /tmp/novex-vio.sock)
//   PORT             HTTP port            (default 8080)
//   NOVEX_HOST       bind address         (default 127.0.0.1)
//   NOVEX_UPDATE_HZ  subscription rate    (default 20)
//   NOVEX_POINTS_HZ  point cloud rate     (default 10; 0 disables)
//
// Point cloud messages are binary (see lib/pointcloud.js). The relay
// subscribes to them only while at least one browser is connected, so
// an idle dashboard costs the daemon nothing.

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const { WebSocketServer } = require('./lib/websocket.js');
const { NovexClient } = require('./lib/novexclient.js');
const pointcloud = require('./lib/pointcloud.js');

const SOCKET_PATH = process.env.NOVEX_SOCKET || '/tmp/novex-vio.sock';
const PORT = Number(process.env.PORT || 8080);
const UPDATE_HZ = Number(process.env.NOVEX_UPDATE_HZ || 20);
const POINTS_HZ = Number(process.env.NOVEX_POINTS_HZ ?? 10);

// Loopback by default and never widened silently. This dashboard can
// reset the estimator; it has no authentication and is not meant to
// leave the machine.
const HOST = process.env.NOVEX_HOST || '127.0.0.1';

const PUBLIC_DIR = path.join(__dirname, 'public');

const MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
};

// ---------------------------------------------------------------
// Daemon connection
// ---------------------------------------------------------------

const client = new NovexClient({
    socketPath: SOCKET_PATH,
    updateHz: UPDATE_HZ,
});

let daemonConnected = false;

client.on('status', ({ connected }) =>
{
    daemonConnected = connected;

    console.log(
        connected
            ? `[novex] connected to ${SOCKET_PATH}`
            : `[novex] lost connection to ${SOCKET_PATH}, retrying`
    );

    broadcast({
        type: 'link',
        connected,
    });
});

client.on('state', (state) =>
{
    // Straight through. No buffering, no interpolation: if the
    // browser cannot keep up, dropping frames is correct.
    broadcast(state);
});

// ---------------------------------------------------------------
// Point cloud relay
// ---------------------------------------------------------------

const mapMirror = new pointcloud.MapMirror();

// Measured, not configured: what actually left for browsers.
const relayStats = {
    liveIn: 0,
    mapIn: 0,
    liveOut: 0,
    mapOut: 0,
    liveDropped: 0,
    mapDeferred: 0,
    bytesOut: 0,
};

let relayWindow = { ...relayStats, at: Date.now() };

// A browser holds a copy of the map as of (epoch, generation). This
// sends whatever is newer, if its socket has room. When it does not,
// nothing is committed and the next attempt sends the combined delta.
function pushMap(connection)
{
    const view = connection.novex;

    if (!view.wantMap)
    {
        return;
    }

    if (connection.pending > 256 << 10)
    {
        ++relayStats.mapDeferred;
        return;
    }

    const encoded = mapMirror.encodeFor(view.epoch, view.generation);

    if (!encoded)
    {
        return;
    }

    // Room was checked above, so the size limit here is only a guard.
    if (connection.sendBinary(encoded.buffer, 64 << 20))
    {
        view.epoch = encoded.next.epoch;
        view.generation = encoded.next.generation;

        ++relayStats.mapOut;
        relayStats.bytesOut += encoded.buffer.length;
    }
}

client.on('points', (payload) =>
{
    const header = pointcloud.parseHeader(payload);

    if (!header)
    {
        return;
    }

    if (header.type === pointcloud.TYPE_LIVE)
    {
        ++relayStats.liveIn;

        // Live points are superseded by the next message, so a browser
        // that is behind simply misses this one.
        for (const connection of sockets.connections)
        {
            if (!connection.novex.wantLive)
            {
                continue;
            }

            if (connection.sendBinary(payload))
            {
                ++relayStats.liveOut;
                relayStats.bytesOut += payload.length;
            }
            else
            {
                ++relayStats.liveDropped;
            }
        }
    }
    else if (header.type === pointcloud.TYPE_MAP)
    {
        ++relayStats.mapIn;

        mapMirror.apply(payload, header);

        for (const connection of sockets.connections)
        {
            pushMap(connection);
        }
    }
});

function updatePointSubscription()
{
    client.setPointsHz(sockets.size > 0 ? POINTS_HZ : 0);
}

// Once a second, tell browsers what the relay actually delivered, so
// the dashboard shows a measured WebSocket rate rather than the
// configured one.
setInterval(() =>
{
    const now = Date.now();
    const seconds = Math.max(0.001, (now - relayWindow.at) / 1000);

    const rate = (key) => (relayStats[key] - relayWindow[key]) / seconds;

    broadcast({
        type: 'relay',
        browsers: sockets.size,
        pointsHz: client.pointsHz,
        liveInHz: rate('liveIn'),
        mapInHz: rate('mapIn'),
        liveOutHz: rate('liveOut'),
        mapOutHz: rate('mapOut'),
        liveDropped: relayStats.liveDropped,
        mapDeferred: relayStats.mapDeferred,
        kbytesPerSecond: rate('bytesOut') / 1024,
        mapSize: mapMirror.mapSize,
        mapCapacity: mapMirror.capacity,
    });

    relayWindow = { ...relayStats, at: now };
}, 1000).unref();

client.start();

// ---------------------------------------------------------------
// HTTP
// ---------------------------------------------------------------

function sendJson(response, status, body)
{
    const text = JSON.stringify(body);

    response.writeHead(status, {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Length': Buffer.byteLength(text),
        'Cache-Control': 'no-store',
    });

    response.end(text);
}

function serveStatic(request, response, urlPath)
{
    const relative = urlPath === '/' ? '/index.html' : urlPath;

    // Resolve, then confirm the result is still inside PUBLIC_DIR.
    // Without this check a request for /../../etc/passwd would be
    // served happily.
    const target = path.join(PUBLIC_DIR, path.normalize(relative));

    if (!target.startsWith(PUBLIC_DIR + path.sep) &&
        target !== PUBLIC_DIR)
    {
        response.writeHead(403);
        response.end('forbidden');
        return;
    }

    fs.readFile(target, (error, data) =>
    {
        if (error)
        {
            response.writeHead(404, { 'Content-Type': 'text/plain' });
            response.end('not found');
            return;
        }

        const type = MIME[path.extname(target)] ||
                     'application/octet-stream';

        response.writeHead(200, {
            'Content-Type': type,
            'Content-Length': data.length,
        });

        response.end(data);
    });
}

async function relay(response, command)
{
    if (!daemonConnected)
    {
        sendJson(response, 503, {
            error: 'novex-vio is not connected',
            socket: SOCKET_PATH,
        });

        return;
    }

    try
    {
        const reply = await client.request(command);
        sendJson(response, 200, reply);
    }
    catch (error)
    {
        sendJson(response, 504, { error: String(error.message || error) });
    }
}

const server = http.createServer((request, response) =>
{
    const url = new URL(request.url, `http://${request.headers.host}`);
    const route = url.pathname;

    if (request.method === 'GET')
    {
        switch (route)
        {
            case '/api/v1/state':
                // Served from the cached push rather than a round
                // trip: it is at most one update old and costs the
                // daemon nothing.
                if (client.latest)
                {
                    sendJson(response, 200, client.latest);
                }
                else
                {
                    sendJson(response, 503, {
                        error: 'no state received yet',
                        connected: daemonConnected,
                    });
                }
                return;

            case '/api/v1/status':
                return void relay(response, 'GET_STATUS');

            case '/api/v1/performance':
                return void relay(response, 'GET_STATS');

            case '/api/v1/debug':
                return void relay(response, 'GET_DEBUG');

            case '/api/v1/camera':
                return void relay(response, 'GET_CAMERA');

            case '/api/v1/diagnostics':
                return void relay(response, 'GET_DIAGNOSTICS');

            case '/api/v1/pointcloud':
                sendJson(response, 200, {
                    daemon: client.latest?.pointCloud ?? null,
                    relay: {
                        subscribedHz: client.pointsHz,
                        mapSize: mapMirror.mapSize,
                        mapCapacity: mapMirror.capacity,
                        mapEpoch: mapMirror.epoch,
                        mapGeneration: mapMirror.generation,
                        ...relayStats,
                    },
                });
                return;

            case '/api/v1/health':
                sendJson(response, 200, {
                    ok: true,
                    daemonConnected,
                    socket: SOCKET_PATH,
                    clients: sockets.size,
                    updateHz: UPDATE_HZ,
                    pointsHz: client.pointsHz,
                });
                return;

            default:
                serveStatic(request, response, route);
                return;
        }
    }

    if (request.method === 'POST')
    {
        const commands = {
            '/api/v1/vio/reset': 'RESET',
            '/api/v1/vio/recenter': 'RECENTER',
            '/api/v1/vio/pause': 'PAUSE',
            '/api/v1/vio/resume': 'RESUME',
            '/api/v1/map/clear': 'CLEAR_MAP',
        };

        const command = commands[route];

        if (command)
        {
            return void relay(response, command);
        }

        if (route === '/api/v1/vio/stereo' ||
            route === '/api/v1/vio/imu' ||
            route === '/api/v1/vio/stationary')
        {
            const on = url.searchParams.get('enabled') !== 'false';

            const verb = route.endsWith('stereo') ? 'SET_STEREO'
                : route.endsWith('imu') ? 'SET_IMU'
                : 'STATIONARY';

            return void relay(response, `${verb} ${on ? 'on' : 'off'}`);
        }
    }

    sendJson(response, 404, { error: 'not found' });
});

// ---------------------------------------------------------------
// WebSocket
// ---------------------------------------------------------------

const sockets = new WebSocketServer(server, {
    onConnect(connection)
    {
        console.log(`[ws] client connected (${sockets.size} total)`);

        // What this browser holds of the map, and which point layers
        // it wants. Both layers are on until the browser says
        // otherwise.
        connection.novex = {
            wantLive: true,
            wantMap: true,
            epoch: 0,
            generation: 0,
        };

        updatePointSubscription();

        // A browser that connects mid-run, or refreshes, gets the
        // newest state immediately instead of waiting for the next
        // push. No VIO restart is involved.
        connection.send(JSON.stringify({
            type: 'link',
            connected: daemonConnected,
        }));

        if (client.latest)
        {
            connection.send(JSON.stringify(client.latest));
        }

        // The whole current map, so a refresh does not start blank.
        pushMap(connection);
    },

    onClose()
    {
        updatePointSubscription();
    },

    onMessage(connection, text)
    {
        // Commands may also arrive over the socket, so the UI does not
        // need a second transport.
        let message;

        try { message = JSON.parse(text); }
        catch { return; }

        if (message.command === 'layers')
        {
            const view = connection.novex;

            view.wantLive = message.live !== false;

            const wanted = message.map !== false;

            if (wanted && !view.wantMap)
            {
                view.wantMap = true;
                pushMap(connection);
            }

            view.wantMap = wanted;

            return;
        }

        const allowed = {
            reset: 'RESET',
            recenter: 'RECENTER',
            pause: 'PAUSE',
            resume: 'RESUME',
            clear_map: 'CLEAR_MAP',
            stationary_start: 'STATIONARY on',
            stationary_stop: 'STATIONARY off',
        };

        const command = allowed[message.command];

        if (command && daemonConnected)
        {
            client.request(command).catch(() => { /* reported via link */ });
        }
    },
});

function broadcast(object)
{
    if (sockets.size === 0)
    {
        return;   // nothing to serialise for
    }

    sockets.broadcast(JSON.stringify(object));
}

// ---------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------

server.listen(PORT, HOST, () =>
{
    console.log(`[web] Novex VIO dashboard on http://${HOST}:${PORT}`);
    console.log(`[web] relaying ${SOCKET_PATH} at ${UPDATE_HZ} Hz`);
});

server.on('error', (error) =>
{
    if (error.code === 'EADDRINUSE')
    {
        console.error(
            `[web] port ${PORT} is already in use. ` +
            `Use --web-port to choose another.`
        );
    }
    else
    {
        console.error(`[web] ${error.message}`);
    }

    process.exit(1);
});

let shuttingDown = false;

function shutdown()
{
    if (shuttingDown)
    {
        return;
    }

    shuttingDown = true;

    console.log('[web] shutting down');

    sockets.closeAll();
    client.stop();

    server.close(() => process.exit(0));

    // Do not hang on a client that will not close.
    setTimeout(() => process.exit(0), 1500).unref();
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
