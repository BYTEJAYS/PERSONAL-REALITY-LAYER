"use client";

import { useMemo, useRef } from "react";
import { useFrame, useLoader } from "@react-three/fiber";
import * as THREE from "three";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { MeshSurfaceSampler } from "three/examples/jsm/math/MeshSurfaceSampler.js";
import { fireTarget } from "@/lib/brainActivity";

const SURFACE = 200000; // dense sampling so the folds resolve clearly
const DUST = 48000;     // dispersing halo lifting off the surface
const TARGET = 2.6;     // normalised max dimension in world units

const vertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uSize;
  uniform float uPixelRatio;
  uniform float uActive;     // 0..1 — chat-driven "firing" level
  attribute float aSeed;
  attribute float aPSize;
  attribute float aBright;
  attribute vec3  aNormal;   // surface normal (zero for free dust)
  varying float vBright;
  varying float vActive;

  void main() {
    vec3 pos = position;
    float t = uTime * 0.5 + aSeed;
    // Drift grows a little when Jerry's thinking, so the brain visibly stirs.
    float wobble = 0.0035 + uActive * 0.0045;
    pos.x += sin(t * 1.3 + aSeed) * wobble;
    pos.y += cos(t * 1.1 + aSeed * 1.7) * wobble;
    pos.z += sin(t * 0.9) * wobble;

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);

    // View-relative lighting so the cortical folds read from every angle.
    float isSurf = step(0.1, length(aNormal));
    vec3 N = normalize(normalMatrix * aNormal);
    vec3 V = normalize(-mv.xyz);
    vec3 L = normalize(vec3(-0.35, 0.55, 0.85)); // key light, upper-left
    float ndl = dot(N, L) * 0.5 + 0.5;           // half-Lambert
    float diff = pow(ndl, 1.6);
    float rim = pow(1.0 - max(dot(N, V), 0.0), 2.5); // bright crease/edge highlight
    float shade = 0.22 + diff * 0.95 + rim * 0.6;
    shade = mix(1.0, shade, isSurf);

    float tw = 0.82 + 0.18 * sin(uTime * 2.0 + aSeed * 6.2831);

    // Firing: a wave of brightness sweeps front→back through the brain while
    // active, so it looks like thought propagating, not just a flat glow.
    float wave = 0.5 + 0.5 * sin(uTime * 5.0 - pos.z * 4.5 + aSeed * 0.6);
    float fire = uActive * (0.45 + 0.55 * wave);
    vBright = aBright * shade * tw * (1.0 + fire * 1.5);
    vActive = uActive;

    gl_PointSize = uSize * aPSize * uPixelRatio * (3.0 / -mv.z) * (1.0 + uActive * 0.45);
    gl_PointSize = clamp(gl_PointSize, 0.0, 7.0);
    gl_Position = projectionMatrix * mv;
  }
`;

const fragmentShader = /* glsl */ `
  precision mediump float;
  varying float vBright;
  varying float vActive;
  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    if (d > 0.5) discard;
    float core = smoothstep(0.5, 0.0, d);
    // Idle = cool blue-white; firing shifts a touch warmer/brighter so the
    // reaction reads as energy, not just exposure.
    vec3 idle = vec3(0.84, 0.9, 1.0);
    vec3 hot  = vec3(0.62, 0.82, 1.0);
    vec3 col = mix(idle, hot, clamp(vActive, 0.0, 1.0)) * (0.45 + vBright);
    gl_FragColor = vec4(col, core * clamp(vBright, 0.0, 1.0));
  }
`;

function findMesh(root: THREE.Object3D): THREE.Mesh | null {
  let mesh: THREE.Mesh | null = null;
  root.traverse((o) => {
    if (!mesh && (o as THREE.Mesh).isMesh) mesh = o as THREE.Mesh;
  });
  return mesh;
}

export function ParticleBrain() {
  const matRef = useRef<THREE.ShaderMaterial>(null);
  const obj = useLoader(OBJLoader, "/brain.obj");

  const geometry = useMemo(() => {
    const mesh = findMesh(obj);
    if (!mesh) return new THREE.BufferGeometry();

    const src = mesh.geometry.clone();
    src.computeBoundingBox();
    const bb = src.boundingBox!;
    const center = bb.getCenter(new THREE.Vector3());
    const size = bb.getSize(new THREE.Vector3());
    const scale = TARGET / Math.max(size.x, size.y, size.z);
    src.translate(-center.x, -center.y, -center.z);
    src.scale(scale, scale, scale);
    if (!src.attributes.normal) src.computeVertexNormals();

    const sampler = new MeshSurfaceSampler(new THREE.Mesh(src)).build();

    const total = SURFACE + DUST;
    const positions = new Float32Array(total * 3);
    const normals = new Float32Array(total * 3);
    const seeds = new Float32Array(total);
    const sizes = new Float32Array(total);
    const bright = new Float32Array(total);

    const p = new THREE.Vector3();
    const n = new THREE.Vector3();
    const surfP = new Float32Array(SURFACE * 3);
    const surfN = new Float32Array(SURFACE * 3);

    for (let i = 0; i < SURFACE; i++) {
      sampler.sample(p, n);
      positions[i * 3] = p.x; positions[i * 3 + 1] = p.y; positions[i * 3 + 2] = p.z;
      normals[i * 3] = n.x; normals[i * 3 + 1] = n.y; normals[i * 3 + 2] = n.z;
      surfP[i * 3] = p.x; surfP[i * 3 + 1] = p.y; surfP[i * 3 + 2] = p.z;
      surfN[i * 3] = n.x; surfN[i * 3 + 1] = n.y; surfN[i * 3 + 2] = n.z;
      seeds[i] = Math.random() * 1000;
      // Lighting comes from the shader now; keep base brightness fairly even
      // with a faint sparkle so dense areas don't blow out.
      const b = 0.6 + Math.pow(Math.random(), 2.6) * 0.4;
      bright[i] = b;
      sizes[i] = 0.7 + Math.random() * 0.7 + (b > 0.96 ? 0.8 : 0);
    }

    for (let i = 0; i < DUST; i++) {
      const k = (Math.random() * SURFACE) | 0;
      const d = Math.pow(Math.random(), 1.9) * 1.25;
      const j = () => (Math.random() - 0.5) * 0.45 * d;
      const idx = SURFACE + i;
      positions[idx * 3] = surfP[k * 3] + surfN[k * 3] * d + j() + d * 0.22;
      positions[idx * 3 + 1] = surfP[k * 3 + 1] + surfN[k * 3 + 1] * d + j() + d * 0.1;
      positions[idx * 3 + 2] = surfP[k * 3 + 2] + surfN[k * 3 + 2] * d + j();
      // Zero normal flags "free dust" → no surface shading in the shader.
      seeds[idx] = Math.random() * 1000;
      bright[idx] = (0.1 + Math.random() * 0.36) * (1 - d / 1.7);
      sizes[idx] = 0.5 + Math.random() * 0.65;
    }

    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    g.setAttribute("aNormal", new THREE.BufferAttribute(normals, 3));
    g.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
    g.setAttribute("aPSize", new THREE.BufferAttribute(sizes, 1));
    g.setAttribute("aBright", new THREE.BufferAttribute(bright, 1));
    return g;
  }, [obj]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uSize: { value: 1.9 },
      uPixelRatio: { value: typeof window !== "undefined" ? Math.min(window.devicePixelRatio, 2) : 1 },
      uActive: { value: 0 },
    }),
    [],
  );

  useFrame((_, delta) => {
    if (!matRef.current) return;
    const u = matRef.current.uniforms;
    u.uTime.value += delta;
    // Ease toward the chat-driven fire level so it ramps in/out smoothly.
    const target = fireTarget();
    u.uActive.value += (target - u.uActive.value) * Math.min(1, delta * 4);
  });

  return (
    <points geometry={geometry}>
      <shaderMaterial
        ref={matRef}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}
