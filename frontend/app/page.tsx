"use client";

import { useEffect, useRef, useState } from "react";
import { BrainCanvas } from "@/components/BrainCanvas";
import { askCompanion, correctCompanion } from "@/lib/api";

type Msg = { who: "you" | "jay" | "system"; text: string };

const TOKEN_KEY = "prl_companion_token";
const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

const WELCOME =
  "Hey, I’m Jerry — Jay’s companion. I know him well and speak for him, but I keep his private stuff private. Ask me anything, or switch to “correct” if I get something wrong (Jay reviews corrections before I learn them).";

export default function Page() {
  const [token, setToken] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([{ who: "system", text: WELCOME }]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"ask" | "correct">("ask");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  // No access gate — friends just open the link and start talking. If a deploy
  // is token-locked (FRIEND_TOKENS set), the code rides in the link (?code=…)
  // or was saved from a previous visit, so there's still nothing to type.
  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("code");
    if (fromUrl) localStorage.setItem(TOKEN_KEY, fromUrl);
    setToken(fromUrl || localStorage.getItem(TOKEN_KEY) || "");
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setMsgs((m) => [...m, { who: "you", text }]);
    setBusy(true);
    try {
      if (mode === "ask") {
        const r = await askCompanion(token, text);
        setMsgs((m) => [...m, { who: "jay", text: r.answer }]);
      } else {
        const r = await correctCompanion(token, text, "friend");
        setMsgs((m) => [...m, { who: "system", text: r.message }]);
        setMode("ask");
      }
    } catch (err) {
      const text =
        err instanceof Error && err.message === "unauthorized"
          ? "This companion is private — open the link Jay sent you (it carries your access code)."
          : "Couldn’t reach the companion just now — try again in a moment.";
      setMsgs((m) => [...m, { who: "system", text }]);
    } finally {
      setBusy(false);
    }
  }

  // --- Brain + chat overlay -------------------------------------------------
  return (
    <main className="relative h-screen w-screen overflow-hidden bg-[#040507] text-zinc-100">
      <BrainCanvas />

      {/* top bar */}
      <header className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between px-5 py-3">
        <div>
          <h1 className="font-semibold leading-tight">Jerry {DEMO && <span className="text-amber-400/80 text-xs">· demo</span>}</h1>
          <p className="text-xs text-zinc-500">Jay’s companion — knows him, keeps his secrets</p>
        </div>
      </header>

      {/* chat overlay docked bottom; brain stays interactive above it */}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 flex justify-center px-3 pb-3">
        <div className="pointer-events-auto flex w-full max-w-xl flex-col rounded-2xl border border-white/10 bg-black/50 backdrop-blur-md">
          <div className="max-h-[46vh] space-y-2 overflow-y-auto px-4 pt-4">
            {msgs.map((m, i) => (
              <div
                key={i}
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
                      : "max-w-[80%] rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm"
                  }
                >
                  {m.text}
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2 text-sm text-zinc-500">
                  {mode === "ask" ? "thinking…" : "noting that…"}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <form onSubmit={send} className="p-3">
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
