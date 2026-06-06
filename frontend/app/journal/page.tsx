"use client";

import { useCallback, useEffect, useState } from "react";
import {
  addJournal,
  fetchTimeline,
  fetchReflection,
  JournalDay,
  ReflectionResp,
} from "@/lib/api";

const OWNER_KEY = "prl_owner_token";

function prettyDay(iso: string): string {
  const today = new Date().toISOString().slice(0, 10);
  if (iso === today) return "Today";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

export default function JournalPage() {
  const [token, setToken] = useState("");
  const [tokenInput, setTokenInput] = useState("");

  const [days, setDays] = useState<JournalDay[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");

  // compose
  const [text, setText] = useState("");
  const [emotion, setEmotion] = useState("");
  const [saving, setSaving] = useState(false);

  // reflection
  const [reflection, setReflection] = useState<ReflectionResp | null>(null);
  const [reflecting, setReflecting] = useState(false);

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
      const t = await fetchTimeline(tok);
      setDays(t.days || []);
    } catch (e) {
      if (e instanceof Error && e.message === "unauthorized") {
        setStatus("That isn't the owner token. Paste your OWNER_TOKEN.");
        localStorage.removeItem(OWNER_KEY);
        setToken("");
      } else {
        setStatus("Couldn't reach the API — try again.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (token) load(token);
  }, [token, load]);

  async function save() {
    if (!text.trim()) return;
    setSaving(true);
    setStatus("");
    try {
      const res = await addJournal(token, text, emotion);
      if (res.ok) {
        setText("");
        setEmotion("");
        setStatus("Saved.");
        await load(token);
      } else {
        setStatus(res.message || "Nothing to save.");
      }
    } catch (e) {
      setStatus(
        e instanceof Error && e.message === "unauthorized"
          ? "Token rejected — re-enter your owner token."
          : "Couldn't save — try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function reflect() {
    setReflecting(true);
    setReflection(null);
    setStatus("");
    try {
      const r = await fetchReflection(token); // today
      setReflection(r);
      if (!r.ready) setStatus(r.message || "Nothing to reflect on today.");
    } catch {
      setStatus("Reflection failed — Jerry may be asleep. Try again.");
    } finally {
      setReflecting(false);
    }
  }

  if (!token) {
    return (
      <main className="min-h-screen bg-[#040507] text-zinc-100 flex items-center justify-center px-4">
        <div className="w-full max-w-sm rounded-2xl border border-white/10 bg-white/5 p-6">
          <h1 className="text-lg font-semibold">Journal</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Your private journal. Paste your owner token to open it.
          </p>
          <input
            className="mt-4 w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-indigo-400"
            placeholder="owner-…"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && tokenInput.trim()) {
                const t = tokenInput.trim();
                localStorage.setItem(OWNER_KEY, t);
                setToken(t);
              }
            }}
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
            <h1 className="text-xl font-semibold">Journal</h1>
            <p className="text-xs text-zinc-500">Private to you — Jerry never quotes it to friends</p>
          </div>
          <button
            onClick={() => load(token)}
            className="rounded-full bg-white/5 px-3 py-1 text-xs text-zinc-300 hover:bg-white/10"
          >
            {loading ? "refreshing…" : "refresh"}
          </button>
        </div>

        {/* Compose */}
        <section className="mt-6 rounded-2xl border border-white/10 bg-white/5 p-4">
          <textarea
            className="w-full resize-y rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-indigo-400"
            rows={4}
            placeholder="How did today go? What happened, who you saw, how you felt…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="mt-3 flex items-center gap-2">
            <input
              className="w-40 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-indigo-400"
              placeholder="mood (optional)"
              value={emotion}
              onChange={(e) => setEmotion(e.target.value)}
            />
            <button
              onClick={save}
              disabled={saving || !text.trim()}
              className="ml-auto rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-40"
            >
              {saving ? "saving…" : "Save entry"}
            </button>
          </div>
        </section>

        {status && <p className="mt-3 text-xs text-amber-400">{status}</p>}

        {/* Reflect on today */}
        <section className="mt-6">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium text-zinc-300">Reflection</h2>
            <button
              onClick={reflect}
              disabled={reflecting}
              className="rounded-full bg-indigo-600/80 px-3 py-1 text-xs font-medium hover:bg-indigo-500 disabled:opacity-40"
            >
              {reflecting ? "reflecting…" : "Reflect on today"}
            </button>
          </div>
          {reflection?.ready && (
            <div className="mt-3 space-y-3 rounded-2xl border border-white/10 bg-white/5 p-4">
              {reflection.narrative && (
                <p className="text-sm leading-relaxed text-zinc-200">{reflection.narrative}</p>
              )}
              <ReflectList label="Wins" items={reflection.wins} tone="text-emerald-300" />
              <ReflectList label="Challenges" items={reflection.challenges} tone="text-amber-300" />
              <ReflectList label="Lessons" items={reflection.lessons} tone="text-sky-300" />
              <ReflectList label="Gratitude" items={reflection.gratitude} tone="text-rose-300" />
              <ReflectList label="Suggestions" items={reflection.suggestions} tone="text-violet-300" />
            </div>
          )}
        </section>

        {/* Timeline */}
        <section className="mt-8">
          <h2 className="text-sm font-medium text-zinc-300">
            Timeline <span className="text-zinc-500">({days.reduce((n, d) => n + d.entries.length, 0)})</span>
          </h2>
          {days.length === 0 ? (
            <p className="mt-2 text-sm text-zinc-500">
              No entries yet — write your first one above. ✍️
            </p>
          ) : (
            <div className="mt-3 space-y-5">
              {days.map((day) => (
                <div key={day.date}>
                  <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                    {prettyDay(day.date)}
                  </p>
                  <ul className="mt-2 space-y-2">
                    {day.entries.map((e) => (
                      <li key={e.id} className="rounded-xl border border-white/10 bg-white/5 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <p className="text-sm text-zinc-100">{e.title}</p>
                          {e.emotion && (
                            <span className="shrink-0 rounded-full bg-indigo-500/15 px-2 py-0.5 text-[11px] text-indigo-300">
                              {e.emotion}
                            </span>
                          )}
                        </div>
                        {(e.categories.length > 0 || e.people.length > 0) && (
                          <div className="mt-1.5 flex flex-wrap gap-1.5">
                            {e.people.map((p) => (
                              <span key={"p" + p} className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-zinc-400">
                                @{p}
                              </span>
                            ))}
                            {e.categories.map((c) => (
                              <span key={"c" + c} className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-zinc-500">
                                {c}
                              </span>
                            ))}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function ReflectList({
  label,
  items,
  tone,
}: {
  label: string;
  items?: string[];
  tone: string;
}) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <p className={`text-xs font-semibold ${tone}`}>{label}</p>
      <ul className="mt-1 space-y-0.5">
        {items.map((it, i) => (
          <li key={i} className="text-sm text-zinc-300">
            • {it}
          </li>
        ))}
      </ul>
    </div>
  );
}
