import { BrainState, EntityNode } from "./types";
import { MOCK_BRAIN, MOCK_ENTITIES } from "./mock";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface BrainFetch {
  state: BrainState;
  live: boolean; // true if served by the real backend, false if mock fallback
}

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

export async function fetchBrainState(): Promise<BrainFetch> {
  try {
    const state = await getJSON<BrainState>("/brain/state");
    return { state, live: true };
  } catch {
    return { state: MOCK_BRAIN, live: false };
  }
}

export async function fetchTopEntities(): Promise<EntityNode[]> {
  try {
    return await getJSON<EntityNode[]>("/brain/entities?limit=40");
  } catch {
    return MOCK_ENTITIES;
  }
}

export interface FocusResult {
  nodes: { type: string; name: string }[];
  edges: { a: string; b: string; w: number }[];
}

export async function fetchFocus(type: string, name: string): Promise<FocusResult> {
  try {
    return await getJSON<FocusResult>(
      `/brain/focus?type=${encodeURIComponent(type)}&name=${encodeURIComponent(name)}`,
    );
  } catch {
    return { nodes: [], edges: [] };
  }
}

export interface ChatCitation {
  id?: string;
  title?: string;
  source?: string;
  ts?: string;
}

export interface ChatReply {
  answer: string;
  intent: string;
  llm_used: boolean;
  citations: ChatCitation[];
}

// Ask the second brain. Throws if the backend is unreachable so the caller can
// show a clear "backend offline" message (answers require Postgres + the API).
export async function fetchChat(message: string, timeoutMs = 12000): Promise<ChatReply> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal: ctrl.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as ChatReply;
  } finally {
    clearTimeout(t);
  }
}

// --- Companion (friends-only, token-gated) --------------------------------
export interface CompanionReply {
  answer: string;
  generated_by: string; // "llm" | "deterministic"
  discretion: string;
}

export interface ContributeReply {
  status: string; // "quarantined" | "logged"
  kind: string;
  message: string;
}

async function companionPost<T>(path: string, token: string, body: object,
                                timeoutMs = 30000): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-access-token": token },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (res.status === 401 || res.status === 403) throw new Error("unauthorized");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

// Demo mode (NEXT_PUBLIC_DEMO=1): canned, realistic answers so the experience can
// be previewed with no backend / DB / LLM. Clearly fictional placeholder content.
const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

const DEMO_ANSWERS: { match: RegExp; answer: string }[] = [
  { match: /who are you|your name|what are you|who r u/i,
    answer: "I'm Jerry — Jay's companion. Think of me as the friend who knows Jay best: how he thinks, how he feels, how he'd react. I'll tell you about him, but the private stuff stays private." },
  { match: /fail|failure|lose|lost|reject/i,
    answer: "Honestly? Jay takes failure hard for about a day — he goes quiet, replays it. Then something flips and he channels it straight into the next thing. He's more resilient than he gives himself credit for; the comeback is usually faster than the sulk." },
  { match: /money|broke|spend|afford|rich|poor/i,
    answer: "He's careful but not stingy — managing fine lately. He'd rather invest in something he's building than splurge. I'll leave the exact numbers to him, though." },
  { match: /stress|anxious|pressure|overwhelm|worried/i,
    answer: "Under pressure Jay gets really focused and a bit nocturnal — he'll disappear into the work at night. The tell is he stops replying to texts. Give him space and he resurfaces." },
  { match: /love|crush|relationship|girl|date/i,
    answer: "That's firmly his to tell, not mine. What I'll say is he's loyal and feels things deeply, even when he plays it cool." },
  { match: /angry|mad|upset|conflict|fight/i,
    answer: "He doesn't blow up — he goes calm and quiet, which is actually the sign he's hurt. He needs a real conversation, not a quick sorry." },
  { match: /happy|joy|excited|best/i,
    answer: "When he's building something that's clicking, he's genuinely lit up — that's his happiest. Late nights, music on, in flow." },
];

const DEMO_DEFAULT =
  "I'm Jerry — I know Jay pretty well. He's a builder: curious, deep-focused, a night owl who throws himself into projects. Ask me how he'd react to something, or what he cares about.";

function demoAnswer(question: string): CompanionReply {
  const hit = DEMO_ANSWERS.find((d) => d.match.test(question));
  return { answer: hit ? hit.answer : DEMO_DEFAULT, generated_by: "demo", discretion: "applied" };
}

function delay<T>(v: T, ms: number): Promise<T> {
  return new Promise((r) => setTimeout(() => r(v), ms));
}

// Cloud Ollama on CPU can take 10-30s+ per reply; the API itself falls back to a
// deterministic answer at 60s, so give the request 90s before the browser bails.
export type ChatTurn = { role: "user" | "assistant"; content: string };

export async function askCompanion(
  token: string,
  question: string,
  history: ChatTurn[] = [],
): Promise<CompanionReply> {
  if (DEMO) return delay(demoAnswer(question), 900); // simulate "thinking"
  return companionPost<CompanionReply>("/companion/ask", token, { question, history }, 90000);
}

// Stream Jerry's reply token-by-token via SSE. Calls onDelta for each chunk and
// resolves with how it was generated. THROWS if the stream endpoint is missing
// (older deploy → 404), unauthorized, or yields nothing — so the caller can fall
// back to the plain askCompanion() request. This keeps the live (non-streaming)
// backend working untouched: streaming simply upgrades the feel once deployed.
export async function streamCompanion(
  token: string,
  question: string,
  history: ChatTurn[],
  onDelta: (text: string) => void,
): Promise<{ generated_by: string }> {
  if (DEMO) {
    const { answer, generated_by } = demoAnswer(question);
    for (const w of answer.split(/(\s+)/)) {
      onDelta(w);
      await delay(null, 18);
    }
    return { generated_by };
  }

  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 120000);
  try {
    const res = await fetch(`${API}/companion/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-access-token": token },
      body: JSON.stringify({ question, history }),
      signal: ctrl.signal,
    });
    if (res.status === 401 || res.status === 403) throw new Error("unauthorized");
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let got = false;
    let generated_by = "llm";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl: number;
      while ((nl = buf.indexOf("\n\n")) >= 0) {
        const raw = buf.slice(0, nl).trim();
        buf = buf.slice(nl + 2);
        if (!raw.startsWith("data:")) continue;
        try {
          const obj = JSON.parse(raw.slice(5).trim());
          if (typeof obj.delta === "string") {
            got = true;
            onDelta(obj.delta);
          }
          if (obj.done && obj.generated_by) generated_by = obj.generated_by;
        } catch {
          /* ignore a partial/garbled frame */
        }
      }
    }
    if (!got) throw new Error("empty stream");
    return { generated_by };
  } finally {
    clearTimeout(t);
  }
}

export async function correctCompanion(
  token: string,
  text: string,
  submitter: string,
): Promise<ContributeReply> {
  if (DEMO)
    return delay(
      { status: "quarantined", kind: "fact",
        message: "Thanks! I've passed that to Jay to confirm before I treat it as something I know about him." },
      700,
    );
  return companionPost<ContributeReply>("/companion/contribute", token, { text, submitter });
}

// --- Owner review (owner token required) -----------------------------------

async function companionGet<T>(path: string, token: string, timeoutMs = 15000): Promise<T> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API}${path}`, {
      headers: { "x-access-token": token },
      cache: "no-store",
      signal: ctrl.signal,
    });
    if (res.status === 401 || res.status === 403) throw new Error("unauthorized");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } finally {
    clearTimeout(t);
  }
}

export interface PendingItem {
  id: string;
  submitted_at?: string;
  text: string;
  submitter?: string;
  kind?: string;
  plausibility?: string;
}
export interface PendingResp {
  pending_count: number;
  pending: PendingItem[];
}
export async function fetchPending(token: string): Promise<PendingResp> {
  return companionGet<PendingResp>("/companion/pending", token);
}

export interface FriendQuestion {
  text: string;
  asked_at?: string;
  count?: number;
  submitter?: string;
}
export interface QuestionsResp {
  question_count: number;
  questions: FriendQuestion[];
}
export async function fetchFriendQuestions(token: string): Promise<QuestionsResp> {
  return companionGet<QuestionsResp>("/companion/questions", token);
}

export interface ReviewResp {
  id: string;
  decision: string;
  message: string;
}
export async function reviewContribution(
  token: string,
  memory_id: string,
  approve: boolean,
  importance = 0.6,
): Promise<ReviewResp> {
  return companionPost<ReviewResp>("/companion/review", token, { memory_id, approve, importance });
}
