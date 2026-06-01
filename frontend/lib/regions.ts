import { RegionName } from "./types";

export interface RegionConfig {
  name: RegionName;
  label: string;
  // Anchor inside brain space. Drives region territory (nearest-anchor coloring)
  // and the focus camera target. Together the five sketch a cortical map.
  anchor: [number, number, number];
  color: string; // hex — spec-mandated category color
  description: string;
  examples: string[];
}

// Brain space: hemispheres span x≈±0.64, height y≈±0.8, length z≈±1.3 (front +z).
export const REGIONS: Record<RegionName, RegionConfig> = {
  memory: {
    name: "memory",
    label: "Memory Cortex",
    anchor: [0.0, -0.28, -0.95],
    color: "#4ea0ff", // blue
    description: "Events, experiences, photos, locations",
    examples: ["Events", "Experiences", "Photos", "Locations"],
  },
  knowledge: {
    name: "knowledge",
    label: "Knowledge Cortex",
    anchor: [0.0, 0.55, 0.35],
    color: "#a855f7", // purple
    description: "FastAPI, AI, mathematics, research",
    examples: ["FastAPI", "AI", "Mathematics", "Research"],
  },
  goal: {
    name: "goal",
    label: "Goal Cortex",
    anchor: [0.0, 0.12, 1.05],
    color: "#f5b301", // gold
    description: "Career goals, projects, objectives",
    examples: ["Career Goals", "Projects", "Objectives"],
  },
  social: {
    name: "social",
    label: "Social Cortex",
    anchor: [0.55, 0.05, -0.15],
    color: "#22c55e", // green
    description: "Friends, team members, mentors",
    examples: ["Friends", "Team Members", "Mentors"],
  },
  project: {
    name: "project",
    label: "Project Cortex",
    anchor: [-0.55, 0.05, -0.15],
    color: "#ef4444", // red
    description: "TGIE, startups, research projects",
    examples: ["TGIE", "Startups", "Research"],
  },
};

export const REGION_ORDER: RegionName[] = [
  "memory",
  "knowledge",
  "goal",
  "social",
  "project",
];

export const REGION_INDEX: Record<RegionName, number> = REGION_ORDER.reduce(
  (acc, name, i) => ({ ...acc, [name]: i }),
  {} as Record<RegionName, number>,
);

export function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace("#", "");
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}

export const REGION_COLORS_RGB: [number, number, number][] = REGION_ORDER.map(
  (n) => hexToRgb(REGIONS[n].color),
);
