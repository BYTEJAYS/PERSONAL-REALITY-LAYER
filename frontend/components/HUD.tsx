"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

import { BrainState, RegionName } from "@/lib/types";
import { REGION_INDEX } from "@/lib/regions";
import type { ChatReply } from "@/lib/api";

interface HUDProps {
  state: BrainState;
  live: boolean;
  focus: RegionName | null;
  onFocus: (r: RegionName | null) => void;
  onAsk: (seq: number[]) => void;
  onQuery?: (q: string) => Promise<ChatReply>;
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

export function HUD({ live, onFocus, onAsk, onQuery }: HUDProps) {
  const [query, setQuery] = useState("");
  const [reply, setReply] = useState<ChatReply | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    const r = inferRegion(q);
    onAsk(reasoningPath(r));            // fire the thinking cascade first…
    setTimeout(() => onFocus(r), 700);  // …then fly into the answer region

    if (!onQuery) return;
    setAsking(true);
    setError(null);
    setReply(null);
    try {
      setReply(await onQuery(q));
    } catch {
      setError("Backend offline — start the API (Docker) to get real answers from your memories.");
    } finally {
      setAsking(false);
    }
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
          <span className="text-xs text-white/60">{live ? "live" : "mock"}</span>
        </div>
      </div>

      {/* No cortex sidebar / region cards — the brain itself is the hero.
          Region detail is intended to emerge through interaction (hover/click),
          never as permanent labels or dashboard widgets. */}

      {/* Command bar + answer */}
      <div className="pointer-events-auto mx-auto w-full max-w-xl">
        {/* Answer panel */}
        <AnimatePresence>
          {(asking || reply || error) && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 10 }}
              className="mb-3 rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-xl"
            >
              {asking && <p className="text-sm text-white/50">Thinking…</p>}
              {error && <p className="text-sm text-amber-300/90">{error}</p>}
              {reply && !asking && (
                <>
                  <p className="whitespace-pre-wrap text-sm text-white/90">{reply.answer}</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2 text-[10px] text-white/35">
                    <span className="rounded bg-white/10 px-1.5 py-0.5">{reply.intent}</span>
                    <span>{reply.llm_used ? "LLM-phrased" : "deterministic"}</span>
                    {reply.citations?.length > 0 && (
                      <span>· {reply.citations.length} source{reply.citations.length === 1 ? "" : "s"}</span>
                    )}
                  </div>
                </>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        <form onSubmit={submit}>
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
              disabled={asking}
              className="rounded-lg bg-white/10 px-3 py-1 text-xs text-white/70 transition hover:bg-white/20 disabled:opacity-50"
            >
              {asking ? "…" : "ask"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
