import { mentionRequest, buildMentionMap } from "./source-mentions";
import type { Source } from "./types";

export type RelationEvidence = {
  source_id: string;
  sha256: string;
  start: number;
  end: number;
  quote: string;
};
type Capability = { id: string; label: string; evidence: RelationEvidence };
export type ProjectNode = {
  id: string;
  name: string;
  version: string;
  role: string;
  capabilities: Capability[];
  score: number;
};
export type DocumentRelation = {
  id: string;
  from: string;
  to: string;
  label: string;
  kind: "explicit" | "shared" | "mention";
  evidence: RelationEvidence[];
  score: number;
};
export type DocumentMap = {
  nodes: ProjectNode[];
  links: DocumentRelation[];
  mode?: "mentions" | "related";
  note?: string;
};
const RULES = [
  {
    id: "routing",
    label: "URL routing",
    text: /\b(?:routing|URL dispatch(?:ing)?|URL rules?|route decorators?)\b/i,
    query: /\b(?:routing|routes?|routers?|URL mapping|endpoints?)\b/i,
    shared: "Both document URL routing",
  },
  {
    id: "templates",
    label: "HTML templates",
    text: /\b(?:templating engine|render\w*[^.!?]{0,40}(?:HTML )?templates?|template inheritance)\b/i,
    query:
      /\b(?:frontend|front.end|templates?|templating|render\w*|HTML|pages?|website)\b/i,
    shared: "Both describe template rendering",
  },
  {
    id: "escaping",
    label: "HTML escaping",
    text: /\b(?:autoescaping|escapes? characters|escap\w*[^.!?]{0,70}(?:HTML|XML)|prevent XSS)\b/i,
    query:
      /\b(?:frontend|front.end|HTML|XSS|escap\w*|injection|untrusted|security)\b/i,
    shared: "Both describe HTML escaping",
  },
  {
    id: "wsgi",
    label: "WSGI web layer",
    text: /\bWSGI\b/i,
    query: /\b(?:WSGI|backend|back.end|web|HTTP|requests?|server)\b/i,
    shared: "Both describe WSGI support",
  },
  {
    id: "web",
    label: "Web application framework",
    text: /\bweb application framework\b/i,
    query:
      /\b(?:backend|back.end|web|framework|HTTP|requests?|server|frontend|front.end)\b/i,
    shared: "",
  },
  {
    id: "cli",
    label: "Command line tools",
    text: /\b(?:command.line interfaces?|command.line tools|CLI)\b/i,
    query: /\b(?:CLI|commands?|terminal|command.line)\b/i,
    shared: "Both describe command line tools",
  },
  {
    id: "async",
    label: "Async support",
    text: /\b(?:async Python web|serve WebSockets|AsyncIO support)\b/i,
    query: /\b(?:async\w*|websockets?|concurren\w*|stream\w*)\b/i,
    shared: "Both describe async support",
  },
  {
    id: "python",
    label: "Python usage",
    text: /\bPython\b/i,
    query: /\bpython\b/i,
    shared: "Both document Python usage",
  },
] as const;
const STOP = new Set(
  "how do i a an the is are to with for and or can use using make build tell me about what does please my this these sources docs documentation project projects line add adding implement implementing which ones one they their it in of on at be there have has help want would could should".split(
    " ",
  ),
);
const NEGATIVE =
  /\b(?:not|never|without|no longer|doesn't|don't|cannot|can't|example|hypothetical)\b/i;
// "Without running a server" and positive examples do not negate a capability.
const CAPABILITY_NEGATIVE =
  /\b(?:not|never|no longer|doesn't|don't|cannot|can't|hypothetical)\b/i;
const tokens = (text: string) => [
  ...new Set(
    (text.toLowerCase().match(/[a-z][a-z0-9_]{2,}/g) ?? []).filter(
      (t) => !STOP.has(t),
    ),
  ),
];
const escaped = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

function projectName(source: Source): string {
  // Resolve project identity from a repository README title or a leading project name.
  const repository = source.title.match(/^[\w.-]+\/([\w.-]+)\s+README$/i);
  const heading = source.text.match(/^#\s+([A-Za-z][\w.-]{1,35})\s*$/m);
  const leading = source.title.match(/^([A-Za-z][\w.-]{1,35})(?:\s|$)/);
  const name = repository?.[1] ?? leading?.[1];
  if (
    !name ||
    /^(?:source|documentation|docs|readme|library|guide|release|notes|test|example)$/i.test(
      name,
    )
  )
    return "";
  return heading?.[1].toLowerCase() === name.toLowerCase() ? heading[1] : name;
}

function prose(source: Source): { text: string; evidence: RelationEvidence }[] {
  // Mask code, HTML and URL declarations without shifting Unicode quote positions.
  const mask = (text: string) => text.replace(/[^\r\n]/g, " ");
  const body = source.text
    .slice(0, 24000)
    .replace(/^\s*(```|~~~)[^\n]*\n[\s\S]*?^\s*\1[^\n]*$/gm, mask)
    .replace(/<[^>]*>/g, mask)
    .replace(/^\s*(?:\[[^\]]+\]:|\.\. _)[^\n]*$/gm, mask)
    .replace(/https?:\/\/[^\s<>]+/g, mask);
  const rows: { text: string; evidence: RelationEvidence }[] = [];
  for (const match of body.matchAll(
    /[^\r\n]+(?:\r?\n(?!\s*\r?\n)[^\r\n]+)*/g,
  )) {
    if (rows.length >= 100) break;
    const quote = source.text.slice(
      match.index!,
      match.index! + match[0].length,
    );
    const text = match[0]
      .replace(/[\[\]`*_]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    if (text.length < 20 || text.length > 1500 || /^#|^\$|^>>>/.test(text))
      continue;
    const start = Array.from(source.text.slice(0, match.index!)).length;
    rows.push({
      text,
      evidence: {
        source_id: source.id,
        sha256: source.sha256,
        start,
        end: start + Array.from(quote).length,
        quote,
      },
    });
  }
  return rows;
}

/** Language and routing examples are evidence of documented usage, never executed. */
function exampleCapabilities(source: Source): Capability[] {
  const result: Capability[] = [];
  for (const match of source.text.matchAll(
    /^(```|~~~)(python|pycon|py)\s*\r?\n([\s\S]*?)^\1\s*$/gim,
  )) {
    const startAt = match.index!;
    const code = match[3];
    const evidenceAt = (start: number, length: number): RelationEvidence => {
      const quote = source.text.slice(start, start + length);
      const offset = Array.from(source.text.slice(0, start)).length;
      return {
        source_id: source.id,
        sha256: source.sha256,
        start: offset,
        end: offset + Array.from(quote).length,
        quote,
      };
    };
    if (!result.some((capability) => capability.id === "python")) {
      // Include the language tag, which is the actual support for this classification.
      const length = Array.from(match[0]).slice(0, 450).join("").length;
      result.push({
        id: "python",
        label: "Python examples",
        evidence: evidenceAt(startAt, length),
      });
    }
    const route = code.match(
      /^\s*@[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\.route\s*\([^\r\n]*$/m,
    );
    if (route && !result.some((capability) => capability.id === "routing")) {
      const offset = startAt + match[0].indexOf(code) + route.index!;
      result.push({
        id: "routing",
        label: "Routing examples",
        evidence: evidenceAt(offset, route[0].length),
      });
    }
  }
  return result;
}

/** Independent display-only English rules. Never changes retrieval or model context. */
export function buildDocumentMap(
  question: string,
  sources: Source[],
): DocumentMap {
  const mentions = mentionRequest(question);
  const literal = mentions ? buildMentionMap(mentions, sources) : null;
  if (
    literal &&
    (literal.nodes.length ||
      mentions!.exact ||
      mentions!.negative ||
      mentions!.terms.length > 1)
  )
    return literal;
  if (mentions) question = mentions.terms.join(" ");
  const documents = sources
    .slice(0, 30)
    .map((source) => ({
      source,
      name: projectName(source) || source.title,
      rows: prose(source),
    }))
    .filter((item) => item.name);
  question = question.slice(0, 2000);
  const query = tokens(question);
  const contents = documents.map(
    (doc) => new Set(tokens(doc.rows.map((row) => row.text).join(" "))),
  );
  const frequencies = new Map(
    query.map((term) => [
      term,
      contents.filter((content) => content.has(term)).length,
    ]),
  );
  const overview = !query.length;
  const names = new Map<string, number>();
  for (const doc of documents)
    names.set(
      doc.name.toLowerCase(),
      (names.get(doc.name.toLowerCase()) ?? 0) + 1,
    );
  const nodes: ProjectNode[] = documents.map(
    ({ source, name, rows }, index) => {
      const capabilities: Capability[] = [];
      for (const rule of RULES) {
        const row = rows.find(
          (row) =>
            !CAPABILITY_NEGATIVE.test(row.text) && rule.text.test(row.text),
        );
        if (row)
          capabilities.push({
            id: rule.id,
            label: rule.label,
            evidence: row.evidence,
          });
      }
      for (const capability of exampleCapabilities(source)) {
        if (!capabilities.some((existing) => existing.id === capability.id))
          capabilities.push(capability);
      }
      const content = contents[index];
      const lexicalMatches = query.filter((term) => content.has(term));
      const lexical =
        lexicalMatches.length < Math.min(2, query.length)
          ? 0
          : query.reduce((sum, term) => {
              if (!content.has(term)) return sum;
              const count = frequencies.get(term) ?? 0;
              return sum + Math.log(1 + documents.length / Math.max(1, count));
            }, 0);
      const roleScore = capabilities.reduce(
        (sum, capability) =>
          sum +
          (RULES.find((r) => r.id === capability.id)!.query.test(question)
            ? 3
            : 0),
        0,
      );
      const named = query.includes(name.toLowerCase()) ? 8 : 0;
      const relevantRole = capabilities.find((capability) =>
        RULES.find((r) => r.id === capability.id)!.query.test(question),
      );
      return {
        id: source.id,
        name,
        version: source.version,
        role:
          (relevantRole ?? capabilities[0])?.label ?? "Project documentation",
        capabilities,
        score: overview ? capabilities.length : named + roleScore + lexical,
      };
    },
  );
  const questionRules = RULES.filter((rule) => rule.query.test(question));
  const focusedCapability =
    questionRules.length === 1 &&
    (mentions || ["routing", "python"].includes(questionRules[0].id))
      ? questionRules[0].id
      : undefined;
  const links: DocumentRelation[] = [];
  const add = (
    from: ProjectNode,
    to: ProjectNode,
    label: string,
    kind: DocumentRelation["kind"],
    evidence: RelationEvidence[],
  ) => {
    if (!overview && from.score <= 0 && to.score <= 0) return;
    if (
      focusedCapability &&
      (!from.capabilities.some((c) => c.id === focusedCapability) ||
        !to.capabilities.some((c) => c.id === focusedCapability))
    )
      return;
    if (
      links.some(
        (link) =>
          (link.from === from.id && link.to === to.id) ||
          (link.to === from.id && link.from === to.id),
      )
    )
      return;
    links.push({
      id: `${from.id}:${to.id}:${kind}`,
      from: from.id,
      to: to.id,
      label,
      kind,
      evidence,
      score: from.score + to.score + (kind === "explicit" ? 5 : 1),
    });
  };
  // Extract only a few explicit English constructions with a named subject.
  for (const { source, name, rows } of documents) {
    if (names.get(name.toLowerCase()) !== 1) continue;
    const from = nodes.find((node) => node.id === source.id)!;
    for (const row of rows) {
      if (NEGATIVE.test(row.text)) continue;
      for (const to of nodes) {
        if (from.id === to.id || names.get(to.name.toLowerCase()) !== 1)
          continue;
        const subject = escaped(name);
        const historical = new RegExp(
          `(?:\\b${subject}\\b|^It|[.!?] It) (?:began|started|originated) as (?:a )?(?:simple )?wrapper around ([^.!?]+)`,
          "i",
        );
        const direct = new RegExp(
          `\\b${subject}\\b (uses?|depends on|is built on|builds on|integrates with|wraps|is (?:an? )?(?:async(?:io)? )?reimplementation of) ([^.!?]+)`,
          "i",
        );
        const history = row.text.match(historical);
        const relation = row.text.match(direct);
        const target = new RegExp(`\\b${escaped(to.name)}\\b`, "i");
        const ownerContext = new RegExp(`^${subject}\\b`, "i").test(row.text);
        const object = (text: string) =>
          text.split(
            /[,;]|\b(?:while|whereas|but|although|because)\b|\band\s+\w+\s+(?:uses?|is|depends)\b/i,
          )[0];
        const supported = (text: string) =>
          !/\b(?:or|instead|rather|might|may|could|optional|optionally|except|unlike)\b/i.test(
            text,
          ) && target.test(object(text));
        if (history && ownerContext && supported(history[1]))
          add(from, to, "Began as a wrapper around", "explicit", [
            row.evidence,
          ]);
        else if (relation && supported(relation[2])) {
          const verb = relation[1].toLowerCase();
          const label = /reimplementation/.test(verb)
            ? "Reimplementation of"
            : /depends/.test(verb)
              ? "Depends on"
              : /built|builds/.test(verb)
                ? "Built on"
                : /integrates/.test(verb)
                  ? "Integrates with"
                  : /wraps/.test(verb)
                    ? "Wraps"
                    : "Uses";
          add(from, to, label, "explicit", [row.evidence]);
        }
      }
    }
  }
  // Shared capabilities are symmetric and never presented as dependencies.
  for (let i = 0; i < nodes.length; i++)
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i],
        b = nodes[j];
      if (a.name.toLowerCase() === b.name.toLowerCase()) continue;
      const shared = RULES.filter(
        (rule) =>
          rule.shared &&
          (rule.id !== "python" || rule.query.test(question)) &&
          a.capabilities.some((c) => c.id === rule.id) &&
          b.capabilities.some((c) => c.id === rule.id),
      ).sort(
        (x, y) =>
          Number(y.query.test(question)) - Number(x.query.test(question)),
      );
      const rule = shared[0];
      if (rule?.id === "python") {
        const reached = new Set([a.id]);
        for (let pass = 0; pass < nodes.length; pass++)
          for (const link of links.filter(
            (link) => link.label === rule.shared,
          )) {
            if (reached.has(link.from)) reached.add(link.to);
            if (reached.has(link.to)) reached.add(link.from);
          }
        if (reached.has(b.id)) continue;
      }
      if (rule && (overview || rule.query.test(question)))
        add(a, b, rule.shared, "shared", [
          a.capabilities.find((c) => c.id === rule.id)!.evidence,
          b.capabilities.find((c) => c.id === rule.id)!.evidence,
        ]);
    }
  const ranked = nodes
    .filter(
      (node) =>
        !focusedCapability ||
        node.capabilities.some((c) => c.id === focusedCapability),
    )
    .filter(
      (node) =>
        node.score > 0 ||
        links.some((link) => link.from === node.id || link.to === node.id),
    )
    .sort(
      (a, b) =>
        b.score +
          Math.min(
            3,
            links.filter((l) => l.from === b.id || l.to === b.id).length,
          ) -
          (a.score +
            Math.min(
              3,
              links.filter((l) => l.from === a.id || l.to === a.id).length,
            )) ||
        a.name.localeCompare(b.name) ||
        a.id.localeCompare(b.id),
    )
    .slice(0, 6);
  const included = new Set(ranked.map((node) => node.id));
  return {
    ...(literal
      ? ranked.length
        ? {
            mode: "related" as const,
            note: `No literal mention of ${mentions!.terms[0]} was found in the selected sources. Showing related documented capabilities instead.`,
          }
        : { mode: "mentions" as const, note: literal.note }
      : {}),
    nodes: ranked,
    links: links
      .filter((link) => included.has(link.from) && included.has(link.to))
      .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id))
      .slice(0, 8),
  };
}

/** Fixed circular MVP layout, with no animation, overlap or random positions. */
export function circularProjects(nodes: ProjectNode[]) {
  return nodes.map((node, i) => {
    const angle = -Math.PI / 2 + (i * Math.PI * 2) / Math.max(1, nodes.length);
    return {
      ...node,
      x: 450 + 290 * Math.cos(angle),
      y: 340 + 230 * Math.sin(angle),
    };
  });
}

/** Bow edges away from the center so the question never hides connection badges. */
export function relationCurve(
  a: { x: number; y: number },
  b: { x: number; y: number },
) {
  const mx = (a.x + b.x) / 2,
    my = (a.y + b.y) / 2;
  const dx = (b.y - a.y) * 0.6,
    dy = -(b.x - a.x) * 0.6;
  const plus = Math.hypot(mx + dx / 2 - 450, my + dy / 2 - 340);
  const minus = Math.hypot(mx - dx / 2 - 450, my - dy / 2 - 340);
  const sign = plus >= minus ? 1 : -1;
  const cx = mx + sign * dx,
    cy = my + sign * dy;
  return { cx, cy, x: (mx + cx) / 2, y: (my + cy) / 2 };
}
