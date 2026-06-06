"use client";

import { useCallback, useEffect, useState } from "react";
import {
  addJournal,
  askCouncil,
  CouncilResp,
  deleteJournalEntry,
  fetchDay,
  fetchMonthReview,
  fetchReflection,
  fetchTimeline,
  fetchPhilosophy,
  fetchPrinciples,
  fetchTruths,
  fetchWisdom,
  fetchYearReview,
  JournalDay,
  JournalFullEntry,
  PhilosophyResp,
  Principle,
  PrinciplesResp,
  ReflectionResp,
  ReviewResp2,
  Truth,
  TruthsResp,
  WisdomInsight,
  WisdomResp,
} from "@/lib/api";

const OWNER_KEY = "prl_owner_token";

function todayISO(): string {
  return new Date().toISOString().slice(0, 10);
}
function prettyDay(iso: string): string {
  if (iso === todayISO()) return "Today";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
function thisMonthISO(): string {
  return todayISO().slice(0, 7);
}

export default function JournalPage() {
  const [token, setToken] = useState("");
  const [tokenInput, setTokenInput] = useState("");
  const [tab, setTab] = useState<"journal" | "reviews" | "wisdom" | "principles" | "council">("journal");

  const [days, setDays] = useState<JournalDay[]>([]);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");

  // compose
  const [text, setText] = useState("");
  const [emotion, setEmotion] = useState("");
  const [saving, setSaving] = useState(false);

  // reflection (any day)
  const [reflectDate, setReflectDate] = useState(todayISO());
  const [reflection, setReflection] = useState<ReflectionResp | null>(null);
  const [reflecting, setReflecting] = useState(false);

  // expandable entries → full content + events, lazy-loaded by day
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [dayCache, setDayCache] = useState<Record<string, JournalFullEntry[]>>({});

  useEffect(() => {
    const fromUrl = new URLSearchParams(window.location.search).get("code");
    if (fromUrl) localStorage.setItem(OWNER_KEY, fromUrl);
    setToken(fromUrl || localStorage.getItem(OWNER_KEY) || "");
  }, []);

  const onAuthError = useCallback((msg: string) => {
    setStatus(msg);
    localStorage.removeItem(OWNER_KEY);
    setToken("");
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
        onAuthError("That isn't the owner token. Paste your OWNER_TOKEN.");
      } else {
        setStatus("Couldn't reach the API — try again.");
      }
    } finally {
      setLoading(false);
    }
  }, [onAuthError]);

  useEffect(() => {
    if (token) load(token);
  }, [token, load]);

  const totalEntries = days.reduce((n, d) => n + d.entries.length, 0);

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
        setDayCache({}); // entries changed → drop cached day views
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
      const r = await fetchReflection(token, reflectDate);
      setReflection(r);
      if (!r.ready) setStatus(r.message || "Nothing to reflect on that day.");
    } catch {
      setStatus("Reflection failed — Jerry may be asleep. Try again.");
    } finally {
      setReflecting(false);
    }
  }

  async function remove(id: string, date: string) {
    if (!confirm("Delete this entry? This can't be undone.")) return;
    setStatus("");
    try {
      const r = await deleteJournalEntry(token, id);
      if (r.ok) {
        setDayCache((c) => {
          const n = { ...c };
          delete n[date];
          return n;
        });
        setExpanded((s) => {
          const n = new Set(s);
          n.delete(id);
          return n;
        });
        await load(token);
      } else {
        setStatus(r.message || "Couldn't delete.");
      }
    } catch (e) {
      setStatus(
        e instanceof Error && e.message === "unauthorized"
          ? "Token rejected — re-enter your owner token."
          : "Couldn't delete — try again.",
      );
    }
  }

  async function toggle(id: string, date: string) {
    setExpanded((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
    if (!dayCache[date]) {
      try {
        const d = await fetchDay(token, date);
        setDayCache((c) => ({ ...c, [date]: d.entries || [] }));
      } catch {
        /* leave uncached; the summary still shows */
      }
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
            <p className="text-xs text-zinc-500">
              {totalEntries} {totalEntries === 1 ? "entry" : "entries"} · private to you — Jerry never quotes it to friends
            </p>
          </div>
          <button
            onClick={() => { setDayCache({}); load(token); }}
            className="rounded-full bg-white/5 px-3 py-1 text-xs text-zinc-300 hover:bg-white/10"
          >
            {loading ? "refreshing…" : "refresh"}
          </button>
        </div>

        {/* Tabs */}
        <div className="mt-5 flex gap-1 rounded-full border border-white/10 bg-white/5 p-1 text-sm">
          {(["journal", "reviews", "wisdom", "principles", "council"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 rounded-full px-4 py-1.5 capitalize transition ${
                tab === t ? "bg-indigo-600 text-white" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        {status && <p className="mt-3 text-xs text-amber-400">{status}</p>}

        {tab === "journal" ? (
          <>
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

            {/* Reflection (any day) */}
            <section className="mt-6">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-sm font-medium text-zinc-300">Reflection</h2>
                <div className="flex items-center gap-2">
                  <input
                    type="date"
                    max={todayISO()}
                    value={reflectDate}
                    onChange={(e) => setReflectDate(e.target.value)}
                    className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-zinc-300 outline-none focus:border-indigo-400"
                  />
                  <button
                    onClick={reflect}
                    disabled={reflecting}
                    className="rounded-full bg-indigo-600/80 px-3 py-1 text-xs font-medium hover:bg-indigo-500 disabled:opacity-40"
                  >
                    {reflecting ? "reflecting…" : "Reflect"}
                  </button>
                </div>
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
                Timeline <span className="text-zinc-500">({totalEntries})</span>
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
                        {day.entries.map((e) => {
                          const open = expanded.has(e.id);
                          const full = dayCache[day.date]?.find((x) => x.id === e.id);
                          return (
                            <li key={e.id} className="rounded-xl border border-white/10 bg-white/5 p-3">
                              <div className="flex items-start justify-between gap-3">
                                <button
                                  onClick={() => toggle(e.id, day.date)}
                                  className="flex-1 text-left"
                                >
                                  <span className="text-sm text-zinc-100">
                                    <span className="mr-1 text-zinc-500">{open ? "▾" : "▸"}</span>
                                    {e.title}
                                  </span>
                                </button>
                                <div className="flex shrink-0 items-center gap-2">
                                  {e.emotion && (
                                    <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[11px] text-indigo-300">
                                      {e.emotion}
                                    </span>
                                  )}
                                  <button
                                    onClick={() => remove(e.id, day.date)}
                                    title="Delete entry"
                                    className="rounded-md px-1.5 py-0.5 text-zinc-500 hover:bg-rose-500/15 hover:text-rose-300"
                                  >
                                    🗑
                                  </button>
                                </div>
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

                              {open && (
                                <div className="mt-3 border-t border-white/10 pt-3">
                                  {full ? (
                                    <>
                                      <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">
                                        {full.content}
                                      </p>
                                      {(full.journal.events?.length ?? 0) > 0 && (
                                        <ul className="mt-3 space-y-1.5">
                                          {full.journal.events!.map((ev, i) => (
                                            <li key={i} className="flex items-start gap-2 text-xs text-zinc-400">
                                              <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-zinc-500">
                                                {ev.category}
                                              </span>
                                              <span className="flex-1">{ev.description}</span>
                                              {ev.emotion && (
                                                <span className="text-indigo-300/80">{ev.emotion}</span>
                                              )}
                                            </li>
                                          ))}
                                        </ul>
                                      )}
                                    </>
                                  ) : (
                                    <p className="text-xs text-zinc-500">loading…</p>
                                  )}
                                </div>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        ) : tab === "reviews" ? (
          <ReviewsTab token={token} />
        ) : tab === "wisdom" ? (
          <WisdomTab token={token} />
        ) : tab === "principles" ? (
          <PrinciplesTab token={token} />
        ) : (
          <CouncilTab token={token} />
        )}
      </div>
    </main>
  );
}

const WISDOM_META: Record<WisdomInsight["category"], { label: string; tone: string; icon: string }> = {
  success_pattern: { label: "Success pattern", tone: "text-emerald-300", icon: "✅" },
  growth_driver: { label: "Growth driver", tone: "text-sky-300", icon: "🚀" },
  philosophy: { label: "Core philosophy", tone: "text-violet-300", icon: "🧭" },
  lesson: { label: "Lesson", tone: "text-amber-300", icon: "📌" },
  pitfall: { label: "Pitfall", tone: "text-rose-300", icon: "⚠️" },
};
const WISDOM_ORDER: WisdomInsight["category"][] = [
  "philosophy", "success_pattern", "growth_driver", "lesson", "pitfall",
];

function WisdomTab({ token }: { token: string }) {
  const [data, setData] = useState<WisdomResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr("");
    fetchWisdom(token)
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setErr("Couldn't load wisdom — try again."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [token]);

  if (loading) return <p className="mt-6 text-sm text-zinc-500">distilling…</p>;
  if (err) return <p className="mt-6 text-xs text-amber-400">{err}</p>;
  if (!data?.ready || !data.wisdom?.length) {
    return (
      <p className="mt-6 text-sm text-zinc-500">
        Not enough recorded yet to draw lessons. Keep journaling — patterns, habits and
        recurring themes turn into wisdom as your history grows. 🌱
      </p>
    );
  }

  const groups = WISDOM_ORDER
    .map((cat) => ({ cat, items: data.wisdom!.filter((w) => w.category === cat) }))
    .filter((g) => g.items.length > 0);

  return (
    <section className="mt-6 space-y-5">
      <p className="text-xs text-zinc-500">{data.note}</p>
      {groups.map(({ cat, items }) => {
        const m = WISDOM_META[cat];
        return (
          <div key={cat}>
            <p className={`text-xs font-semibold ${m.tone}`}>
              {m.icon} {m.label}
            </p>
            <ul className="mt-2 space-y-2">
              {items.map((w, i) => (
                <li key={i} className="rounded-xl border border-white/10 bg-white/5 p-3">
                  <p className="text-sm text-zinc-100">{w.statement}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                    <span className="rounded-full bg-white/5 px-2 py-0.5">
                      confidence {Math.round(w.confidence * 100)}%
                    </span>
                    {w.evidence.slice(0, 2).map((e, j) => (
                      <span key={j} className="rounded-full bg-white/5 px-2 py-0.5">{e}</span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}

const MIND_ICON: Record<string, string> = {
  Scientist: "🔬", Critic: "⚠️", Optimist: "🌅", Strategist: "♟️",
  Philosopher: "🧭", Psychologist: "🫀", Historian: "📜", Entrepreneur: "🚀",
  Engineer: "🛠️", "Creative Thinker": "💡",
};

const COUNCIL_PROMPTS = [
  "Should I start a new project or finish what I have?",
  "Is this friendship worth keeping?",
  "Should I take the risky path or the safe one?",
];

function CouncilTab({ token }: { token: string }) {
  const [q, setQ] = useState("");
  const [data, setData] = useState<CouncilResp | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function convene(question: string) {
    if (!question.trim()) return;
    setBusy(true);
    setErr("");
    setData(null);
    try {
      const r = await askCouncil(token, question.trim());
      setData(r);
    } catch (e) {
      setErr(
        e instanceof Error && e.message === "unauthorized"
          ? "Token rejected — re-enter your owner token."
          : "Couldn't reach the council — try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-6">
      <p className="text-xs text-zinc-500">
        Ten minds — Scientist, Critic, Optimist, Strategist, Philosopher, Psychologist,
        Historian, Entrepreneur, Engineer, Creative — weigh in on your dilemma, grounded
        in your own principles.
      </p>

      <div className="mt-3 flex items-center gap-2">
        <input
          className="flex-1 rounded-lg border border-white/10 bg-black/40 px-3 py-2 text-sm outline-none focus:border-indigo-400"
          placeholder="Ask the council a real question…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") convene(q); }}
        />
        <button
          onClick={() => convene(q)}
          disabled={busy || !q.trim()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-40"
        >
          {busy ? "convening…" : "Convene"}
        </button>
      </div>

      {!data && !busy && (
        <div className="mt-3 flex flex-wrap gap-2">
          {COUNCIL_PROMPTS.map((p) => (
            <button
              key={p}
              onClick={() => { setQ(p); convene(p); }}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-zinc-400 hover:bg-white/10"
            >
              {p}
            </button>
          ))}
        </div>
      )}

      {err && <p className="mt-3 text-xs text-amber-400">{err}</p>}

      {data && (
        <div className="mt-5 space-y-4">
          {/* Verdict */}
          <div className="rounded-2xl border border-indigo-400/20 bg-indigo-500/5 p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold text-indigo-200">The council&apos;s verdict</p>
              <span className="text-[10px] text-zinc-500">
                {data.generated_by === "llm" ? "fused by Jerry" : "deterministic"}
              </span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-zinc-100">{data.synthesis}</p>
          </div>

          {/* Individual minds */}
          <ul className="space-y-2">
            {data.takes.map((t) => (
              <li key={t.mind} className="rounded-xl border border-white/10 bg-white/5 p-3">
                <p className="text-sm font-medium text-zinc-200">
                  {MIND_ICON[t.mind] || "•"} {t.mind}
                  <span className="ml-2 text-[11px] font-normal text-zinc-500">{t.lens}</span>
                </p>
                <p className="mt-1 text-sm text-zinc-300">{t.take}</p>
                {t.draws_on.length > 0 && (
                  <p className="mt-1 text-[10px] text-zinc-600">from your principles</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

const STATUS_TONE: Record<Principle["status"], string> = {
  active: "text-emerald-400",
  forming: "text-sky-400",
  weakening: "text-amber-400",
  dormant: "text-zinc-500",
};

function PrinciplesTab({ token }: { token: string }) {
  const [data, setData] = useState<PrinciplesResp | null>(null);
  const [philo, setPhilo] = useState<PhilosophyResp | null>(null);
  const [truths, setTruths] = useState<TruthsResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr("");
    // Build/persist principles first, then read their evolution, contradictions & truths.
    fetchPrinciples(token)
      .then((d) => {
        if (alive) setData(d);
        return Promise.all([fetchPhilosophy(token), fetchTruths(token)]);
      })
      .then(([p, t]) => { if (alive) { setPhilo(p); setTruths(t); } })
      .catch(() => { if (alive) setErr("Couldn't load principles — try again."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [token]);

  if (loading) return <p className="mt-6 text-sm text-zinc-500">reconciling your principles…</p>;
  if (err) return <p className="mt-6 text-xs text-amber-400">{err}</p>;
  if (!data?.ready || !data.principles?.length) {
    return (
      <p className="mt-6 text-sm text-zinc-500">
        No principles yet. As lessons recur and gather evidence, they graduate into
        principles you live by — and you&apos;ll see them strengthen here over time. 🌱
      </p>
    );
  }

  return (
    <section className="mt-6 space-y-6">
      {/* Truths (Meta-Wisdom apex) */}
      {(truths?.truth_count ?? 0) > 0 && (
        <div className="rounded-2xl border border-amber-300/30 bg-gradient-to-b from-amber-500/10 to-transparent p-4">
          <p className="text-sm font-semibold text-amber-200">🏛 Truths</p>
          <ul className="mt-3 space-y-2">
            {truths!.truths!.map((t) => (
              <li key={t.key} className="text-sm text-zinc-100">
                <span className="mr-1.5 text-amber-300">✦</span>{t.statement}
                <span className="ml-1 text-[11px] text-zinc-500">
                  ({Math.round(t.truthhood * 100)}%)
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Emerging truths — watch them climb */}
      {(truths?.emerging?.length ?? 0) > 0 && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs font-semibold text-zinc-300">
            Emerging truths{" "}
            <span className="text-zinc-600">
              (toward the {Math.round((truths!.threshold ?? 0.7) * 100)}% bar)
            </span>
          </p>
          <ul className="mt-3 space-y-3">
            {truths!.emerging!.map((t) => (
              <li key={t.key}>
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm text-zinc-200">{t.statement}</p>
                  <span className="shrink-0 text-xs text-zinc-500">{Math.round(t.truthhood * 100)}%</span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/5">
                  <div
                    className="h-full rounded-full bg-amber-400/60"
                    style={{ width: `${Math.min(100, (t.truthhood / (truths!.threshold ?? 0.7)) * 100)}%` }}
                  />
                </div>
                <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-zinc-600">
                  {(["confidence", "evidence", "longevity", "sources", "stability"] as const).map((k) => (
                    <span key={k} className="rounded bg-white/5 px-1.5 py-0.5">
                      {k} {Math.round((t.components[k] ?? 0) * 100)}%
                    </span>
                  ))}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Personal Commandments */}
      {(data.commandments?.length ?? 0) > 0 && (
        <div className="rounded-2xl border border-indigo-400/20 bg-indigo-500/5 p-4">
          <p className="text-sm font-semibold text-indigo-200">📜 Principles I Live By</p>
          <ol className="mt-3 space-y-2">
            {data.commandments!.map((c, i) => (
              <li key={i} className="flex gap-3 text-sm text-zinc-100">
                <span className="shrink-0 font-mono text-indigo-300">{i + 1}.</span>
                <span>{c.statement}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Recent changes */}
      {(data.recent_changes?.length ?? 0) > 0 && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs font-semibold text-zinc-300">What shifted</p>
          <ul className="mt-2 space-y-1">
            {data.recent_changes!.map((c, i) => (
              <li key={i} className="text-xs text-zinc-400">
                <span className={
                  c.event === "strengthened" ? "text-emerald-400"
                  : c.event === "weakened" || c.event === "faded" ? "text-amber-400"
                  : "text-sky-400"
                }>{c.event}</span>
                {" · "}{c.statement}
                {c.from != null && c.to != null && (
                  <span className="text-zinc-600"> ({c.from}→{c.to})</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Philosophy narrative */}
      {philo?.narrative && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs font-semibold text-zinc-300">How your thinking has evolved</p>
          <p className="mt-2 text-sm leading-relaxed text-zinc-200">{philo.narrative}</p>
        </div>
      )}

      {/* Contradictions / tensions */}
      {(philo?.contradictions?.length ?? 0) > 0 && (
        <div className="rounded-2xl border border-amber-400/20 bg-amber-500/5 p-4">
          <p className="text-xs font-semibold text-amber-200">⚖️ Tensions &amp; belief shifts</p>
          <ul className="mt-2 space-y-2">
            {philo!.contradictions!.map((c, i) => (
              <li key={i} className="text-sm text-zinc-200">
                <span className="mr-1.5 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] capitalize text-amber-300">
                  {c.type}
                </span>
                {c.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Evolution timeline */}
      {(philo?.timeline?.length ?? 0) > 0 && (
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs font-semibold text-zinc-300">Evolution timeline</p>
          <ol className="mt-3 space-y-3 border-l border-white/10 pl-4">
            {philo!.timeline!.map((p) => (
              <li key={p.period} className="relative">
                <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-indigo-400" />
                <p className="text-xs font-medium text-zinc-300">{p.period}</p>
                <p className="text-[11px] text-zinc-500">{p.summary}</p>
                <ul className="mt-1 space-y-0.5">
                  {p.events.slice(0, 6).map((e, j) => (
                    <li key={j} className="text-xs text-zinc-400">
                      <span className={
                        e.event === "strengthened" ? "text-emerald-400"
                        : e.event === "weakened" || e.event === "faded" ? "text-amber-400"
                        : e.event === "revised" ? "text-violet-400" : "text-sky-400"
                      }>{e.event}</span>
                      {" · "}{e.statement}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* All principles */}
      <div>
        <p className="text-xs font-medium text-zinc-400">
          All principles <span className="text-zinc-600">({data.principle_count})</span>
        </p>
        <ul className="mt-2 space-y-2">
          {data.principles!.map((p) => (
            <li key={p.key} className="rounded-xl border border-white/10 bg-white/5 p-3">
              <p className="text-sm text-zinc-100">{p.statement}</p>
              <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                <span className={`font-medium ${STATUS_TONE[p.status]}`}>{p.status}</span>
                <span className="rounded-full bg-white/5 px-2 py-0.5">{p.category.replace("_", " ")}</span>
                <span className="rounded-full bg-white/5 px-2 py-0.5">conf {Math.round(p.confidence * 100)}%</span>
                <span className="rounded-full bg-white/5 px-2 py-0.5">{p.evidence_count} data pts</span>
                {p.history.length > 1 && (
                  <span className="rounded-full bg-white/5 px-2 py-0.5">{p.history.length} updates</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function ReviewsTab({ token }: { token: string }) {
  const [ym, setYm] = useState(thisMonthISO());
  const [year, setYear] = useState(new Date().getFullYear());
  const [scope, setScope] = useState<"month" | "year">("month");
  const [data, setData] = useState<ReviewResp2 | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const run = useCallback(async () => {
    setLoading(true);
    setErr("");
    setData(null);
    try {
      const r = scope === "month"
        ? await fetchMonthReview(token, ym)
        : await fetchYearReview(token, year);
      setData(r);
    } catch {
      setErr("Couldn't load review — try again.");
    } finally {
      setLoading(false);
    }
  }, [token, scope, ym, year]);

  useEffect(() => { run(); }, [run]);

  return (
    <section className="mt-6">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1 rounded-full border border-white/10 bg-white/5 p-1 text-xs">
          {(["month", "year"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`rounded-full px-3 py-1 capitalize ${
                scope === s ? "bg-indigo-600 text-white" : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
        {scope === "month" ? (
          <input
            type="month"
            max={thisMonthISO()}
            value={ym}
            onChange={(e) => setYm(e.target.value)}
            className="rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-zinc-300 outline-none focus:border-indigo-400"
          />
        ) : (
          <input
            type="number"
            min={2000}
            max={new Date().getFullYear()}
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="w-24 rounded-lg border border-white/10 bg-black/40 px-2 py-1 text-xs text-zinc-300 outline-none focus:border-indigo-400"
          />
        )}
        {loading && <span className="text-xs text-zinc-500">loading…</span>}
      </div>

      {err && <p className="mt-3 text-xs text-amber-400">{err}</p>}

      {data && !data.ready && (
        <p className="mt-4 text-sm text-zinc-500">{data.message || "No entries for this period."}</p>
      )}

      {data?.ready && (
        <div className="mt-4 space-y-4">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <p className="text-sm text-zinc-200">{data.headline}</p>
            <div className="mt-3 flex flex-wrap gap-4 text-xs text-zinc-400">
              <Stat label="Entries" value={String(data.entry_count ?? 0)} />
              <Stat label="Mood" value={data.mood ?? "—"} />
              <Stat label="Growth" value={data.growth_score != null ? `${Math.round(data.growth_score * 100)}%` : "—"} />
            </div>
          </div>

          <BarCard title="Where life went" rows={(data.where_life_went || []).map((r) => ({ label: r.category, n: r.count }))} />
          <BarCard title="Emotions" rows={(data.emotion_mix || []).map((r) => ({ label: r.emotion, n: r.count }))} tone="bg-rose-500/40" />

          {(data.people?.length ?? 0) > 0 && (
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs font-semibold text-zinc-300">People</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {data.people!.map((p) => (
                  <span key={p.name} className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-zinc-400">
                    @{p.name} · {p.mentions}
                  </span>
                ))}
              </div>
            </div>
          )}

          {(data.chapters?.length ?? 0) > 0 && (
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs font-semibold text-zinc-300">Chapters</p>
              <ul className="mt-2 space-y-1.5">
                {data.chapters!.map((c, i) => (
                  <li key={i} className="text-sm text-zinc-300">
                    <span className="text-indigo-300">{c.title}</span>
                    <span className="text-zinc-500"> · {c.start}{c.span_months > 1 ? `–${c.end}` : ""}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {(data.standout_memories?.length ?? 0) > 0 && (
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <p className="text-xs font-semibold text-zinc-300">Standout moments</p>
              <ul className="mt-2 space-y-1.5">
                {data.standout_memories!.map((m, i) => (
                  <li key={i} className="flex items-center justify-between gap-3 text-sm text-zinc-300">
                    <span className="truncate">{m.title}</span>
                    <span className="shrink-0 text-xs text-zinc-500">{m.date}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-zinc-500">{label}: </span>
      <span className="font-medium capitalize text-zinc-200">{value}</span>
    </div>
  );
}

function BarCard({
  title,
  rows,
  tone = "bg-indigo-500/50",
}: {
  title: string;
  rows: { label: string; n: number }[];
  tone?: string;
}) {
  if (rows.length === 0) return null;
  const max = Math.max(...rows.map((r) => r.n), 1);
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs font-semibold text-zinc-300">{title}</p>
      <div className="mt-2 space-y-1.5">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center gap-2">
            <span className="w-28 shrink-0 truncate text-xs capitalize text-zinc-400">{r.label}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-white/5">
              <div className={`h-full rounded-full ${tone}`} style={{ width: `${(r.n / max) * 100}%` }} />
            </div>
            <span className="w-6 shrink-0 text-right text-xs text-zinc-500">{r.n}</span>
          </div>
        ))}
      </div>
    </div>
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
