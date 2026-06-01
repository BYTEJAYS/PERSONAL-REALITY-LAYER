"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

import { BrainState, RegionName } from "@/lib/types";
import { REGIONS, REGION_ORDER, REGION_INDEX } from "@/lib/regions";

interface HUDProps {
  state: BrainState;
  live: boolean;
  focus: RegionName | null;
  onFocus: (r: RegionName | null) => void;
  onAsk: (seq: number[]) => void;
}

// A reasoning path across cortices, ending at the region the query is about —
// this is what the brain animates as it "thinks".
function reasoningPath(target: RegionName | null): number[] {
  const chain: RegionName[] = ["memory", "knowledge", "project", "goal"];
  if (target && !chain.includes(target)) chain.push(target);
  if (target) {
    // Make the target the climax of the cascade.
    const without = chain.filter((r) => r !== target);
    without.push(target);
    return without.map((r) => REGION_INDEX[r]);
  }
  return chain.map((r) => REGION_INDEX[r]);
}

// Map a free-text query to a region (the "Tell me about TGIE" interaction).
function inferRegion(q: string): RegionName | null {
  const s = q.toLowerCase();
  if (/(project|tgie|build|repo|genesis|echo|app)/.test(s)) return "project";
  if (/(learn|skill|know|python|ml|fastapi|study)/.test(s)) return "knowledge";
  if (/(goal|mission|career|aim|target)/.test(s)) return "goal";
  if (/(who|friend|mentor|people|team|social|talk)/.test(s)) return "social";
  if (/(where|when|memory|remember|day|event|place|visit)/.test(s)) return "memory";
  return null;
}

export function HUD({ state, live, focus, onFocus, onAsk }: HUDProps) {
  const [query, setQuery] = useState("");
  const byRegion = Object.fromEntries(state.regions.map((r) => [r.region, r]));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const r = inferRegion(query);
    onAsk(reasoningPath(r));        // fire the thinking cascade first…
    setTimeout(() => onFocus(r), 700); // …then fly into the answer region
  }

  return (
    <div className="pointer-events-none absolute inset-0 flex flex-col justify-between p-6 md:p-10">
      {/* Top bar */}
      <div className="flex items-start justify-between">
        <div className="pointer-events-auto">
          <h1 className="text-lg font-medium tracking-tight text-white/90">
            Cognitive Core
          </h1>
          <p className="text-xs text-white/40">Personal Reality Layer · the AI&apos;s mind</p>
        </div>
        <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 backdrop-blur-md">
          <span
            className={`h-2 w-2 rounded-full ${live ? "bg-emerald-400" : "bg-amber-400"}`}
            style={{ boxShadow: live ? "0 0 8px #34d399" : "0 0 8px #fbbf24" }}
          />
          <span className="text-xs text-white/60">
            {live ? "live" : "mock"} · {state.total_memories} memories
          </span>
        </div>
      </div>

      {/* Region legend */}
      <div className="pointer-events-auto absolute left-6 top-1/2 hidden -translate-y-1/2 flex-col gap-2 md:flex">
        {REGION_ORDER.map((name) => {
          const cfg = REGIONS[name];
          const r = byRegion[name];
          const active = focus === name;
          return (
            <button
              key={name}
              onClick={() => onFocus(active ? null : name)}
              className={`group flex items-center gap-3 rounded-xl border px-3 py-2 text-left backdrop-blur-md transition-all ${
                active
                  ? "border-white/30 bg-white/10"
                  : "border-white/5 bg-white/[0.03] hover:bg-white/[0.06]"
              }`}
            >
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: cfg.color, boxShadow: `0 0 10px ${cfg.color}` }}
              />
              <span className="min-w-[88px]">
                <span className="block text-sm text-white/85">{cfg.label}</span>
                <span className="block text-[10px] text-white/35">
                  {r ? r.count : 0} nodes · {r ? Math.round(r.intensity * 100) : 0}%
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {/* Focus detail */}
      <AnimatePresence>
        {focus && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="pointer-events-auto absolute right-6 top-1/2 hidden w-64 -translate-y-1/2 rounded-2xl border border-white/10 bg-white/[0.04] p-4 backdrop-blur-xl md:block"
          >
            <div className="mb-1 flex items-center gap-2">
              <span
                className="h-2.5 w-2.5 rounded-full"
                style={{ background: REGIONS[focus].color, boxShadow: `0 0 10px ${REGIONS[focus].color}` }}
              />
              <h2 className="text-sm font-medium text-white/90">{REGIONS[focus].label} region</h2>
            </div>
            <p className="text-xs leading-relaxed text-white/50">{REGIONS[focus].description}</p>
            <div className="mt-3 flex items-baseline gap-1">
              <span className="text-2xl font-light text-white/90">
                {byRegion[focus]?.count ?? 0}
              </span>
              <span className="text-xs text-white/40">nodes active</span>
            </div>
            <button
              onClick={() => onFocus(null)}
              className="mt-3 text-[11px] text-white/40 underline-offset-2 hover:text-white/70 hover:underline"
            >
              ← back to full mind
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Command bar */}
      <form onSubmit={submit} className="pointer-events-auto mx-auto w-full max-w-xl">
        <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 backdrop-blur-xl">
          <span className="text-white/30">✦</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask the brain…  e.g. “Tell me about TGIE” or “Where was I?”"
            className="flex-1 bg-transparent text-sm text-white/90 placeholder:text-white/25 focus:outline-none"
          />
          <button
            type="submit"
            className="rounded-lg bg-white/10 px-3 py-1 text-xs text-white/70 transition hover:bg-white/20"
          >
            focus
          </button>
        </div>
      </form>
    </div>
  );
}
