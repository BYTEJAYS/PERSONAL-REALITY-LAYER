"use client";

/**
 * PlutoHead — the stylized PLUTONDURAK head as a floating R3F avatar.
 * Ported from the standalone Three.js sculpt; transparent background so it
 * sits on the journal's dark surface. Idle: breathing, sway, blink, hair +
 * mustache micro-motion.
 */

import { useMemo } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

/* ----------------------------------------------------------------- palette */
const C = {
  skin: 0xe8ded1, hairA: 0xc62f1e, hairB: 0x7a1c12, brow: 0x59310a,
  lid: 0x8c653b, glass: 0x666666, lens: 0xd7ecf0, nose: 0xd49a84,
  blush: 0xd88268, earIn: 0xa75e4b, must: 0x141414, beard: 0x141414,
};

/* --------------------------------------------------------- painterly helpers */
function softRamp() {
  const n = 96, data = new Uint8Array(n * 4);
  for (let i = 0; i < n; i++) {
    const t = i / (n - 1);
    let v = 0.66 + 0.34 * t + 0.03 * Math.sin(t * Math.PI * 3);
    v = Math.max(0.6, Math.min(1, v));
    const c = Math.round(v * 255);
    data[i * 4] = c; data[i * 4 + 1] = c; data[i * 4 + 2] = c; data[i * 4 + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, n, 1, THREE.RGBAFormat);
  tex.needsUpdate = true; tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function mottle(hex: number, { patches = 40, spread = 0.16, light = 0.16, dark = 0.2, size = 256 } = {}) {
  const cv = document.createElement("canvas"); cv.width = cv.height = size;
  const x = cv.getContext("2d")!;
  const base = new THREE.Color(hex);
  const hsl = { h: 0, s: 0, l: 0 }; base.getHSL(hsl);
  x.fillStyle = `#${base.getHexString()}`; x.fillRect(0, 0, size, size);
  for (let i = 0; i < patches; i++) {
    const px = Math.random() * size, py = Math.random() * size;
    const r = size * (0.05 + Math.random() * 0.16);
    const dl = Math.random() * 2 - 1;
    const l = THREE.MathUtils.clamp(hsl.l + (dl > 0 ? light : -dark) * Math.abs(dl), 0.02, 0.97);
    const h = (hsl.h + (Math.random() * 2 - 1) * spread * 0.12 + 1) % 1;
    const s = THREE.MathUtils.clamp(hsl.s + (Math.random() * 2 - 1) * 0.1, 0, 1);
    const col = new THREE.Color().setHSL(h, s, l);
    const g = x.createRadialGradient(px, py, 0, px, py, r);
    g.addColorStop(0, `rgba(${(col.r * 255) | 0},${(col.g * 255) | 0},${(col.b * 255) | 0},${0.16 + Math.random() * 0.22})`);
    g.addColorStop(1, "rgba(0,0,0,0)");
    x.fillStyle = g; x.beginPath(); x.arc(px, py, r, 0, 7); x.fill();
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace; tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function radialTex(stops: [number, string][]) {
  const s = 128, cv = document.createElement("canvas"); cv.width = cv.height = s;
  const x = cv.getContext("2d")!; const g = x.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
  stops.forEach(([o, c]) => g.addColorStop(o, c));
  x.fillStyle = g; x.fillRect(0, 0, s, s);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; return t;
}

/* ---------------------------------------------------------- build the sculpt */
type Built = { root: THREE.Group; tick: (t: number) => void };

function buildHead(): Built {
  const RAMP = softRamp();
  const paint = (hex: number, map?: THREE.Texture) =>
    new THREE.MeshToonMaterial({ color: hex, gradientMap: RAMP, map: map ?? null });

  const blob = (mat: THREE.Material, r: number, detail = 2, jitter = 0.14) => {
    const g = new THREE.IcosahedronGeometry(r, detail);
    const p = g.attributes.position; const v = new THREE.Vector3();
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i);
      const n = 1 + (Math.sin(v.x * 5.3) + Math.cos(v.y * 4.7) + Math.sin(v.z * 6.1)) * 0.018 + (Math.random() - 0.5) * jitter * 0.12;
      v.multiplyScalar(n); p.setXYZ(i, v.x, v.y, v.z);
    }
    g.computeVertexNormals();
    return new THREE.Mesh(g, mat);
  };

  const root = new THREE.Group();
  const headPivot = new THREE.Group(); root.add(headPivot);
  const head = new THREE.Group(); headPivot.add(head);

  const SKIN = paint(C.skin, mottle(C.skin, { patches: 38, light: 0.1, dark: 0.1 }));
  (SKIN.map as THREE.Texture).repeat.set(2, 2);

  // cranium / cheeks / jaw
  const cranium = blob(SKIN, 1.06, 4, 0.05); cranium.scale.set(1.05, 1.02, 0.92); cranium.position.y = 0.16; head.add(cranium);
  const cheek = (s: number) => { const m = blob(SKIN, 0.5, 3, 0.06); m.scale.set(0.9, 0.78, 0.7); m.position.set(s * 0.46, -0.46, 0.62); if (s < 0) m.scale.multiplyScalar(1.05); head.add(m); };
  cheek(-1); cheek(1);
  const jaw = blob(SKIN, 0.6, 3, 0.05); jaw.scale.set(0.92, 0.62, 0.74); jaw.position.set(0.02, -0.86, 0.42); head.add(jaw);

  // ears
  const ear = (s: number) => {
    const g = new THREE.Group();
    const outer = blob(SKIN, 0.32, 3, 0.05); outer.scale.set(0.62, 1.0, 0.4); g.add(outer);
    const inner = blob(paint(C.earIn, mottle(C.earIn, { patches: 18 })), 0.2, 2, 0.05); inner.scale.set(0.5, 0.85, 0.35); inner.position.set(s * -0.04, -0.02, 0.12); g.add(inner);
    g.position.set(s * 1.08, -0.16, 0.24); g.rotation.z = s * -0.18; g.rotation.y = s * 0.4; g.scale.setScalar(1.12); if (s < 0) g.scale.multiplyScalar(1.06);
    head.add(g);
  };
  ear(-1); ear(1);

  // nose + nostrils
  const nose = blob(paint(C.nose, mottle(C.nose, { patches: 14, light: 0.12 })), 0.17, 2, 0.05); nose.scale.set(1.05, 0.85, 0.95); nose.position.set(0, -0.34, 1.0); head.add(nose);
  [-1, 1].forEach((s) => { const n = blob(paint(0xb07866), 0.05, 1, 0); n.scale.set(1, 0.6, 0.6); n.position.set(s * 0.075, -0.4, 1.06); head.add(n); });

  // blush
  const blushTex = radialTex([[0, "rgba(216,130,104,0.85)"], [0.6, "rgba(216,130,104,0.45)"], [1, "rgba(216,130,104,0)"]]);
  const blush = (s: number) => { const m = new THREE.Mesh(new THREE.CircleGeometry(0.27, 40), new THREE.MeshBasicMaterial({ map: blushTex, transparent: true, depthWrite: false })); m.position.set(s * 0.5, -0.42, 1.0); m.scale.set(1, 0.82, 1); m.renderOrder = 2; head.add(m); };
  blush(-1); blush(1);

  // eyes
  const eyes = new THREE.Group(); head.add(eyes);
  const eye = (s: number) => {
    const g = new THREE.Group();
    const lid = new THREE.Mesh(new THREE.TorusGeometry(0.13, 0.026, 8, 24, Math.PI * 0.92), paint(C.lid));
    lid.rotation.z = Math.PI + (s < 0 ? -0.12 : 0.08); lid.position.set(0, 0.02, 0); g.add(lid);
    const low = new THREE.Mesh(new THREE.TorusGeometry(0.12, 0.012, 6, 20, Math.PI * 0.7), paint(0xc9a98a)); low.position.y = -0.05; g.add(low);
    g.position.set(s * 0.42, -0.12, 0.9); eyes.add(g); return g;
  };
  const eyeL = eye(-1), eyeR = eye(1);

  // eyebrows
  const brow = (s: number) => { const b = new THREE.Mesh(new THREE.TorusGeometry(0.18, 0.03, 6, 20, Math.PI * 0.55), paint(C.brow)); b.rotation.z = Math.PI - s * 0.12; b.position.set(s * 0.42, 0.12, 0.92); b.scale.set(1, 0.7, 1); head.add(b); };
  brow(-1); brow(1);

  // glasses
  const frameMat = new THREE.MeshStandardMaterial({ color: C.glass, metalness: 0.85, roughness: 0.42 });
  const lensMat = new THREE.MeshPhysicalMaterial({ color: C.lens, roughness: 0.06, metalness: 0, transparent: true, opacity: 0.15, depthWrite: false, clearcoat: 0.25, clearcoatRoughness: 0.15, reflectivity: 0.18, side: THREE.DoubleSide });
  const R = 0.43;
  const lensUnit = (s: number) => {
    const g = new THREE.Group();
    g.add(new THREE.Mesh(new THREE.TorusGeometry(R, 0.022, 12, 48), frameMat));
    const lens = new THREE.Mesh(new THREE.CircleGeometry(R * 0.97, 48), lensMat); lens.position.z = -0.005; lens.renderOrder = 3; g.add(lens);
    const glint = new THREE.Mesh(new THREE.CircleGeometry(R * 0.2, 24), new THREE.MeshBasicMaterial({ map: radialTex([[0, "rgba(255,255,255,0.5)"], [1, "rgba(255,255,255,0)"]]), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    glint.position.set(-R * 0.4, R * 0.42, 0.03); glint.scale.set(1.6, 0.6, 1); glint.rotation.z = -0.5; glint.renderOrder = 5; g.add(glint);
    const glow = new THREE.Mesh(new THREE.RingGeometry(R * 0.9, R * 1.0, 48), new THREE.MeshBasicMaterial({ color: 0xeaf6fb, transparent: true, opacity: 0.1, depthWrite: false, blending: THREE.AdditiveBlending })); glow.position.z = 0.01; g.add(glow);
    g.position.set(s * 0.44, -0.12, 1.02); g.rotation.y = s * 0.06; return g;
  };
  const tube = (pts: number[][], r = 0.016) => {
    const curve = new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(p[0], p[1], p[2])));
    return new THREE.Mesh(new THREE.TubeGeometry(curve, 24, r, 8, false), frameMat);
  };
  const glasses = new THREE.Group(); head.add(glasses);
  glasses.add(lensUnit(-1), lensUnit(1));
  glasses.add(tube([[-0.16, -0.16, 1.06], [0, -0.2, 1.09], [0.16, -0.16, 1.06]], 0.013));
  glasses.add(tube([[-0.86, -0.1, 1.0], [-1.0, -0.12, 0.55], [-1.05, -0.15, 0.1]]));
  glasses.add(tube([[0.86, -0.1, 1.0], [1.0, -0.12, 0.55], [1.05, -0.15, 0.1]]));

  // mustache
  const mustGrp = new THREE.Group(); head.add(mustGrp);
  const mustMat = paint(C.must, mottle(C.must, { patches: 30, light: 0.1, dark: 0.12 }));
  const mustChunk = (x: number, y: number, z: number, sx: number, sy: number, sz: number, rot = 0) => { const m = blob(mustMat, 0.2, 2, 0.18); m.scale.set(sx, sy, sz); m.position.set(x, y, z); m.rotation.z = rot; mustGrp.add(m); };
  mustChunk(0, -0.47, 1.02, 2.1, 0.62, 0.85);
  mustChunk(-0.34, -0.5, 0.98, 1.15, 0.72, 0.78, 0.3);
  mustChunk(0.34, -0.5, 0.98, 1.15, 0.72, 0.78, -0.3);
  mustChunk(-0.56, -0.64, 0.84, 0.7, 1.05, 0.62, 1.0);
  mustChunk(0.56, -0.64, 0.84, 0.7, 1.05, 0.62, -1.0);
  const mustBaseZ = mustGrp.rotation.z;

  // beard
  const beardMat = paint(C.beard, mottle(C.beard, { patches: 34, light: 0.08, dark: 0.12 }));
  const beardChunk = (x: number, y: number, z: number, s: number) => { const m = blob(beardMat, 0.2 * s, 2, 0.2); m.position.set(x, y, z); m.scale.set(1, 0.9, 0.8); head.add(m); };
  beardChunk(0, -0.95, 0.82, 1.05); beardChunk(-0.26, -0.86, 0.78, 0.72); beardChunk(0.26, -0.86, 0.78, 0.7);
  beardChunk(-0.44, -0.74, 0.6, 0.5); beardChunk(0.44, -0.74, 0.6, 0.5); beardChunk(0, -1.05, 0.7, 0.7);

  // hair
  const hair = new THREE.Group(); head.add(hair);
  const orangeMat = paint(C.hairA, mottle(C.hairA, { patches: 28, light: 0.12, dark: 0.1 }));
  const brownMat = paint(C.hairB, mottle(C.hairB, { patches: 24, light: 0.16, dark: 0.1 }));
  (orangeMat.map as THREE.Texture).repeat.set(2, 2); (brownMat.map as THREE.Texture).repeat.set(2, 2);
  const hairChunk = (mat: THREE.Material, x: number, y: number, z: number, s: number, sx = 1, sy = 1, sz = 1) => {
    const m = blob(mat, s, 3, 0.16); m.position.set(x, y, z); m.scale.set(sx, sy, sz);
    m.rotation.set(Math.random() * 0.5, Math.random() * 0.6, (Math.random() - 0.5) * 0.5); hair.add(m);
  };
  hairChunk(orangeMat, 0.05, 0.95, 0.15, 0.62, 1.5, 1.0, 1.35);
  hairChunk(orangeMat, 0.35, 0.86, 0.35, 0.5, 1.2, 0.95, 1.1);
  hairChunk(orangeMat, -0.3, 0.92, 0.25, 0.5, 1.2, 1.0, 1.1);
  hairChunk(orangeMat, 0.78, 0.5, 0.25, 0.5, 0.95, 1.25, 1.0);
  hairChunk(orangeMat, 0.86, 0.18, 0.15, 0.42, 0.9, 1.1, 0.95);
  hairChunk(brownMat, -0.72, 0.55, 0.2, 0.58, 1.1, 1.4, 1.05);
  hairChunk(brownMat, -0.86, 0.2, 0.05, 0.5, 1.0, 1.25, 1.0);
  hairChunk(brownMat, -0.7, -0.05, -0.05, 0.42, 0.9, 1.1, 0.95);
  hairChunk(brownMat, -0.5, 0.78, 0.0, 0.5, 1.1, 1.1, 1.0);
  hairChunk(brownMat, 0.0, 0.55, -0.7, 0.7, 1.4, 1.2, 1.0);
  hairChunk(orangeMat, 0.4, 0.6, -0.5, 0.5, 1.1, 1.1, 1.0);

  // fringe
  const fringeBand = blob(orangeMat, 0.5, 3, 0.18); fringeBand.scale.set(1.7, 0.62, 0.7); fringeBand.position.set(-0.05, 0.5, 0.7); fringeBand.rotation.z = -0.06; hair.add(fringeBand);
  const locks: [number, number, number, number][] = [[-0.62, 0.3, 0.78, 0.6], [-0.3, 0.2, 0.9, 0.55], [0.02, 0.26, 0.95, 0.5], [0.34, 0.2, 0.9, 0.55], [0.62, 0.32, 0.78, 0.5], [-0.46, 0.4, 0.86, 0.45]];
  locks.forEach(([x, y, z, h], i) => { const m = blob(i === 0 ? brownMat : orangeMat, 0.2, 3, 0.2); m.position.set(x, y - Math.random() * 0.05, z); m.scale.set(0.62, h + 0.5, 0.6); m.rotation.z = -x * 0.5; hair.add(m); });

  // upward strands
  const strands: { mesh: THREE.Mesh; phase: number; base: THREE.Euler }[] = [];
  for (let i = 0; i < 7; i++) {
    const m = new THREE.Mesh(new THREE.ConeGeometry(0.03, 0.34 + Math.random() * 0.2, 6), Math.random() < 0.5 ? orangeMat : brownMat);
    const a = Math.random() * Math.PI * 2, rr = 0.2 + Math.random() * 0.45;
    m.position.set(Math.cos(a) * rr, 1.32 + Math.random() * 0.12, Math.sin(a) * rr * 0.7);
    m.rotation.set((Math.random() - 0.5) * 0.6, 0, (Math.random() - 0.5) * 0.6);
    hair.add(m); strands.push({ mesh: m, phase: Math.random() * 7, base: m.rotation.clone() });
  }

  // idle animation
  let nextBlink = 4 + Math.random() * 2, blinkT = -1, last = 0;
  const tick = (t: number) => {
    const dt = Math.min(0.05, t - last); last = t;
    headPivot.scale.setScalar(1 + Math.sin(t * 1.1) * 0.012);
    headPivot.position.y = Math.sin(t * 0.9) * 0.03;
    headPivot.rotation.y = Math.sin(t * 0.45) * 0.16;
    headPivot.rotation.z = Math.sin(t * 0.33) * 0.025;
    headPivot.rotation.x = Math.sin(t * 0.6) * 0.02;
    hair.rotation.z = Math.sin(t * 0.7) * 0.012;
    hair.rotation.x = Math.sin(t * 0.5 + 1) * 0.01;
    strands.forEach((s) => { s.mesh.rotation.z = s.base.z + Math.sin(t * 2.2 + s.phase) * 0.12; s.mesh.rotation.x = s.base.x + Math.cos(t * 1.8 + s.phase) * 0.08; });
    mustGrp.rotation.z = mustBaseZ + Math.sin(t * 1.6) * 0.02;
    mustGrp.position.y = Math.sin(t * 1.3) * 0.006;
    if (blinkT < 0 && t > nextBlink) blinkT = 0;
    if (blinkT >= 0) {
      blinkT += dt; const p = blinkT / 0.16; const close = p < 1 ? Math.sin(p * Math.PI) : 0; const sy = 1 - close * 0.9;
      eyeL.scale.y = sy; eyeR.scale.y = sy;
      if (p >= 1) { blinkT = -1; eyeL.scale.y = eyeR.scale.y = 1; nextBlink = t + 4 + Math.random() * 2; }
    }
  };

  return { root, tick };
}

function HeadObject() {
  const built = useMemo(() => buildHead(), []);
  useFrame((state) => built.tick(state.clock.getElapsedTime()));
  return <primitive object={built.root} />;
}

export default function PlutoHead({ className }: { className?: string }) {
  return (
    <Canvas
      flat
      dpr={[1, 2]}
      gl={{ alpha: true, antialias: true }}
      camera={{ fov: 21, position: [0, 0.12, 9.4] }}
      className={className}
      style={{ background: "transparent" }}
    >
      <hemisphereLight args={[0xf3ece1, 0x9fb4c7, 0.72]} />
      <directionalLight color={0xfff4e6} intensity={1.05} position={[-3.2, 2.6, 3.4]} />
      <directionalLight color={0xbcd4ff} intensity={0.35} position={[3.4, 0.4, 2.2]} />
      <directionalLight color={0xffc488} intensity={0.35} position={[0.6, 1.8, -3.6]} />
      <HeadObject />
    </Canvas>
  );
}
