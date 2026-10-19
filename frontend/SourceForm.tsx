import React, { useEffect, useRef, useState } from "react";
import {
  applyReadmeDraft,
  emptySourceDraft,
  readmeFailureMessage,
  ReadmePreview,
  SourceDraft,
  validateReadmePreview,
} from "./readme";

export function SourceForm({
  disabled,
  revision,
  save,
  fetchReadme,
  importDemo,
}: {
  disabled: boolean;
  revision: number;
  save: (source: Record<string, string>) => Promise<boolean>;
  importDemo?: () => Promise<void>;
  fetchReadme?: (
    url: string,
    revision: number,
    signal: AbortSignal,
  ) => Promise<unknown>;
}) {
  const [draft, setDraft] = useState<SourceDraft>(emptySourceDraft);
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [fetching, setFetching] = useState(false);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const importRef = useRef(false);
  const savingRef = useRef(false);
  const readmeDetails = useRef<HTMLDetailsElement>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<ReadmePreview | null>(null);
  const edits = useRef(0);
  const sequence = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const current = useRef({ revision, enabled: !disabled && !!fetchReadme });
  current.current = { revision, enabled: !disabled && !!fetchReadme };
  const draftRef = useRef(draft);
  draftRef.current = draft;
  useEffect(
    () => () => {
      sequence.current++;
      controller.current?.abort();
    },
    [],
  );

  function edit(field: keyof SourceDraft, value: string) {
    edits.current++;
    setDraft((previous) => ({ ...previous, [field]: value }));
  }
  function apply(value: ReadmePreview) {
    if (
      !current.current.enabled ||
      current.current.revision !== value.revision
    ) {
      setError(
        "The workspace changed. Fetch the README again; your draft is unchanged.",
      );
      return;
    }
    setDraft((previous) => applyReadmeDraft(previous, value));
    edits.current++;
    setPreview(null);
    setMessage(
      `README loaded from ${value.repository} at commit ${value.commit.slice(0, 12)}. Review Source text, then choose Save source. Nothing has been saved yet.`,
    );
  }
  async function load() {
    if (
      !fetchReadme ||
      !current.current.enabled ||
      fetching ||
      controller.current
    )
      return;
    const request = new AbortController();
    controller.current = request;
    const run = ++sequence.current;
    const startedAtEdit = edits.current;
    const expected = revision;
    setFetching(true);
    setError("");
    setMessage("");
    setPreview(null);
    const timer = setTimeout(() => request.abort(), 25000);
    try {
      const raw = await fetchReadme(
        repositoryUrl.trim(),
        expected,
        request.signal,
      );
      if (run !== sequence.current || !current.current.enabled) return;
      if (current.current.revision !== expected)
        throw new Error(
          "The workspace changed. Fetch the README again; your draft is unchanged.",
        );
      const value = validateReadmePreview(raw, expected);
      if (draftRef.current.text.length || edits.current !== startedAtEdit) {
        setPreview(value);
        setMessage(
          "README fetched. Your existing draft has been kept. Review the fetched text below and choose whether to replace Source text.",
        );
      } else apply(value);
    } catch (reason) {
      if (run === sequence.current && current.current.enabled)
        setError(readmeFailureMessage(reason));
    } finally {
      clearTimeout(timer);
      if (run === sequence.current) {
        setFetching(false);
        controller.current = null;
      }
    }
  }

  async function submit() {
    if (disabled || fetching || preview || savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    setError("");
    try {
      const saved = await save({
        ...draft,
        license: "User supplied; verify redistribution rights",
      });
      if (!saved) return;
      edits.current++;
      sequence.current++;
      setDraft(emptySourceDraft());
      setRepositoryUrl("");
      setPreview(null);
      setMessage("");
      setError("");
      if (readmeDetails.current) readmeDetails.current.open = false;
    } catch {
      setError(
        "Could not save the source. Your draft is unchanged; try again.",
      );
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  }

  return (
    <section className="panel source-form">
      <h2>Add Evidence</h2>
      {importDemo && (
        <div className="source-demo-import">
          <button
            type="button"
            className="button full"
            disabled={disabled || saving || fetching || importing}
            onClick={async () => {
              if (disabled || importRef.current) return;
              importRef.current = true;
              setImporting(true);
              try {
                await importDemo();
              } finally {
                importRef.current = false;
                setImporting(false);
              }
            }}
          >
            {importing
              ? "Importing demo documents…"
              : "Import mock data for demo purposes"}
          </button>
          <p className="small muted">
            Adds six fictional documents: LumenUI frontend and HarborAPI
            backend, each at versions 1.0, 2.0 and 3.0. Includes shared APIs,
            migrations and one deliberate documentation disagreement. No network
            requests. Existing sources stay; identical demo documents are
            skipped.
          </p>
        </div>
      )}
      {fetchReadme && (
        <details ref={readmeDetails} className="source-readme">
          <summary>Fetch a public GitHub README</summary>
          <p className="small muted">
            Load the repository README into the draft below. Fetching does not
            save a source. Public GitHub repositories only.
          </p>
          <label>
            Public GitHub repository URL
            <input
              type="url"
              maxLength={1000}
              placeholder="https://github.com/owner/repository"
              value={repositoryUrl}
              disabled={disabled || saving || fetching}
              onChange={(event) => {
                setRepositoryUrl(event.target.value);
                setPreview(null);
                setMessage("");
                setError("");
              }}
            />
          </label>
          <button
            type="button"
            className="button"
            data-help="fetchReadme"
            disabled={disabled || saving || fetching || !repositoryUrl.trim()}
            onClick={() => void load()}
          >
            {fetching ? "Fetching README…" : "Fetch README"}
          </button>
          <p className="small muted">
            Up to 12,000 characters. Title and version are suggested when blank.
          </p>
        </details>
      )}
      {error && (
        <p className="chat-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="small" role="status">
          {message}
        </p>
      )}
      {preview && (
        <div className="chat-source-action">
          <strong>
            {preview.repository}: {preview.path}
          </strong>
          <p>
            Commit {preview.commit.slice(0, 12)}. Your current text will be
            replaced only if you choose Replace source text.
          </p>
          <details>
            <summary>Review fetched README</summary>
            <blockquote>{preview.source.text}</blockquote>
          </details>
          {preview.revision !== revision && (
            <p>The workspace changed. Fetch the README again.</p>
          )}
          <button
            type="button"
            className="button"
            disabled={disabled || saving || preview.revision !== revision}
            onClick={() => apply(preview)}
          >
            Replace source text
          </button>{" "}
          <button
            type="button"
            className="button"
            disabled={disabled || saving}
            onClick={() => {
              setPreview(null);
              setMessage("Kept your current draft. No source was saved.");
            }}
          >
            Keep current draft
          </button>
        </div>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label>
          Source title
          <input
            name="title"
            required
            maxLength={160}
            placeholder="Library 2.0 release notes"
            disabled={disabled || saving}
            value={draft.title}
            onChange={(event) => edit("title", event.target.value)}
          />
        </label>
        <div className="form-columns">
          <label>
            Version
            <input
              name="version"
              required
              maxLength={80}
              placeholder="2.0"
              disabled={disabled || saving}
              value={draft.version}
              onChange={(event) => edit("version", event.target.value)}
            />
          </label>
          <label>
            Source URL (optional)
            <input
              name="url"
              type="url"
              maxLength={1000}
              placeholder="https://…"
              disabled={disabled || saving}
              value={draft.url}
              onChange={(event) => edit("url", event.target.value)}
            />
          </label>
        </div>
        <p className="small muted">
          {fetchReadme
            ? "Source URL is a reference link. To load text from GitHub, use Fetch README above."
            : "Source URL is a reference link. Paste the document into Source text."}
        </p>
        <label>
          Source text
          <textarea
            name="text"
            required
            maxLength={12000}
            rows={7}
            placeholder="Paste release notes or documentation. Keep headings, paragraphs, lists and code blocks intact."
            disabled={disabled || saving}
            value={draft.text}
            onChange={(event) => edit("text", event.target.value)}
          />
        </label>
        <button
          className="button primary full"
          disabled={disabled || saving || fetching || !!preview}
        >
          {saving ? "Saving source…" : "Save source"}
        </button>
        <p className="small muted">
          Source text stays in this workspace and its exports. Limit: 12,000
          characters per source.
        </p>
      </form>
    </section>
  );
}
