# Novex VIO dashboard

Development visualisation for the Novex VIO daemon: a Three.js scene
showing the estimated pose, the trajectory and a live 3D feature point
cloud (live points, an accumulated map, an optional experimental
mesh), plus live pipeline timings and geometry diagnostics.

**This is a diagnostic tool, not a product.** It has no
authentication, it can reset the estimator, and it binds to loopback
for those reasons.

## Architecture

```
novex-vio (C++)
     │  Unix domain socket
     │  SUBSCRIBE 20           ->  one JSON state object per push
     │  SUBSCRIBE_POINTS 10    ->  "BIN <n>\n" + n bytes (LIVE, MAP delta)
     ▼
server.js (Node)                 <- relay; keeps a map MIRROR only to
     │  HTTP  (static + /api/v1/*)     serve per-browser deltas
     │  WebSocket: JSON text frames + binary point frames
     ▼
public/app.js (Three.js)         <- viewer, owns no state
public/mesh-worker.js            <- optional mesh, off the render thread
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
| `NOVEX_UPDATE_HZ` | `20` | state subscription rate |
| `NOVEX_POINTS_HZ` | `10` | point cloud rate while a browser is connected; `0` disables |

## HTTP API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/state` | newest state, served from cache |
| GET | `/api/v1/status` | run mode, subsystem flags |
| GET | `/api/v1/performance` | per-stage timings |
| GET | `/api/v1/debug` | `--debug` statistics, or `enabled:false` |
| GET | `/api/v1/camera` | negotiated camera mode |
| GET | `/api/v1/diagnostics` | geometry, drift, stationary test, point cloud counters |
| GET | `/api/v1/pointcloud` | daemon point counters + relay mirror and delivery stats |
| GET | `/api/v1/health` | relay health, client count, point rate |
| POST | `/api/v1/vio/reset` | restart tracking and estimator |
| POST | `/api/v1/vio/recenter` | move reported origin, keep tracking |
| POST | `/api/v1/vio/pause` | stop processing frames |
| POST | `/api/v1/vio/resume` | |
| POST | `/api/v1/vio/stereo?enabled=false` | toggle stereo depth |
| POST | `/api/v1/vio/imu?enabled=false` | toggle IMU consumption |
| POST | `/api/v1/vio/stationary?enabled=true` | start / stop the stationary drift test |
| POST | `/api/v1/map/clear` | drop the point map (new epoch), keep tracking |

Control endpoints are **enqueued**, not executed synchronously. They
return `{"queued":"..."}` and the VIO thread applies them at the next
frame boundary. Nothing outside that thread ever mutates estimator
state.

## WebSocket messages

Text frames are JSON: `vio_state` (pose, timings, `geometry`, `drift`,
`stationary`, `pointCloud`, `origin`), `link` (daemon connection) and
`relay` (measured per-second delivery rates and bandwidth).

Binary frames are point cloud messages, format in
[`include/PointCloud.hpp`](../include/PointCloud.hpp) and
[`lib/pointcloud.js`](lib/pointcloud.js):

* **LIVE** - this frame's camera-local points (20 bytes each) with the
  camera pose they were measured at. Relayed byte for byte; a browser
  that is behind misses one and gets the next.
* **MAP** - a delta of 24-byte slot records in the internal world frame.
  The relay tracks each browser's `(epoch, generation)` and sends
  everything newer, so a late or backed-up browser is brought up to
  date exactly, never double-sent, and a map clear/reset arrives as a
  full resend with the reset flag.

A browser may send `{"command":"layers","live":bool,"map":bool}` to
stop receiving a hidden layer, and `reset`, `recenter`, `pause`,
`resume`, `clear_map`, `stationary_start`, `stationary_stop`.

## Coordinate systems

Novex uses the **OpenCV camera convention**, right-handed:

```
Novex:     X right,  Y DOWN,  Z forward (the left lens' optical axis)
Three.js:  X right,  Y up,    Z toward the viewer
```

They differ by `C = diag(1, -1, -1)`, a 180° rotation about X - a
proper rotation (determinant +1), not a mirror: `(x, y, z) ->
(x, -y, -z)`, `q(x, y, z, w) -> (x, -y, -z, w)`. Verified against 2000
random rotations and asserted as check `D7`.

The browser applies each transform exactly once, in the scene graph:

```
scene ─ novexFrame (C) ─┬─ drone            reported pose
                        └─ internalFrame (O^-1)
                              ├─ trajectory, map, mesh    internal world
                              └─ liveFrame (T_wc)
                                    └─ live points        camera-local
```

`O` is the recenter origin sent in every state. RECENTER changes `O`
only, so the map and trajectory move with the reported frame without
being rewritten; RESET starts a new map epoch and clears the trajectory.

Euler angles shown in the panel are derived **for display only**.

## Layers and presets

Live points, accumulated map, trajectory, camera, mesh (experimental),
feature-id colours, depth colouring, fading, grid, point size. Any
toggle can be preset from the URL, e.g. `/?mesh=1&traj=0&live=0`.
Press **F** to follow the camera.

## Testing without a camera

`tools/mock-daemon.js` speaks the IPC protocol and emits a synthetic
circular trajectory, so the transport and the UI can be exercised with
no hardware:

```bash
node tools/mock-daemon.js /tmp/novex-mock.sock &
NOVEX_SOCKET=/tmp/novex-mock.sock PORT=8080 node server.js
```

**It is a test fixture. Its numbers are invented and must never be
used to show that the estimator works.** It does not emit point cloud
or geometry diagnostics; the dashboard shows dashes for those.
