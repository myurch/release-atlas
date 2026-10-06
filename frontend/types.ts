export type Source = {
  id: string;
  title: string;
  version: string;
  text: string;
  url: string;
  license: string;
  sha256: string;
};
export type Review = {
  status: "applicable" | "not-applicable" | "needs-investigation";
  note: string;
  by: string;
  at: string;
};
export type Claim = {
  id: string;
  source_id: string;
  quote: string;
  start: number;
  end: number;
  entities: string[];
  category: string;
  score: number;
  topic: number;
  applicable: boolean;
  conflicts: string[];
  review: Review | null;
};
export type GraphNode = {
  id: string;
  label: string;
  kind: "claim" | "entity" | "source" | "component";
  degree: number;
};
export type Workspace = {
  schema_version: 1;
  revision: number;
  title: string;
  sources: Source[];
  usage: { component: string; entity: string }[];
  claims: Claim[];
  topics: { id: number; terms: string[]; count: number }[];
  graph: {
    nodes: GraphNode[];
    edges: { source: string; target: string; relation: string }[];
  };
  analysis: {
    method: string;
    embedding_model: string;
    training_hash: string;
    source_digest: string;
    created_at: string;
  } | null;
  answers: {
    id: string;
    question: string;
    answer: string;
    citations: string[];
    uncertainty: string;
    method: string;
    at: string;
  }[];
  audit: { at: string; by: string; action: string; revision: number }[];
};
