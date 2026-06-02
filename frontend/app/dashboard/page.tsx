"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import {
  Bar, Badge, Card, Pill,
  CATEGORY_COLOR, SCENARIO_COLOR, STAGE_COLOR, STATUS_COLOR, TREND_COLOR,
} from "@/components/dashboard/ui";
import { loadCognitive, MOCK, type Cognitive } from "@/lib/cognitive";

const pct = (n: number) => `${Math.round(n * 100)}%`;

export default function Dashboard() {
  const [data, setData] = useState<Cognitive>(MOCK);
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const run = () =>
      loadCognitive().then((r) => {
        if (!alive) return;
        setData(r.data);
        setLive(r.live);
        setLoading(false);
      });
    run();
    const id = setInterval(run, 30_000);
    return () => { alive = false; clearInterval(id); };
  }, []);

  const { model, chapters, identity, sim, habits, decisions, blind, os, kg, learning, trends } = data;
  const totalMonths = chapters.chapters.reduce((s, c) => s + c.span_months, 0) || 1;
  const chapterHue = (i: number) => `hsl(${(i * 67) % 360} 70% 55%)`;

  return (
    <main className="h-screen overflow-y-auto bg-ink">
      <div className="mx-auto max-w-7xl px-5 py-8">
        {/* Header */}
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-black tracking-tight">
              Self-Evolution Dashboard
            </h1>
            <p className="mt-1 text-sm text-white/50">
              {model.summary}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <div className="text-[11px] uppercase tracking-wide text-white/40">Model maturity</div>
              <div className="text-xl font-bold tabular-nums">{pct(model.maturity)}</div>
            </div>
            <Badge color={live ? "#22c55e" : "#f5b301"}>
              {loading ? "Loading…" : live ? "Live data" : "Demo data"}
            </Badge>
            <Link href="/" className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/60 hover:bg-white/5">
              ← Brain
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {/* PERSONAL OS — hero */}
          <Card title="Personal OS" subtitle="navigation map" icon="🧭" className="xl:col-span-3">
            <div className="grid gap-6 md:grid-cols-4">
              <div>
                <div className="mb-2 text-[11px] uppercase tracking-wide text-white/40">Current focus</div>
                <div className="flex flex-wrap gap-1.5">
                  {os.current_state.active_focus.map((f) => <Pill key={f}>{f}</Pill>)}
                </div>
                <div className="mb-2 mt-4 text-[11px] uppercase tracking-wide text-white/40">Established habits</div>
                <div className="flex flex-wrap gap-1.5">
                  {os.current_state.established_habits.map((h) => <Pill key={h}>{h}</Pill>)}
                </div>
              </div>
              <div>
                <div className="mb-2 text-[11px] uppercase tracking-wide text-white/40">
                  Desired → distance ({pct(os.distance.overall)} gap)
                </div>
                {os.distance.per_goal.map((g) => (
                  <Bar key={g.goal} value={g.distance} color="#f97316" label={g.goal} right={pct(g.distance)} />
                ))}
              </div>
              <div>
                <div className="mb-2 text-[11px] uppercase tracking-wide text-white/40">Obstacles</div>
                {os.obstacles.map((o) => (
                  <div key={o.title} className="mb-2 rounded-lg border border-red-500/20 bg-red-500/5 p-2">
                    <div className="text-xs font-semibold text-red-300">{o.title}</div>
                    <div className="text-[11px] text-white/50">{o.detail}</div>
                  </div>
                ))}
              </div>
              <div>
                <div className="mb-2 text-[11px] uppercase tracking-wide text-white/40">Leverage points</div>
                {os.leverage_points.map((l) => (
                  <div key={l.action} className="mb-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2">
                    <div className="text-xs font-semibold text-emerald-300">{l.action}</div>
                    <div className="text-[11px] text-white/50">{l.expected_effect}</div>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          {/* COGNITIVE TWIN */}
          <Card title="Cognitive Twin" subtitle="evidence-backed traits" icon="🧠">
            {model.traits.map((t) => (
              <Bar key={t.name} value={t.score} label={t.label} right={pct(t.score)} />
            ))}
          </Card>

          {/* KNOWLEDGE DISTRIBUTION */}
          <Card title="Knowledge Galaxy" subtitle="where mind-share concentrates" icon="✨">
            {model.knowledge_distribution.map((k, i) => (
              <Bar key={k.skill} value={Math.min(1, k.weight / (model.knowledge_distribution[0]?.weight || 1))}
                color={chapterHue(i)} label={k.skill} right={`${k.mentions}×`} />
            ))}
          </Card>

          {/* TRENDS */}
          <Card title="Interest Evolution" subtitle="how you're changing" icon="📈">
            {trends.trends.map((t) => (
              <div key={t.name} className="mb-2 flex items-center justify-between">
                <span className="text-sm text-white/80">{t.name}</span>
                <Badge color={TREND_COLOR[t.direction] ?? "#6b7280"}>{t.direction}</Badge>
              </div>
            ))}
          </Card>

          {/* LIFE CHAPTERS */}
          <Card title="Life Chapters" subtitle="auto-detected phases" icon="🕰️" className="xl:col-span-3">
            <div className="flex h-12 w-full overflow-hidden rounded-lg">
              {chapters.chapters.map((c, i) => (
                <div key={c.start} style={{ width: `${(c.span_months / totalMonths) * 100}%`, background: chapterHue(i) }}
                  className="flex items-center justify-center text-[11px] font-semibold text-black/80" title={`${c.start} → ${c.end}`}>
                  <span className="truncate px-1">{c.theme}</span>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-white/40">
              {chapters.chapters.map((c) => (
                <span key={c.start}>{c.theme}: {c.start}–{c.end} ({c.span_months}mo)</span>
              ))}
            </div>
          </Card>

          {/* KNOWLEDGE EVOLUTION GRAPH */}
          <Card title="Knowledge Evolution" subtitle="how ideas emerged → spine" icon="🌱" className="xl:col-span-3">
            <div className="flex flex-wrap items-center gap-1">
              {kg.spine.map((n, i) => {
                const node = kg.nodes.find((x) => x.name === n);
                const w = node ? Math.min(1, node.weight / 9) : 0.5;
                return (
                  <Fragment key={n}>
                    <span className="rounded-lg border border-white/15 px-3 py-1.5 text-sm font-medium"
                      style={{ background: `rgba(78,160,255,${0.12 + w * 0.25})` }}>
                      {n}
                    </span>
                    {i < kg.spine.length - 1 && <span className="text-white/30">→</span>}
                  </Fragment>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] text-white/40">
              {kg.nodes.length} concepts · {kg.edges.length} influence links · spine = longest line of intellectual evolution
            </p>
          </Card>

          {/* HABIT GENOME */}
          <Card title="Habit Genome" subtitle="habits as living things" icon="🧬">
            {habits.habits.map((h) => (
              <div key={h.name} className="mb-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-sm text-white/80">{h.name}</span>
                  <Badge color={STAGE_COLOR[h.stage] ?? "#6b7280"}>{h.stage}</Badge>
                </div>
                <Bar value={h.strength} color={STAGE_COLOR[h.stage] ?? "#6b7280"} right={`str ${pct(h.strength)}`} />
              </div>
            ))}
          </Card>

          {/* DECISION GENOME */}
          <Card title="Decision Genome" subtitle={`follow-through ${pct(decisions.followthrough_rate)}`} icon="⚖️">
            <div className="mb-3 flex h-3 w-full overflow-hidden rounded-full">
              {Object.entries(decisions.outcome_counts).map(([k, v]) => {
                const tot = Object.values(decisions.outcome_counts).reduce((a, b) => a + b, 0) || 1;
                const col = { thriving: "#22c55e", sustained: "#4ea0ff", stalled: "#f5b301", abandoned: "#ef4444" }[k] ?? "#6b7280";
                return <div key={k} style={{ width: `${(v / tot) * 100}%`, background: col }} title={`${k}: ${v}`} />;
              })}
            </div>
            {decisions.patterns.map((p) => (
              <div key={p.name} className="mb-2 text-xs text-white/60">
                <Badge color={p.lift >= 0 ? "#22c55e" : "#ef4444"}>{p.lift >= 0 ? "+" : ""}{Math.round(p.lift * 100)}%</Badge>
                <span className="ml-2">{p.observation}</span>
              </div>
            ))}
          </Card>

          {/* LEARNING MODEL */}
          <Card title="Learning & Retention" subtitle="spaced-repetition decay" icon="📚">
            {learning.concepts.map((c) => (
              <Bar key={c.concept} value={c.retention} color={STATUS_COLOR[c.status] ?? "#6b7280"}
                label={<span>{c.concept} <span className="text-white/30">· {c.status.replace("_", " ")}</span></span>}
                right={`${pct(c.retention)} · ${c.half_life_days}d`} />
            ))}
          </Card>

          {/* BLIND SPOTS */}
          <Card title="Blind Spots" subtitle="hidden structures surfaced" icon="🔦" className="xl:col-span-2">
            <div className="grid gap-2 sm:grid-cols-2">
              {blind.blind_spots.map((b) => (
                <div key={b.title} className="rounded-lg border p-3"
                  style={{ borderColor: `${CATEGORY_COLOR[b.category] ?? "#6b7280"}40` }}>
                  <div className="mb-1 flex items-center justify-between">
                    <Badge color={CATEGORY_COLOR[b.category] ?? "#6b7280"}>{b.category}</Badge>
                    <span className="text-[10px] text-white/30">sev {pct(b.severity)}</span>
                  </div>
                  <div className="text-sm font-semibold text-white/90">{b.title}</div>
                  <div className="text-[11px] text-white/50">{b.finding}</div>
                </div>
              ))}
            </div>
          </Card>

          {/* IDENTITY */}
          <Card title="Identity · Claim vs Pursuit" subtitle="what you say vs do" icon="🎯">
            {identity.alignments.map((a) => (
              <div key={a.goal} className="mb-3">
                <div className="mb-1 flex items-center justify-between">
                  <span className="text-sm text-white/80">{a.goal}</span>
                  {a.contradiction && <Badge color="#ef4444">contradiction</Badge>}
                </div>
                <Bar value={a.claim_strength} color="#a855f7" label="claim" right={pct(a.claim_strength)} />
                <Bar value={a.pursuit_share} color="#22c55e" label="pursuit" right={pct(a.pursuit_share)} />
              </div>
            ))}
          </Card>

          {/* LIFE SIMULATION */}
          <Card title="Life Simulation" subtitle="plausible futures" icon="🔮" className="xl:col-span-2">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-white/40">
                  <tr><th className="py-1 pr-3">Scenario</th><th className="pr-3">Horizon</th><th className="pr-3">Activity</th><th>Skills kept</th></tr>
                </thead>
                <tbody>
                  {sim.trajectories.map((t, i) => (
                    <tr key={i} className="border-t border-white/5">
                      <td className="py-1.5 pr-3"><Badge color={SCENARIO_COLOR[t.scenario] ?? "#6b7280"}>{t.scenario}</Badge></td>
                      <td className="pr-3 text-white/70">{t.horizon}</td>
                      <td className="pr-3 tabular-nums text-white/90">{t.projected_activity}</td>
                      <td className="tabular-nums text-white/70">{t.skills_kept} / {t.skills_kept + t.skills_faded}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* COUNTERFACTUALS */}
          <Card title="Counterfactuals" subtitle="what if…" icon="🔀">
            {sim.counterfactuals.map((c) => (
              <div key={c.premise} className="mb-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-white/80">{c.premise}</span>
                  <Badge color={c.delta_pct >= 0 ? "#22c55e" : "#ef4444"}>{c.delta_pct >= 0 ? "+" : ""}{c.delta_pct}%</Badge>
                </div>
                <p className="text-[11px] text-white/50">{c.explanation}</p>
              </div>
            ))}
          </Card>
        </div>

        <p className="mt-8 text-center text-[11px] text-white/30">
          PRL Cognitive Engine · 10 evidence-backed models · {live ? "live from your data" : "demo data — start the backend for live"}
        </p>
      </div>
    </main>
  );
}
