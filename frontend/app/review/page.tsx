"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchPending,
  fetchFriendQuestions,
  reviewContribution,
  PendingItem,
  FriendQuestion,
} from "@/lib/api";

const OWNER_KEY = "prl_owner_token";

export default function ReviewPage() {
  const [token, setToken] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [questions, setQuestions] = useState<FriendQuestion[]>([]);
  const [status, setStatus] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("code");
    if (fromUrl) localStorage.setItem(OWNER_KEY, fromUrl);
    setToken(fromUrl || localStorage.getItem(OWNER_KEY) || "");
  }, []);

  const load = useCallback(async (tok: string) => {
    if (!tok) return;
    setLoading(true);
    setStatus("");
    try {
      const [p, q] = await Promise.all([fetchPending(tok), fetchFriendQuestions(tok)]);
      setPending(p.pending || []);
      setQuestions(q.questions || []);
    } catch (e) {
      setStatus(
        e instanceof Error && e.message === "unauthorized"
          ? "That token isn't the owner token. Paste your OWNER_TOKEN."
          : "Couldn't reach the API — try again.",
      );
      if (e instanceof Error && e.message === "unauthorized") {
        localStorage.removeItem(OWNER_KEY);
        setToken("");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) load(token);
  }, [token, load]);

  async function decide(item: PendingItem, approve: boolean) {
    setBusyId(item.id);
    try {
      await reviewContribution(token, item.id, approve, 0.6);
      setPending((list) => list.filter((p) => p.id !== item.id));
      setStatus(approve ? "Approved — Jerry knows it now." : "Rejected — discarded.");
    } catch {
      setStatus("That action failed — try again.");
    } finally {
      setBusyId(null);
    }
  }

  if (!token) {
    return (
      <main className="min-h-screen bg-[#040507] text-zinc-100 flex items-center justify-center px-4">
        <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-white/5 p-6">
          <h1 className="text-lg font-semibold">Owner review</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Paste your owner token to review what friends have submitted.
          </p>
          <input
            className="mt-4 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-indigo-400"
            placeholder="owner-…"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
          />
          <button
            className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-40"
            disabled={!tokenInput.trim()}
            onClick={() => {
              const t = tokenInput.trim();
              localStorage.setItem(OWNER_KEY, t);
              setToken(t);
            }}
          >
            Open
          </button>
          {status && <p className="mt-3 text-xs text-amber-400">{status}</p>}
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#040507] text-zinc-100 px-4 py-8">
      <div className="mx-auto max-w-2xl">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">Review</h1>
            <p className="text-xs text-zinc-500">What friends submitted & asked Jerry</p>
          </div>
          <button
            onClick={() => load(token)}
            className="rounded-full bg-white/5 px-3 py-1 text-xs text-zinc-300 hover:bg-white/10"
          >
            {loading ? "refreshing…" : "refresh"}
          </button>
        </div>

        {status && <p className="mt-3 text-xs text-amber-400">{status}</p>}

        {/* Pending submissions */}
        <section className="mt-6">
          <h2 className="text-sm font-medium text-zinc-300">
            Pending submissions <span className="text-zinc-500">({pending.length})</span>
          </h2>
          {pending.length === 0 ? (
            <p className="mt-2 text-sm text-zinc-500">Nothing waiting. 🎉</p>
          ) : (
            <ul className="mt-3 space-y-3">
              {pending.map((item) => (
                <li key={item.id} className="rounded-xl border border-white/10 bg-white/5 p-4">
                  <p className="text-sm">{item.text}</p>
                  <p className="mt-1 text-xs text-zinc-500">
                    from {item.submitter || "a friend"}
                    {item.kind ? ` · ${item.kind}` : ""}
                    {item.plausibility ? ` · ${item.plausibility}` : ""}
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button
                      disabled={busyId === item.id}
                      onClick={() => decide(item, true)}
                      className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium hover:bg-emerald-500 disabled:opacity-40"
                    >
                      Approve — Jerry learns it
                    </button>
                    <button
                      disabled={busyId === item.id}
                      onClick={() => decide(item, false)}
                      className="rounded-lg bg-white/5 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/10 disabled:opacity-40"
                    >
                      Reject
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* What friends are asking */}
        <section className="mt-8">
          <h2 className="text-sm font-medium text-zinc-300">
            What friends are asking <span className="text-zinc-500">({questions.length})</span>
          </h2>
          {questions.length === 0 ? (
            <p className="mt-2 text-sm text-zinc-500">No questions logged yet.</p>
          ) : (
            <ul className="mt-3 space-y-1.5">
              {questions.map((q, i) => (
                <li key={i} className="rounded-lg bg-white/5 px-3 py-2 text-sm text-zinc-300">
                  {q.text}
                  {q.count && q.count > 1 ? (
                    <span className="text-zinc-500"> · ×{q.count}</span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
