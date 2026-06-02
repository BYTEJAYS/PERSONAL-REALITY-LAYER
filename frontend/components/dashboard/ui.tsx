"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";

export const STAGE_COLOR: Record<string, string> = {
  forming: "#a855f7", growing: "#22c55e", stable: "#4ea0ff",
  declining: "#f5b301", dormant: "#f97316", dead: "#ef4444",
};
export const STATUS_COLOR: Record<string, string> = {
  mastered: "#22c55e", learning: "#4ea0ff", weak_foundation: "#f5b301",
  bottleneck: "#f97316", forgotten: "#ef4444", dormant: "#6b7280",
};
export const CATEGORY_COLOR: Record<string, string> = {
  risk: "#ef4444", opportunity: "#22c55e", misalignment: "#f5b301", pattern: "#a855f7",
};
export const TREND_COLOR: Record<string, string> = {
  rising: "#22c55e", emerging: "#4ea0ff", fading: "#f5b301", dormant: "#6b7280", dimming: "#f97316",
};
export const SCENARIO_COLOR: Record<string, string> = {
  growth: "#22c55e", steady: "#4ea0ff", decline: "#ef4444",
};

export function Card({
  title, subtitle, icon, children, className = "",
}: {
  title: string; subtitle?: string; icon?: string; children: ReactNode; className?: string;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.4 }}
      className={`rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur ${className}`}
    >
      <header className="mb-4 flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold tracking-wide text-white/90">
          {icon && <span className="mr-2">{icon}</span>}
          {title}
        </h2>
        {subtitle && <span className="text-[11px] text-white/40">{subtitle}</span>}
      </header>
      {children}
    </motion.section>
  );
}

export function Bar({
  value, color = "#4ea0ff", label, right,
}: {
  value: number; color?: string; label?: ReactNode; right?: ReactNode;
}) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className="mb-2.5">
      {(label || right) && (
        <div className="mb-1 flex items-center justify-between text-xs text-white/60">
          <span className="truncate">{label}</span>
          <span className="tabular-nums text-white/40">{right}</span>
        </div>
      )}
      <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
        <motion.div
          initial={{ width: 0 }}
          whileInView={{ width: `${pct}%` }}
          viewport={{ once: true }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="h-full rounded-full"
          style={{ background: color }}
        />
      </div>
    </div>
  );
}

export function Badge({ children, color = "#4ea0ff" }: { children: ReactNode; color?: string }) {
  return (
    <span
      className="inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ color, background: `${color}1f`, border: `1px solid ${color}40` }}
    >
      {children}
    </span>
  );
}

export function Pill({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-white/70">
      {children}
    </span>
  );
}
