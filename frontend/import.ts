import { Workspace } from "./types";

const string = (value: unknown, max: number): value is string =>
  typeof value === "string" &&
  Array.from(value).length <= max &&
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
  for (const t of value.topics)
    require(
      object(t) &&
        Number.isInteger(t.id) &&
        Number.isInteger(t.count) &&
        list(t.terms, 6) &&
        t.terms.every((x) => string(x, 100)),
    );
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
  return value as Workspace;
}
