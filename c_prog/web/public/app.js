// Novex VIO dashboard.
//
// Consumes the state stream relayed by server.js and draws it. This
// file is a VIEWER: it holds no authoritative state, and every number
// shown came from the daemon. Where the daemon has not measured
// something, this shows a dash rather than a zero.
//
// COORDINATE SYSTEM
// -----------------
// Novex reports poses in the OpenCV camera convention, because that is
// what the stereo geometry produces: triangulation runs with the left
// camera as [I|0] and points are accepted on z > 0.
//
//     Novex:    X right,  Y DOWN,  Z forward (along the optical axis)
//     Three.js: X right,  Y up,    Z toward the viewer
//
// The two differ by a 180 degree rotation about X, i.e. M =
// diag(1, -1, -1). That is a proper rotation (determinant +1), so it
// applies to orientations as a conjugation, which works out to simply
// negating the y and z components of the quaternion:
//
//     position    (x, y, z)    -> (x, -y, -z)
//     quaternion  (x, y, z, w) -> (x, -y, -z, w)
//
// This was verified numerically against 2000 random rotations before
// being written here: rotating in the Novex frame and then converting
// gives bit-identical results to converting and then rotating.
//
// The camera object's local forward is -Z in Three.js, which is what
// the converted orientation expects, so the frustum points where the
// camera is actually looking.

import * as THREE from './vendor/three.module.min.js';

// ---------------------------------------------------------------
// Coordinate conversion
// ---------------------------------------------------------------

function toThreePosition(p, out)
{
    return out.set(p.x, -p.y, -p.z);
}

function toThreeQuaternion(q, out)
{
    return out.set(q.x, -q.y, -q.z, q.w);
}

// ---------------------------------------------------------------
// Scene
// ---------------------------------------------------------------

const container = document.getElementById('scene');

const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: 'low-power',
});

renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
container.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0d1117);

const view = new THREE.PerspectiveCamera(
    55, innerWidth / innerHeight, 0.01, 500
);

view.position.set(2.2, 1.8, 2.8);

const grid = new THREE.GridHelper(20, 40, 0x2b3a4f, 0x1a2431);
scene.add(grid);

// World axes at the origin: red X, green Y (up in Three, which is
// Novex -Y), blue Z.
scene.add(new THREE.AxesHelper(0.5));

scene.add(new THREE.AmbientLight(0xffffff, 0.75));

const key = new THREE.DirectionalLight(0xffffff, 1.1);
key.position.set(3, 5, 2);
scene.add(key);

// ---- the camera/drone body ----------------------------------

const drone = new THREE.Group();
scene.add(drone);

const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.13, 0.06, 0.19),
    new THREE.MeshStandardMaterial({
        color: 0x58a6ff,
        metalness: 0.1,
        roughness: 0.6,
    })
);

drone.add(body);

// A wireframe frustum showing where the camera looks. Built pointing
// down -Z, which is forward for a Three.js camera and therefore
// forward for the converted orientation too.
const frustum = new THREE.LineSegments(
    (() => {
        const near = 0.05;
        const far = 0.42;
        const w = 0.26;
        const h = 0.17;

        const tip = [0, 0, 0];

        const corners = [
            [ w,  h, -far], [-w,  h, -far],
            [-w, -h, -far], [ w, -h, -far],
        ];

        const points = [];

        for (const c of corners)
        {
            points.push(...tip, ...c);
        }

        for (let i = 0; i < 4; ++i)
        {
            points.push(...corners[i], ...corners[(i + 1) % 4]);
        }

        // Short stub marking the optical axis.
        points.push(0, 0, -near, 0, 0, -far);

        const geometry = new THREE.BufferGeometry();

        geometry.setAttribute(
            'position',
            new THREE.Float32BufferAttribute(points, 3)
        );

        return geometry;
    })(),
    new THREE.LineBasicMaterial({ color: 0x4ec9a0 })
);

drone.add(frustum);

// Local axes on the body, so orientation is readable at a glance.
drone.add(new THREE.AxesHelper(0.22));

// ---- trajectory ---------------------------------------------

// Preallocated. The whole point is that adding a point writes three
// floats and bumps a draw range - it never rebuilds geometry, never
// reallocates, and never touches the rest of the scene.
let maxPoints = 5000;

let trajectoryPositions = new Float32Array(maxPoints * 3);
let trajectoryCount = 0;

const trajectoryGeometry = new THREE.BufferGeometry();

trajectoryGeometry.setAttribute(
    'position',
    new THREE.BufferAttribute(trajectoryPositions, 3)
);

trajectoryGeometry.setDrawRange(0, 0);

const trajectory = new THREE.Line(
    trajectoryGeometry,
    new THREE.LineBasicMaterial({ color: 0xe0a44c })
);

trajectory.frustumCulled = false;
scene.add(trajectory);

function clearTrajectory()
{
    trajectoryCount = 0;
    trajectoryGeometry.setDrawRange(0, 0);
    document.getElementById('traj-count').textContent = '0';
}

function resizeTrajectory(next)
{
    maxPoints = Math.max(100, Math.min(200000, next | 0));

    trajectoryPositions = new Float32Array(maxPoints * 3);
    trajectoryCount = 0;

    trajectoryGeometry.setAttribute(
        'position',
        new THREE.BufferAttribute(trajectoryPositions, 3)
    );

    trajectoryGeometry.setDrawRange(0, 0);
}

const lastPoint = new THREE.Vector3(NaN, NaN, NaN);

function pushTrajectory(v)
{
    // Skip points that have not moved measurably. A stationary camera
    // would otherwise fill the buffer with duplicates and evict real
    // history.
    if (lastPoint.distanceToSquared(v) < 1e-8)
    {
        return;
    }

    if (trajectoryCount >= maxPoints)
    {
        // Ring behaviour by shifting: keeps the line contiguous, which
        // a THREE.Line needs. Only happens once the cap is reached,
        // and the cap is configurable for exactly this reason.
        trajectoryPositions.copyWithin(0, 3);
        trajectoryCount = maxPoints - 1;
    }

    const offset = trajectoryCount * 3;

    trajectoryPositions[offset] = v.x;
    trajectoryPositions[offset + 1] = v.y;
    trajectoryPositions[offset + 2] = v.z;

    ++trajectoryCount;

    trajectoryGeometry.attributes.position.needsUpdate = true;
    trajectoryGeometry.setDrawRange(0, trajectoryCount);

    lastPoint.copy(v);

    document.getElementById('traj-count').textContent =
        String(trajectoryCount);
}

// ---------------------------------------------------------------
// Orbit controls
//
// Hand-written rather than vendoring three's OrbitControls: this needs
// orbit, zoom and pan and nothing else, and it keeps the vendored
// surface to the one three.js file.
// ---------------------------------------------------------------

const target = new THREE.Vector3(0, 0, 0);

let radius = 4.2;
let theta = 0.9;
let phi = 1.1;

let dragging = 0;
let lastX = 0;
let lastY = 0;

function applyView()
{
    phi = Math.max(0.05, Math.min(Math.PI - 0.05, phi));

    view.position.set(
        target.x + radius * Math.sin(phi) * Math.sin(theta),
        target.y + radius * Math.cos(phi),
        target.z + radius * Math.sin(phi) * Math.cos(theta)
    );

    view.lookAt(target);
}

applyView();

renderer.domElement.addEventListener('pointerdown', (event) =>
{
    dragging = event.button === 2 ? 2 : 1;
    lastX = event.clientX;
    lastY = event.clientY;
    renderer.domElement.setPointerCapture(event.pointerId);
});

renderer.domElement.addEventListener('pointerup', (event) =>
{
    dragging = 0;
    renderer.domElement.releasePointerCapture(event.pointerId);
});

renderer.domElement.addEventListener('pointermove', (event) =>
{
    if (!dragging) return;

    const dx = event.clientX - lastX;
    const dy = event.clientY - lastY;

    lastX = event.clientX;
    lastY = event.clientY;

    if (dragging === 1)
    {
        theta -= dx * 0.006;
        phi -= dy * 0.006;
    }
    else
    {
        const scale = radius * 0.0016;

        const right = new THREE.Vector3();
        const up = new THREE.Vector3();

        view.matrixWorld.extractBasis(right, up, new THREE.Vector3());

        target.addScaledVector(right, -dx * scale);
        target.addScaledVector(up, dy * scale);
    }

    applyView();
});

renderer.domElement.addEventListener('contextmenu',
    (event) => event.preventDefault());

renderer.domElement.addEventListener('wheel', (event) =>
{
    event.preventDefault();
    radius = Math.max(0.3, Math.min(60, radius * (1 + Math.sign(event.deltaY) * 0.1)));
    applyView();
}, { passive: false });

addEventListener('resize', () =>
{
    view.aspect = innerWidth / innerHeight;
    view.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
});

// ---------------------------------------------------------------
// Rolling graphs
// ---------------------------------------------------------------

class Sparkline
{
    constructor(id, { color, windowSeconds = 20, unit = '', fixed = 1 })
    {
        this.canvas = document.getElementById(id);
        this.ctx = this.canvas.getContext('2d');
        this.color = color;
        this.windowSeconds = windowSeconds;
        this.unit = unit;
        this.fixed = fixed;

        // Rolling window, not unlimited history: a long run must not
        // grow the browser's memory.
        this.samples = [];
    }

    push(value, now)
    {
        if (!Number.isFinite(value)) return;

        this.samples.push({ t: now, v: value });

        const cutoff = now - this.windowSeconds * 1000;

        while (this.samples.length && this.samples[0].t < cutoff)
        {
            this.samples.shift();
        }
    }

    draw()
    {
        const { ctx, canvas } = this;
        const w = canvas.width;
        const h = canvas.height;

        ctx.clearRect(0, 0, w, h);

        if (this.samples.length < 2) return;

        let min = Infinity;
        let max = -Infinity;

        for (const s of this.samples)
        {
            if (s.v < min) min = s.v;
            if (s.v > max) max = s.v;
        }

        if (max - min < 1e-6) { max = min + 1; }

        const pad = (max - min) * 0.12;
        min -= pad;
        max += pad;

        const t0 = this.samples[0].t;
        const t1 = this.samples[this.samples.length - 1].t;
        const span = Math.max(1, t1 - t0);

        ctx.beginPath();

        this.samples.forEach((s, i) =>
        {
            const x = ((s.t - t0) / span) * (w - 2) + 1;
            const y = h - 3 - ((s.v - min) / (max - min)) * (h - 6);

            if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        });

        ctx.strokeStyle = this.color;
        ctx.lineWidth = 1.4;
        ctx.stroke();

        const latest = this.samples[this.samples.length - 1].v;

        ctx.fillStyle = '#7d8899';
        ctx.font = '10px ui-monospace, monospace';
        ctx.fillText(latest.toFixed(this.fixed) + this.unit, 5, 12);
    }
}

const graphs = {
    frame: new Sparkline('g-frame', { color: '#58a6ff', unit: ' ms' }),
    fps: new Sparkline('g-fps', { color: '#4ec9a0', unit: '' }),
    features: new Sparkline('g-feat', { color: '#e0a44c', fixed: 0 }),
};

// ---------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------

const el = (id) => document.getElementById(id);

function setText(id, value)
{
    const node = el(id);
    if (node && node.textContent !== value) node.textContent = value;
}

function setPill(id, text, cls)
{
    const node = el(id);
    node.textContent = text;
    node.className = 'pill ' + cls;
}

const ms = (v) => (Number.isFinite(v) ? v.toFixed(2) + ' ms' : '—');
const num = (v, d = 3) => (Number.isFinite(v) ? v.toFixed(d) : '—');

// Euler angles derived here purely for reading. The estimator keeps a
// quaternion; nothing internal ever uses these.
const eulerHelper = new THREE.Euler();
const quatHelper = new THREE.Quaternion();

function eulerDegrees(q)
{
    // Read in the Novex frame so the numbers match the daemon's own
    // report, rather than the display frame.
    quatHelper.set(q.x, q.y, q.z, q.w);
    eulerHelper.setFromQuaternion(quatHelper, 'ZYX');

    const d = 180 / Math.PI;

    return {
        roll: eulerHelper.x * d,
        pitch: eulerHelper.y * d,
        yaw: eulerHelper.z * d,
    };
}

// ---------------------------------------------------------------
// State handling
// ---------------------------------------------------------------

const posHelper = new THREE.Vector3();
const quatHelper2 = new THREE.Quaternion();

let lastResetCount = null;
let lastRecenterCount = null;
let paused = false;
let haveState = false;

function onState(s)
{
    haveState = true;

    const now = performance.now();

    // Reset restarts the estimator, so old trajectory points refer to
    // a frame that no longer exists. Recenter moves the reported
    // origin, so they refer to a different frame. Both invalidate the
    // drawn path, and both are detected by watching the daemon's
    // counters rather than by trusting our own button presses - that
    // way a command issued from another client is handled too.
    if (lastResetCount !== null && s.resetCount !== lastResetCount)
    {
        clearTrajectory();
        lastPoint.set(NaN, NaN, NaN);
    }

    if (lastRecenterCount !== null &&
        s.recenterCount !== lastRecenterCount)
    {
        clearTrajectory();
        lastPoint.set(NaN, NaN, NaN);
    }

    lastResetCount = s.resetCount;
    lastRecenterCount = s.recenterCount;

    el('origin-state').hidden = !s.recentered;

    // ---- 3D ----
    toThreePosition(s.position, posHelper);
    toThreeQuaternion(s.orientation, quatHelper2);

    drone.position.copy(posHelper);
    drone.quaternion.copy(quatHelper2);

    if (s.tracking) pushTrajectory(posHelper);

    // ---- status ----
    paused = !!s.paused;

    el('btn-pause').textContent = paused ? 'Resume' : 'Pause';

    setText('s-vio', paused ? 'PAUSED' : 'RUNNING');
    el('s-vio').className = paused ? 'warn' : 'good';

    setText('s-tracking', s.tracking ? 'GOOD' : 'LOST');
    el('s-tracking').className = s.tracking ? 'good' : 'bad';

    setText('s-features', String(s.trackedFeatures));

    setText('s-stereo', s.stereoEnabled ? 'ACTIVE' : 'OFF');
    el('s-stereo').className = s.stereoEnabled ? 'good' : 'dim';

    setText('s-imu', s.imuEnabled
        ? (s.imuHealthy ? 'ACTIVE' : 'STALLED')
        : 'DISABLED');

    el('s-imu').className = s.imuEnabled
        ? (s.imuHealthy ? 'good' : 'bad')
        : 'dim';

    // ---- performance ----
    setText('p-camfps', num(s.cameraFps, 1));
    setText('p-viofps', num(s.fps, 1));
    setText('p-latency', ms(s.latencyMs));

    const t = s.timing || {};

    setText('p-frame', ms(t.totalMs));
    setText('p-decode', ms(t.decodeMs));
    setText('p-detect', ms(t.detectMs));
    setText('p-track', ms(t.trackMs));
    setText('p-stereo', ms(t.stereoMs));
    setText('p-motion', ms(t.motionMs));
    setText('p-state', ms(t.stateMs));
    setText('p-imu', ms(t.imuMs));

    // ---- pose ----
    setText('pos-x', num(s.position.x));
    setText('pos-y', num(s.position.y));
    setText('pos-z', num(s.position.z));

    const e = eulerDegrees(s.orientation);

    setText('rot-r', e.roll.toFixed(2) + '°');
    setText('rot-p', e.pitch.toFixed(2) + '°');
    setText('rot-y', e.yaw.toFixed(2) + '°');

    // ---- tracking ----
    setText('t-features', String(s.trackedFeatures));
    setText('t-inliers', String(s.inliers));
    setText('t-matched', String(s.stereoMatches));
    setText('t-tri', String(s.stereoTriangulated));
    setText('t-fail', String(s.debug?.trackingFailures ?? '—'));
    setText('t-drop', String(s.droppedFrames));

    // ---- debug ----
    const d = s.debug || { enabled: false };

    el('debug-off').hidden = !!d.enabled;
    el('debug-on').hidden = !d.enabled;
    el('debug-note').textContent = d.enabled ? '--debug' : 'off';

    if (d.enabled)
    {
        setText('d-runtime', num(d.runtimeS, 1) + ' s');
        setText('d-frames', String(d.framesProcessed));
        setText('d-avg', ms(d.avgFrameMs));
        setText('d-min', ms(d.minFrameMs));
        setText('d-max', ms(d.maxFrameMs));
        setText('d-feat', num(d.avgFeatures, 1));
        setText('d-imu', String(d.imuSamples));
        setText('d-traj', num(d.trajectoryM, 3) + ' m');
    }

    // ---- graphs ----
    graphs.frame.push(t.totalMs, now);
    graphs.fps.push(s.fps, now);
    graphs.features.push(s.trackedFeatures, now);
}

// ---------------------------------------------------------------
// Transport
// ---------------------------------------------------------------

let socket = null;
let reconnectDelay = 400;

function connect()
{
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';

    socket = new WebSocket(`${protocol}://${location.host}`);

    socket.addEventListener('open', () =>
    {
        reconnectDelay = 400;
        setPill('link-state', 'connected', 'pill-good');
    });

    socket.addEventListener('message', (event) =>
    {
        let message;

        try { message = JSON.parse(event.data); }
        catch { return; }

        if (message.type === 'vio_state')
        {
            onState(message);
        }
        else if (message.type === 'link')
        {
            if (!message.connected)
            {
                setPill('link-state', 'no daemon', 'pill-bad');
            }
            else if (haveState)
            {
                setPill('link-state', 'connected', 'pill-good');
            }
        }
    });

    socket.addEventListener('close', () =>
    {
        setPill('link-state', 'disconnected', 'pill-bad');

        // The dashboard reconnects on its own. Refreshing the page or
        // restarting this server never requires restarting the VIO.
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 5000);
    });

    socket.addEventListener('error', () => socket.close());
}

connect();

async function post(path)
{
    try
    {
        await fetch(path, { method: 'POST' });
    }
    catch
    {
        // The link pill already shows the connection state.
    }
}

el('btn-reset').addEventListener('click', () =>
{
    post('/api/v1/vio/reset');
});

el('btn-recenter').addEventListener('click', () =>
{
    post('/api/v1/vio/recenter');
});

el('btn-pause').addEventListener('click', () =>
{
    post(paused ? '/api/v1/vio/resume' : '/api/v1/vio/pause');
});

el('max-points').addEventListener('change', (event) =>
{
    resizeTrajectory(Number(event.target.value));
});

el('show-grid').addEventListener('change', (event) =>
{
    grid.visible = event.target.checked;
});

// ---------------------------------------------------------------
// Render loop
//
// Runs on requestAnimationFrame, decoupled from the state stream. A
// slow browser therefore drops frames of RENDERING, never of state.
// ---------------------------------------------------------------

function tick()
{
    requestAnimationFrame(tick);

    graphs.frame.draw();
    graphs.fps.draw();
    graphs.features.draw();

    renderer.render(scene, view);
}

tick();
