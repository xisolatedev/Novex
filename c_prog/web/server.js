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

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const { WebSocketServer } = require('./lib/websocket.js');
const { NovexClient } = require('./lib/novexclient.js');

const SOCKET_PATH = process.env.NOVEX_SOCKET || '/tmp/novex-vio.sock';
const PORT = Number(process.env.PORT || 8080);
const UPDATE_HZ = Number(process.env.NOVEX_UPDATE_HZ || 20);

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

            case '/api/v1/health':
                sendJson(response, 200, {
                    ok: true,
                    daemonConnected,
                    socket: SOCKET_PATH,
                    clients: sockets.size,
                    updateHz: UPDATE_HZ,
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
        };

        const command = commands[route];

        if (command)
        {
            return void relay(response, command);
        }

        if (route === '/api/v1/vio/stereo' || route === '/api/v1/vio/imu')
        {
            const on = url.searchParams.get('enabled') !== 'false';

            const verb = route.endsWith('stereo')
                ? 'SET_STEREO'
                : 'SET_IMU';

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
    },

    onMessage(connection, text)
    {
        // Commands may also arrive over the socket, so the UI does not
        // need a second transport.
        let message;

        try { message = JSON.parse(text); }
        catch { return; }

        const allowed = {
            reset: 'RESET',
            recenter: 'RECENTER',
            pause: 'PAUSE',
            resume: 'RESUME',
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
