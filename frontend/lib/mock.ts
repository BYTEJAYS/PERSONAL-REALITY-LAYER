import { BrainState, EntityNode } from "./types";

// Stand-in state so the brain is alive before the backend is up. Roughly mirrors
// what seeding Jay's real repos (TGIE, synthetic-genesis, echo) would produce.
export const MOCK_BRAIN: BrainState = {
  total_memories: 37,
  total_entities: 24,
  neo4j: false,
  regions: [
    { region: "memory", count: 37, weight: 18.5, intensity: 1.0 },
    { region: "knowledge", count: 9, weight: 7.4, intensity: 0.62 },
    { region: "project", count: 4, weight: 9.1, intensity: 0.78 },
    { region: "goal", count: 3, weight: 3.2, intensity: 0.34 },
    { region: "social", count: 3, weight: 4.0, intensity: 0.41 },
  ],
};

export const MOCK_ENTITIES: EntityNode[] = [
  { id: "p1", type: "project", name: "transaction-graph-intelligence", region: "project", weight: 5.2, mentions: 29 },
  { id: "p2", type: "project", name: "synthetic-genesis", region: "project", weight: 2.1, mentions: 6 },
  { id: "p3", type: "project", name: "echo-interrogation", region: "project", weight: 1.8, mentions: 2 },
  { id: "s1", type: "skill", name: "Python", region: "knowledge", weight: 3.4, mentions: 22 },
  { id: "s2", type: "skill", name: "FastAPI", region: "knowledge", weight: 2.1, mentions: 14 },
  { id: "s3", type: "skill", name: "Fraud Detection", region: "knowledge", weight: 1.6, mentions: 9 },
  { id: "s4", type: "skill", name: "Graph", region: "knowledge", weight: 1.2, mentions: 7 },
  { id: "u1", type: "person", name: "Jay", region: "social", weight: 4.0, mentions: 30 },
];
