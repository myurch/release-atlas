import React from "react";
import { RetrievalReport } from "./retrieval";
import { Source } from "./types";

export function RetrievedContext({
  report,
  sources,
  openSource,
}: {
  report: RetrievalReport;
  sources: Source[];
  openSource: (id: string) => void;
}) {
  return (
    <details className="chat-retrieval">
      <summary>
        Retrieved context · {report.included_sources} sources ·{" "}
        {report.passages.length} passages
      </summary>
      <p className="small">
        <strong>
          {report.encoder === "neural-minilm"
            ? "Local semantic encoder: MiniLM"
            : "Statistical fallback: TF-IDF / LSA"}
        </strong>
        <br />
        {report.mode === "overview"
          ? "Coverage-oriented source overview"
          : "Question-focused hybrid retrieval"}{" "}
        · {report.candidate_count} indexed passages
      </p>
      <p className="small muted">
        NLP signals: structural text matching, embedding similarity,
        documentation-purpose classification, NMF topic preferences and typed
        technical entities. Reasons below describe selection, not proof that a
        passage answers your question.
      </p>
      {report.fallback && <p className="chat-caution">{report.fallback}</p>}
      {report.partial && (
        <p className="small muted">
          Only selected passages were supplied. This answer did not receive all
          saved source text.
        </p>
      )}
      {report.notices.map((notice, i) => (
        <p className="small muted" key={i}>
          {notice}
        </p>
      ))}
      {!report.passages.length && (
        <p className="small">
          No sufficiently relevant passages were found within the requested
          scope. Try a more specific question or select a source.
        </p>
      )}
      {report.passages.map((p) => {
        const source = sources.find(
          (s) => s.id === p.source_id && s.sha256 === p.sha256,
        );
        return (
          <details className="chat-retrieval-passage" key={p.id}>
            <summary>
              {source?.title || "Source no longer current"}
              {source ? ` (${source.version})` : ""}
            </summary>
            <div className="chips">
              {p.reasons.map((reason) => (
                <span className="badge neutral" key={reason}>
                  {reason}
                </span>
              ))}
            </div>
            <blockquote>{p.quote}</blockquote>
            <p className="small muted">
              Characters {p.start + 1}–{p.end}. Context used for this answer,
              whether or not the model cited it.
            </p>
            <button
              type="button"
              className="citation"
              disabled={!source}
              onClick={() => openSource(p.source_id)}
            >
              Open source ↗
            </button>
          </details>
        );
      })}
    </details>
  );
}
