// Experimental surface mesh from the accumulated point map.
//
// Runs in a Web Worker, on a copy of the map, a couple of times a
// second at most. It is a VISUALISATION of the point cloud and nothing
// more: the points remain the data, and this never feeds back into
// anything. It deliberately does not attempt a watertight surface.
//
// Method - local neighbourhood fans:
//
//   1. Bucket points into a uniform grid with cell = maxEdge, so every
//      neighbour within maxEdge is in the 27 surrounding cells.
//   2. For each point, take up to K nearest neighbours within maxEdge.
//   3. Estimate the local surface normal as the smallest-eigenvalue
//      eigenvector of the neighbourhood covariance (power iteration on
//      a shifted matrix - no library needed).
//   4. Sort neighbours by angle around that normal and connect each
//      consecutive pair into a triangle with the centre point, only if
//      the angular gap is under 90 degrees and every edge is shorter
//      than maxEdge. Long edges are exactly where there is no surface
//      evidence, so they are rejected rather than bridged.
//   5. Deduplicate triangles found from several of their corners.
//
// Cost is O(N K log K); with the map budget capped this stays well
// inside a worker's time slice.

const MAX_NEIGHBOURS = 8;
const MAX_TRIANGLES = 120000;

self.onmessage = ({ data }) =>
{
    const positions = data.positions;
    const maxEdge = Math.max(0.005, data.maxEdge);
    const count = positions.length / 3;

    const indices = triangulate(positions, count, maxEdge);

    self.postMessage({ positions, indices }, [positions.buffer, indices.buffer]);
};

function triangulate(p, count, maxEdge)
{
    const maxEdge2 = maxEdge * maxEdge;
    const inverseCell = 1 / maxEdge;

    // ---- 1. grid ----
    const cells = new Map();

    const keyOf = (x, y, z) =>
        // Cell coordinates stay small for a local map; a string key is
        // unambiguous and fast enough at this rate.
        `${x},${y},${z}`;

    for (let i = 0; i < count; ++i)
    {
        const key = keyOf(
            Math.floor(p[i * 3] * inverseCell),
            Math.floor(p[i * 3 + 1] * inverseCell),
            Math.floor(p[i * 3 + 2] * inverseCell)
        );

        let bucket = cells.get(key);

        if (!bucket)
        {
            bucket = [];
            cells.set(key, bucket);
        }

        bucket.push(i);
    }

    const triangles = [];
    const seen = new Set();

    const neighbourIndex = new Int32Array(64);
    const neighbourDistance = new Float64Array(64);
    const order = [];

    for (let i = 0; i < count && triangles.length < MAX_TRIANGLES * 3; ++i)
    {
        const px = p[i * 3];
        const py = p[i * 3 + 1];
        const pz = p[i * 3 + 2];

        const cx = Math.floor(px * inverseCell);
        const cy = Math.floor(py * inverseCell);
        const cz = Math.floor(pz * inverseCell);

        // ---- 2. neighbours ----
        let found = 0;

        for (let dx = -1; dx <= 1; ++dx)
        for (let dy = -1; dy <= 1; ++dy)
        for (let dz = -1; dz <= 1; ++dz)
        {
            const bucket = cells.get(keyOf(cx + dx, cy + dy, cz + dz));

            if (!bucket) continue;

            for (const j of bucket)
            {
                if (j === i || found >= 64) continue;

                const ex = p[j * 3] - px;
                const ey = p[j * 3 + 1] - py;
                const ez = p[j * 3 + 2] - pz;

                const d2 = ex * ex + ey * ey + ez * ez;

                if (d2 < maxEdge2 && d2 > 1e-12)
                {
                    neighbourIndex[found] = j;
                    neighbourDistance[found] = d2;
                    ++found;
                }
            }
        }

        if (found < 2) continue;

        order.length = 0;

        for (let k = 0; k < found; ++k) order.push(k);

        order.sort((a, b) => neighbourDistance[a] - neighbourDistance[b]);

        const used = Math.min(MAX_NEIGHBOURS, found);

        // ---- 3. normal ----
        let mx = px, my = py, mz = pz;

        for (let k = 0; k < used; ++k)
        {
            const j = neighbourIndex[order[k]];
            mx += p[j * 3]; my += p[j * 3 + 1]; mz += p[j * 3 + 2];
        }

        const n = used + 1;
        mx /= n; my /= n; mz /= n;

        let xx = 0, xy = 0, xz = 0, yy = 0, yz = 0, zz = 0;

        const accumulate = (qx, qy, qz) =>
        {
            const a = qx - mx, b = qy - my, c = qz - mz;
            xx += a * a; xy += a * b; xz += a * c;
            yy += b * b; yz += b * c; zz += c * c;
        };

        accumulate(px, py, pz);

        for (let k = 0; k < used; ++k)
        {
            const j = neighbourIndex[order[k]];
            accumulate(p[j * 3], p[j * 3 + 1], p[j * 3 + 2]);
        }

        // Smallest eigenvector of C = largest of (trace * I - C).
        const trace = xx + yy + zz;

        if (trace < 1e-14) continue;

        let vx = 0.577, vy = 0.577, vz = 0.577;

        for (let it = 0; it < 12; ++it)
        {
            const wx = (trace - xx) * vx - xy * vy - xz * vz;
            const wy = -xy * vx + (trace - yy) * vy - yz * vz;
            const wz = -xz * vx - yz * vy + (trace - zz) * vz;

            const length = Math.hypot(wx, wy, wz);

            if (length < 1e-18) break;

            vx = wx / length; vy = wy / length; vz = wz / length;
        }

        // ---- 4. fan ----
        // Tangent basis (u, w) perpendicular to the normal v.
        let ux, uy, uz;

        if (Math.abs(vx) < 0.9) { ux = 0; uy = vz; uz = -vy; }
        else { ux = -vz; uy = 0; uz = vx; }

        const ul = Math.hypot(ux, uy, uz);
        ux /= ul; uy /= ul; uz /= ul;

        const tx = vy * uz - vz * uy;
        const ty = vz * ux - vx * uz;
        const tz = vx * uy - vy * ux;

        const fan = [];

        for (let k = 0; k < used; ++k)
        {
            const j = neighbourIndex[order[k]];

            const ex = p[j * 3] - px;
            const ey = p[j * 3 + 1] - py;
            const ez = p[j * 3 + 2] - pz;

            fan.push({
                j,
                angle: Math.atan2(ex * tx + ey * ty + ez * tz,
                                  ex * ux + ey * uy + ez * uz),
            });
        }

        fan.sort((a, b) => a.angle - b.angle);

        for (let k = 0; k < fan.length; ++k)
        {
            const a = fan[k];
            const b = fan[(k + 1) % fan.length];

            let gap = b.angle - a.angle;

            if (gap <= 0) gap += 2 * Math.PI;

            if (gap > Math.PI / 2 || a.j === b.j) continue;

            const ex = p[a.j * 3] - p[b.j * 3];
            const ey = p[a.j * 3 + 1] - p[b.j * 3 + 1];
            const ez = p[a.j * 3 + 2] - p[b.j * 3 + 2];

            if (ex * ex + ey * ey + ez * ez >= maxEdge2) continue;

            // ---- 5. dedupe ----
            let i0 = i, i1 = a.j, i2 = b.j;

            if (i0 > i1) [i0, i1] = [i1, i0];
            if (i1 > i2) [i1, i2] = [i2, i1];
            if (i0 > i1) [i0, i1] = [i1, i0];

            // Numeric key is exact while count^3 < 2^53 (~200 000
            // points); past that, a string key stays unambiguous.
            const key = count < 200000
                ? (i0 * count + i1) * count + i2
                : `${i0},${i1},${i2}`;

            if (seen.has(key)) continue;

            seen.add(key);
            triangles.push(i, a.j, b.j);
        }
    }

    return new Uint32Array(triangles);
}
