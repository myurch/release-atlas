import { Source } from "./types";

export type SourcePassage = {
  id: string;
  source_id: string;
  sha256: string;
  start: number;
  end: number;
  quote: string;
};

export function validatedSourcePassages(
  passages: unknown,
  citations: unknown,
  sources: Source[],
): SourcePassage[] {
  const fail = () => {
    throw new Error("The assistant source citations could not be verified.");
  };
  if (!Array.isArray(passages) || !Array.isArray(citations)) return fail();
  if (passages.length > 8 || citations.length > 8) return fail();
  const checked: SourcePassage[] = [];
  for (const p of passages) {
    if (!p || typeof p !== "object") return fail();
    const source = sources.find((s) => s.id === p.source_id);
    if (
      !source ||
      source.sha256 !== p.sha256 ||
      !Number.isInteger(p.start) ||
      !Number.isInteger(p.end) ||
      p.start < 0 ||
      p.end <= p.start ||
      p.end > Array.from(source.text).length ||
      typeof p.quote !== "string" ||
      p.quote.length === 0 ||
      Array.from(p.quote).length > 2000 ||
      p.id !== `p-${source.id}-${p.start}-${p.end}` ||
      Array.from(source.text).slice(p.start, p.end).join("") !== p.quote ||
      checked.some((previous) => previous.id === p.id)
    )
      return fail();
    checked.push(p);
  }
  if (
    citations.length !== checked.length ||
    new Set(citations).size !== citations.length ||
    citations.some(
      (id) => typeof id !== "string" || !checked.some((p) => p.id === id),
    )
  )
    return fail();
  return citations.map((id) => checked.find((p) => p.id === id)!);
}
