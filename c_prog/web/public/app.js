// Novex VIO dashboard.
//
// Consumes the state stream and the binary point cloud stream relayed
// by server.js, and draws them. This file is a VIEWER: it holds no
// authoritative state, and every number shown came from the daemon.
// Where the daemon has not measured something, this shows a dash
// rather than a zero. No point is ever invented here.
//
// COORDINATE SYSTEMS
// ------------------
// Novex uses the OpenCV camera convention, right-handed:
//
//     Novex:    X right,  Y DOWN,  Z forward (the left lens' optical axis)
//     Three.js: X right,  Y up,    Z toward the viewer
//
// The two differ by a 180 degree rotation about X, C = diag(1, -1, -1).
// That is a proper rotation (determinant +1), not a mirror, so nothing
// is handed backwards. It was verified numerically against 2000 random
// rotations, and is asserted in the C++ suite as check D7.
//
// The daemon reports three frames (see include/PointCloud.hpp):
//
//   camera-local    live stereo points, in the current left camera
//   internal world  the estimator's integration frame; the point map
//                   and the trajectory are stored here
//   reported        internal world re-expressed through the RECENTER
//                   origin O = (R_o, p_o): X_rep = R_o^T (X_int - p_o)
//
// The scene graph applies exactly those transforms, once each:
//
//   scene (Three.js world, Y up)
//    └─ novexFrame            matrix = C             reported -> Three
//        ├─ drone             reported pose           camera -> reported
//        └─ internalFrame     matrix = O^-1           internal -> reported
//            ├─ trajectory    internal positions
//            ├─ mapPoints     internal world points
//            ├─ mesh          internal world points
//            └─ liveFrame     matrix = T_wc           camera -> internal
//                 └─ livePoints  camera-local points
//
// Recenter changes O only. The map and the trajectory move with it
// without a single point being rewritten, and tracking is untouched.

import * as THREE from './vendor/three.module.min.js';

// The WebSocket. Declared first: layer toggles below report to the
// relay through it as soon as they are bound.
let socket = null;

// ---------------------------------------------------------------
// Renderer and scene
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
scene.background = new THREE.Color(0x05080d);

const view = new THREE.PerspectiveCamera(
    55, innerWidth / innerHeight, 0.01, 500
);

const grid = new THREE.GridHelper(20, 40, 0x1f2c3d, 0x111a25);
scene.add(grid);

// World axes at the Three.js origin: red X, green Y (up), blue Z.
scene.add(new THREE.AxesHelper(0.5));

scene.add(new THREE.AmbientLight(0xffffff, 0.75));

const key = new THREE.DirectionalLight(0xffffff, 1.1);
key.position.set(3, 5, 2);
scene.add(key);

// ---- frame chain ----------------------------------------------

function fixedGroup()
{
    const group = new THREE.Group();
    group.matrixAutoUpdate = false;
    return group;
}

const novexFrame = fixedGroup();

// C = diag(1, -1, -1), written row by row.
novexFrame.matrix.set(
    1,  0,  0, 0,
    0, -1,  0, 0,
    0,  0, -1, 0,
    0,  0,  0, 1
);

scene.add(novexFrame);

const internalFrame = fixedGroup();
novexFrame.add(internalFrame);

const liveFrame = fixedGroup();
internalFrame.add(liveFrame);

// Sets `matrix` to the rigid transform with row-major rotation R and
// translation p, i.e. X_parent = R X_child + p.
function setRigid(matrix, R, p)
{
    matrix.set(
        R[0], R[1], R[2], p[0],
        R[3], R[4], R[5], p[1],
        R[6], R[7], R[8], p[2],
        0,    0,    0,    1
    );
}

// O^-1 from the origin quaternion and position: rotation R_o^T,
// translation -R_o^T p_o.
const originQuaternion = new THREE.Quaternion();
const originPosition = new THREE.Vector3();

function setOrigin(orientation, position)
{
    originQuaternion.set(orientation.x, orientation.y,
                         orientation.z, orientation.w);
    originPosition.set(position.x, position.y, position.z);

    const inverse = new THREE.Matrix4().compose(
        originPosition, originQuaternion, new THREE.Vector3(1, 1, 1)
    ).invert();

    internalFrame.matrix.copy(inverse);
    internalFrame.matrixWorldNeedsUpdate = true;
}

// ---- the camera / drone ---------------------------------------
//
// Built directly in Novex camera axes, because it lives under
// novexFrame: forward is +Z, image-down is +Y.

// ---- floor / ground plane -------------------------------------
//
// The daemon sends the plane in the REPORTED frame, so it hangs off
// novexFrame beside the drone - NOT off internalFrame. Recentring
// therefore moves it exactly as it moves the camera, with no special
// case here.
//
// PlaneGeometry lies in its own XY plane with its normal along +Z, so
// orienting it is one setFromUnitVectors from +Z to the floor normal.
// Nothing here recomputes a plane; it only draws the one it is given.

const floorGroup = new THREE.Group();
floorGroup.visible = false;
novexFrame.add(floorGroup);

const floorFill = new THREE.Mesh(
    new THREE.PlaneGeometry(8, 8),
    new THREE.MeshBasicMaterial({
        color: 0x2f81f7,
        transparent: true,
        opacity: 0.10,
        side: THREE.DoubleSide,
        depthWrite: false,
    })
);

floorGroup.add(floorFill);

// A grid on the plane makes its ORIENTATION readable; a flat quad
// does not. GridHelper is built in the XZ plane, so it is rotated to
// match the quad's XY convention once, here, and never again.
const floorGrid = new THREE.GridHelper(8, 16, 0x58a6ff, 0x1f4e79);
floorGrid.rotation.x = Math.PI / 2;
floorGroup.add(floorGrid);

// The normal, drawn from the point under the camera.
const floorNormal = new THREE.ArrowHelper(
    new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, 0),
    0.5, 0x58a6ff, 0.12, 0.07
);

floorGroup.add(floorNormal);

// Marks the foot of the perpendicular from the camera.
const floorMarker = new THREE.Mesh(
    new THREE.SphereGeometry(0.035, 12, 8),
    new THREE.MeshBasicMaterial({ color: 0x58a6ff })
);

floorGroup.add(floorMarker);

// Dropped line from the camera to that point: the camera height, made
// visible as a length rather than a number.
const floorDropGeometry = new THREE.BufferGeometry();

floorDropGeometry.setAttribute(
    'position',
    new THREE.BufferAttribute(new Float32Array(6), 3)
);

const floorDrop = new THREE.Line(
    floorDropGeometry,
    new THREE.LineDashedMaterial({
        color: 0x58a6ff,
        dashSize: 0.06,
        gapSize: 0.04,
    })
);

floorDrop.frustumCulled = false;
novexFrame.add(floorDrop);

const floorZ = new THREE.Vector3(0, 0, 1);
const floorNormalVector = new THREE.Vector3();
const floorPointVector = new THREE.Vector3();
const floorQuaternion = new THREE.Quaternion();

// Applies one floor estimate to the scene. `f` is the daemon's floor
// object; anything invalid hides the layer rather than drawing a
// stale plane.
function updateFloorScene(f, position)
{
    const show = !!(f && f.valid && layers.floor);

    floorGroup.visible = show;
    floorDrop.visible = show;

    if (!show)
    {
        return;
    }

    floorNormalVector.set(f.normal.x, f.normal.y, f.normal.z);

    if (floorNormalVector.lengthSq() < 1e-9)
    {
        floorGroup.visible = false;
        floorDrop.visible = false;
        return;
    }

    floorNormalVector.normalize();
    floorPointVector.set(f.point.x, f.point.y, f.point.z);

    floorQuaternion.setFromUnitVectors(floorZ, floorNormalVector);

    floorGroup.position.copy(floorPointVector);
    floorGroup.quaternion.copy(floorQuaternion);

    // The arrow lives inside the rotated group, so in local space the
    // normal is simply +Z.
    floorNormal.setDirection(floorZ);
    floorMarker.position.set(0, 0, 0);

    const drop = floorDropGeometry.attributes.position;

    drop.setXYZ(0, position.x, position.y, position.z);
    drop.setXYZ(1, floorPointVector.x, floorPointVector.y,
                floorPointVector.z);

    drop.needsUpdate = true;

    floorDrop.computeLineDistances();
}

const drone = new THREE.Group();
novexFrame.add(drone);

const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.13, 0.06, 0.08),
    new THREE.MeshStandardMaterial({
        color: 0x58a6ff,
        metalness: 0.1,
        roughness: 0.6,
    })
);

drone.add(body);

const frustum = new THREE.LineSegments(
    (() =>
    {
        const far = 0.42;
        const w = 0.26;
        const h = 0.17;

        const tip = [0, 0, 0];

        const corners = [
            [ w, -h, far], [-w, -h, far],
            [-w,  h, far], [ w,  h, far],
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

        // "Up" tick on the top edge (Novex -Y), so roll is readable.
        points.push(0, -h, far, 0, -h * 1.5, far);

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

// Local Novex axes on the body: red X right, green Y down, blue Z fwd.
drone.add(new THREE.AxesHelper(0.18));

// ---- trajectory (internal frame) ------------------------------

let maxTrajectory = 5000;

let trajectoryPositions = new Float32Array(maxTrajectory * 3);
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
internalFrame.add(trajectory);

const lastTrajectoryPoint = new THREE.Vector3(NaN, NaN, NaN);

function clearTrajectory()
{
    trajectoryCount = 0;
    trajectoryGeometry.setDrawRange(0, 0);
    lastTrajectoryPoint.set(NaN, NaN, NaN);
    setText('traj-count', '0');
}

function resizeTrajectory(next)
{
    maxTrajectory = Math.max(100, Math.min(200000, next | 0));

    trajectoryPositions = new Float32Array(maxTrajectory * 3);

    trajectoryGeometry.setAttribute(
        'position',
        new THREE.BufferAttribute(trajectoryPositions, 3)
    );

    clearTrajectory();
}

function pushTrajectory(v)
{
    // A stationary camera would otherwise fill the buffer with
    // duplicates and evict real history.
    if (lastTrajectoryPoint.distanceToSquared(v) < 1e-8)
    {
        return;
    }

    if (trajectoryCount >= maxTrajectory)
    {
        // Shifting keeps the line contiguous, which THREE.Line needs.
        trajectoryPositions.copyWithin(0, 3);
        trajectoryCount = maxTrajectory - 1;
    }

    const offset = trajectoryCount * 3;

    trajectoryPositions[offset] = v.x;
    trajectoryPositions[offset + 1] = v.y;
    trajectoryPositions[offset + 2] = v.z;

    ++trajectoryCount;

    trajectoryGeometry.attributes.position.needsUpdate = true;
    trajectoryGeometry.setDrawRange(0, trajectoryCount);

    lastTrajectoryPoint.copy(v);

    setText('traj-count', String(trajectoryCount));
}

// ---------------------------------------------------------------
// Point rendering
//
// ONE THREE.Points per layer, over preallocated typed arrays. A point
// is a vertex, never an object. Colour, size and fading happen on the
// GPU in a small shader, so updating a point is writing a few floats
// and marking a byte range for upload.
// ---------------------------------------------------------------

const pointVertexShader = /* glsl */ `
    uniform float uSize;        // world-space point size, metres
    uniform float uScale;       // pixels per metre at distance 1
    uniform float uNow;         // map clock, seconds
    uniform float uFade;        // seconds to fade over; 0 = no fading
    uniform float uRangeMax;    // range at which points are dimmest
    uniform int uDepthColour;
    uniform vec3 uCamera;       // the physical camera, Three.js world

    attribute vec3 aColour;
    attribute vec2 aInfo;       // quality 0..1 (<0 = empty slot), seen

    varying vec3 vColour;
    varying float vAlpha;

    // Turbo colormap, polynomial fit (Google, Apache 2.0).
    vec3 turbo(float x)
    {
        x = clamp(x, 0.0, 1.0);
        vec4 v4 = vec4(1.0, x, x * x, x * x * x);
        vec2 v2 = v4.zw * v4.z;
        return vec3(
            dot(v4, vec4(0.13572138, 4.61539260, -42.66032258, 132.13108234)) +
                dot(v2, vec2(-152.94239396, 59.28637943)),
            dot(v4, vec4(0.09140261, 2.19418839, 4.84296658, -14.18503333)) +
                dot(v2, vec2(4.27729857, 2.82956604)),
            dot(v4, vec4(0.10667330, 12.64194608, -60.58204836, 110.36276771)) +
                dot(v2, vec2(-89.90310912, 27.34824973)));
    }

    void main()
    {
        if (aInfo.x < 0.0)
        {
            // Empty slot: put it outside the clip volume.
            gl_Position = vec4(2.0, 2.0, 2.0, 1.0);
            gl_PointSize = 0.0;
            vAlpha = 0.0;
            vColour = vec3(0.0);
            return;
        }

        vec4 world = modelMatrix * vec4(position, 1.0);
        vec4 eye = viewMatrix * world;

        gl_Position = projectionMatrix * eye;

        // Nearer to the physical camera = brighter and larger, like a
        // scanner's returns.
        float near = clamp(1.0 - distance(world.xyz, uCamera) / uRangeMax,
                           0.0, 1.0);

        float quality = aInfo.x;

        float age = uFade > 0.0
            ? clamp((uNow - aInfo.y) / uFade, 0.0, 1.0)
            : 0.0;

        vec3 base = uDepthColour == 1 ? turbo(0.08 + 0.84 * near) : aColour;

        vColour = base * (0.55 + 0.45 * near);
        vAlpha = (0.30 + 0.70 * near) * (1.0 - 0.8 * age) *
                 (0.45 + 0.55 * quality);

        gl_PointSize = clamp(
            uSize * uScale * (0.55 + 0.45 * near) * (0.6 + 0.4 * quality) /
                max(-eye.z, 0.05),
            1.0, 28.0);
    }
`;

const pointFragmentShader = /* glsl */ `
    varying vec3 vColour;
    varying float vAlpha;

    void main()
    {
        vec2 d = gl_PointCoord - 0.5;
        float r = dot(d, d) * 4.0;

        if (r > 1.0 || vAlpha <= 0.0)
        {
            discard;
        }

        float glow = 1.0 - r;

        gl_FragColor = vec4(vColour * (0.75 + 0.45 * glow),
                            vAlpha * (0.35 + 0.65 * glow));
    }
`;

const pointUniforms = {
    uSize: { value: 0.025 },
    uScale: { value: 1 },
    uNow: { value: 0 },
    uFade: { value: 20 },
    uRangeMax: { value: 6 },
    uDepthColour: { value: 1 },
    uCamera: { value: new THREE.Vector3() },
};

function makePointMaterial(overrides = {})
{
    return new THREE.ShaderMaterial({
        uniforms: { ...pointUniforms, ...overrides },
        vertexShader: pointVertexShader,
        fragmentShader: pointFragmentShader,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
    });
}

class PointLayer
{
    constructor(parent, material, capacity)
    {
        this.geometry = new THREE.BufferGeometry();
        this.points = new THREE.Points(this.geometry, material);

        // Bounds change every update; culling on stale bounds would
        // hide points, and computing bounds per update costs more than
        // drawing a few thousand vertices.
        this.points.frustumCulled = false;

        parent.add(this.points);

        this.allocate(capacity);
    }

    allocate(capacity)
    {
        this.capacity = capacity;

        this.position = new Float32Array(capacity * 3);
        this.colour = new Float32Array(capacity * 3);
        this.info = new Float32Array(capacity * 2);

        for (let i = 0; i < capacity; ++i)
        {
            this.info[i * 2] = -1;
        }

        const usage = THREE.DynamicDrawUsage;

        this.geometry.setAttribute('position',
            new THREE.BufferAttribute(this.position, 3).setUsage(usage));
        this.geometry.setAttribute('aColour',
            new THREE.BufferAttribute(this.colour, 3).setUsage(usage));
        this.geometry.setAttribute('aInfo',
            new THREE.BufferAttribute(this.info, 2).setUsage(usage));
    }

    // Marks slots [first, last] for upload. Without a range the whole
    // buffer goes; with one, only those bytes do.
    upload(first, last)
    {
        for (const name of ['position', 'aColour', 'aInfo'])
        {
            const attribute = this.geometry.getAttribute(name);

            attribute.clearUpdateRanges();

            if (first !== undefined && last >= first)
            {
                attribute.addUpdateRange(first * attribute.itemSize,
                    (last - first + 1) * attribute.itemSize);
            }

            attribute.needsUpdate = true;
        }
    }
}

// Uniform objects are shared, so size, colouring and the camera
// position apply to both layers at once. Only fading differs: live
// points are by definition current.
const liveLayer = new PointLayer(
    liveFrame, makePointMaterial({ uFade: { value: 0 } }), 1024
);

const mapLayer = new PointLayer(internalFrame, makePointMaterial(), 0);

liveLayer.points.renderOrder = 2;
mapLayer.points.renderOrder = 1;

// Colours for the two non-depth modes.
function intensityColour(out, offset, intensity, live)
{
    const t = intensity / 255;

    if (live)
    {
        out[offset] = 0.35 + 0.6 * t;
        out[offset + 1] = 0.9;
        out[offset + 2] = 0.55 + 0.4 * t;
    }
    else
    {
        out[offset] = 0.12 + 0.6 * t;
        out[offset + 1] = 0.45 + 0.55 * t;
        out[offset + 2] = 0.55 + 0.45 * t;
    }
}

function idColour(out, offset, id)
{
    // Golden-ratio hue walk: neighbouring ids get distant hues, and a
    // feature keeps its colour for as long as it is tracked.
    const hue = (id * 0.6180339887) % 1;

    const colour = new THREE.Color().setHSL(hue, 0.85, 0.6);

    out[offset] = colour.r;
    out[offset + 1] = colour.g;
    out[offset + 2] = colour.b;
}

// ---- wire format (see include/PointCloud.hpp) ----

const HEADER_BYTES = 144;

function readHeader(data)
{
    if (data.byteLength < HEADER_BYTES ||
        data.getUint8(0) !== 0x4e || data.getUint8(1) !== 0x58 ||
        data.getUint8(2) !== 0x50 || data.getUint8(3) !== 0x43 ||
        data.getUint8(4) !== 1)
    {
        return null;
    }

    const floats = (offset, n) =>
    {
        const out = new Array(n);
        for (let i = 0; i < n; ++i) out[i] = data.getFloat32(offset + 4 * i, true);
        return out;
    };

    const header = {
        type: data.getUint8(5),
        flags: data.getUint16(6, true),
        count: data.getUint32(8, true),
        frameId: data.getUint32(12, true),
        timestamp: data.getFloat64(16, true),
        epoch: data.getUint32(24, true),
        generation: data.getUint32(28, true),
        capacity: data.getUint32(32, true),
        entryBytes: data.getUint32(36, true),
        rotation: floats(40, 9),
        position: floats(76, 3),
        mapSize: data.getUint32(136, true),
        voxelSize: data.getFloat32(140, true),
    };

    if (data.byteLength !== HEADER_BYTES + header.count * header.entryBytes)
    {
        return null;
    }

    return header;
}

// ---- live ----

const pointStats = {
    live: 0,
    liveMessages: 0,
    mapMessages: 0,
};

function onLivePoints(data, header)
{
    const count = header.count;

    if (count > liveLayer.capacity)
    {
        liveLayer.allocate(Math.max(count, liveLayer.capacity * 2));
    }

    const { position, colour, info } = liveLayer;
    const showIds = layers.ids;

    for (let i = 0; i < count; ++i)
    {
        const offset = HEADER_BYTES + i * 20;

        position[i * 3] = data.getFloat32(offset, true);
        position[i * 3 + 1] = data.getFloat32(offset + 4, true);
        position[i * 3 + 2] = data.getFloat32(offset + 8, true);

        const id = data.getUint32(offset + 12, true);
        const quality = data.getUint8(offset + 16);
        const intensity = data.getUint8(offset + 18);

        if (showIds)
        {
            idColour(colour, i * 3, id);
        }
        else
        {
            intensityColour(colour, i * 3, intensity, true);
        }

        info[i * 2] = quality / 255;
        info[i * 2 + 1] = 0;
    }

    // Slots past `count` from a previous, larger frame must go dark.
    for (let i = count; i < pointStats.live; ++i)
    {
        info[i * 2] = -1;
    }

    liveLayer.upload(0, Math.max(count, pointStats.live) - 1);

    pointStats.live = count;
    ++pointStats.liveMessages;

    // The live points are camera-local; this is the pose they were
    // measured at, from the same message - never a later state.
    setRigid(liveFrame.matrix, header.rotation, header.position);
    liveFrame.matrixWorldNeedsUpdate = true;
}

// ---- map ----

const mapClock = {
    latestSeen: 0,
    receivedAt: 0,
};

let mapEpoch = 0;
let mapChangedForMesh = false;

function onMapPoints(data, header)
{
    if (header.capacity !== mapLayer.capacity)
    {
        mapLayer.allocate(header.capacity);
    }

    const reset = (header.flags & 1) !== 0 || header.epoch !== mapEpoch;

    const { position, colour, info } = mapLayer;

    if (reset)
    {
        for (let i = 0; i < mapLayer.capacity; ++i)
        {
            info[i * 2] = -1;
        }

        mapEpoch = header.epoch;
        mapClock.latestSeen = 0;
    }

    let first = Infinity;
    let last = -1;

    for (let i = 0; i < header.count; ++i)
    {
        const offset = HEADER_BYTES + i * 24;
        const slot = data.getUint32(offset, true);

        if (slot >= mapLayer.capacity)
        {
            continue;
        }

        if (slot < first) first = slot;
        if (slot > last) last = slot;

        const alive = data.getUint8(offset + 22);

        if (!alive)
        {
            info[slot * 2] = -1;
            continue;
        }

        position[slot * 3] = data.getFloat32(offset + 4, true);
        position[slot * 3 + 1] = data.getFloat32(offset + 8, true);
        position[slot * 3 + 2] = data.getFloat32(offset + 12, true);

        const seen = data.getFloat32(offset + 16, true);
        const quality = data.getUint8(offset + 20);
        const intensity = data.getUint8(offset + 21);

        info[slot * 2] = quality / 255;
        info[slot * 2 + 1] = seen;

        intensityColour(colour, slot * 3, intensity, false);

        if (seen > mapClock.latestSeen)
        {
            mapClock.latestSeen = seen;
        }
    }

    mapClock.receivedAt = performance.now();

    if (reset)
    {
        mapLayer.upload();
    }
    else if (last >= 0)
    {
        mapLayer.upload(first, last);
    }

    pointStats.mapSize = header.mapSize;
    pointStats.mapCapacity = header.capacity;
    pointStats.voxelSize = header.voxelSize;
    ++pointStats.mapMessages;

    mapChangedForMesh = true;
}

// ---------------------------------------------------------------
// Experimental mesh
//
// OPTIONAL and web-only. The point map stays the authoritative data;
// this is a picture of it. Triangulation runs in a Web Worker at most
// a couple of times a second on a copy of the live map, so it can
// never slow rendering, and the daemon never waits for it.
// ---------------------------------------------------------------

const meshGeometry = new THREE.BufferGeometry();

const mesh = new THREE.Group();

mesh.add(new THREE.Mesh(
    meshGeometry,
    new THREE.MeshStandardMaterial({
        color: 0x1fb6a6,
        transparent: true,
        opacity: 0.32,
        side: THREE.DoubleSide,
        flatShading: true,
        depthWrite: false,
    })
));

mesh.add(new THREE.Mesh(
    meshGeometry,
    new THREE.MeshBasicMaterial({
        color: 0x5eead4,
        wireframe: true,
        transparent: true,
        opacity: 0.18,
        depthWrite: false,
    })
));

mesh.visible = false;
mesh.children.forEach((child) => { child.frustumCulled = false; });
internalFrame.add(mesh);

const meshWorker = new Worker('./mesh-worker.js');
let meshBusy = false;
let meshTriangles = 0;

meshWorker.onmessage = ({ data }) =>
{
    meshBusy = false;

    meshGeometry.setAttribute('position',
        new THREE.BufferAttribute(data.positions, 3));
    meshGeometry.setIndex(new THREE.BufferAttribute(data.indices, 1));
    meshGeometry.computeVertexNormals();

    meshTriangles = data.indices.length / 3;
};

function requestMesh()
{
    if (!layers.mesh || meshBusy || !mapChangedForMesh)
    {
        return;
    }

    const { position, info, capacity } = mapLayer;

    let alive = 0;

    for (let i = 0; i < capacity; ++i)
    {
        if (info[i * 2] >= 0) ++alive;
    }

    const compact = new Float32Array(alive * 3);

    let k = 0;

    for (let i = 0; i < capacity; ++i)
    {
        if (info[i * 2] < 0) continue;

        compact[k++] = position[i * 3];
        compact[k++] = position[i * 3 + 1];
        compact[k++] = position[i * 3 + 2];
    }

    meshBusy = true;
    mapChangedForMesh = false;

    meshWorker.postMessage({
        positions: compact,
        maxEdge: Number(el('mesh-edge').value) || 0.12,
    }, [compact.buffer]);
}

setInterval(requestMesh, 600);

// ---------------------------------------------------------------
// Orbit controls
//
// Hand-written rather than vendoring three's OrbitControls: this needs
// orbit, zoom and pan and nothing else.
// ---------------------------------------------------------------

const target = new THREE.Vector3(0, 0, 0);

let radius = 4.2;
let theta = 0.9;
let phi = 1.1;

let dragging = 0;
let lastX = 0;
let lastY = 0;
let follow = false;

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

const panRight = new THREE.Vector3();
const panUp = new THREE.Vector3();
const panForward = new THREE.Vector3();

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

        view.matrixWorld.extractBasis(panRight, panUp, panForward);

        target.addScaledVector(panRight, -dx * scale);
        target.addScaledVector(panUp, dy * scale);

        follow = false;
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

addEventListener('keydown', (event) =>
{
    if (event.key === 'f' || event.key === 'F')
    {
        follow = !follow;
    }
});

function updatePointScale()
{
    // Pixels covered by one metre at distance one metre.
    const height = renderer.domElement.height;
    const fov = THREE.MathUtils.degToRad(view.fov);

    pointUniforms.uScale.value = height / (2 * Math.tan(fov / 2));
}

addEventListener('resize', () =>
{
    view.aspect = innerWidth / innerHeight;
    view.updateProjectionMatrix();
    renderer.setSize(innerWidth, innerHeight);
    updatePointScale();
});

updatePointScale();

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

        // Rolling window, not unlimited history.
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

        if (max - min < 1e-9) { max = min + 1; }

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
    frame: new Sparkline('gr-frame', { color: '#58a6ff', unit: ' ms' }),
    rot: new Sparkline('gr-rot', { color: '#e0a44c', unit: '°', fixed: 4 }),
    trans: new Sparkline('gr-trans', { color: '#4ec9a0', unit: ' mm', fixed: 3 }),
    reproj: new Sparkline('gr-reproj', { color: '#c678dd', unit: ' px', fixed: 3 }),
    inliers: new Sparkline('gr-inliers', { color: '#d4dae3', fixed: 0 }),
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

function setClass(id, cls)
{
    const node = el(id);
    if (node && node.className !== cls) node.className = cls;
}

function setPill(id, text, cls)
{
    const node = el(id);
    node.textContent = text;
    node.className = 'pill ' + cls;
}

const finite = Number.isFinite;
const ms = (v) => (finite(v) ? v.toFixed(2) + ' ms' : '—');
const num = (v, d = 3) => (finite(v) ? v.toFixed(d) : '—');
const unit = (v, d, u) => (finite(v) ? v.toFixed(d) + u : '—');
const vec = (a, d, u) => (Array.isArray(a)
    ? a.map((x) => (x >= 0 ? '+' : '') + x.toFixed(d)).join(' ') + u
    : '—');

// Euler angles derived here purely for reading, in the Novex frame so
// they match the daemon's own report.
const eulerHelper = new THREE.Euler();
const quatHelper = new THREE.Quaternion();

function eulerDegrees(q)
{
    quatHelper.set(q.x, q.y, q.z, q.w);
    eulerHelper.setFromQuaternion(quatHelper, 'ZYX');

    const d = 180 / Math.PI;

    return { roll: eulerHelper.x * d, pitch: eulerHelper.y * d, yaw: eulerHelper.z * d };
}

// ---------------------------------------------------------------
// Layers
// ---------------------------------------------------------------

const layers = {
    live: true,
    map: true,
    trajectory: true,
    camera: true,
    mesh: false,
    floor: true,
    ids: false,
    depth: true,
    fade: true,
};

function sendLayers()
{
    // Tells the relay which binary streams this browser wants, so a
    // hidden layer costs no bandwidth.
    if (socket && socket.readyState === WebSocket.OPEN)
    {
        socket.send(JSON.stringify({
            command: 'layers',
            live: layers.live,
            map: layers.map || layers.mesh,
        }));
    }
}

// Layers can be preset from the URL, e.g. ?mesh=1&live=0, so a view
// can be bookmarked.
const presets = new URLSearchParams(location.search);

function bindLayer(id, apply)
{
    const input = el(id);

    const preset = presets.get(id.replace(/^l-/, ''));

    if (preset !== null)
    {
        input.checked = preset !== '0' && preset !== 'false';
    }

    const update = () => apply(input.checked);

    input.addEventListener('change', update);
    update();
}

bindLayer('l-live', (on) =>
{
    layers.live = on;
    liveLayer.points.visible = on;
    sendLayers();
});

bindLayer('l-map', (on) =>
{
    layers.map = on;
    mapLayer.points.visible = on;
    sendLayers();
});

bindLayer('l-traj', (on) => { layers.trajectory = on; trajectory.visible = on; });
bindLayer('l-camera', (on) => { layers.camera = on; drone.visible = on; });

bindLayer('l-mesh', (on) =>
{
    layers.mesh = on;
    mesh.visible = on;

    if (on)
    {
        mapChangedForMesh = true;
    }

    sendLayers();
});

bindLayer('l-ids', (on) => { layers.ids = on; });

bindLayer('l-depth', (on) =>
{
    layers.depth = on;
    pointUniforms.uDepthColour.value = on ? 1 : 0;
});

bindLayer('l-fade', (on) =>
{
    layers.fade = on;
    pointUniforms.uFade.value = on ? 20 : 0;
});

bindLayer('l-floor', (on) => { layers.floor = on; });

bindLayer('l-grid', (on) => { grid.visible = on; });

el('l-size').addEventListener('input', (event) =>
{
    pointUniforms.uSize.value = Number(event.target.value);
});

// ---------------------------------------------------------------
// State handling
// ---------------------------------------------------------------

const internalPosition = new THREE.Vector3();
const droneWorld = new THREE.Vector3();

let lastResetCount = null;
let paused = false;
let haveState = false;

function onState(s)
{
    haveState = true;

    const now = performance.now();

    // Reset discards the internal frame, so the stored trajectory no
    // longer refers to anything. Recenter does NOT clear it: the
    // trajectory is kept in the internal frame and simply re-expressed
    // through the new origin.
    if (lastResetCount !== null && s.resetCount !== lastResetCount)
    {
        clearTrajectory();
    }

    lastResetCount = s.resetCount;

    el('origin-state').hidden = !s.recentered;

    if (s.origin)
    {
        setOrigin(s.origin.orientation, s.origin.position);
    }

    // ---- 3D ----
    drone.position.set(s.position.x, s.position.y, s.position.z);
    drone.quaternion.set(s.orientation.x, s.orientation.y,
                         s.orientation.z, s.orientation.w);

    if (s.tracking)
    {
        // Reported -> internal: X_int = R_o X_rep + p_o.
        internalPosition.set(s.position.x, s.position.y, s.position.z)
            .applyQuaternion(originQuaternion)
            .add(originPosition);

        pushTrajectory(internalPosition);
    }

    const g = s.geometry || {};
    const drift = s.drift || {};
    const t = s.timing || {};
    const pc = s.pointCloud || {};
    const floor = s.floor || {};

    updateFloorScene(floor, s.position);

    // ---- status ----
    paused = !!s.paused;

    el('btn-pause').disabled = paused;
    el('btn-resume').disabled = !paused;

    setText('s-vio', paused ? 'PAUSED' : 'RUNNING');
    setClass('s-vio', paused ? 'warn' : 'good');

    setText('s-tracking', s.tracking ? 'GOOD' : 'LOST');
    setClass('s-tracking', s.tracking ? 'good' : 'bad');

    if (g.motionAttempted === undefined)
    {
        setText('s-motion', '—');
    }
    else
    {
        const text = g.motionAccepted
            ? 'ACCEPTED'
            : 'REJECTED' + (g.motionRejectReason ? ': ' + g.motionRejectReason : '');

        setText('s-motion', text);
        setClass('s-motion', g.motionAccepted ? 'good' : 'bad');

        const pill = el('motion-state');
        pill.hidden = !!g.motionAccepted;
        pill.textContent = text;
        pill.className = 'pill pill-bad';
    }

    setText('s-stereo', s.stereoEnabled ? 'ACTIVE' : 'OFF');
    setClass('s-stereo', s.stereoEnabled ? 'good' : 'dim');

    setText('s-imu', s.imuEnabled
        ? (s.imuHealthy ? 'ACTIVE' : 'STALLED')
        : 'DISABLED');

    setClass('s-imu', s.imuEnabled ? (s.imuHealthy ? 'good' : 'bad') : 'dim');

    // ---- HUD ----
    const e = eulerDegrees(s.orientation);

    setText('h-viofps', num(s.fps, 1));
    setText('h-camfps', num(s.cameraFps, 1));
    setText('h-features', String(s.trackedFeatures));
    setText('h-stereo', String(s.stereoTriangulated));
    setText('h-inliers', finite(g.inliers)
        ? `${g.inliers}/${g.correspondences}` : '—');
    setText('h-depth', unit(g.depthMedian, 2, ' m'));
    setText('h-reproj', unit(g.reprojectionMedianPx, 3, ' px'));
    setText('h-relrot', unit(g.relativeRotationDeg, 4, '°'));
    setText('h-reltrans', unit(g.relativeTranslationMm, 3, ' mm'));
    setText('h-pos', `${num(s.position.x, 2)} ${num(s.position.y, 2)} ${num(s.position.z, 2)}`);
    setText('h-vel', `${num(s.velocity.x, 2)} ${num(s.velocity.y, 2)} ${num(s.velocity.z, 2)}`);
    setText('h-rpy', `${e.roll.toFixed(1)} ${e.pitch.toFixed(1)} ${e.yaw.toFixed(1)}`);

    // ---- performance ----
    setText('p-camfps', num(s.cameraFps, 1));
    setText('p-viofps', num(s.fps, 1));
    setText('p-latency', ms(s.latencyMs));
    setText('p-capture', ms(t.captureMs));
    setText('p-decode', ms(t.decodeMs));
    setText('p-detect', ms(t.detectMs));
    setText('p-track', ms(t.trackMs));
    setText('p-stereo', ms(t.stereoMs));
    setText('p-motion', ms(t.motionMs));
    setText('p-points', ms(t.pointsMs));
    setText('p-state', ms(t.stateMs));
    setText('p-frame', ms(t.totalMs));

    // ---- geometry ----
    setText('g-flow', `${unit(g.flowMedianPx, 3, '')} / ${unit(g.flowMeanPx, 3, ' px')}`);
    setText('g-disp', g.stereoPoints > 0
        ? `${num(g.disparityMedianPx, 2)} ± ${num(g.disparityStdPx, 2)} px` : '—');
    setText('g-depth', g.stereoPoints > 0 ? unit(g.depthMedian, 3, ' m') : '—');
    setText('g-depthrange', g.stereoPoints > 0
        ? `${num(g.depthMin, 2)} / ${num(g.depthMax, 2)} m` : '—');
    setText('g-depthstd', g.stereoPoints > 0 ? unit(g.depthStd, 3, ' m') : '—');
    setText('g-stereo', finite(g.stereoPoints)
        ? `${g.stereoPoints} / ${g.stereoRejected}` : '—');
    setText('g-stereorej', finite(g.stereoRejectedMatch)
        ? `${g.stereoRejectedMatch} / ${g.stereoRejectedEpipolar} / ${g.stereoRejectedDepth}` : '—');
    setText('g-miss', g.stereoPoints > 0 ? unit(g.stereoResidualPx, 3, ' px') : '—');
    setText('g-vert', g.stereoPoints > 0 ? unit(g.stereoVerticalOffsetPx, 3, ' px') : '—');

    const measured = g.motionAttempted;

    setText('g-inliers', measured ? `${g.inliers} / ${g.correspondences}` : '—');
    setText('g-ratio', measured ? unit(g.inlierRatio * 100, 1, ' %') : '—');
    setText('g-reproj', g.motionAccepted
        ? `${num(g.reprojectionMedianPx, 3)} / ${num(g.reprojectionMaxPx, 3)} px` : '—');
    setText('g-sigma', g.motionAccepted
        ? `${num(g.rotationSigmaDeg, 4)}° / ${num(g.translationSigmaMm, 3)} mm` : '—');
    setText('g-relrot', g.motionAccepted
        ? `${num(g.relativeRotationDeg, 4)}°  (${vec(g.relativeRotationVectorDeg, 3, '')})` : '—');
    setText('g-reltrans', g.motionAccepted
        ? `${num(g.relativeTranslationMm, 3)} mm  (${vec(g.relativeTranslationVectorMm, 2, '')})` : '—');
    setText('g-posedelta', `${unit(g.poseDeltaMm, 3, ' mm')} / ${unit(g.poseDeltaDeg, 4, '°')}`);
    setText('g-speed', unit(g.speed, 3, ' m/s'));
    setText('g-span', finite(g.referenceSpan) && measured ? String(g.referenceSpan) : '—');
    setText('g-motionrej', String(g.motionRejectedTotal ?? '—'));
    setText('g-reanchor', String(g.referenceResetsTotal ?? '—'));
    setText('g-stereorejtotal', String(g.stereoRejectedTotal ?? '—'));
    setText('g-corrrej', String(g.correspondencesRejectedTotal ?? '—'));

    // ---- drift ----
    setText('d-accrot', unit(drift.accumulatedRotationDeg, 2, '°'));
    setText('d-acctrans', unit(drift.accumulatedTranslationM, 3, ' m'));
    setText('d-netrot', unit(drift.netRotationDeg, 2, '°'));
    setText('d-nettrans', unit(drift.netTranslationM, 3, ' m'));

    // ---- stationary ----
    updateStationary(s.stationary);

    // ---- point cloud ----
    setText('pc-live', pc.enabled ? String(pc.livePoints) : 'disabled');
    setText('pc-map', pc.mapEnabled ? `${pc.mapPoints} / ${pc.mapCapacity}` : 'disabled');
    setText('pc-voxel', pc.mapEnabled
        ? (pc.voxelSize > 0 ? `${(pc.voxelSize * 100).toFixed(1)} cm` : 'off') : '—');
    setText('pc-gen', finite(pc.generated) ? `${pc.generated} / ${pc.accepted}` : '—');
    setText('pc-rej', finite(pc.rejected) ? String(pc.rejected) : '—');
    setText('pc-rejsplit', finite(pc.rejectedResidual)
        ? `${pc.rejectedResidual} / ${pc.rejectedUncertainty} / ${pc.rejectedNotInlier} / ${pc.rejectedNoPose}`
        : '—');
    setText('pc-ins', finite(pc.mapInserted)
        ? `${pc.mapInserted} / ${pc.mapMerged} / ${pc.mapRefined} / ${pc.mapEvicted}` : '—');
    setText('pc-innov', pc.innovationSamples > 0
        ? `${num(pc.innovationPct, 2)} % of range` : '—');
    setText('pc-mesh', layers.mesh ? String(meshTriangles) : 'off');

    // ---- floor ----
    updateFloor(floor);

    // ---- pose ----
    setText('pos-x', num(s.position.x));
    setText('pos-y', num(s.position.y));
    setText('pos-z', num(s.position.z));
    setText('rot-r', e.roll.toFixed(2) + '°');
    setText('rot-p', e.pitch.toFixed(2) + '°');
    setText('rot-y', e.yaw.toFixed(2) + '°');

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
        setText('t-fail', String(d.trackingFailures));
        setText('d-traj', num(d.trajectoryM, 3) + ' m');
    }

    // ---- graphs ----
    graphs.frame.push(t.totalMs, now);

    if (g.motionAccepted)
    {
        graphs.rot.push(g.relativeRotationDeg, now);
        graphs.trans.push(g.relativeTranslationMm, now);
        graphs.reproj.push(g.reprojectionMedianPx, now);
    }

    graphs.inliers.push(g.inliers, now);
}

// The floor panel. Everything shown is measured by the daemon; the
// browser derives nothing, which is why a lost floor blanks the rows
// instead of leaving the last numbers on screen looking live.
function updateFloor(f)
{
    if (!f || f.enabled === false)
    {
        setText('f-status', 'disabled');
        setClass('f-status', 'muted');
        setText('f-height', '—');
        return;
    }

    const status = f.status || 'UNKNOWN';

    const klass = status === 'TRACKING' ? 'good'
        : (status === 'PREDICTING' || status === 'INITIALIZING') ? 'warn'
        : 'bad';

    setText('f-status', `${status}  (${f.downSource || '—'})`);
    setClass('f-status', klass);

    // Confidence is a ranking score, not a probability - shown as a
    // bare number for that reason, never as a percentage.
    setText('f-conf', num(f.confidence, 2));

    if (!f.valid)
    {
        setText('f-height', 'GROUND UNKNOWN');
        setText('f-distance', '—');
        setText('f-normal', '—');
        setText('f-tilt', '—');
        setText('f-gravity', '—');
        setText('f-support', '—');
        setText('f-quality', '—');
        setText('f-age', '—');
        setText('f-detail', f.detail || '—');
        return;
    }

    setText('f-height', unit(f.heightM, 3, ' m'));
    setText('f-distance', unit(f.distanceM, 3, ' m'));

    setText('f-normal',
            `${num(f.normal.x, 3)} ${num(f.normal.y, 3)} ${num(f.normal.z, 3)}`);

    setText('f-tilt',
            `${unit(f.tiltDeg, 1, '°')}  (p ${num(f.pitchDeg, 1)}° / r ${num(f.rollDeg, 1)}°)`);

    // Negative means no gravity measurement was available at all,
    // which is a different thing from a disagreement of zero.
    setText('f-gravity', f.gravityDeg >= 0 ? unit(f.gravityDeg, 2, '°') : 'no IMU gravity');

    setText('f-support',
            `${f.inliers} / ${f.candidates}  (${(f.inlierFraction * 100).toFixed(0)} %)`);

    setText('f-quality',
            `${(f.rmsResidualM * 1000).toFixed(1)} mm rms, span ${num(f.spanM, 2)} m`);

    setText('f-age', unit(f.ageS, 1, ' s'));
    setText('f-detail', f.detail || '');
}

function updateStationary(r)
{
    if (!r)
    {
        return;
    }

    el('btn-stat-start').textContent = r.active ? 'Restart' : 'Start';
    el('btn-stat-stop').disabled = !r.active;
    el('stat-body').hidden = !r.haveData;

    if (!r.haveData)
    {
        return;
    }

    setText('st-window', `${num(r.durationS, 1)} s, ${r.frames} frames` +
        (r.active ? '' : ' (stopped)'));
    setText('st-trans', `${num(r.translationMeanMm, 3)} ± ${num(r.translationStdMm, 3)} mm`);
    setText('st-tbias', `${vec(r.translationBiasMm, 4, ' mm')} (${num(r.translationBiasSigma, 1)}σ)`);
    setText('st-rot', `${num(r.rotationMeanDeg, 4)} ± ${num(r.rotationStdDeg, 4)}°`);
    setText('st-rbias', `${vec(r.rotationBiasDeg, 5, '°')} (${num(r.rotationBiasSigma, 1)}σ)`);
    setText('st-flow', unit(r.flowPx, 3, ' px'));
    setText('st-depth', unit(r.depthMedianM, 2, ' m'));
    setText('st-reproj', unit(r.reprojectionPx, 3, ' px'));
    setText('st-ratio', unit(r.inlierRatio * 100, 1, ' %'));
    setText('st-vert', unit(r.stereoVerticalOffsetPx, 3, ' px'));
    setText('st-pdrift', `${unit(r.positionDriftM * 1000, 1, ' mm')}  (${vec(r.positionDrift.map((x) => x * 1000), 1, '')})`);
    setText('st-odrift', unit(r.orientationDriftDeg, 3, '°'));
    setText('st-measured', `${unit(r.measuredPositionDriftM * 1000, 1, ' mm')} / ${unit(r.measuredOrientationDriftDeg, 3, '°')}`);
    setText('st-indication', r.indication ? 'Indication: ' + r.indication : '');
}

function onRelay(r)
{
    setText('pc-rate', `${num(r.liveOutHz, 1)} / ${num(r.mapOutHz, 1)} Hz`);
    setText('pc-kbps', `${num(r.kbytesPerSecond, 1)} kB/s`);
}

// ---------------------------------------------------------------
// Transport
// ---------------------------------------------------------------

let reconnectDelay = 400;

function connect()
{
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws';

    socket = new WebSocket(`${protocol}://${location.host}`);
    socket.binaryType = 'arraybuffer';

    socket.addEventListener('open', () =>
    {
        reconnectDelay = 400;
        setPill('link-state', 'connected', 'pill-good');

        // The relay treats a new connection as holding no map; our
        // copy will be replaced by its first (reset) message.
        sendLayers();
    });

    socket.addEventListener('message', (event) =>
    {
        if (event.data instanceof ArrayBuffer)
        {
            const data = new DataView(event.data);
            const header = readHeader(data);

            if (!header)
            {
                return;
            }

            if (header.type === 1)
            {
                onLivePoints(data, header);
            }
            else if (header.type === 2)
            {
                onMapPoints(data, header);
            }

            return;
        }

        let message;

        try { message = JSON.parse(event.data); }
        catch { return; }

        if (message.type === 'vio_state')
        {
            onState(message);
        }
        else if (message.type === 'relay')
        {
            onRelay(message);
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

        // Reconnects on its own. Refreshing the page or restarting the
        // relay never requires restarting the VIO.
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

el('btn-reset').addEventListener('click', () => post('/api/v1/vio/reset'));
el('btn-recenter').addEventListener('click', () => post('/api/v1/vio/recenter'));
el('btn-pause').addEventListener('click', () => post('/api/v1/vio/pause'));
el('btn-resume').addEventListener('click', () => post('/api/v1/vio/resume'));
el('btn-clear-map').addEventListener('click', () => post('/api/v1/map/clear'));

el('btn-stat-start').addEventListener('click',
    () => post('/api/v1/vio/stationary?enabled=true'));
el('btn-stat-stop').addEventListener('click',
    () => post('/api/v1/vio/stationary?enabled=false'));

el('max-points').addEventListener('change', (event) =>
{
    resizeTrajectory(Number(event.target.value));
});

el('mesh-edge').addEventListener('change', () =>
{
    mapChangedForMesh = true;
});

// ---------------------------------------------------------------
// Render loop
//
// requestAnimationFrame, decoupled from both streams. A slow browser
// drops frames of RENDERING, never of data.
// ---------------------------------------------------------------

let lastGraphDraw = 0;

function tick(time)
{
    requestAnimationFrame(tick);

    // The map clock advances with wall time since the newest map data,
    // capped so a paused or disconnected daemon does not fade out the
    // whole map.
    const elapsed = Math.min(2, (performance.now() - mapClock.receivedAt) / 1000);
    pointUniforms.uNow.value = mapClock.latestSeen + Math.max(0, elapsed);

    scene.updateMatrixWorld();

    drone.getWorldPosition(droneWorld);
    pointUniforms.uCamera.value.copy(droneWorld);

    if (follow)
    {
        target.copy(droneWorld);
        applyView();
    }

    // Graphs at ~10 Hz; there is nothing to gain from 60.
    if (time - lastGraphDraw > 100)
    {
        lastGraphDraw = time;

        for (const graph of Object.values(graphs))
        {
            graph.draw();
        }
    }

    renderer.render(scene, view);
}

requestAnimationFrame(tick);
