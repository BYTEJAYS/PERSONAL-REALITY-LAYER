"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

import { REGION_COLORS_RGB } from "@/lib/regions";
import { BrainModel } from "./brainModel";

// Dim static wiring whose brightness breathes with region activation, so the
// network reads as alive even between synapse pulses.
const vertexShader = /* glsl */ `
  uniform float uFocus;
  uniform float uActivation[5];
  uniform vec3  uColors[5];
  attribute float aRegion;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    int ri = int(aRegion + 0.5);
    vColor = uColors[ri];
    float act = uActivation[ri];
    float focus = (uFocus < 0.0) ? 1.0 : (abs(float(ri) - uFocus) < 0.5 ? 1.6 : 0.12);
    vAlpha = (0.035 + act * 0.22) * focus;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const fragmentShader = /* glsl */ `
  precision mediump float;
  varying vec3 vColor;
  varying float vAlpha;
  void main() {
    gl_FragColor = vec4(vColor, vAlpha);
  }
`;

interface Props {
  model: BrainModel;
  activation: React.MutableRefObject<Float32Array>;
  focusIndex: number;
}

export function Connections({ model, activation, focusIndex }: Props) {
  const matRef = useRef<THREE.ShaderMaterial>(null);

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(model.linePositions, 3));
    g.setAttribute("aRegion", new THREE.BufferAttribute(model.lineRegion, 1));
    return g;
  }, [model]);

  const uniforms = useMemo(
    () => ({
      uFocus: { value: -1 },
      uActivation: { value: new Array(5).fill(0) },
      uColors: { value: REGION_COLORS_RGB.map((c) => new THREE.Vector3(...c)) },
    }),
    [],
  );

  useFrame(() => {
    if (!matRef.current) return;
    const u = matRef.current.uniforms;
    const arr = u.uActivation.value as number[];
    const live = activation.current;
    for (let i = 0; i < 5; i++) arr[i] = live[i];
    u.uFocus.value = focusIndex;
  });

  return (
    <lineSegments geometry={geometry}>
      <shaderMaterial
        ref={matRef}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </lineSegments>
  );
}
