"use client";

import { useEffect, useRef, useState } from "react";
import { BrainCanvas } from "@/components/BrainCanvas";
import { askCompanion, streamCompanion, correctCompanion, ChatTurn } from "@/lib/api";
import { setThinking, pulseBrain } from "@/lib/brainActivity";

type Msg = { id?: number; who: "you" | "jay" | "system"; text: string };
type Status = "idle" | "awake" | "sleeping" | "flat";

const TOKEN_KEY = "prl_companion_token";
const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

const WELCOME =
  "Hey, I’m Jerry — Jay’s companion. I know him well and speak for him, but I keep his private stuff private. Ask me anything, or switch to “correct” if I get something wrong (Jay reviews corrections before I learn them).";

const STARTERS = [
  "What’s Jay actually like?",
  "What’s he scared of?",
  "What’s he into?",
  "Are you savage, Jerry?",
];

const UNAUTH =
  "That part’s just for Jay — but you can still ask me anything about him.";
const OFFLINE = "Couldn’t reach the companion just now — try again in a moment.";

// Map how a reply was generated → the little status the dot shows.
function statusFromGen(g: string): Status {
  if (g === "asleep") return "sleeping";
  if (g === "deterministic") return "flat";
  return "awake"; // "llm" or "demo"
}

const STATUS_UI: Record<Status, { dot: string; label: string }> = {
  idle: { dot: "bg-zinc-500", label: "" },
  awake: { dot: "bg-emerald-400", label: "awake" },
  sleeping: { dot: "bg-zinc-400", label: "sleeping 😴" },
  flat: { dot: "bg-amber-400", label: "low-power" },
};

// Reveal text word-by-word — the fallback "streaming feel" when the SSE endpoint
// isn't there (e.g. talking to a not-yet-deployed backend).
function typewriter(full: string, onUpdate: (sofar: string) => void): Promise<void> {
  return new Promise((resolve) => {
    const parts = full.split(/(\s+)/);
    let i = 0;
    let acc = "";
    const tick = () => {
      acc += parts[i++] ?? "";
      onUpdate(acc);
      if (i < parts.length) setTimeout(tick, 22);
      else resolve();
    };
    tick();
  });
}

export default function Page() {
  const [token, setToken] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([{ who: "system", text: WELCOME }]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"ask" | "correct">("ask");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const endRef = useRef<HTMLDivElement>(null);

  // No access gate — anyone just opens the page and starts talking. Only the
  // OWNER code unlocks owner-only features (review/correct approval); it rides
  // in the link (?code=…) or was saved from a previous visit, so there's still
  // nothing for a normal visitor to type.
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("code");
    if (fromUrl) localStorage.setItem(TOKEN_KEY, fromUrl);
    setToken(fromUrl || localStorage.getItem(TOKEN_KEY) || "");
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  const setMsgText = (id: number, next: (t: string) => string) =>
    setMsgs((m) => m.map((x) => (x.id === id ? { ...x, text: next(x.text) } : x)));
  const setMsgWho = (id: number, who: Msg["who"], text: string) =>
    setMsgs((m) => m.map((x) => (x.id === id ? { ...x, who, text } : x)));

  async function runAsk(text: string, history: ChatTurn[]) {
    const id = Date.now();
    setMsgs((m) => [...m, { id, who: "jay", text: "" }]); // placeholder to stream into
    setThinking(true);
    try {
      // Preferred path: true token streaming over SSE.
      const { generated_by } = await streamCompanion(token, text, history, (delta) => {
        pulseBrain();
        setMsgText(id, (t) => t + delta);
      });
      setStatus(statusFromGen(generated_by));
    } catch (err) {
      if (err instanceof Error && err.message === "unauthorized") {
        setMsgWho(id, "system", UNAUTH);
        return;
      }
      // Fallback: the stream endpoint isn't available (older backend) — get the
      // whole answer and reveal it with a typewriter so it still feels alive.
      try {
        const r = await askCompanion(token, text, history);
        setStatus(statusFromGen(r.generated_by));
        await typewriter(r.answer, (sofar) => {
          pulseBrain();
          setMsgText(id, () => sofar);
        });
      } catch (e2) {
        const msg = e2 instanceof Error && e2.message === "unauthorized" ? UNAUTH : OFFLINE;
        setMsgWho(id, "system", msg);
      }
    } finally {
      setThinking(false);
    }
  }

  async function submitText(raw: string) {
    const text = raw.trim();
    if (!text || busy) return;
    setInput("");
    // Recent conversation so Jerry can follow the thread (excludes this new turn).
    const history: ChatTurn[] = msgs
      .filter((m) => m.who === "you" || m.who === "jay")
      .map((m) => ({ role: (m.who === "you" ? "user" : "assistant") as "user" | "assistant", content: m.text }))
      .slice(-6);
    setMsgs((m) => [...m, { who: "you", text }]);
    setBusy(true);
    try {
      if (mode === "ask") {
        await runAsk(text, history);
      } else {
        const r = await correctCompanion(token, text, "friend");
        setMsgs((m) => [...m, { who: "system", text: r.message }]);
        setMode("ask");
      }
    } catch (err) {
      const msg = err instanceof Error && err.message === "unauthorized" ? UNAUTH : OFFLINE;
      setMsgs((m) => [...m, { who: "system", text: msg }]);
    } finally {
      setBusy(false);
    }
  }

  const hasAsked = msgs.some((m) => m.who === "you");
  const su = STATUS_UI[status];

  // --- Brain + chat overlay -------------------------------------------------
  return (
    <main className="relative h-screen w-screen overflow-hidden bg-[#040507] text-zinc-100">
      <BrainCanvas />

      {/* top bar */}
      <header className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between px-5 py-3">
        <div>
          <h1 className="flex items-center gap-2 font-semibold leading-tight">
            Jerry {DEMO && <span className="text-amber-400/80 text-xs">· demo</span>}
            <span className="flex items-center gap-1 text-[11px] font-normal text-zinc-400">
              <span className={`inline-block h-2 w-2 rounded-full ${su.dot} ${status === "awake" ? "animate-pulse" : ""}`} />
              {su.label}
            </span>
          </h1>
          <p className="text-xs text-zinc-500">Jay’s companion — knows him, keeps his secrets</p>
        </div>
      </header>

      {/* chat overlay docked bottom; brain stays interactive above it */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex justify-center px-3 pb-3">
        <div className="pointer-events-auto flex w-full max-w-xl flex-col rounded-2xl border border-white/10 bg-black/50 backdrop-blur-md">
          <div className="max-h-[46vh] space-y-2 overflow-y-auto px-4 pt-4">
            {msgs.map((m, i) => (
              <div
                key={m.id ?? i}
                className={
                  m.who === "you"
                    ? "flex justify-end"
                    : m.who === "system"
                    ? "flex justify-center"
                    : "flex justify-start"
                }
              >
                <div
                  className={
                    m.who === "you"
                      ? "max-w-[80%] rounded-2xl bg-indigo-600 px-4 py-2 text-sm"
                      : m.who === "system"
                      ? "max-w-[92%] rounded-lg bg-white/5 px-3 py-2 text-center text-xs text-zinc-400"
                      : "max-w-[80%] whitespace-pre-wrap rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm"
                  }
                >
                  {/* A streaming reply with no text yet shows animated dots. */}
                  {m.who === "jay" && m.text === "" ? <TypingDots /> : m.text}
                </div>
              </div>
            ))}
            {/* "noting that…" only for the correct-mode round-trip (ask streams inline). */}
            {busy && mode === "correct" && (
              <div className="flex justify-start">
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-zinc-500">
                  noting that…
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Starter chips — only before the first question, so newcomers know what to ask. */}
          {!hasAsked && mode === "ask" && (
            <div className="flex flex-wrap gap-2 px-4 pt-3">
              {STARTERS.map((q) => (
                <button
                  key={q}
                  type="button"
                  disabled={busy}
                  onClick={() => submitText(q)}
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-zinc-300 transition hover:border-indigo-400/60 hover:text-white disabled:opacity-40"
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              submitText(input);
            }}
            className="p-3"
          >
            <div className="mb-2 flex gap-2 text-xs">
              <button
                type="button"
                onClick={() => setMode("ask")}
                className={`rounded-full px-3 py-1 ${mode === "ask" ? "bg-indigo-600" : "bg-white/5 text-zinc-400"}`}
              >
                Ask about Jay
              </button>
              <button
                type="button"
                onClick={() => setMode("correct")}
                className={`rounded-full px-3 py-1 ${mode === "correct" ? "bg-amber-600" : "bg-white/5 text-zinc-400"}`}
              >
                Correct / add info
              </button>
            </div>
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm outline-none focus:border-indigo-400"
                placeholder={mode === "ask" ? "How would Jay react if…" : "Tell it what it got wrong…"}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={busy}
              />
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="rounded-lg bg-indigo-600 px-4 text-sm font-medium transition hover:bg-indigo-500 disabled:opacity-40"
              >
                {mode === "ask" ? "Ask" : "Send"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </main>
  );
}

// Three pulsing dots while Jerry "types" the first token.
function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1 text-zinc-400">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-zinc-400" />
    </span>
  );
}
