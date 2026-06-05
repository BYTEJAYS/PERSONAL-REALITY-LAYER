"use client";

import { useEffect, useRef, useState } from "react";
import { askCompanion, correctCompanion } from "@/lib/api";

type Msg = { who: "you" | "jay" | "system"; text: string };

const TOKEN_KEY = "prl_companion_token";
const NAME_KEY = "prl_companion_name";

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

  // Restore a saved access code so friends don't re-enter it each visit.
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
    if (!token.trim() || !name.trim()) return;
    localStorage.setItem(TOKEN_KEY, token.trim());
    localStorage.setItem(NAME_KEY, name.trim());
    setReady(true);
    setMsgs([
      {
        who: "system",
        text:
          "This is Jay's companion — it knows him well and speaks for him, but keeps his private stuff private. Ask anything, or switch to “correct” if it gets something wrong (Jay reviews corrections before he learns them).",
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
          { who: "system", text: "Couldn't reach the companion just now — try again in a moment." },
        ]);
      }
    } finally {
      setBusy(false);
    }
  }

  // --- Access gate ----------------------------------------------------------
  if (!ready) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-[#0a0a0f] text-zinc-100 px-4">
        <form onSubmit={enter} className="w-full max-w-sm space-y-4">
          <div className="space-y-1 text-center">
            <h1 className="text-2xl font-semibold">Talk to Jay</h1>
            <p className="text-sm text-zinc-400">A companion that knows him. Friends only.</p>
          </div>
          {authError && (
            <p className="text-sm text-red-400 text-center">That access code didn’t work.</p>
          )}
          <input
            className="w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 outline-none focus:border-indigo-500"
            placeholder="Your name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="w-full rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 outline-none focus:border-indigo-500"
            placeholder="Access code (Jay gave you one)"
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <button
            type="submit"
            className="w-full rounded-lg bg-indigo-600 hover:bg-indigo-500 py-2 font-medium transition"
          >
            Enter
          </button>
        </form>
      </main>
    );
  }

  // --- Chat -----------------------------------------------------------------
  return (
    <main className="min-h-screen flex flex-col bg-[#0a0a0f] text-zinc-100">
      <header className="flex items-center justify-between px-4 py-3 border-b border-zinc-900">
        <div>
          <h1 className="font-semibold leading-tight">Jay’s companion</h1>
          <p className="text-xs text-zinc-500">Hi {name} · knows Jay, keeps his secrets</p>
        </div>
        <button onClick={signOut} className="text-xs text-zinc-500 hover:text-zinc-300">
          sign out
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 max-w-2xl w-full mx-auto">
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
                  ? "max-w-[80%] rounded-2xl bg-indigo-600 px-4 py-2"
                  : m.who === "system"
                  ? "max-w-[90%] rounded-lg bg-zinc-900/60 text-zinc-400 text-xs px-3 py-2 text-center"
                  : "max-w-[80%] rounded-2xl bg-zinc-900 border border-zinc-800 px-4 py-2"
              }
            >
              {m.text}
            </div>
          </div>
        ))}
        {busy && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-zinc-900 border border-zinc-800 px-4 py-2 text-zinc-500">
              {mode === "ask" ? "thinking…" : "noting that…"}
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={send} className="border-t border-zinc-900 px-4 py-3 max-w-2xl w-full mx-auto">
        <div className="mb-2 flex gap-2 text-xs">
          <button
            type="button"
            onClick={() => setMode("ask")}
            className={`rounded-full px-3 py-1 ${
              mode === "ask" ? "bg-indigo-600" : "bg-zinc-900 text-zinc-400"
            }`}
          >
            Ask about Jay
          </button>
          <button
            type="button"
            onClick={() => setMode("correct")}
            className={`rounded-full px-3 py-1 ${
              mode === "correct" ? "bg-amber-600" : "bg-zinc-900 text-zinc-400"
            }`}
          >
            Correct / add info
          </button>
        </div>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-lg bg-zinc-900 border border-zinc-800 px-3 py-2 outline-none focus:border-indigo-500"
            placeholder={
              mode === "ask" ? "How would Jay react if…" : "Tell Jay’s companion what it got wrong…"
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={busy}
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 px-4 font-medium transition"
          >
            {mode === "ask" ? "Ask" : "Send"}
          </button>
        </div>
        {mode === "correct" && (
          <p className="mt-2 text-xs text-zinc-500">
            Jay reviews every correction before his companion learns from it — nothing changes him automatically.
          </p>
        )}
      </form>
    </main>
  );
}
