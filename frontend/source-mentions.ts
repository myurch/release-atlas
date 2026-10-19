import type {
  DocumentMap,
  ProjectNode,
  RelationEvidence,
} from "./document-relations";
import type { Source } from "./types";

export type MentionRequest = {
  terms: string[];
  all: boolean;
  exact: boolean;
  negative: boolean;
};
export function mentionRequest(question: string): MentionRequest | null {
  const match = question
    .slice(0, 2000)
    .match(
      /\b(?:mentions?|mentioned|references?|referenc(?:e|es|ing)|contains?|discuss(?:es)?)\b\s+(.+)/i,
    );
  if (!match) return null;
  const tail = match[1]
    .replace(
      /\s+in\s+(?:(?:their|the|these|its)\s+)?(?:readmes?|docs?|documentation|sources?|text)\b.*$/i,
      "",
    )
    .replace(/[?.!]+$/, "")
    .trim();
  const quoted = [...tail.matchAll(/["“]([^"”]{1,100})["”]/g)].map((m) =>
    m[1].trim(),
  );
  const terms = (
    quoted.length
      ? quoted
      : tail
          .split(/\s+(?:and|or)\s+|[,;]/i)
          .map((term) =>
            term
              .replace(
                /^(?:(?:the|a|an|any|word|term|topic|protocol|concept|about|anything|something)\s+)+/i,
                "",
              )
              .trim(),
          )
  )
    .filter((term) => term && Array.from(term).length <= 80)
    .slice(0, 3);
  if (!terms.length) return null;
  return {
    terms: [...new Set(terms)],
    all: /\band\b/i.test(tail) && !/\bor\b/i.test(tail),
    exact:
      !!quoted.length || /\b(?:exact|exactly|literal|word)\b/i.test(question),
    negative:
      /\b(?:not|never|without|don't|doesn't|didn't|do not|does not)\b/i.test(
        question,
      ),
  };
}
const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const label = (term: string) =>
  /^(?:https?|html|xml|json|api|cli|sql|xss|wsgi)$/i.test(term)
    ? term.toUpperCase()
    : term;

/** Literal mentions can be in prose, code, links or markup. Nothing is executed. */
export function buildMentionMap(
  request: MentionRequest,
  sources: Source[],
): DocumentMap {
  const note = `Text matches include links and examples. A mention does not establish a capability or dependency.`;
  if (request.negative)
    return {
      nodes: [],
      links: [],
      mode: "mentions",
      note: "Negative mention filters are not supported by this map yet.",
    };
  const nodes: ProjectNode[] = [];
  for (const source of sources.slice(0, 30)) {
    const body = source.text.slice(0, 24000);
    const characters = Array.from(body);
    const capabilities: ProjectNode["capabilities"] = [];
    for (const term of request.terms) {
      const boundary = "[\\p{L}\\p{N}_]";
      const pattern = `${/^[\p{L}\p{N}_]/u.test(term) ? `(?<!${boundary})` : ""}${escape(term).replace(/\s+/g, "\\s+")}${/[\p{L}\p{N}_]$/u.test(term) ? `(?!${boundary})` : ""}`;
      const match = body.match(new RegExp(pattern, "iu"));
      if (!match) continue;
      const at = Array.from(body.slice(0, match.index!)).length;
      const start = Math.max(0, at - 70),
        end = Math.min(
          characters.length,
          at + Array.from(match[0]).length + 110,
        );
      const evidence: RelationEvidence = {
        source_id: source.id,
        sha256: source.sha256,
        start,
        end,
        quote: characters.slice(start, end).join(""),
      };
      capabilities.push({
        id: "mention:" + term.toLowerCase(),
        label: `Mentions ${label(term)}`,
        evidence,
      });
    }
    if (
      !capabilities.length ||
      (request.all && capabilities.length !== request.terms.length)
    )
      continue;
    const name = source.title
      .replace(/^[\w.-]+\//, "")
      .replace(/\s+(?:README|documentation|docs)$/i, "");
    nodes.push({
      id: source.id,
      name: name || source.title,
      version: source.version,
      role: capabilities[0].label,
      capabilities,
      score: capabilities.length,
    });
  }
  nodes.sort(
    (a, b) =>
      b.score - a.score ||
      a.name.localeCompare(b.name) ||
      a.id.localeCompare(b.id),
  );
  const selected = nodes.slice(0, 6);
  const links: DocumentMap["links"] = [];
  // One sparse star per term, never a complete all-to-all mention graph.
  for (const term of request.terms) {
    const id = "mention:" + term.toLowerCase();
    const matches = selected.filter((n) =>
      n.capabilities.some((c) => c.id === id),
    );
    const first = matches[0];
    if (!first) continue;
    for (const node of matches.slice(1)) {
      if (links.length === 8) break;
      if (
        links.some(
          (l) =>
            (l.from === first.id && l.to === node.id) ||
            (l.to === first.id && l.from === node.id),
        )
      )
        continue;
      links.push({
        id: `mention:${first.id}:${node.id}:${id}`,
        from: first.id,
        to: node.id,
        label: `Both mention ${label(term)}`,
        kind: "mention",
        evidence: [first, node].map(
          (n) => n.capabilities.find((c) => c.id === id)!.evidence,
        ),
        score: 2,
      });
    }
  }
  return {
    nodes: selected,
    links,
    mode: "mentions",
    note: selected.length
      ? note
      : `No literal matches for ${request.terms.map(label).join(request.all ? " and " : " or ")} in the selected source text. ${note}`,
  };
}
