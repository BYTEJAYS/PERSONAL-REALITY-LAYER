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
