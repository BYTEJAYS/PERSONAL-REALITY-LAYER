"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { REGION_COLORS_RGB } from "@/lib/regions";
import { BrainModel } from "./brainModel";

const PULSES = 1600;

const vertexShader = /* glsl */ `
  uniform float uPixelRatio;
  attribute vec3 aColor;
  attribute float aLife;   // 0..1 along its edge — fades in/out at the ends
  varying vec3 vColor;
  varying float vLife;
  void main() {
    vColor = aColor;
    vLife = sin(aLife * 3.14159);  // brightest mid-travel
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = uPixelRatio * (2.0 + vLife * 5.0) * (9.0 / -mv.z);
    gl_Position = projectionMatrix * mv;
  }
`;

const fragmentShader = /* glsl */ `
  precision mediump float;
  varying vec3 vColor;
  varying float vLife;
  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    if (d > 0.5) discard;
    float core = smoothstep(0.5, 0.0, d);
    vec3 col = mix(vColor, vec3(1.0), pow(core, 3.0) * 0.7);
    gl_FragColor = vec4(col, core * vLife);
  }
`;

interface Props {
  model: BrainModel;
  activation: React.MutableRefObject<Float32Array>;
}

export function Synapses({ model, activation }: Props) {
  const matRef = useRef<THREE.ShaderMaterial>(null);

  // Per-pulse travel state, rebuilt when the model changes.
  const state = useMemo(() => {
    const positions = new Float32Array(PULSES * 3);
    const colors = new Float32Array(PULSES * 3);
    const life = new Float32Array(PULSES);
    const edgeOf = new Int32Array(PULSES);
    const t = new Float32Array(PULSES);
    const speed = new Float32Array(PULSES);
    return { positions, colors, life, edgeOf, t, speed };
  }, [model]);

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(state.positions, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute("aColor", new THREE.BufferAttribute(state.colors, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute("aLife", new THREE.BufferAttribute(state.life, 1).setUsage(THREE.DynamicDrawUsage));
    return g;
  }, [state]);

  const uniforms = useMemo(
    () => ({ uPixelRatio: { value: typeof window !== "undefined" ? Math.min(window.devicePixelRatio, 2) : 1 } }),
    [],
  );

  function assignEdge(i: number) {
    const { edgesByRegion, edgeCount, edgeRegion } = model;
    // Bias 60% of new pulses into the most-active cortex.
    let edge = -1;
    const live = activation.current;
    let hot = 0;
    for (let r = 1; r < 5; r++) if (live[r] > live[hot]) hot = r;
    if (live[hot] > 0.15 && Math.random() < 0.6 && edgesByRegion[hot].length) {
      const list = edgesByRegion[hot];
      edge = list[(Math.random() * list.length) | 0];
    } else {
      edge = (Math.random() * edgeCount) | 0;
    }
    state.edgeOf[i] = edge;
    state.t[i] = 0;
    state.speed[i] = 0.35 + Math.random() * 0.9;
    const [cr, cg, cb] = REGION_COLORS_RGB[edgeRegion[edge]];
    state.colors[i * 3] = cr; state.colors[i * 3 + 1] = cg; state.colors[i * 3 + 2] = cb;
  }

  // Seed all pulses on first run.
  const seeded = useRef(false);
  if (!seeded.current && model.edgeCount > 0) {
    for (let i = 0; i < PULSES; i++) {
      assignEdge(i);
      state.t[i] = Math.random();
    }
    seeded.current = true;
  }

  useFrame((_, delta) => {
    if (model.edgeCount === 0) return;
    const { positions, life, t, speed, edgeOf } = state;
    const { edges, positions: nodePos } = model;
    for (let i = 0; i < PULSES; i++) {
      t[i] += delta * speed[i];
      if (t[i] >= 1) assignEdge(i);
      const e = edgeOf[i];
      const a = edges[e * 2], b = edges[e * 2 + 1];
      const tt = t[i];
      positions[i * 3] = nodePos[a * 3] + (nodePos[b * 3] - nodePos[a * 3]) * tt;
      positions[i * 3 + 1] = nodePos[a * 3 + 1] + (nodePos[b * 3 + 1] - nodePos[a * 3 + 1]) * tt;
      positions[i * 3 + 2] = nodePos[a * 3 + 2] + (nodePos[b * 3 + 2] - nodePos[a * 3 + 2]) * tt;
      life[i] = tt;
    }
    geometry.attributes.position.needsUpdate = true;
    geometry.attributes.aColor.needsUpdate = true;
    geometry.attributes.aLife.needsUpdate = true;
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
