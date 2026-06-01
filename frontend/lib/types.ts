export type RegionName = "memory" | "knowledge" | "project" | "goal" | "social";

export interface RegionState {
  region: RegionName;
  count: number;
  weight: number;
  intensity: number; // 0..1, drives particle density + brightness
}

export interface BrainState {
  total_memories: number;
  total_entities: number;
  regions: RegionState[];
  neo4j: boolean;
}

export interface Thought {
  seq: number[]; // region indices, fired in order — the reasoning cascade
  token: number; // bump to re-trigger
}

export interface EntityNode {
  id: string;
  type: "person" | "project" | "goal" | "skill" | "place";
  name: string;
  region: RegionName;
  weight: number;
  mentions: number;
}
