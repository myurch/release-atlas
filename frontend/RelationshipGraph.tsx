import React, { useMemo, useState } from "react";
import {
  buildDocumentMap,
  circularProjects,
  relationCurve,
  RelationEvidence,
  DocumentMap,
} from "./document-relations";
import type { QuestionGraph } from "./question-graph";
import type { Source } from "./types";

export function RelationshipGraph({
  graph,
  sources,
  openSource,
  reset,
  canAsk = false,
}: {
  canAsk?: boolean;
  graph: QuestionGraph | null;
  sources: Source[];
  openSource: (id: string) => void;
  reset: () => void;
}) {
  const [focus, setFocus] = useState("");
  const question = graph?.question ?? "";
  const centerText = question || "Projects and their roles";
  const centerWords = centerText.split(/\s+/);
  const centerLines = [""];
  for (const word of centerWords) {
    const i = centerLines.length - 1;
    if ((centerLines[i] + " " + word).trim().length > 25 && centerLines[i]) {
      if (centerLines.length === 2) {
        centerLines[1] = centerLines[1].slice(0, 23) + "…";
        break;
      }
      centerLines.push(word.slice(0, 25));
    } else centerLines[i] = (centerLines[i] + " " + word).trim();
  }
  const map = useMemo<DocumentMap>(() => {
    const selected = new Set(graph?.report?.passages.map((p) => p.source_id));
    return graph && !graph.report
      ? { nodes: [], links: [] }
      : buildDocumentMap(
          question,
          graph ? sources.filter((source) => selected.has(source.id)) : sources,
        );
  }, [question, graph?.report, sources, !!graph]);
  const positions = circularProjects(map.nodes);
  const node = map.nodes.find((item) => focus === "node:" + item.id);
  const relation = node
    ? undefined
    : (map.links.find((item) => focus === "edge:" + item.id) ?? map.links[0]);
  const evidence =
    relation?.evidence ??
    node?.capabilities.map((capability) => capability.evidence) ??
    [];
  const uniqueEvidence = [
    ...new Map(
      evidence.map((item) => [item.source_id + ":" + item.start, item]),
    ).values(),
  ].slice(0, 3);
  const name = (id: string) =>
    map.nodes.find((item) => item.id === id)?.name ?? "Project";
  const relevant = (id: string) =>
    node
      ? id === node.id ||
        map.links.some(
          (link) =>
            (link.from === node.id && link.to === id) ||
            (link.to === node.id && link.from === id),
        )
      : relation
        ? relation.from === id || relation.to === id
        : true;
  const quote = (item: RelationEvidence) => {
    const source = sources.find((s) => s.id === item.source_id);
    if (
      !source ||
      source.sha256 !== item.sha256 ||
      Array.from(source.text).slice(item.start, item.end).join("") !==
        item.quote
    )
      return null;
    return (
      <div key={item.source_id + item.start} className="relationship-quote">
        <strong>{source.title}</strong>
        <span className="small muted">{source.version}</span>
        <blockquote>{item.quote}</blockquote>
        <button
          className="citation"
          type="button"
          onClick={() => openSource(source.id)}
        >
          Open source ↗
        </button>
      </div>
    );
  };
  return (
    <section
      className="panel graph-panel relationship-panel"
      aria-label="Documentation relationship map"
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">DOCUMENTATION RELATIONSHIPS</span>
          <h2>
            {map.mode === "mentions"
              ? "Where your question appears"
              : "How these projects fit together"}
          </h2>
        </div>
        {graph && (
          <button className="button" onClick={reset}>
            Show documentation overview
          </button>
        )}
      </div>
      <p className="relationship-question">
        {question ||
          "Explore the roles and supported connections in your documentation."}
      </p>
      <p className="small muted" role="status">
        {graph?.phase === "loading"
          ? "Waiting for source selection…"
          : graph?.phase === "error"
            ? graph.report
              ? "The answer could not finish. Its selected-source map is still available."
              : "Source selection could not finish. Try the question again."
            : `${map.nodes.length} ${map.mode === "mentions" ? "sources" : "projects"} · ${map.links.length} supported connections`}
      </p>
      {map.note && (
        <p className="small muted" role="status">
          {map.note}
        </p>
      )}
      {!map.nodes.length ? (
        <div className="empty">
          {graph?.phase === "loading"
            ? "The map will appear when Ask Atlas selects sources."
            : sources.length
              ? map.mode === "mentions"
                ? "No matching sources in this selection."
                : "No supported project relationships or roles match this question."
              : "Add documentation in Sources to explore project relationships."}
        </div>
      ) : (
        <div className="relationship-layout">
          <div>
            <div className="relationship-scroll">
              <svg
                className="relationship-canvas"
                viewBox="0 0 900 680"
                role="group"
                aria-label="Circular project relationship map. Select a project or a numbered connection; the readable list follows."
              >
                <circle
                  className="relationship-orbit"
                  cx="450"
                  cy="340"
                  r="235"
                />
                {map.links.map((link, index) => {
                  const a = positions.find((item) => item.id === link.from)!;
                  const b = positions.find((item) => item.id === link.to)!;
                  const { cx, cy, x, y } = relationCurve(a, b);
                  const active = node
                    ? link.from === node.id || link.to === node.id
                    : relation?.id === link.id;
                  const choose = () => setFocus("edge:" + link.id);
                  return (
                    <g
                      key={link.id}
                      className={`relationship-edge ${link.kind} ${active ? "active" : "dim"}`}
                    >
                      <path d={`M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`} />
                      <g
                        role="button"
                        tabIndex={0}
                        aria-label={`${name(link.from)}: ${link.label}: ${name(link.to)}`}
                        aria-pressed={active}
                        onClick={choose}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            choose();
                          }
                        }}
                      >
                        <title>
                          {name(link.from)} · {link.label} · {name(link.to)}
                        </title>
                        <circle cx={x} cy={y} r="16" />
                        <text x={x} y={y + 5} textAnchor="middle">
                          {index + 1}
                        </text>
                      </g>
                    </g>
                  );
                })}
                <g className="relationship-center">
                  <rect x="345" y="286" width="210" height="108" rx="24" />
                  <text x="450" y="319" textAnchor="middle">
                    {question ? "YOUR QUESTION" : "DOCUMENTATION"}
                  </text>
                  <text
                    x="450"
                    y="349"
                    textAnchor="middle"
                    className="relationship-center-title"
                  >
                    {question
                      ? "Relevant project roles"
                      : "Projects and their roles"}
                  </text>
                  <text x="450" y="374" textAnchor="middle">
                    Select a connection to inspect
                  </text>
                </g>
                {positions.map((item) => (
                  <g
                    key={item.id}
                    className={`relationship-node ${item.capabilities[0]?.id ?? "other"} ${relevant(item.id) ? "" : "dim"}`}
                    role="button"
                    tabIndex={0}
                    aria-label={`Inspect ${item.name}: ${item.role}`}
                    aria-pressed={node?.id === item.id}
                    onClick={() => setFocus("node:" + item.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setFocus("node:" + item.id);
                      }
                    }}
                  >
                    <title>
                      {item.name} · {item.role} · {item.version}
                    </title>
                    <rect
                      x={item.x - 106}
                      y={item.y - 38}
                      width="212"
                      height="76"
                      rx="22"
                    />
                    <text
                      x={item.x}
                      y={item.y - 12}
                      textAnchor="middle"
                      className="relationship-node-name"
                    >
                      {item.name.slice(0, 24)}
                    </text>
                    <text x={item.x} y={item.y + 9} textAnchor="middle">
                      {item.role.length > 27
                        ? item.role.slice(0, 26) + "…"
                        : item.role}
                    </text>
                    <text
                      className="relationship-node-version"
                      x={item.x}
                      y={item.y + 29}
                      textAnchor="middle"
                    >
                      {item.version.length > 25
                        ? item.version.slice(0, 24) + "…"
                        : item.version}
                    </text>
                  </g>
                ))}
              </svg>
            </div>
            <p className="small muted">
              Solid: an explicit statement. Dashed: a shared capability. Dotted:
              a shared text mention. Numbers match the connections below.
            </p>
            <div
              className="relationship-list"
              aria-label="Supported relationships"
            >
              {map.links.map((link, index) => (
                <button
                  type="button"
                  key={link.id}
                  className="relationship-choice"
                  aria-pressed={relation?.id === link.id}
                  onClick={() => setFocus("edge:" + link.id)}
                >
                  <span className="relationship-number">{index + 1}</span>
                  <span>
                    <strong>
                      {name(link.from)} · {name(link.to)}
                    </strong>
                    <span>
                      {link.kind === "explicit"
                        ? `${name(link.from)} ${link.label.toLowerCase()} ${name(link.to)}`
                        : link.label}
                    </span>
                  </span>
                </button>
              ))}
            </div>
            {!map.links.length && (
              <p className="small muted">
                {map.mode === "mentions"
                  ? map.nodes.length === 1
                    ? "One source matches. A shared text-mention link needs at least two sources."
                    : "These matched sources do not share a query term."
                  : "Project roles were found, but no supported cross-project relationship matches. A shared keyword alone does not create a link."}
              </p>
            )}
          </div>
          <aside
            className="relationship-detail"
            aria-label="Relationship evidence"
          >
            <span className="eyebrow">WHY THIS CONNECTION?</span>
            <h3>
              {node
                ? node.name
                : relation
                  ? `${name(relation.from)} · ${name(relation.to)}`
                  : "Project role"}
            </h3>
            <p>
              {node?.role ??
                (relation
                  ? relation.kind === "explicit"
                    ? `${name(relation.from)} ${relation.label.toLowerCase()} ${name(relation.to)}.`
                    : relation.label
                  : undefined) ??
                "Select a project to inspect its documented role."}
            </p>
            {relation && (
              <p className="small muted">
                {relation.kind === "mention"
                  ? "Both excerpts contain the query term. It may occur in a link or example; this does not establish a feature, dependency or security guarantee."
                  : relation.kind === "shared"
                    ? "Both documents describe this capability. This does not establish integration between the projects."
                    : "An explicit statement in the documentation. Historical wording is preserved; it does not prove a current dependency."}
              </p>
            )}
            {uniqueEvidence.map(quote)}
            {node && (
              <button
                className="button"
                type="button"
                onClick={() => openSource(node.id)}
              >
                Open full source
              </button>
            )}
          </aside>
        </div>
      )}
      <p className="small muted">
        Independent, local English text rules; up to six projects and eight
        connections.{" "}
        {graph
          ? "Uses only the sources selected for this question. "
          : canAsk
            ? "Uses saved source text. Send a Model chat question in Ask Atlas on this page to focus the map. "
            : "Uses saved source text. "}
        Read the quotes before relying on a connection.
      </p>
    </section>
  );
}
