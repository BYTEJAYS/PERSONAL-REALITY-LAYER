"use client";

import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";

import { BrainState, RegionName, Thought } from "@/lib/types";
import { REGION_INDEX } from "@/lib/regions";
import { buildBrain, densitySignature } from "./brainModel";
import { Nodes } from "./Nodes";
import { Connections } from "./Connections";
import { Synapses } from "./Synapses";

interface Props {
  state: BrainState;
  focus: RegionName | null;
  thought: Thought | null;
}

/**
 * Owns the brain model + the shared activation buffer. An idle scheduler fires
 * random cortices so the brain never looks static; a query enqueues a staggered
 * cascade across regions — the AI visibly "thinking".
 */
export function BrainScene({ state, focus, thought }: Props) {
  const sig = densitySignature(state);
  const model = useMemo(() => buildBrain(state), [sig]); // eslint-disable-line react-hooks/exhaustive-deps

  const activation = useRef<Float32Array>(new Float32Array(5));
  const focusIndex = focus ? REGION_INDEX[focus] : -1;

  const clock = useRef(0);
  const fireTimer = useRef(1.5);
  const queue = useRef<{ at: number; region: number; strength: number }[]>([]);

  // Enqueue a reasoning cascade whenever a new thought arrives.
  useEffect(() => {
    if (!thought) return;
    const base = clock.current;
    thought.seq.forEach((r, i) => {
      queue.current.push({ at: base + i * 0.5, region: r, strength: 1.35 });
    });
  }, [thought?.token]); // eslint-disable-line react-hooks/exhaustive-deps

  useFrame((_, delta) => {
    const dt = Math.min(delta, 0.05);
    clock.current += dt;
    const a = activation.current;
    for (let i = 0; i < 5; i++) a[i] = Math.max(0, a[i] - dt * 0.85);

    // Idle: a random cortex fires every couple of seconds.
    fireTimer.current -= dt;
    if (fireTimer.current <= 0) {
      const r = (Math.random() * 5) | 0;
      a[r] = Math.max(a[r], 0.9);
      fireTimer.current = 1.3 + Math.random() * 1.6;
    }

    // Drain the thought cascade.
    while (queue.current.length && queue.current[0].at <= clock.current) {
      const item = queue.current.shift()!;
      a[item.region] = Math.max(a[item.region], item.strength);
    }
  });

  return (
    <group>
      <Connections model={model} activation={activation} focusIndex={focusIndex} />
      <Nodes model={model} activation={activation} focusIndex={focusIndex} />
      <Synapses model={model} activation={activation} />
    </group>
  );
}
