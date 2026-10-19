import { Source } from "./types";
import { SourcePassage, validatedSourcePassages } from "./source-citations";

export const retrievalReasons = [
  "lexical match",
  "semantic match",
  "statistical similarity",
  "exact entity",
  "related topic",
  "purpose match",
  "selected source",
  "source overview",
  "conflict partner",
  "neighboring context",
  "terminology match",
  "graph connection",
] as const;
export type GraphPath = {
  from_passage: string;
  to_passage: string;
  via: string;
  relation: "technology reference" | "shared identifier";
};
export type RetrievalReport = {
  graph_paths?: GraphPath[];
  connections?: GraphPath[];
  encoder: "neural-minilm" | "statistical-lsa";
  mode: "focused" | "overview";
  model: string;
  included_sources: number;
  total_sources: number;
  candidate_count: number;
  partial: boolean;
  fallback: string;
  notices: string[];
  passages: (SourcePassage & { reasons: string[] })[];
};
export function validatedRetrieval(
  value: unknown,
  sources: Source[],
): RetrievalReport | undefined {
  if (value === undefined || value === null) return undefined;
  const row = value as RetrievalReport;
  const text = (v: unknown, max: number): v is string =>
    typeof v === "string" &&
    Array.from(v).length <= max &&
    !/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/.test(v) &&
    new TextDecoder().decode(new TextEncoder().encode(v)) === v;
  const fail = () => {
    throw new Error(
      "The retrieved context could not be verified. Try the question again.",
    );
  };
  if (
    !row ||
    !["neural-minilm", "statistical-lsa"].includes(row.encoder) ||
    !["focused", "overview"].includes(row.mode) ||
    !text(row.model, 120) ||
    !text(row.fallback, 300) ||
    typeof row.partial !== "boolean" ||
    !Array.isArray(row.notices) ||
    row.notices.length > 6 ||
    !row.notices.every((v) => text(v, 300)) ||
    !Array.isArray(row.passages)
  )
    return fail();
  validatedSourcePassages(
    row.passages,
    row.passages.map((p) => p?.id),
    sources,
  );
  for (const p of row.passages)
    if (
      !Array.isArray(p.reasons) ||
      p.reasons.length < 1 ||
      p.reasons.length > 8 ||
      p.reasons.some(
        (reason) =>
          !retrievalReasons.includes(
            reason as (typeof retrievalReasons)[number],
          ),
      )
    )
      return fail();
  if (
    !Number.isInteger(row.total_sources) ||
    row.total_sources !== sources.length ||
    !Number.isInteger(row.included_sources) ||
    row.included_sources !==
      new Set(row.passages.map((p) => p.source_id)).size ||
    !Number.isInteger(row.candidate_count) ||
    row.candidate_count < 0 ||
    row.candidate_count > 600
  )
    return fail();
  const validatePaths = (paths: GraphPath[], expansion: boolean) => {
    if (!Array.isArray(paths) || paths.length > (expansion ? 2 : 12))
      return fail();
    const seen = new Set<string>();
    const targets = new Set<string>();
    for (const path of paths) {
      if (
        !path ||
        !text(path.via, 100) ||
        !/^[a-zA-Z][a-zA-Z0-9_.:/-]{2,99}$/.test(path.via) ||
        !["technology reference", "shared identifier"].includes(path.relation)
      )
        return fail();
      const origin = row.passages.find((p) => p.id === path.from_passage);
      const target = row.passages.find((p) => p.id === path.to_passage);
      if (
        !origin ||
        !target ||
        origin.source_id === target.source_id ||
        (expansion &&
          (!target.reasons.includes("graph connection") ||
            targets.has(target.id)))
      )
        return fail();
      const key = JSON.stringify([
        [origin.source_id, target.source_id].sort(),
        path.via,
        path.relation,
      ]);
      if (seen.has(key)) return fail();
      seen.add(key);
      targets.add(target.id);
      const includes = (value: string) =>
        new RegExp(
          `(^|[^\\w.-])${path.via.split(".").join("\\.")}(?![\\w-]|\\.\\w)`,
          "i",
        ).test(value);
      const source = sources.find((s) => s.id === target.source_id)!;
      if (
        !includes(origin.quote) ||
        !includes(
          path.relation === "technology reference"
            ? source.title
            : target.quote,
        )
      )
        return fail();
    }
    if (
      expansion &&
      row.passages.some(
        (p) => p.reasons.includes("graph connection") && !targets.has(p.id),
      )
    )
      return fail();
  };
  if (row.graph_paths !== undefined) validatePaths(row.graph_paths, true);
  else if (row.passages.some((p) => p.reasons.includes("graph connection")))
    return fail();
  if (row.connections !== undefined) validatePaths(row.connections, false);
  return row;
}
