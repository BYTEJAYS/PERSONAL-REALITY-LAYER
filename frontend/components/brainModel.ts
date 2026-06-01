import { BrainState, RegionName } from "@/lib/types";
import { REGIONS, REGION_ORDER, REGION_COLORS_RGB } from "@/lib/regions";

// Particle budget per region scales with that cortex's data intensity, so the
// brain literally grows where the life has more activity.
const MAX_PER_REGION = 5200;
const MIN_PER_REGION = 1400;

// --- cheap 3D value-noise for gyri-like surface wrinkles -------------------
function hash3(x: number, y: number, z: number): number {
  let h = (x * 374761393 + y * 668265263 + z * 1274126177) | 0;
  h = (Math.imul(h ^ (h >>> 13), 1274126177)) | 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
function smooth(t: number) {
  return t * t * (3 - 2 * t);
}
function vnoise(x: number, y: number, z: number): number {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  const u = smooth(xf), v = smooth(yf), w = smooth(zf);
  const c = (dx: number, dy: number, dz: number) => hash3(xi + dx, yi + dy, zi + dz);
  const x00 = c(0, 0, 0) * (1 - u) + c(1, 0, 0) * u;
  const x10 = c(0, 1, 0) * (1 - u) + c(1, 1, 0) * u;
  const x01 = c(0, 0, 1) * (1 - u) + c(1, 0, 1) * u;
  const x11 = c(0, 1, 1) * (1 - u) + c(1, 1, 1) * u;
  const y0 = x00 * (1 - v) + x10 * v;
  const y1 = x01 * (1 - v) + x11 * v;
  return y0 * (1 - w) + y1 * w;
}
function fbm(x: number, y: number, z: number): number {
  return (
    vnoise(x, y, z) * 0.6 +
    vnoise(x * 2.1, y * 2.1, z * 2.1) * 0.3 +
    vnoise(x * 4.3, y * 4.3, z * 4.3) * 0.1
  );
}

function randUnit(): [number, number, number] {
  let x = 0, y = 0, z = 0, l = 0;
  do {
    x = Math.random() * 2 - 1;
    y = Math.random() * 2 - 1;
    z = Math.random() * 2 - 1;
    l = x * x + y * y + z * z;
  } while (l > 1 || l < 1e-4);
  l = Math.sqrt(l);
  return [x / l, y / l, z / l];
}

// Per-hemisphere ellipsoid; longer front-back, narrow each side → brain-like.
const SEMI = { x: 0.32, y: 0.8, z: 1.3 };
const HEMI_OFFSET = 0.34; // centre of each hemisphere; gap at the midline

/** Sample one point on the wrinkled cortical surface of either hemisphere. */
function sampleBrainPoint(): [number, number, number] {
  const sx = Math.random() < 0.5 ? 1 : -1;
  const [dx, dy, dz] = randUnit();
  // Concentrate near the shell so the silhouette stays crisp; sparse interior.
  const shell = Math.random();
  let r = shell < 0.82 ? 0.92 + Math.random() * 0.1 : Math.pow(Math.random(), 0.5) * 0.9;
  // Gyri/sulci: undulate the radius with noise on the surface direction.
  r *= 1 + (fbm(dx * 2.4 + 9, dy * 2.4, dz * 2.4) - 0.5) * 0.28;

  let x = dx * r * SEMI.x + sx * HEMI_OFFSET;
  let y = dy * r * SEMI.y;
  let z = dz * r * SEMI.z;

  // Flatten the underside (cerebrum sits flat above the brain stem).
  if (y < 0) y *= 0.72;
  // Slight frontal lift so the brain tilts naturally.
  y += z * 0.06;
  return [x, y, z];
}

const ANCHORS = REGION_ORDER.map((n) => REGIONS[n].anchor);

function nearestRegion(x: number, y: number, z: number): number {
  let best = 0, bestD = Infinity;
  for (let i = 0; i < ANCHORS.length; i++) {
    const [ax, ay, az] = ANCHORS[i];
    const d = (x - ax) ** 2 + (y - ay) ** 2 + (z - az) ** 2;
    if (d < bestD) { bestD = d; best = i; }
  }
  return best;
}

export interface BrainModel {
  count: number;
  positions: Float32Array;  // count * 3
  seeds: Float32Array;      // count
  region: Float32Array;     // count (region index as float, for the shader)
  importance: Float32Array; // count, heavy-tailed 0..1
  // connections
  edgeCount: number;
  linePositions: Float32Array; // edgeCount * 2 * 3
  lineRegion: Float32Array;    // edgeCount * 2 (region per endpoint, for shader)
  edges: Uint32Array;          // edgeCount * 2 (node indices) — for synapse travel
  edgeRegion: Uint8Array;      // edgeCount
  edgesByRegion: number[][];   // region -> edge indices (synapse biasing)
  hubs: number[][];            // region -> node indices (association hubs)
}

export function buildBrain(state: BrainState): BrainModel {
  const intensity = new Map<RegionName, number>();
  for (const r of state.regions) intensity.set(r.region, r.intensity);

  // 1) Oversample the whole cortex once, bucket points by nearest region.
  const POOL = 46000;
  const buckets: number[][][] = REGION_ORDER.map(() => []);
  for (let i = 0; i < POOL; i++) {
    const p = sampleBrainPoint();
    buckets[nearestRegion(p[0], p[1], p[2])].push(p);
  }

  // 2) Per region, take a count proportional to its intensity.
  const chosen: number[][] = [];
  const regionOf: number[] = [];
  REGION_ORDER.forEach((name, ri) => {
    const inten = intensity.get(name) ?? 0.1;
    const target = Math.round(MIN_PER_REGION + inten * (MAX_PER_REGION - MIN_PER_REGION));
    const pool = buckets[ri];
    // Fisher–Yates partial shuffle, then take the target slice.
    const take = Math.min(target, Math.floor(pool.length * 0.95));
    for (let i = 0; i < take; i++) {
      const j = i + Math.floor(Math.random() * (pool.length - i));
      [pool[i], pool[j]] = [pool[j], pool[i]];
      chosen.push(pool[i]);
      regionOf.push(ri);
    }
  });

  const count = chosen.length;
  const positions = new Float32Array(count * 3);
  const seeds = new Float32Array(count);
  const region = new Float32Array(count);
  const importance = new Float32Array(count);

  for (let i = 0; i < count; i++) {
    positions[i * 3] = chosen[i][0];
    positions[i * 3 + 1] = chosen[i][1];
    positions[i * 3 + 2] = chosen[i][2];
    seeds[i] = Math.random() * 1000;
    region[i] = regionOf[i];
    importance[i] = Math.pow(Math.random(), 3); // few bright hubs, many dim nodes
  }

  // 3) Region hubs = brightest nodes (used for long-range fibers + thought).
  const hubs: number[][] = REGION_ORDER.map(() => []);
  {
    const byRegion: number[][] = REGION_ORDER.map(() => []);
    for (let i = 0; i < count; i++) byRegion[regionOf[i]].push(i);
    byRegion.forEach((idxs, ri) => {
      idxs.sort((a, b) => importance[b] - importance[a]);
      hubs[ri] = idxs.slice(0, 8);
    });
  }

  // 4) Neural connections via a spatial hash (each node → a few near neighbours).
  const CELL = 0.17;
  const grid = new Map<string, number[]>();
  const key = (x: number, y: number, z: number) =>
    `${Math.floor(x / CELL)},${Math.floor(y / CELL)},${Math.floor(z / CELL)}`;
  for (let i = 0; i < count; i++) {
    const k = key(positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]);
    (grid.get(k) ?? grid.set(k, []).get(k)!).push(i);
  }

  const edgeSet = new Set<number>();
  const edgesA: number[] = [];
  const edgesB: number[] = [];
  const R2 = 0.21 * 0.21;
  for (let i = 0; i < count; i++) {
    const x = positions[i * 3], y = positions[i * 3 + 1], z = positions[i * 3 + 2];
    const cx = Math.floor(x / CELL), cy = Math.floor(y / CELL), cz = Math.floor(z / CELL);
    const cand: [number, number][] = [];
    for (let ox = -1; ox <= 1 && cand.length < 24; ox++)
      for (let oy = -1; oy <= 1; oy++)
        for (let oz = -1; oz <= 1; oz++) {
          const cell = grid.get(`${cx + ox},${cy + oy},${cz + oz}`);
          if (!cell) continue;
          for (const j of cell) {
            if (j === i) continue;
            const d = (positions[j * 3] - x) ** 2 + (positions[j * 3 + 1] - y) ** 2 + (positions[j * 3 + 2] - z) ** 2;
            if (d < R2) cand.push([d, j]);
          }
        }
    cand.sort((a, b) => a[0] - b[0]);
    const links = 1 + (importance[i] > 0.4 ? 2 : 1); // hubs wire more
    for (let n = 0; n < Math.min(links, cand.length); n++) {
      const j = cand[n][1];
      const a = Math.min(i, j), b = Math.max(i, j);
      const id = a * count + b;
      if (edgeSet.has(id)) continue;
      edgeSet.add(id);
      edgesA.push(a); edgesB.push(b);
    }
  }

  // 5) Long-range association fibers between region hubs.
  for (let a = 0; a < REGION_ORDER.length; a++)
    for (let b = a + 1; b < REGION_ORDER.length; b++) {
      const ha = hubs[a], hb = hubs[b];
      const n = Math.min(3, ha.length, hb.length);
      for (let k = 0; k < n; k++) {
        edgesA.push(ha[k]); edgesB.push(hb[(k + 1) % hb.length]);
      }
    }

  const edgeCount = edgesA.length;
  const edges = new Uint32Array(edgeCount * 2);
  const edgeRegion = new Uint8Array(edgeCount);
  const linePositions = new Float32Array(edgeCount * 6);
  const lineRegion = new Float32Array(edgeCount * 2);
  const edgesByRegion: number[][] = REGION_ORDER.map(() => []);

  for (let e = 0; e < edgeCount; e++) {
    const a = edgesA[e], b = edgesB[e];
    edges[e * 2] = a; edges[e * 2 + 1] = b;
    const ri = regionOf[a];
    edgeRegion[e] = ri;
    edgesByRegion[ri].push(e);
    linePositions[e * 6] = positions[a * 3];
    linePositions[e * 6 + 1] = positions[a * 3 + 1];
    linePositions[e * 6 + 2] = positions[a * 3 + 2];
    linePositions[e * 6 + 3] = positions[b * 3];
    linePositions[e * 6 + 4] = positions[b * 3 + 1];
    linePositions[e * 6 + 5] = positions[b * 3 + 2];
    lineRegion[e * 2] = ri;
    lineRegion[e * 2 + 1] = regionOf[b];
  }

  return {
    count, positions, seeds, region, importance,
    edgeCount, linePositions, lineRegion, edges, edgeRegion, edgesByRegion, hubs,
  };
}

export function densitySignature(state: BrainState): string {
  return state.regions
    .map((r) => `${r.region}:${Math.round(r.intensity * 16)}`)
    .sort()
    .join("|");
}

export { REGION_COLORS_RGB };
