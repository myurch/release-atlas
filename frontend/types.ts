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
export const purposes = [
  "installation",
  "configuration",
  "api-reference",
  "example",
  "troubleshooting",
  "security",
  "migration",
  "overview",
  "resources",
  "other",
] as const;
export type Purpose = (typeof purposes)[number];
export type EntityMention = {
  name: string;
  normalized: string;
  kind:
    | "api"
    | "configuration"
    | "command"
    | "endpoint"
    | "package"
    | "protocol"
    | "identifier";
  start: number;
  end: number;
  rule: string;
};
export type PassageAnalysis = {
  title: string;
  headings: string[];
  kind: "paragraph" | "list-item" | "code" | "table";
  words: number;
  sentences: number;
  purpose: Purpose;
  alternatives: { label: Purpose; score: number }[];
  examples: { label: Purpose; text: string; similarity: number }[];
  mentions: EntityMention[];
  topic_strength: number;
};
export type PipelineSummary = {
  version: "documentation-v1";
  evaluation?: {
    held_out_examples: number;
    macro_f1: number;
    keyword_macro_f1: number;
    evaluation_hash: string;
  } | null;
  sources: number;
  passages: number;
  words: number;
  sections: number;
  code_blocks: number;
  entity_mentions: number;
  unique_entities: number;
  embedding_dimensions: number;
  training_examples: number;
  notices: string[];
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
  document?: PassageAnalysis | null;
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
  topics: {
    id: number;
    terms: string[];
    count: number;
    weights?: number[];
    representatives?: string[];
    source_count?: number;
  }[];
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
    pipeline?: PipelineSummary | null;
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
