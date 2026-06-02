// Typed client for the /cognitive/* engines, with per-endpoint mock fallback so
// the Self-Evolution Dashboard renders fully even when the backend (Postgres/
// Docker) isn't running. `loadCognitive()` fetches everything concurrently.

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getJSON<T>(path: string, timeoutMs = 2500): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}${path}`, { signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

// ---- shapes (only the fields the UI reads) ----
export interface Trait { name: string; label: string; score: number; explanation: string; }
export interface TwinModel {
  summary: string; maturity: number; traits: Trait[];
  knowledge_distribution: { skill: string; weight: number; mentions: number }[];
}
export interface Chapter { title: string; theme: string; start: string; end: string; span_months: number; }
export interface ChaptersResult { ready: boolean; chapters: Chapter[]; current_chapter?: Chapter | null; }
export interface GoalAlignment {
  goal: string; claim_strength: number; pursuit_share: number; alignment: string;
  contradiction: boolean; explanation: string;
}
export interface IdentityResult { ready: boolean; alignments: GoalAlignment[]; contradictions: string[]; }
export interface Trajectory {
  scenario: string; horizon: string; projected_activity: number; skills_kept: number; skills_faded: number;
}
export interface Counterfactual { premise: string; horizon: string; delta_pct: number; explanation: string; }
export interface SimResult { ready: boolean; trajectories: Trajectory[]; counterfactuals: Counterfactual[]; }
export interface HabitGene {
  name: string; stage: string; strength: number; consistency: number; outcome_correlation: number; explanation: string;
}
export interface HabitsResult { ready: boolean; stage_counts: Record<string, number>; habits: HabitGene[]; }
export interface DecisionItem { subject: string; outcome: string; followthrough: number; explanation: string; }
export interface DecisionPattern { name: string; observation: string; lift: number; }
export interface DecisionsResult {
  ready: boolean; followthrough_rate: number; outcome_counts: Record<string, number>;
  patterns: DecisionPattern[]; decisions: DecisionItem[];
}
export interface BlindSpot {
  category: string; title: string; finding: string; severity: number; confidence: number; references: string[];
}
export interface BlindSpotsResult { ready: boolean; category_counts: Record<string, number>; blind_spots: BlindSpot[]; }
export interface Leverage { action: string; rationale: string; expected_effect: string; impact: number; source: string; }
export interface OSResult {
  ready: boolean;
  current_state: { summary: string; active_focus: string[]; established_habits: string[] };
  desired_state: { goals: { goal: string; priority: number }[] };
  distance: { overall: number; per_goal: { goal: string; distance: number }[] };
  obstacles: { title: string; detail: string; severity: number }[];
  leverage_points: Leverage[];
}
export interface KGNode { name: string; order: number; weight: number; }
export interface KGEdge { source: string; target: string; strength: number; }
export interface KGResult { ready: boolean; nodes: KGNode[]; edges: KGEdge[]; spine: string[]; }
export interface ConceptLearning {
  concept: string; knowledge_level: number; retention: number; status: string; half_life_days: number;
}
export interface LearningResult {
  ready: boolean; status_counts: Record<string, number>; concepts: ConceptLearning[];
}
export interface TrendItem { name: string; direction: string; change: number; }
export interface TrendsResult { ready: boolean; trends: TrendItem[]; }

export interface Cognitive {
  model: TwinModel; chapters: ChaptersResult; identity: IdentityResult; sim: SimResult;
  habits: HabitsResult; decisions: DecisionsResult; blind: BlindSpotsResult; os: OSResult;
  kg: KGResult; learning: LearningResult; trends: TrendsResult;
}

export interface CognitiveLoad { data: Cognitive; live: boolean; }

export async function loadCognitive(): Promise<CognitiveLoad> {
  const grab = async <T>(path: string, mock: T): Promise<{ v: T; live: boolean }> => {
    try { return { v: await getJSON<T>(path), live: true }; }
    catch { return { v: mock, live: false }; }
  };

  const [model, chapters, identity, sim, habits, decisions, blind, os, kg, learning, trends] =
    await Promise.all([
      grab("/cognitive/model", MOCK.model),
      grab("/cognitive/chapters", MOCK.chapters),
      grab("/cognitive/identity", MOCK.identity),
      grab("/cognitive/simulate", MOCK.sim),
      grab("/cognitive/habits", MOCK.habits),
      grab("/cognitive/decisions", MOCK.decisions),
      grab("/cognitive/blind-spots", MOCK.blind),
      grab("/cognitive/os", MOCK.os),
      grab("/cognitive/knowledge-graph", MOCK.kg),
      grab("/cognitive/learning", MOCK.learning),
      grab("/cognitive/trends", MOCK.trends),
    ]);

  return {
    live: model.live,
    data: {
      model: model.v, chapters: chapters.v, identity: identity.v, sim: sim.v,
      habits: habits.v, decisions: decisions.v, blind: blind.v, os: os.v,
      kg: kg.v, learning: learning.v, trends: trends.v,
    },
  };
}

// ---- demo data (mirrors Jay's real profile shape) ----
export const MOCK: Cognitive = {
  model: {
    summary: "This person is a hands-on builder, exploratory, independent, working best as a night owl.",
    maturity: 0.42,
    traits: [
      { name: "learning_style", label: "Hands-on builder", score: 0.71, explanation: "71% of skill activity happens while building real projects." },
      { name: "curiosity", label: "Highly curious", score: 0.68, explanation: "Engages many distinct topics, several picked up recently." },
      { name: "focus_concentration", label: "Deep focuser", score: 0.67, explanation: "Top project holds 67% of all project activity." },
      { name: "persistence", label: "Exploratory / starts many", score: 0.28, explanation: "Several projects have gone quiet for 3+ weeks." },
      { name: "attention_rhythm", label: "Night owl", score: 0.95, explanation: "Activity concentrates around 23:00." },
    ],
    knowledge_distribution: [
      { skill: "Python", weight: 9.2, mentions: 61 }, { skill: "FastAPI", weight: 6.4, mentions: 38 },
      { skill: "Three.js", weight: 5.1, mentions: 29 }, { skill: "Machine Learning", weight: 4.7, mentions: 24 },
      { skill: "Next.js", weight: 4.2, mentions: 22 }, { skill: "Graph Intelligence", weight: 3.0, mentions: 14 },
    ],
  },
  chapters: {
    ready: true,
    chapters: [
      { title: "School Phase", theme: "School", start: "2023-01", end: "2023-08", span_months: 8 },
      { title: "Backend Phase", theme: "Backend", start: "2023-09", end: "2024-03", span_months: 7 },
      { title: "Machine Learning Phase", theme: "Machine Learning", start: "2024-04", end: "2024-11", span_months: 8 },
      { title: "PRL Phase", theme: "PRL", start: "2024-12", end: "2026-06", span_months: 19 },
    ],
    current_chapter: { title: "PRL Phase", theme: "PRL", start: "2024-12", end: "2026-06", span_months: 19 },
  },
  identity: {
    ready: true,
    alignments: [
      { goal: "Become ML Engineer", claim_strength: 1.0, pursuit_share: 0.12, alignment: "partial", contradiction: false, explanation: "Stated priority ~100%, 12% of recent activity — partial alignment." },
      { goal: "Ship PRL", claim_strength: 0.8, pursuit_share: 0.46, alignment: "strong", contradiction: false, explanation: "Strongly pursued (46% of activity)." },
      { goal: "Exercise regularly", claim_strength: 0.7, pursuit_share: 0.03, alignment: "weak", contradiction: true, explanation: "Claimed important yet only 3% of activity — claimed as important yet rarely pursued." },
    ],
    contradictions: ["Exercise regularly"],
  },
  sim: {
    ready: true,
    trajectories: [
      { scenario: "decline", horizon: "30 days", projected_activity: 12, skills_kept: 3, skills_faded: 3 },
      { scenario: "steady", horizon: "30 days", projected_activity: 26, skills_kept: 5, skills_faded: 1 },
      { scenario: "growth", horizon: "30 days", projected_activity: 41, skills_kept: 6, skills_faded: 0 },
      { scenario: "decline", horizon: "1 year", projected_activity: 140, skills_kept: 2, skills_faded: 4 },
      { scenario: "steady", horizon: "1 year", projected_activity: 312, skills_kept: 5, skills_faded: 1 },
      { scenario: "growth", horizon: "1 year", projected_activity: 498, skills_kept: 6, skills_faded: 0 },
    ],
    counterfactuals: [
      { premise: "If you were active every day", horizon: "365 days", delta_pct: 150.0, explanation: "Active ~2.8 days/week; daily practice adds ~219 more active days/yr." },
      { premise: "If every week matched your best week", horizon: "365 days", delta_pct: 82.0, explanation: "Best week hit 6 active days vs a ~3.3 average." },
      { premise: "If you revived your stalled projects", horizon: "365 days", delta_pct: 100.0, explanation: "2 projects have gone quiet; reviving them could double completed output." },
    ],
  },
  habits: {
    ready: true,
    stage_counts: { growing: 1, stable: 2, declining: 1, dormant: 1 },
    habits: [
      { name: "Daily Coding", stage: "stable", strength: 0.82, consistency: 0.83, outcome_correlation: 0.74, explanation: "Active in 83% of tracked weeks; lines up with productive weeks." },
      { name: "PRL", stage: "growing", strength: 0.77, consistency: 0.67, outcome_correlation: 0.61, explanation: "Gaining momentum." },
      { name: "Research", stage: "stable", strength: 0.55, consistency: 0.5, outcome_correlation: 0.4, explanation: "Steady." },
      { name: "Reading", stage: "declining", strength: 0.31, consistency: 0.42, outcome_correlation: 0.1, explanation: "Losing momentum." },
      { name: "Exercise", stage: "dormant", strength: 0.12, consistency: 0.25, outcome_correlation: -0.2, explanation: "Gone quiet recently." },
    ],
  },
  decisions: {
    ready: true,
    followthrough_rate: 0.43,
    outcome_counts: { thriving: 1, sustained: 2, stalled: 2, abandoned: 2 },
    patterns: [
      { name: "collaborative", observation: "Decisions that involve other people follow through 50% more often (83% vs 33%).", lift: 0.5 },
      { name: "busy_start", observation: "Decisions started during a busy period follow through 30% less often (35% vs 65%).", lift: -0.3 },
    ],
    decisions: [
      { subject: "PRL", outcome: "thriving", followthrough: 0.9, explanation: "Sustained over many weeks." },
      { subject: "Transaction Graph Engine", outcome: "sustained", followthrough: 0.6, explanation: "Ongoing." },
      { subject: "Echo Interrogation", outcome: "stalled", followthrough: 0.3, explanation: "Quiet for weeks." },
      { subject: "Synthetic Genesis", outcome: "sustained", followthrough: 0.55, explanation: "Active." },
    ],
  },
  blind: {
    ready: true,
    category_counts: { risk: 2, opportunity: 1, misalignment: 1, pattern: 1 },
    blind_spots: [
      { category: "pattern", title: "You start more than you finish", finding: "5 of 8 initiatives stalled or abandoned; only 43% reached sustained follow-through.", severity: 0.57, confidence: 0.7, references: ["decision_genome"] },
      { category: "opportunity", title: "A hidden driver of your productive weeks", finding: "Your more productive weeks consistently coincide with 'Daily Coding' (r=0.74).", severity: 0.74, confidence: 0.7, references: ["habit_genome"] },
      { category: "misalignment", title: "A goal you claim but rarely pursue", finding: "'Exercise regularly': claimed important yet only 3% of activity.", severity: 0.67, confidence: 0.6, references: ["identity"] },
      { category: "risk", title: "A repeated decision mistake", finding: "Decisions started during a busy period follow through 30% less often.", severity: 0.3, confidence: 0.6, references: ["decision_genome"] },
    ],
  },
  os: {
    ready: true,
    current_state: {
      summary: "Hands-on builder, exploratory, deep focuser, night owl.",
      active_focus: ["Python", "FastAPI", "Three.js", "Machine Learning", "Next.js"],
      established_habits: ["Daily Coding", "PRL", "Research"],
    },
    desired_state: { goals: [{ goal: "Become ML Engineer", priority: 1.0 }, { goal: "Ship PRL", priority: 0.8 }, { goal: "Exercise regularly", priority: 0.7 }] },
    distance: { overall: 0.51, per_goal: [{ goal: "Become ML Engineer", distance: 0.88 }, { goal: "Exercise regularly", distance: 0.67 }, { goal: "Ship PRL", distance: 0.34 }] },
    obstacles: [
      { title: "You start more than you finish", detail: "Only 43% of initiatives reach follow-through.", severity: 0.57 },
      { title: "A goal you claim but rarely pursue", detail: "Exercise: 3% of activity.", severity: 0.67 },
    ],
    leverage_points: [
      { action: "Lean into: A hidden driver of your productive weeks", rationale: "Daily Coding correlates with your best output.", expected_effect: "Reinforces a condition linked to your best output.", impact: 0.74, source: "blind_spots" },
      { action: "If you were active every day", rationale: "Active ~2.8 days/week.", expected_effect: "~150% change over 365 days.", impact: 0.75, source: "life_sim" },
      { action: "Shift more activity toward 'Become ML Engineer'", rationale: "Largest gap between values and actions.", expected_effect: "Closes the widest claim/behaviour gap.", impact: 0.88, source: "identity" },
    ],
  },
  kg: {
    ready: true,
    nodes: [
      { name: "Python", order: 0, weight: 9.2 }, { name: "FastAPI", order: 1, weight: 6.4 },
      { name: "Backend", order: 2, weight: 5.0 }, { name: "Fraud Detection", order: 3, weight: 3.8 },
      { name: "Machine Learning", order: 4, weight: 4.7 }, { name: "Graph Intelligence", order: 5, weight: 3.0 },
      { name: "PRL", order: 6, weight: 8.1 },
    ],
    edges: [
      { source: "Python", target: "FastAPI", strength: 22 }, { source: "FastAPI", target: "Backend", strength: 15 },
      { source: "Backend", target: "Fraud Detection", strength: 9 }, { source: "Fraud Detection", target: "Machine Learning", strength: 11 },
      { source: "Machine Learning", target: "Graph Intelligence", strength: 8 }, { source: "Graph Intelligence", target: "PRL", strength: 12 },
    ],
    spine: ["Python", "FastAPI", "Backend", "Fraud Detection", "Machine Learning", "Graph Intelligence", "PRL"],
  },
  learning: {
    ready: true,
    status_counts: { mastered: 2, learning: 2, weak_foundation: 1, forgotten: 1 },
    concepts: [
      { concept: "Python", knowledge_level: 0.92, retention: 0.95, status: "mastered", half_life_days: 64 },
      { concept: "FastAPI", knowledge_level: 0.86, retention: 0.88, status: "mastered", half_life_days: 52 },
      { concept: "Three.js", knowledge_level: 0.61, retention: 0.7, status: "learning", half_life_days: 31 },
      { concept: "Machine Learning", knowledge_level: 0.54, retention: 0.66, status: "learning", half_life_days: 28 },
      { concept: "Graph Theory", knowledge_level: 0.38, retention: 0.41, status: "weak_foundation", half_life_days: 18 },
      { concept: "Rust", knowledge_level: 0.44, retention: 0.12, status: "forgotten", half_life_days: 14 },
    ],
  },
  trends: {
    ready: true,
    trends: [
      { name: "Three.js", direction: "rising", change: 0.6 }, { name: "PRL", direction: "rising", change: 0.5 },
      { name: "Graph Intelligence", direction: "emerging", change: 0.4 }, { name: "Fraud Detection", direction: "fading", change: -0.4 },
      { name: "Rust", direction: "dormant", change: -0.7 },
    ],
  },
};
