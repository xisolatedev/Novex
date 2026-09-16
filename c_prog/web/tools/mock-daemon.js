'use strict';

// TEST FIXTURE - NOT PART OF NOVEX VIO.
//
// Speaks the novex-vio IPC protocol on a Unix socket so the dashboard
// can be exercised without a camera. Every number it emits is
// obviously synthetic: the pose walks a circle. It exists to test the
// TRANSPORT and the UI, and it must never be used to demonstrate that
// the estimator works.
//
//   node tools/mock-daemon.js [socketPath]

const net = require('node:net');
const fs = require('node:fs');

const SOCKET = process.argv[2] || '/tmp/novex-mock.sock';

try { fs.unlinkSync(SOCKET); } catch { /* not there */ }

let frame = 0;
const started = Date.now();

function state()
{
    const t = (Date.now() - started) / 1000;

    // A circle, so trajectory drawing and orientation are visibly
    // exercised. Synthetic.
    const x = Math.cos(t * 0.5) * 1.5;
    const z = Math.sin(t * 0.5) * 1.5;
    const y = Math.sin(t * 0.9) * 0.15;

    const yaw = -t * 0.5;

    return {
        type: 'vio_state',
        timestamp: t,
        position: { x, y, z },
        velocity: { x: -Math.sin(t * 0.5) * 0.75, y: 0, z: Math.cos(t * 0.5) * 0.75 },
        orientation: {
            x: 0,
            y: Math.sin(yaw / 2),
            z: 0,
            w: Math.cos(yaw / 2),
        },
        tracking: true,
        paused: false,
        trackedFeatures: 380 + Math.round(Math.sin(t) * 40),
        inliers: 44,
        stereoMatches: 105,
        stereoTriangulated: 70,
        stereoEnabled: true,
        imuEnabled: false,
        imuHealthy: false,
        fps: 30 + Math.sin(t * 2) * 0.4,
        cameraFps: 30.0,
        latencyMs: 54 + Math.sin(t * 3) * 3,
        frameId: ++frame,
        droppedFrames: 0,
        lostFrames: 0,
        resetCount: resets,
        recenterCount: recenters,
        recentered: recenters > 0,
        timing: {
            totalMs: 17 + Math.sin(t * 4) * 2,
            captureMs: 15.7,
            decodeMs: 3.6,
            detectMs: 5.7,
            trackMs: 5.0,
            stereoMs: 6.3,
            motionMs: 0.7,
            stateMs: 0.02,
            imuMs: 0,
        },
        debug: {
            enabled: process.env.NOVEX_DEBUG === '1',
            runtimeS: t,
            framesProcessed: frame,
            avgFrameMs: 17.5,
            minFrameMs: 9.8,
            maxFrameMs: 41.7,
            trackingFailures: 4,
            avgFeatures: 402.3,
            imuSamples: 0,
            trajectoryM: t * 0.75,
        },
    };
}

let resets = 0;
let recenters = 0;

const server = net.createServer((socket) =>
{
    let timer = null;
    let buffer = '';

    socket.on('data', (chunk) =>
    {
        buffer += chunk.toString();

        let index;

        while ((index = buffer.indexOf('\n')) >= 0)
        {
            const line = buffer.slice(0, index).trim();
            buffer = buffer.slice(index + 1);

            const verb = line.split(' ')[0];

            if (verb === 'SUBSCRIBE')
            {
                const hz = Number(line.split(' ')[1] || 20);

                socket.write(JSON.stringify({ subscribed: true, hz }) + '\n');

                if (timer) clearInterval(timer);

                timer = setInterval(() =>
                {
                    socket.write(JSON.stringify(state()) + '\n');
                }, 1000 / hz);
            }
            else if (verb === 'RESET')
            {
                ++resets;
                socket.write(JSON.stringify({ queued: 'reset' }) + '\n');
            }
            else if (verb === 'RECENTER')
            {
                ++recenters;
                socket.write(JSON.stringify({ queued: 'recenter' }) + '\n');
            }
            else if (verb === 'GET_STATUS')
            {
                socket.write(JSON.stringify({
                    running: true, paused: false, tracking: true,
                    mock: true,
                }) + '\n');
            }
            else if (verb === 'GET_STATE')
            {
                socket.write(JSON.stringify(state()) + '\n');
            }
            else if (verb === 'PING')
            {
                socket.write('PONG\n');
            }
            else
            {
                socket.write(JSON.stringify({ queued: verb }) + '\n');
            }
        }
    });

    socket.on('close', () => { if (timer) clearInterval(timer); });
    socket.on('error', () => { if (timer) clearInterval(timer); });
});

server.listen(SOCKET, () =>
{
    console.log(`[mock] SYNTHETIC daemon on ${SOCKET}`);
    console.log('[mock] this is a test fixture; the data is not real');
});

process.on('SIGTERM', () => { server.close(); try { fs.unlinkSync(SOCKET); } catch {} process.exit(0); });
process.on('SIGINT', () => { server.close(); try { fs.unlinkSync(SOCKET); } catch {} process.exit(0); });
