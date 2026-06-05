"use client";

import { useEffect, useState } from "react";

import { BrainState, RegionName } from "@/lib/types";
import { MOCK_BRAIN } from "@/lib/mock";
import { fetchBrainState, fetchChat } from "@/lib/api";
import { HUD } from "@/components/HUD";
import { BrainCanvas } from "@/components/BrainCanvas";

const POLL_MS = 5000;

export default function Page() {
  const [state, setState] = useState<BrainState>(MOCK_BRAIN);
  const [live, setLive] = useState(false);
  const [focus, setFocus] = useState<RegionName | null>(null);

  // Keep the HUD (status pill + region readouts) driven by real backend data.
  useEffect(() => {
    let active = true;
    async function tick() {
      const { state, live } = await fetchBrainState();
      if (!active) return;
      setState(state);
      setLive(live);
    }
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return (
    <main className="relative h-screen w-screen overflow-hidden bg-ink">
      <BrainCanvas />
      <HUD state={state} live={live} focus={focus} onFocus={setFocus} onAsk={() => {}} onQuery={fetchChat} />
    </main>
  );
}
