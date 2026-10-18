import React, { useState } from "react";
import { Claim, purposes, Workspace } from "./types";
import {
  emptyPassageFilters,
  PassageFilters,
  sectionKey,
  technicalInventory,
} from "./pipeline";

const human = (value: string) => value.replaceAll("-", " ");
const stages = [
  ["structure", "Text analytics", "Structure, sections and exact passages"],
  ["purposes", "Embedding classification", "What each passage helps you do"],
  ["topics", "Topic modeling", "Subjects discovered across prose"],
  ["entities", "Technical entities", "Interfaces and commands in context"],
] as const;

export function PipelineExplorer({
  workspace,
  filters,
  setFilters,
  openPassage,
}: {
  workspace: Workspace;
  filters: PassageFilters;
  setFilters: (value: PassageFilters) => void;
  openPassage: (id: string) => void;
}) {
  const [stage, setStage] = useState<string>("structure");
  const [entitySearch, setEntitySearch] = useState("");
  const summary = workspace.analysis?.pipeline;
  const inventory = technicalInventory(workspace);
  const counts = [
    summary?.passages || 0,
    new Set(workspace.claims.map((c) => c.document?.purpose).filter(Boolean))
      .size,
    workspace.topics.length,
    inventory.length,
  ];
  const change = (key: keyof PassageFilters, value: string | number | null) =>
    setFilters({ ...filters, [key]: value });
  return (
    <section
      className="panel nlp-pipeline"
      aria-label="Documentation NLP pipeline"
    >
      <div className="section-heading">
        <div>
          <span className="eyebrow">DOCUMENTATION NLP PIPELINE</span>
          <h2>From source text to useful evidence.</h2>
        </div>
        <span className="badge neutral">
          {summary ? "Local statistical NLP" : "Analysis needed"}
        </span>
      </div>
      <p className="muted">
        Parse meaningful passages, classify their purpose, discover subjects and
        extract technical interfaces. Every result leads back to exact source
        text.
      </p>
      <div
        className="pipeline-stages"
        role="group"
        aria-label="Explore NLP stages"
      >
        {stages.map(([id, title, description], i) => (
          <button
            key={id}
            type="button"
            aria-pressed={stage === id}
            className={"pipeline-stage " + (stage === id ? "selected" : "")}
            onClick={() => setStage(id)}
          >
            <span className="eyebrow">0{i + 1}</span>
            <strong>{title}</strong>
            <span>{description}</span>
            <b>{summary ? counts[i] : "…"}</b>
          </button>
        ))}
      </div>
      {!summary ? (
        <p className="small">
          Run Analyze sources to build the documentation pipeline. Older
          snapshots keep their original evidence and can be reanalyzed in the
          live app.
        </p>
      ) : (
        <>
          <div className="pipeline-stats">
            <span>{summary.sources} sources</span>
            <span>{summary.words.toLocaleString()} words</span>
            <span>{summary.sections} section paths</span>
            <span>{summary.code_blocks} code blocks</span>
            <span>{summary.entity_mentions} entity mentions</span>
          </div>
          {stage === "structure" && (
            <div className="pipeline-stage-content">
              <h3>Document map</h3>
              <p className="small muted">
                Markdown and reStructuredText blocks retain headings, wrapped
                paragraphs, list continuations, code and tables. Select a
                section to filter passages.
              </p>
              <div className="pipeline-scroll">
                {workspace.sources.map((source) => (
                  <div className="document-map" key={source.id}>
                    <button
                      type="button"
                      className="source-link"
                      aria-pressed={
                        filters.source === source.id && !filters.section
                      }
                      onClick={() =>
                        setFilters({
                          ...filters,
                          source: source.id,
                          section: "",
                        })
                      }
                    >
                      {source.title} <span>{source.version}</span>
                    </button>
                    {[
                      ...new Map(
                        workspace.claims
                          .filter((c) => c.source_id === source.id)
                          .map((c) => [sectionKey(c), c]),
                      ).entries(),
                    ].map(([key, claim]) => (
                      <button
                        key={key}
                        className="map-section"
                        type="button"
                        aria-pressed={
                          filters.source === source.id &&
                          filters.section === key
                        }
                        onClick={() =>
                          setFilters({
                            ...filters,
                            source: source.id,
                            section: key,
                          })
                        }
                      >
                        <span>
                          {claim.document?.headings.join(" › ") ||
                            "Document body"}
                        </span>
                        <span>
                          {
                            workspace.claims.filter(
                              (c) =>
                                c.source_id === source.id &&
                                sectionKey(c) === key,
                            ).length
                          }{" "}
                          passages
                        </span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}
          {stage === "purposes" && (
            <div className="pipeline-stage-content">
              <h3>What can you learn here?</h3>
              <p className="small muted">
                Predefined purposes, predicted using{" "}
                {summary.embedding_dimensions}-dimensional TF-IDF / LSA
                embeddings and logistic regression trained on{" "}
                {summary.training_examples} synthetic examples. These are
                statistical embeddings, not a pretrained language model. Inspect
                a passage for competing labels and nearby examples.
              </p>
              <div className="purpose-grid">
                {purposes.map((purpose) => {
                  const count = workspace.claims.filter(
                    (c) => c.document?.purpose === purpose,
                  ).length;
                  return (
                    count > 0 && (
                      <button
                        className="purpose-row"
                        type="button"
                        key={purpose}
                        aria-pressed={filters.purpose === purpose}
                        onClick={() => change("purpose", purpose)}
                      >
                        <span>{human(purpose)}</span>
                        <meter
                          min={0}
                          max={workspace.claims.length}
                          value={count}
                          aria-label={`${purpose} passage count`}
                        />
                        <strong>{count}</strong>
                      </button>
                    )
                  );
                })}
              </div>
              <p className="small muted">
                “Other” means the classifier abstained. Purpose scores are
                uncalibrated; inspect the passage before relying on its label.
              </p>
            </div>
          )}
          {stage === "topics" && (
            <div className="pipeline-stage-content">
              <h3>Subjects discovered in this corpus</h3>
              <p className="small muted">
                NMF learns weighted word patterns from prose. Subjects are
                separate from predefined purposes. Labels below are actual top
                terms, not generated summaries. Code blocks are excluded.
              </p>
              <div className="pipeline-topic-grid">
                {workspace.topics.map((topic) => (
                  <article className="pipeline-topic" key={topic.id}>
                    <button
                      type="button"
                      className="source-link"
                      aria-pressed={filters.topic === topic.id}
                      onClick={() => change("topic", topic.id)}
                    >
                      <strong>{topic.terms.slice(0, 3).join(" · ")}</strong>
                    </button>
                    <span className="small muted">
                      {topic.count} passages · {topic.source_count ?? "?"}{" "}
                      sources
                    </span>
                    <div className="topic-terms">
                      {topic.terms.map((term, i) => (
                        <span key={term}>
                          {term}
                          <meter
                            min={0}
                            max={1}
                            value={topic.weights?.[i] || 0}
                            aria-label={`${term} relative term weight`}
                          />
                        </span>
                      ))}
                    </div>
                    <p className="small">Representative passages</p>
                    {topic.representatives?.map((id) => {
                      const claim = workspace.claims.find((c) => c.id === id);
                      return (
                        claim && (
                          <button
                            type="button"
                            className="topic-example"
                            key={id}
                            onClick={() => openPassage(id)}
                          >
                            {claim.quote.slice(0, 180)}
                            {claim.quote.length > 180 ? "…" : ""}
                          </button>
                        )
                      );
                    })}
                  </article>
                ))}
              </div>
              {!workspace.topics.length && (
                <p role="status">
                  Not enough varied prose to discover useful topics. Add more
                  documentation; the pipeline does not force a topic for every
                  source.
                </p>
              )}
            </div>
          )}
          {stage === "entities" && (
            <div className="pipeline-stage-content">
              <h3>Technical inventory</h3>
              <p className="small muted">
                Syntax rules identify APIs, configuration keys, commands,
                endpoints, packages and protocols. Exact spelling and source
                positions are preserved. Types are candidates, not verified API
                contracts.
              </p>
              <label>
                Filter technical inventory
                <input
                  value={entitySearch}
                  onChange={(e) => setEntitySearch(e.target.value)}
                  placeholder="Find an API, command or setting…"
                />
              </label>
              <div className="pipeline-scroll inventory-list">
                {inventory
                  .filter((row) =>
                    (row.name + " " + row.kind)
                      .toLowerCase()
                      .includes(entitySearch.toLowerCase()),
                  )
                  .map((row) => (
                    <button
                      type="button"
                      key={row.key}
                      className="inventory-row"
                      aria-pressed={filters.entity === row.key}
                      onClick={() => change("entity", row.key)}
                    >
                      <code>{row.name}</code>
                      <span className="badge neutral">{row.kind}</span>
                      <span>
                        {row.mentions} mentions · {row.passageIds.size} passages
                        · {row.sourceIds.size} sources
                      </span>
                      <small>Rule: {[...row.rules].join(", ")}</small>
                    </button>
                  ))}
              </div>
              {!inventory.length && (
                <p>
                  No technical syntax was found. Ordinary prose is still
                  analyzed.
                </p>
              )}
            </div>
          )}
          <details className="pipeline-method">
            <summary>Methods and limits</summary>
            {summary.evaluation && (
              <div className="pipeline-evaluation">
                <h3>Measured on held-out synthetic documentation</h3>
                <p className="small">
                  {summary.evaluation.held_out_examples} examples · Purpose
                  macro-F1 {summary.evaluation.macro_f1.toFixed(2)} · Keyword
                  baseline {summary.evaluation.keyword_macro_f1.toFixed(2)}
                </p>
                <p className="small muted">
                  Training and evaluation wording are separate, but share an
                  author and domain. This small benchmark is not evidence of
                  real-world accuracy. Scores describe the model recorded with
                  this analysis, not the quality of this workspace's labels.
                </p>
              </div>
            )}
            {summary.notices.map((notice) => (
              <p className="small" key={notice}>
                {notice}
              </p>
            ))}
            <p className="small">
              No generation API is used for analysis. Headings help classify
              purpose but do not define discovered topics. Adding sources or
              changing usage requires fresh analysis. Older human reviews
              survive only when their exact passage identity survives.
            </p>
          </details>
        </>
      )}
      <div
        className="pipeline-active-filters"
        aria-label="Active passage filters"
      >
        {Object.entries(filters)
          .filter(([, v]) => v !== "" && v !== null)
          .map(([key, value]) => (
            <button
              type="button"
              className="button"
              key={key}
              onClick={() =>
                change(key as keyof PassageFilters, key === "topic" ? null : "")
              }
            >
              Clear {key}:{" "}
              {key === "section"
                ? "selected section"
                : key === "source"
                  ? workspace.sources.find((s) => s.id === value)?.title
                  : String(value)}{" "}
              ×
            </button>
          ))}
        {Object.values(filters).some((v) => v !== "" && v !== null) && (
          <button
            type="button"
            className="button"
            onClick={() => setFilters(emptyPassageFilters())}
          >
            Clear pipeline filters
          </button>
        )}
      </div>
    </section>
  );
}

export function PassageMethods({ claim }: { claim: Claim }) {
  const doc = claim.document;
  if (!doc) return null;
  return (
    <div className="passage-methods">
      <div className="chips">
        <span className="badge neutral">{human(doc.purpose)}</span>
        <span className="badge neutral">{doc.kind}</span>
        <span className="small muted">
          {doc.words} words · {doc.sentences} sentence endings
        </span>
      </div>
      <details>
        <summary>Inspect NLP classification and entities</summary>
        <h3>Competing purpose labels</h3>
        {doc.alternatives.map((row) => (
          <div className="purpose-row" key={row.label}>
            <span>{human(row.label)}</span>
            <meter
              min={0}
              max={1}
              value={row.score}
              aria-label={`${row.label} model score`}
            />
            <span>{row.score.toFixed(2)}</span>
          </div>
        ))}
        <p className="small muted">
          Uncalibrated model scores, not confidence percentages. Nearby training
          examples below show embedding similarity, not causal feature
          importance.
        </p>
        {doc.examples.map((example) => (
          <div className="classification-example" key={example.text}>
            <span className="small">
              {human(example.label)} · cosine {example.similarity.toFixed(2)}
            </span>
            <blockquote>{example.text}</blockquote>
          </div>
        ))}
        <h3>Exact technical mentions</h3>
        {doc.mentions.map((mention, i) => (
          <p className="small" key={i}>
            <code>{mention.name}</code> · {mention.kind} · {mention.rule} ·
            characters {mention.start + 1}–{mention.end}
          </p>
        ))}
        {!doc.mentions.length && (
          <p className="small">
            No technical syntax matched the extraction rules.
          </p>
        )}
        <p className="small muted">
          {doc.topic_strength > 0
            ? `Primary topic share: ${doc.topic_strength.toFixed(2)} of this passage's NMF weight. This is not a probability.`
            : "No topic assigned, including code blocks and passages without usable topic vocabulary."}
        </p>
      </details>
    </div>
  );
}
