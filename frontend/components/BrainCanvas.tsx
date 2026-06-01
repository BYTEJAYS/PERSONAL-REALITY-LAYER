"use client";

import { Suspense } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";

import { ParticleBrain } from "./ParticleBrain";

export function BrainCanvas() {
  return (
    <Canvas
      camera={{ position: [0, 0.1, 3.4], fov: 50, near: 0.1, far: 100 }}
      dpr={[1, 2]}
      gl={{ antialias: true, alpha: false, powerPreference: "high-performance" }}
      style={{ position: "absolute", inset: 0 }}
    >
      <color attach="background" args={["#040507"]} />
      <fog attach="fog" args={["#040507", 4.5, 9]} />
      <Suspense fallback={null}>
        <ParticleBrain />
      </Suspense>
      <OrbitControls
        makeDefault
        enablePan={false}
        enableDamping
        dampingFactor={0.08}
        autoRotate
        autoRotateSpeed={0.45}
        minDistance={1.4}
        maxDistance={7}
        rotateSpeed={0.5}
      />
    </Canvas>
  );
}
