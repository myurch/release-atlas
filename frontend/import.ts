import { purposes, Workspace } from "./types";

const string = (value: unknown, max: number): value is string =>
  typeof value === "string" &&
  Array.from(value).length <= max &&
  !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(value) &&
  new TextDecoder().decode(new TextEncoder().encode(value)) === value;
const list = (value: unknown, max: number): value is unknown[] =>
  Array.isArray(value) && value.length <= max;
const object = (value: unknown): value is Record<string, any> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
function require(condition: unknown): asserts condition {
  if (!condition)
    throw new Error(
      "Invalid saved analysis. Use a Release Atlas schema version 1 export.",
    );
}
async function sha(text: string): Promise<string> {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return Array.from(new Uint8Array(bytes), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}

export async function validateSnapshot(value: unknown): Promise<Workspace> {
  require(object(value));
  require(new TextEncoder().encode(JSON.stringify(value)).length <= 1800000);
  require(
    value.schema_version === 1 &&
      Number.isSafeInteger(value.revision) &&
      value.revision >= 0 &&
      string(value.title, 160),
  );
  require(
    list(value.sources, 30) &&
      list(value.claims, 200) &&
      list(value.usage, 40) &&
      list(value.topics, 8) &&
      list(value.answers, 30) &&
      list(value.audit, 200),
  );
  require(
    object(value.graph) &&
      list(value.graph.nodes, 7000) &&
      list(value.graph.edges, 15000),
  );
  const sources = new Map<string, any>();
  let length = 0;
  for (const s of value.sources) {
    require(
      object(s) &&
        string(s.id, 80) &&
        string(s.title, 160) &&
        string(s.version, 80) &&
        string(s.text, 12000) &&
        string(s.url, 1000) &&
        string(s.license, 300),
    );
    require(
      !sources.has(s.id) &&
        s.title.trim() &&
        s.version.trim() &&
        s.text.trim() &&
        (!s.url || /^https?:\/\//.test(s.url)),
    );
    const hash = await sha(s.text);
    require(
      s.sha256 === hash &&
        s.id === "s-" + (await sha(s.version + "\0" + hash)).slice(0, 20),
    );
    sources.set(s.id, s);
    length += Array.from(s.text).length;
  }
  require(length <= 300000);
  const ids = new Set<string>();
  for (const c of value.claims) {
    require(
      object(c) &&
        string(c.id, 80) &&
        string(c.source_id, 80) &&
        string(c.quote, 12000) &&
        !ids.has(c.id),
    );
    require(
      Number.isInteger(c.start) &&
        c.start >= 0 &&
        Number.isInteger(c.end) &&
        c.end > c.start &&
        sources.has(c.source_id),
    );
    // Python offsets count Unicode code points, unlike JavaScript string offsets.
    require(
      Array.from(sources.get(c.source_id).text)
        .slice(c.start, c.end)
        .join("") === c.quote,
    );
    require(
      c.id ===
        "c-" +
          (await sha(c.source_id + "\0" + c.start + "\0" + c.quote)).slice(
            0,
            20,
          ),
    );
    require(
      list(c.entities, 30) &&
        c.entities.every((x) => string(x, 100)) &&
        list(c.conflicts, 200) &&
        c.conflicts.every((x) => string(x, 80)),
    );
    require(
      [
        "breaking",
        "deprecation",
        "security",
        "feature",
        "fix",
        "other",
      ].includes(c.category),
    );
    require(
      Number.isFinite(c.score) &&
        c.score >= 0 &&
        c.score <= 1 &&
        Number.isInteger(c.topic) &&
        c.topic >= 0 &&
        typeof c.applicable === "boolean",
    );
    if (c.document !== undefined && c.document !== null) {
      const d = c.document;
      require(
        object(d) &&
          string(d.title, 160) &&
          !!d.title.trim() &&
          list(d.headings, 8) &&
          d.headings.every((x) => string(x, 160)) &&
          ["paragraph", "list-item", "code", "table"].includes(d.kind) &&
          Number.isInteger(d.words) &&
          d.words >= 0 &&
          Number.isInteger(d.sentences) &&
          d.sentences >= 0 &&
          purposes.includes(d.purpose) &&
          list(d.alternatives, 3) &&
          list(d.examples, 2) &&
          list(d.mentions, 60) &&
          Number.isFinite(d.topic_strength) &&
          d.topic_strength >= 0 &&
          d.topic_strength <= 1,
      );
      for (const row of d.alternatives)
        require(
          object(row) &&
            purposes.includes(row.label) &&
            Number.isFinite(row.score) &&
            row.score >= 0 &&
            row.score <= 1,
        );
      for (const row of d.examples)
        require(
          object(row) &&
            purposes.includes(row.label) &&
            string(row.text, 400) &&
            row.text.length > 0 &&
            Number.isFinite(row.similarity) &&
            row.similarity >= -1 &&
            row.similarity <= 1,
        );
      for (const m of d.mentions)
        require(
          object(m) &&
            string(m.name, 100) &&
            m.name.length > 0 &&
            string(m.normalized, 100) &&
            m.normalized === m.name.replace(/\(\)$/, "").toLowerCase() &&
            [
              "api",
              "configuration",
              "command",
              "endpoint",
              "package",
              "protocol",
              "identifier",
            ].includes(m.kind) &&
            string(m.rule, 80) &&
            !!m.rule &&
            Number.isInteger(m.start) &&
            Number.isInteger(m.end) &&
            m.start >= c.start &&
            m.end <= c.end &&
            m.end > m.start &&
            Array.from(sources.get(c.source_id).text)
              .slice(m.start, m.end)
              .join("") === m.name,
        );
    }
    if (c.review !== null)
      require(
        object(c.review) &&
          ["applicable", "not-applicable", "needs-investigation"].includes(
            c.review.status,
          ) &&
          string(c.review.note, 2000) &&
          string(c.review.by, 60) &&
          string(c.review.at, 80),
      );
    ids.add(c.id);
  }
  for (const c of value.claims) {
    require(object(c));
    require(c.conflicts.every((id: string) => ids.has(id) && id !== c.id));
  }
  for (const u of value.usage)
    require(
      object(u) &&
        string(u.component, 80) &&
        u.component.length > 0 &&
        string(u.entity, 100) &&
        /^[A-Za-z_][A-Za-z0-9_.:/-]*$/.test(u.entity),
    );
  const topicIds = new Set<number>();
  for (const t of value.topics) {
    require(
      object(t) &&
        Number.isInteger(t.id) &&
        t.id >= 0 &&
        !topicIds.has(t.id) &&
        Number.isInteger(t.count) &&
        t.count >= 0 &&
        list(t.terms, 6) &&
        t.terms.every((x) => string(x, 100)),
    );
    topicIds.add(t.id);
    if (t.weights !== undefined)
      require(
        list(t.weights, 6) &&
          (!t.weights.length || t.weights.length === t.terms.length) &&
          t.weights.every(
            (x) =>
              typeof x === "number" && Number.isFinite(x) && x >= 0 && x <= 1,
          ),
      );
    if (t.source_count !== undefined)
      require(
        Number.isInteger(t.source_count) &&
          t.source_count >= 0 &&
          t.source_count <= 30,
      );
    if (t.representatives !== undefined)
      require(
        list(t.representatives, 3) &&
          t.representatives.every(
            (id) =>
              string(id, 80) &&
              value.claims.some((c: any) => c.id === id && c.topic === t.id),
          ),
      );
  }
  const nodes = new Set<string>();
  for (const n of value.graph.nodes) {
    require(
      object(n) &&
        string(n.id, 240) &&
        string(n.label, 240) &&
        ["claim", "entity", "source", "component"].includes(n.kind) &&
        Number.isInteger(n.degree) &&
        n.degree >= 0 &&
        !nodes.has(n.id),
    );
    require(n.kind !== "claim" || ids.has(n.id));
    require(n.kind !== "source" || sources.has(n.id));
    nodes.add(n.id);
  }
  for (const e of value.graph.edges)
    require(
      object(e) &&
        nodes.has(e.source) &&
        nodes.has(e.target) &&
        ["supports", "mentions", "uses", "conflicts"].includes(e.relation),
    );
  for (const a of value.answers)
    require(
      object(a) &&
        string(a.id, 80) &&
        string(a.question, 2000) &&
        string(a.answer, 8000) &&
        string(a.uncertainty, 2000) &&
        string(a.method, 200) &&
        string(a.at, 80) &&
        list(a.citations, 12) &&
        a.citations.every((x) => ids.has(x as string)),
    );
  for (const a of value.audit)
    require(
      object(a) &&
        string(a.at, 80) &&
        string(a.by, 60) &&
        string(a.action, 200) &&
        Number.isInteger(a.revision),
    );
  if (value.analysis !== null)
    require(
      object(value.analysis) &&
        string(value.analysis.method, 300) &&
        string(value.analysis.embedding_model, 200) &&
        string(value.analysis.training_hash, 64) &&
        string(value.analysis.source_digest, 64) &&
        string(value.analysis.created_at, 80),
    );
  if (
    value.analysis?.pipeline !== undefined &&
    value.analysis.pipeline !== null
  ) {
    const p = value.analysis.pipeline;
    if (p.evaluation !== undefined && p.evaluation !== null) {
      const e = p.evaluation;
      require(
        object(e) &&
          Number.isInteger(e.held_out_examples) &&
          e.held_out_examples >= 1 &&
          e.held_out_examples <= 1000 &&
          string(e.evaluation_hash, 64) &&
          /^[a-f0-9]{64}$/.test(e.evaluation_hash),
      );
      for (const score of [e.macro_f1, e.keyword_macro_f1])
        require(Number.isFinite(score) && score >= 0 && score <= 1);
    }
    require(
      object(p) &&
        p.version === "documentation-v1" &&
        list(p.notices, 6) &&
        p.notices.every((x) => string(x, 300)),
    );
    for (const field of [
      "sources",
      "passages",
      "words",
      "sections",
      "code_blocks",
      "entity_mentions",
      "unique_entities",
      "embedding_dimensions",
      "training_examples",
    ])
      require(Number.isInteger(p[field]) && p[field] >= 0);
    require(
      p.sources <= 30 &&
        p.passages <= 200 &&
        p.code_blocks <= 200 &&
        p.entity_mentions <= 12000 &&
        p.unique_entities <= 12000 &&
        p.embedding_dimensions >= 1 &&
        p.embedding_dimensions <= 300 &&
        p.training_examples >= 1 &&
        p.training_examples <= 1000,
    );
  }
  return value as Workspace;
}
