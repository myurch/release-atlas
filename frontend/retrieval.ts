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
] as const;
export type RetrievalReport = {
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
  return row;
}
