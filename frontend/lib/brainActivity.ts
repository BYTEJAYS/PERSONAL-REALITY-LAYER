// A tiny, render-free signal so the chat can drive the particle brain WITHOUT
// re-rendering the <Canvas> (which would rebuild the 250k-point geometry). The
// chat mutates these fields; ParticleBrain's per-frame loop reads them and eases
// a "fire" level up and down. No React state, no re-renders — just a shared ref.

type BrainActivity = {
  thinking: boolean; // true while a reply is being generated → steady glow
  lastPulse: number; // performance.now() of the last answer chunk → ripple
};

export const brainActivity: BrainActivity = { thinking: false, lastPulse: 0 };

const now = () =>
  typeof performance !== "undefined" ? performance.now() : Date.now();

/** Jerry started/stopped thinking (call with true on send, false when done). */
export function setThinking(v: boolean): void {
  brainActivity.thinking = v;
}

/** A burst of activity — fire the brain (call as each answer chunk arrives). */
export function pulseBrain(): void {
  brainActivity.lastPulse = now();
}

/** 0..1 fire target for this instant: steady while thinking + a decaying pulse. */
export function fireTarget(): number {
  const sincePulse = (now() - brainActivity.lastPulse) / 1000;
  const pulse = sincePulse < 1.1 ? Math.max(0, 1 - sincePulse / 1.1) : 0;
  return Math.max(brainActivity.thinking ? 0.8 : 0, pulse);
}
