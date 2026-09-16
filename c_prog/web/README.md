# Novex VIO dashboard

Development visualisation for the Novex VIO daemon: a Three.js scene
showing the estimated pose and trajectory, plus live pipeline timings.

**This is a diagnostic tool, not a product.** It has no
authentication, it can reset the estimator, and it binds to loopback
for those reasons.

## Architecture

```
novex-vio (C++)
     │  Unix domain socket, newline-delimited JSON
     │  SUBSCRIBE 20   ->  one state object per push
     ▼
server.js (Node)                 <- relay, owns no state
     │  HTTP  (static + /api/v1/*)
     │  WebSocket (live stream)
     ▼
public/app.js (Three.js)         <- viewer, owns no state
```

The Node server is a **relay**. It computes nothing, stores nothing
authoritative, and caches only the most recent state so a browser that
connects late gets something immediately. If it crashes, the estimator
does not notice.

## Zero dependencies

`npm install` is not required and there is no `node_modules`.

* The WebSocket server is [`lib/websocket.js`](lib/websocket.js), a
  small RFC 6455 implementation over `node:http` and `node:crypto`.
* Three.js r160 is vendored at
  [`public/vendor/three.module.min.js`](public/vendor/three.module.min.js).

That is deliberate: this has to deploy to a Raspberry Pi Zero 2 W that
may have no network, where `npm install` is a step that can fail in the
field. The tradeoff is that the WebSocket implementation is ours to
maintain — it handles text frames, ping/pong and close, and
deliberately omits `permessage-deflate`, outgoing fragmentation and
subprotocol negotiation, none of which this uses.

## Running

Normally `novex-vio --web` starts this automatically as a managed child
process. To run it by hand:

```bash
cd web
NOVEX_SOCKET=/tmp/novex-vio.sock PORT=8080 node server.js
```

Then start the daemon with `--no-web-autostart` so it does not spawn a
second copy:

```bash
./build/novex-vio --web --no-web-autostart
```

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `NOVEX_SOCKET` | `/tmp/novex-vio.sock` | daemon IPC socket |
| `PORT` | `8080` | HTTP port |
| `NOVEX_HOST` | `127.0.0.1` | bind address |
| `NOVEX_UPDATE_HZ` | `20` | subscription rate |

## HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/state` | newest state, served from cache |
| GET | `/api/v1/status` | run mode, subsystem flags |
| GET | `/api/v1/performance` | per-stage timings |
| GET | `/api/v1/debug` | `--debug` statistics, or `enabled:false` |
| GET | `/api/v1/camera` | negotiated camera mode |
| GET | `/api/v1/health` | relay health, client count |
| POST | `/api/v1/vio/reset` | restart tracking and estimator |
| POST | `/api/v1/vio/recenter` | move reported origin, keep tracking |
| POST | `/api/v1/vio/pause` | stop processing frames |
| POST | `/api/v1/vio/resume` | |
| POST | `/api/v1/vio/stereo?enabled=false` | toggle stereo depth |
| POST | `/api/v1/vio/imu?enabled=false` | toggle IMU consumption |

Control endpoints are **enqueued**, not executed synchronously. They
return `{"queued":"..."}` and the VIO thread applies them at the next
frame boundary. Nothing outside that thread ever mutates estimator
state.

## Coordinate system

Novex reports poses in the **OpenCV camera convention**, because that
is what its stereo geometry produces:

```
Novex:     X right,  Y DOWN,  Z forward (along the optical axis)
Three.js:  X right,  Y up,    Z toward the viewer
```

They differ by a 180° rotation about X, `M = diag(1, -1, -1)`. Since
that is a proper rotation (determinant +1, not a mirror):

```
position    (x, y, z)     ->  (x, -y, -z)
quaternion  (x, y, z, w)  ->  (x, -y, -z, w)
```

Verified numerically against 2000 random rotations, and asserted in
the C++ suite as check `D7`. The conversion lives in
[`public/app.js`](public/app.js); the daemon always emits Novex
coordinates.

Euler angles shown in the panel are derived **for display only**. The
estimator holds a quaternion throughout and never converts internally.

## Testing without a camera

`tools/mock-daemon.js` speaks the IPC protocol and emits a synthetic
circular trajectory, so the transport and the UI can be exercised with
no hardware:

```bash
node tools/mock-daemon.js /tmp/novex-mock.sock &
NOVEX_SOCKET=/tmp/novex-mock.sock PORT=8080 node server.js
```

**It is a test fixture. Its numbers are invented and must never be
used to show that the estimator works.**
