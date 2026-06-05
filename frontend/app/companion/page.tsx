"use client";

import { useEffect, useRef, useState } from "react";
import { BrainCanvas } from "@/components/BrainCanvas";
import { askCompanion, correctCompanion } from "@/lib/api";

type Msg = { who: "you" | "jay" | "system"; text: string };

const TOKEN_KEY = "prl_companion_token";
const NAME_KEY = "prl_companion_name";
const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

export default function CompanionPage() {
  const [token, setToken] = useState("");
  const [name, setName] = useState("");
  const [ready, setReady] = useState(false);
  const [authError, setAuthError] = useState(false);

  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"ask" | "correct">("ask");
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = localStorage.getItem(TOKEN_KEY);
    const n = localStorage.getItem(NAME_KEY);
    if (t) {
      setToken(t);
      setName(n || "");
      setReady(true);
    }
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  function enter(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || (!token.trim() && !DEMO)) return;
    localStorage.setItem(TOKEN_KEY, token.trim() || "demo");
    localStorage.setItem(NAME_KEY, name.trim());
    setReady(true);
    setMsgs([
      {
        who: "system",
        text:
          "Hey, I’m Jerry — Jay’s companion. I know him well and speak for him, but I keep his private stuff private. Ask me anything, or switch to “correct” if I get something wrong (Jay reviews corrections before I learn them).",
      },
    ]);
  }

  function signOut() {
    localStorage.removeItem(TOKEN_KEY);
    setReady(false);
    setToken("");
    setMsgs([]);
  }

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
        const r = await correctCompanion(token, text, name || "friend");
        setMsgs((m) => [...m, { who: "system", text: r.message }]);
        setMode("ask");
      }
    } catch (err) {
      if (err instanceof Error && err.message === "unauthorized") {
        setAuthError(true);
        signOut();
      } else {
        setMsgs((m) => [
          ...m,
          { who: "system", text: "Couldn’t reach the companion just now — try again in a moment." },
        ]);
      }
    } finally {
      setBusy(false);
    }
  }

  // --- Access gate ----------------------------------------------------------
  if (!ready) {
    return (
      <main className="relative h-screen w-screen overflow-hidden bg-[#040507] text-zinc-100">
        <BrainCanvas />
        <div className="absolute inset-0 flex items-center justify-center px-4">
          <form
            onSubmit={enter}
            className="w-full max-w-sm space-y-4 rounded-2xl border border-white/10 bg-black/50 p-6 backdrop-blur-md"
          >
            <div className="space-y-1 text-center">
              <h1 className="text-2xl font-semibold">Meet Jerry</h1>
              <p className="text-sm text-zinc-400">Jay’s companion — knows him, keeps his secrets. Friends only.</p>
            </div>
            {authError && (
              <p className="text-center text-sm text-red-400">That access code didn’t work.</p>
            )}
            <input
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 outline-none focus:border-indigo-400"
              placeholder="Your name"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <input
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 outline-none focus:border-indigo-400"
              placeholder={DEMO ? "Access code (any, in demo)" : "Access code (Jay gave you one)"}
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <button
              type="submit"
              className="w-full rounded-lg bg-indigo-600 py-2 font-medium transition hover:bg-indigo-500"
            >
              Enter
            </button>
            {DEMO && <p className="text-center text-xs text-amber-400/80">demo mode — sample answers</p>}
          </form>
        </div>
      </main>
    );
  }

  // --- Brain + chat overlay -------------------------------------------------
  return (
    <main className="relative h-screen w-screen overflow-hidden bg-[#040507] text-zinc-100">
      <BrainCanvas />

      {/* top bar */}
      <header className="absolute left-0 right-0 top-0 z-10 flex items-center justify-between px-5 py-3">
        <div>
          <h1 className="font-semibold leading-tight">Jerry {DEMO && <span className="text-amber-400/80 text-xs">· demo</span>}</h1>
          <p className="text-xs text-zinc-500">Hi {name} · Jay’s companion — knows him, keeps his secrets</p>
        </div>
        <button onClick={signOut} className="text-xs text-zinc-500 hover:text-zinc-300">
          sign out
        </button>
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
