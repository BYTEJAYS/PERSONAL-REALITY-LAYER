"use client";

import { useState } from "react";

// The published Spline scene Jay specified ("Particle AI Brain"). The share URL
// embeds with no frame restrictions, so this renders the exact scene.
// Override with a different published scene via NEXT_PUBLIC_SPLINE_URL.
const SCENE_URL =
  process.env.NEXT_PUBLIC_SPLINE_URL ||
  "https://my.spline.design/particleaibrain-4Zo20EaDCjwPc0v8ejQh9AQV/";

function Loader({ show }: { show: boolean }) {
  return (
    <div
      className={`pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-[#04050a] transition-opacity duration-700 ${
        show ? "opacity-100" : "opacity-0"
      }`}
    >
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/15 border-t-white/70" />
        <span className="text-xs tracking-[0.3em] text-white/40">INITIALIZING MIND…</span>
      </div>
    </div>
  );
}

export function SplineBrain() {
  const [loading, setLoading] = useState(true);

  return (
    <div className="absolute inset-0 bg-[#04050a]">
      <Loader show={loading} />
      <iframe
        src={SCENE_URL}
        title="PRL Cognitive Core — Particle AI Brain"
        className="h-full w-full border-0"
        allow="autoplay; fullscreen; xr-spatial-tracking"
        onLoad={() => setLoading(false)}
      />
      {/* Mask the Spline free-tier "Built with Spline" badge (it lives inside
          the cross-origin iframe, so it can't be removed from the DOM). The
          flat fill matches the scene background for a seamless blend. */}
      <div
        aria-hidden
        className="pointer-events-none absolute bottom-0 right-0 h-16 w-56 bg-[#04050a]"
      />
    </div>
  );
}
