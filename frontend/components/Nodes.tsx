"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { REGION_COLORS_RGB } from "@/lib/regions";
import { BrainModel } from "./brainModel";

const vertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uSize;
  uniform float uPixelRatio;
  uniform float uFocus;          // focused region idx, or -1
  uniform float uActivation[5];  // 0..1 per region (live firing)
  uniform vec3  uColors[5];

  attribute float aSeed;
  attribute float aRegion;
  attribute float aImp;

  varying vec3  vColor;
  varying float vBright;

  void main() {
    int ri = int(aRegion + 0.5);
    vec3 pos = position;

    // Each particle keeps a small, unique orbit — alive but shape-preserving.
    float t = uTime * 0.6 + aSeed;
    float amp = 0.012 + aImp * 0.012;
    pos.x += sin(t * 1.3 + aSeed) * amp;
    pos.y += cos(t * 1.1 + aSeed * 1.7) * amp;
    pos.z += sin(t * 0.9 + aSeed * 0.5) * amp;

    float act = uActivation[ri];
    float focus = (uFocus < 0.0) ? 1.0 : (abs(float(ri) - uFocus) < 0.5 ? 1.0 : 0.22);

    vColor = uColors[ri];
    // Importance and activation set brightness; most nodes stay dim & distinct.
    vBright = (0.32 + aImp * 0.55 + act * 0.6) * focus;

    vec4 mv = modelViewMatrix * vec4(pos, 1.0);
    float sizeBoost = 0.6 + aImp * 2.2 + act * 0.6;     // hubs are visibly bigger
    gl_PointSize = uSize * uPixelRatio * sizeBoost * focus * (8.5 / -mv.z);
    gl_PointSize = clamp(gl_PointSize, 0.0, 26.0);
    gl_Position = projectionMatrix * mv;
  }
`;

const fragmentShader = /* glsl */ `
  precision mediump float;
  varying vec3  vColor;
  varying float vBright;

  void main() {
    // Crisp node with a tight core and a thin halo — reads as a star, not fog.
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    if (d > 0.5) discard;
    float core = smoothstep(0.5, 0.04, d);
    float halo = smoothstep(0.5, 0.32, d) * 0.5;
    float a = clamp(core + halo, 0.0, 1.0) * clamp(0.45 + vBright, 0.2, 1.0);
    // Keep saturation; only the very centre of bright nodes whitens slightly.
    vec3 col = mix(vColor, vec3(1.0), pow(core, 6.0) * min(vBright, 0.8) * 0.5);
    col *= 0.75 + vBright * 0.7;
    gl_FragColor = vec4(col, a);
  }
`;

interface Props {
  model: BrainModel;
  activation: React.MutableRefObject<Float32Array>;
  focusIndex: number; // -1 = none
}

export function Nodes({ model, activation, focusIndex }: Props) {
  const matRef = useRef<THREE.ShaderMaterial>(null);

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(model.positions, 3));
    g.setAttribute("aSeed", new THREE.BufferAttribute(model.seeds, 1));
    g.setAttribute("aRegion", new THREE.BufferAttribute(model.region, 1));
    g.setAttribute("aImp", new THREE.BufferAttribute(model.importance, 1));
    return g;
  }, [model]);

  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uSize: { value: 9.0 },
      uPixelRatio: { value: typeof window !== "undefined" ? Math.min(window.devicePixelRatio, 2) : 1 },
      uFocus: { value: -1 },
      uActivation: { value: new Array(5).fill(0) },
      uColors: { value: REGION_COLORS_RGB.map((c) => new THREE.Vector3(...c)) },
    }),
    [],
  );

  const focusSmooth = useRef(-1);

  useFrame((_, delta) => {
    if (!matRef.current) return;
    const u = matRef.current.uniforms;
    u.uTime.value += delta;
    const arr = u.uActivation.value as number[];
    const live = activation.current;
    for (let i = 0; i < 5; i++) arr[i] = live[i];

    if (focusIndex < 0) {
      u.uFocus.value = -1;
      focusSmooth.current = -1;
    } else {
      if (focusSmooth.current < 0) focusSmooth.current = focusIndex;
      focusSmooth.current += (focusIndex - focusSmooth.current) * Math.min(1, delta * 6);
      u.uFocus.value = focusSmooth.current;
    }
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
        blending={THREE.NormalBlending}
      />
    </points>
  );
}
