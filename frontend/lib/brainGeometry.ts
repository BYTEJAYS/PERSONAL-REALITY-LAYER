// Procedural particle brain — a folded cortical surface (two hemispheres with a
// longitudinal fissure), cerebellum, and brain stem, sampled into points, with a
// dispersing "dust" halo. Monochrome, to match the reference Spline scene.

// ---------- value noise + ridged fbm (gyri / sulci) ------------------------
function hash3(x: number, y: number, z: number): number {
  let h = (x * 374761393 + y * 668265263 + z * 1274126177) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177) | 0;
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}
const sm = (t: number) => t * t * (3 - 2 * t);
function vnoise(x: number, y: number, z: number): number {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  const u = sm(xf), v = sm(yf), w = sm(zf);
  const c = (dx: number, dy: number, dz: number) => hash3(xi + dx, yi + dy, zi + dz);
  const x00 = c(0, 0, 0) * (1 - u) + c(1, 0, 0) * u;
  const x10 = c(0, 1, 0) * (1 - u) + c(1, 1, 0) * u;
  const x01 = c(0, 0, 1) * (1 - u) + c(1, 0, 1) * u;
  const x11 = c(0, 1, 1) * (1 - u) + c(1, 1, 1) * u;
  return (x00 * (1 - v) + x10 * v) * (1 - w) + (x01 * (1 - v) + x11 * v) * w;
}
// Ridged multifractal → sharp creases that read as cortical folds.
function ridged(x: number, y: number, z: number, oct: number, lac = 2.0): number {
  let sum = 0, amp = 0.5, freq = 1, norm = 0;
  for (let i = 0; i < oct; i++) {
    const n = 1 - Math.abs(2 * vnoise(x * freq, y * freq, z * freq) - 1);
    sum += n * n * amp;
    norm += amp;
    amp *= 0.5;
    freq *= lac;
  }
  return sum / norm;
}

function randUnit(): [number, number, number] {
  let x = 0, y = 0, z = 0, l = 0;
  do {
    x = Math.random() * 2 - 1; y = Math.random() * 2 - 1; z = Math.random() * 2 - 1;
    l = x * x + y * y + z * z;
  } while (l > 1 || l < 1e-4);
  l = Math.sqrt(l);
  return [x / l, y / l, z / l];
}

interface Comp {
  c: [number, number, number];   // centre
  s: [number, number, number];   // semi-axes
  freq: number;                  // fold frequency
  amp: number;                   // fold depth
  oct: number;
}

// Cerebrum hemispheres are wide & long; cerebellum tighter folds; stem smooth.
const HEMI_L: Comp = { c: [-0.46, 0.06, 0.0], s: [0.5, 0.72, 1.04], freq: 6.5, amp: 0.12, oct: 4 };
const HEMI_R: Comp = { c: [0.46, 0.06, 0.0], s: [0.5, 0.72, 1.04], freq: 6.5, amp: 0.12, oct: 4 };
const CEREB: Comp = { c: [0.0, -0.52, -0.92], s: [0.64, 0.4, 0.46], freq: 16.0, amp: 0.07, oct: 3 };
const STEM: Comp = { c: [0.0, -0.82, -0.52], s: [0.14, 0.34, 0.16], freq: 4.0, amp: 0.03, oct: 2 };

function insideOther(x: number, y: number, z: number, comp: Comp, iso: number): boolean {
  // Hide internal seams: drop points that fall well inside a *different* lobe.
  for (const o of [HEMI_L, HEMI_R, CEREB]) {
    if (o === comp) continue;
    const dx = (x - o.c[0]) / o.s[0];
    const dy = (y - o.c[1]) / o.s[1];
    const dz = (z - o.c[2]) / o.s[2];
    if (dx * dx + dy * dy + dz * dz < iso) return true;
  }
  return false;
}

function sampleComp(comp: Comp, sx: number): [number, number, number] | null {
  const [dx, dy, dz] = randUnit();
  // Fold the surface inward along ridge lines.
  const n = ridged(dx * comp.freq + 11.3, dy * comp.freq + 4.7, dz * comp.freq + 19.1, comp.oct);
  const r = 1 - n * comp.amp;
  let x = comp.c[0] + dx * r * comp.s[0];
  let y = comp.c[1] + dy * r * comp.s[1];
  let z = comp.c[2] + dz * r * comp.s[2];

  if (comp === HEMI_L || comp === HEMI_R) {
    // Medial wall + longitudinal fissure: flatten the inner face, leave a gap.
    if (sx > 0 && x < 0.06) x = 0.06 + (x - 0.06) * 0.12;
    if (sx < 0 && x > -0.06) x = -0.06 + (x + 0.06) * 0.12;
    // Flatter underside of the cerebrum.
    if (y < -0.04) y = -0.04 + (y + 0.04) * 0.7;
  }
  if (insideOther(x, y, z, comp, 0.82)) return null;
  return [x, y, z];
}

export interface BrainParticles {
  count: number;
  positions: Float32Array;
  seeds: Float32Array;
  sizes: Float32Array;
  bright: Float32Array;
}

export function generateBrainParticles(scale = 1): BrainParticles {
  const SURFACE = Math.round(95000 * scale);
  const DUST = Math.round(42000 * scale);
  const total = SURFACE + DUST;

  const positions = new Float32Array(total * 3);
  const seeds = new Float32Array(total);
  const sizes = new Float32Array(total);
  const bright = new Float32Array(total);

  // Allocate surface budget by approximate area.
  const plan: [Comp, number, number][] = [
    [HEMI_L, Math.round(SURFACE * 0.39), -1],
    [HEMI_R, Math.round(SURFACE * 0.39), 1],
    [CEREB, Math.round(SURFACE * 0.18), 0],
    [STEM, Math.round(SURFACE * 0.04), 0],
  ];

  let p = 0;
  const surfRef: number[] = []; // indices of surface points, for dust seeding
  for (const [comp, n, sx] of plan) {
    let made = 0, attempts = 0;
    const cap = n * 4 + 2000;
    while (made < n && attempts < cap) {
      attempts++;
      const s = sampleComp(comp, sx);
      if (!s) continue;
      positions[p * 3] = s[0];
      positions[p * 3 + 1] = s[1];
      positions[p * 3 + 2] = s[2];
      seeds[p] = Math.random() * 1000;
      // Mostly fine dim points, a sparse few bright → crisp, not a white slab.
      const b = 0.55 + Math.pow(Math.random(), 2.2) * 0.45;
      bright[p] = b;
      sizes[p] = 0.9 + Math.random() * 1.0 + (b > 0.95 ? 1.2 : 0);
      surfRef.push(p);
      p++; made++;
    }
  }

  const surfCount = p;

  // Dust halo: particles lifting off the surface into space, drifting +x/up a
  // touch like the reference, fading with distance.
  for (let i = 0; i < DUST && surfCount > 0; i++) {
    const sIdx = surfRef[(Math.random() * surfCount) | 0];
    const sxp = positions[sIdx * 3], syp = positions[sIdx * 3 + 1], szp = positions[sIdx * 3 + 2];
    const len = Math.hypot(sxp, syp, szp) || 1;
    const nx = sxp / len, ny = syp / len, nz = szp / len;
    const d = Math.pow(Math.random(), 1.8) * 1.4;
    const jitter = () => (Math.random() - 0.5) * 0.5 * d;
    positions[p * 3] = sxp + nx * d + jitter() + d * 0.25;       // slight +x drift
    positions[p * 3 + 1] = syp + ny * d + jitter() + d * 0.12;   // slight up drift
    positions[p * 3 + 2] = szp + nz * d + jitter();
    seeds[p] = Math.random() * 1000;
    bright[p] = (0.12 + Math.random() * 0.4) * (1 - d / 1.8);     // dimmer further out
    sizes[p] = 0.6 + Math.random() * 0.8;
    p++;
  }

  return {
    count: p,
    positions: positions.subarray(0, p * 3),
    seeds: seeds.subarray(0, p),
    sizes: sizes.subarray(0, p),
    bright: bright.subarray(0, p),
  };
}
