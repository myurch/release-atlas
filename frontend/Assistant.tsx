import { AssistantStreamError, readAssistantReply } from "./assistant-stream";
import { QuestionGraphEvent } from "./question-graph";
import React, { useEffect, useRef, useState } from "react";
import { Workspace } from "./types";
import { guideReply } from "./guide";
import { RetrievalReport, validatedRetrieval } from "./retrieval";
import { RetrievedContext } from "./RetrievedContext";
import { SourcePassage, validatedSourcePassages } from "./source-citations";
import {
  SourceAction,
  sourceActionItems,
  sourceActionLabel,
  validatedSourceAction,
} from "./source-actions";

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  citations?: string[];
  sourcePassages?: SourcePassage[];
  uncertainty?: string;
  guide?: boolean;
  sourceAction?: SourceAction;
  retrieval?: RetrievalReport;
};
export function Assistant({
  workspace,
  page,
  claimId,
  sourceId,
  live,
  provider,
  navigate,
  openClaim,
  openSource,
  onAuthExpired,
  refresh,
  blocked = false,
  onQuestionGraph,
}: {
  workspace: Workspace;
  page: string;
  claimId: string;
  sourceId: string;
  live: boolean;
  provider: string;
  navigate: (
    page:
      "Overview" | "Sources" | "Evidence" | "Graph" | "Questions" | "Activity",
  ) => void;
  openClaim: (id: string) => void;
  openSource: (id: string) => void;
  onAuthExpired: () => void;
  refresh: () => Promise<unknown>;
  blocked?: boolean;
  onQuestionGraph?: (event: QuestionGraphEvent) => void;
}) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState(live ? "model" : "guide");
  const [pending, setPending] = useState(false);
  const [applying, setApplying] = useState(false);
  const actionInFlight = useRef(false);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const transcript = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const current = useRef({
    revision: workspace.revision,
    live,
    blocked,
    page,
    onQuestionGraph,
  });
  current.current = {
    revision: workspace.revision,
    live,
    blocked,
    page,
    onQuestionGraph,
  };
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  const stop = () => {
    current.current.onQuestionGraph?.(null);
    sequence.current++;
    abort.current?.abort();
    abort.current = null;
    setPending(false);
  };
  useEffect(
    () => () => {
      sequence.current++;
      abort.current?.abort();
    },
    [],
  );
  useEffect(() => {
    if (pending) {
      stop();
      setError(
        "The workspace changed. Your question is kept below; send it again with the current context.",
      );
    }
  }, [workspace.revision]);
  useEffect(() => {
    if (blocked || !live) stop();
  }, [blocked, live]);
  useEffect(() => {
    if (!open || blocked) return;
    input.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (
        e.key === "Escape" &&
        !(e.target as Element).closest("[role=tooltip]")
      ) {
        e.preventDefault();
        close();
      }
    };
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, [open, blocked]);
  useEffect(() => {
    if (transcript.current)
      transcript.current.scrollTop = transcript.current.scrollHeight;
  }, [turns, pending]);
  async function send(text = draft) {
    const message = text.trim();
    if (!message || pending || actionInFlight.current || message.length > 2000)
      return;
    setError("");
    const previous = turns
      .slice(-10)
      .map(({ role, content }) => ({ role, content }));
    const user: ChatTurn = { role: "user", content: message };
    setTurns((t) => [...t.slice(-38), user]);
    if (mode === "guide" || !live) {
      if (page === "Graph") current.current.onQuestionGraph?.(null);
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: guideReply(page, workspace, message, !live),
          guide: true,
        },
      ]);
      setDraft("");
      return;
    }
    setDraft(message);
    const controller = new AbortController();
    abort.current = controller;
    const run = ++sequence.current,
      revision = workspace.revision;
    setPending(true);
    let graphReport: RetrievalReport | undefined;
    const graphRequest = page === "Graph";
    const graphEvent = (
      phase: "loading" | "ready" | "error",
      report?: RetrievalReport,
    ) => {
      if (
        graphRequest &&
        run === sequence.current &&
        current.current.live &&
        !current.current.blocked &&
        current.current.revision === revision
      )
        current.current.onQuestionGraph?.({
          requestId: run,
          revision,
          question: message,
          phase,
          report,
        });
    };
    graphEvent("loading");
    try {
      const response = await fetch("/api/assistant", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(graphRequest ? { Accept: "application/x-ndjson" } : {}),
        },
        signal: controller.signal,
        body: JSON.stringify({
          revision,
          page,
          selected_claim: claimId,
          selected_source: sourceId,
          message,
          history: previous,
        }),
      });
      const value = await readAssistantReply(response, (event) => {
        if (
          run !== sequence.current ||
          !current.current.live ||
          current.current.blocked ||
          current.current.revision !== revision
        )
          return;
        if (event.revision !== revision)
          throw new Error("The workspace changed. Send your question again.");
        graphReport = validatedRetrieval(event.retrieval, workspace.sources);
        if (!graphReport)
          throw new Error("The retrieved context could not be verified.");
        graphEvent("ready", graphReport);
      });
      if (
        run !== sequence.current ||
        !current.current.live ||
        current.current.blocked ||
        current.current.revision !== revision
      )
        return;
      if (!response.ok) {
        if (response.status === 401) onAuthExpired();
        if (response.status === 409) void refresh();
        throw new Error(
          typeof value.detail === "string"
            ? value.detail
            : "The assistant could not answer. Try again or use App guide.",
        );
      }
      if (
        value.revision !== revision ||
        typeof value.answer !== "string" ||
        !Array.isArray(value.citations) ||
        value.citations.some(
          (id: string) => !workspace.claims.some((c) => c.id === id),
        )
      )
        throw new Error(
          "The assistant response could not be verified. Try again.",
        );
      const sourcePassages = validatedSourcePassages(
        value.source_passages ?? [],
        value.source_citations ?? [],
        workspace.sources,
      );
      const retrieval = validatedRetrieval(value.retrieval, workspace.sources);
      if (
        graphReport &&
        JSON.stringify(graphReport) !== JSON.stringify(retrieval)
      )
        throw new Error(
          "The assistant context changed unexpectedly. Try the question again.",
        );
      const sourceAction = validatedSourceAction(
        value.source_action,
        workspace,
      );
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: value.answer,
          citations: value.citations,
          sourcePassages,
          uncertainty: value.uncertainty,
          sourceAction,
          retrieval,
        },
      ]);
      setDraft("");
      graphEvent("ready", retrieval);
    } catch (e) {
      if (run === sequence.current && (e as Error).name !== "AbortError") {
        if (e instanceof AssistantStreamError && e.status === 401)
          onAuthExpired();
        if (e instanceof AssistantStreamError && e.status === 409)
          void refresh();
        setError((e as Error).message);
        graphEvent("error", graphReport);
      }
    } finally {
      if (run === sequence.current) {
        setPending(false);
        abort.current = null;
      }
    }
  }
  async function applySourceAction(index: number, action: SourceAction) {
    if (
      actionInFlight.current ||
      pending ||
      !live ||
      blocked ||
      current.current.revision !== action.revision
    )
      return;
    actionInFlight.current = true;
    setApplying(true);
    setError("");
    try {
      const response = await fetch("/api/assistant/source-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          revision: action.revision,
          token: action.token,
          source_ids: sourceActionItems(action).map((item) => item.source_id),
        }),
      });
      const value = await response.json();
      if (!response.ok) {
        if (response.status === 401) onAuthExpired();
        if (response.status === 409) void refresh();
        throw new Error(
          typeof value.detail === "string"
            ? value.detail
            : "Source action failed. Refresh the workspace before trying again.",
        );
      }
      if (
        !current.current.live ||
        current.current.blocked ||
        current.current.revision > value.revision
      )
        return;
      if (
        value.revision !== action.revision + 1 ||
        value.action !== action.action ||
        value.source_id !== action.source_id ||
        JSON.stringify(value.source_ids) !==
          JSON.stringify(
            sourceActionItems(action).map((item) => item.source_id),
          ) ||
        typeof value.message !== "string"
      )
        throw new Error(
          "Refresh the workspace to verify the source action result.",
        );
      setTurns((items) =>
        items.map((turn, i) =>
          i === index
            ? {
                ...turn,
                content: value.message,
                sourceAction: undefined,
              }
            : turn,
        ),
      );
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      actionInFlight.current = false;
      setApplying(false);
    }
  }
  return (
    <div className="assistant-host" hidden={blocked}>
      {open && (
        <section className="assistant-panel" aria-label="Atlas assistant">
          <header className="assistant-heading">
            <div>
              <h2>Ask Atlas</h2>
            </div>
            <button
              type="button"
              className="icon-button"
              data-help="clearChat"
              aria-label="Clear conversation"
              disabled={pending || applying || !turns.length}
              onClick={() => {
                setTurns([]);
                setError("");
                current.current.onQuestionGraph?.(null);
              }}
            >
              ↺
            </button>
            <button
              type="button"
              className="icon-button"
              aria-label="Close assistant"
              onClick={close}
            >
              ×
            </button>
          </header>
          <div
            className="assistant-transcript"
            ref={transcript}
            role="log"
            aria-label="Assistant conversation"
            aria-live="polite"
            aria-relevant="additions text"
            aria-busy={pending}
          >
            {!turns.length && (
              <div className="assistant-welcome">
                <h3>Ask about your sources</h3>
                <p>
                  Ask about this page, trace a finding, or get a practical next
                  step.
                </p>
                <div className="assistant-prompts">
                  {[
                    "What should I do next?",
                    "Explain this page simply",
                    "How do I check a conflict?",
                  ].map((q) => (
                    <button
                      key={q}
                      type="button"
                      data-help="chatPrompt"
                      onClick={() => void send(q)}
                    >
                      {q}
                      <span aria-hidden="true">↗</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {turns.map((turn, i) => (
              <article key={i} className={"chat-turn " + turn.role}>
                <span className="chat-speaker">
                  {turn.role === "user"
                    ? "You"
                    : turn.guide
                      ? "Atlas · App guide"
                      : "Atlas · Model answer"}
                </span>
                <p>{turn.content}</p>
                {turn.sourceAction && live && !blocked && (
                  <div className="chat-source-action">
                    <strong>{sourceActionLabel(turn.sourceAction)}</strong>
                    {turn.sourceAction.match_text && (
                      <p>
                        Literal match in full source titles or text, ignoring
                        case: {JSON.stringify(turn.sourceAction.match_text)}
                      </p>
                    )}
                    {sourceActionItems(turn.sourceAction).map((item, index) => (
                      <details key={item.source_id}>
                        <summary>
                          {index + 1}. {item.source.title} (version{" "}
                          {item.source.version})
                        </summary>
                        <p>
                          License / permission: {item.source.license}
                          <br />
                          Source URL: {item.source.url || "None"}
                        </p>
                        <blockquote>{item.source.text}</blockquote>
                      </details>
                    ))}
                    {turn.sourceAction.action === "delete_source" && (
                      <p>
                        Removes {turn.sourceAction.removed_findings} findings
                        and {turn.sourceAction.removed_answers} saved answers.
                        Graph and topics will be cleared. Analyze sources again
                        afterward.
                      </p>
                    )}
                    <p>
                      {turn.sourceAction.revision !== workspace.revision
                        ? "Workspace changed. Ask Atlas again for a current proposal."
                        : "Review these details before applying. This proposal expires after 10 minutes."}
                    </p>
                    <button
                      type="button"
                      className="primary"
                      disabled={
                        pending ||
                        applying ||
                        turn.sourceAction.revision !== workspace.revision
                      }
                      onClick={() =>
                        void applySourceAction(i, turn.sourceAction!)
                      }
                    >
                      {applying
                        ? "Applying…"
                        : sourceActionLabel(turn.sourceAction)}
                    </button>{" "}
                    <button
                      type="button"
                      disabled={applying}
                      onClick={() =>
                        setTurns((items) =>
                          items.map((item, index) =>
                            index === i
                              ? {
                                  ...item,
                                  content:
                                    "Source proposal canceled. No changes saved.",
                                  sourceAction: undefined,
                                }
                              : item,
                          ),
                        )
                      }
                    >
                      Cancel
                    </button>
                  </div>
                )}
                {!!turn.citations?.length && (
                  <div className="citation-row">
                    {turn.citations.map((id, index) => (
                      <button
                        className="citation"
                        disabled={!workspace.claims.some((c) => c.id === id)}
                        data-help="citation"
                        type="button"
                        key={id}
                        onClick={() => {
                          openClaim(id);
                          if (innerWidth < 800) close();
                        }}
                      >
                        {workspace.claims.some((c) => c.id === id)
                          ? `Evidence ${index + 1} ↗`
                          : "Evidence no longer current"}
                      </button>
                    ))}
                  </div>
                )}
                {turn.sourcePassages?.map((passage, index) => {
                  const source = workspace.sources.find(
                    (s) =>
                      s.id === passage.source_id && s.sha256 === passage.sha256,
                  );
                  return (
                    <details className="chat-source" key={passage.id}>
                      <summary>
                        Source {index + 1}:{" "}
                        {source?.title || "Source no longer current"}
                        {source ? ` (${source.version})` : ""}
                      </summary>
                      <blockquote>{passage.quote}</blockquote>
                      <button
                        className="citation"
                        type="button"
                        disabled={!source}
                        onClick={() => {
                          openSource(passage.source_id);
                          if (innerWidth < 800) close();
                        }}
                      >
                        Open source ↗
                      </button>
                    </details>
                  );
                })}
                {turn.retrieval && (
                  <RetrievedContext
                    report={turn.retrieval}
                    sources={workspace.sources}
                    openSource={(id) => {
                      openSource(id);
                      if (innerWidth < 800) close();
                    }}
                  />
                )}
                {turn.uncertainty && (
                  <small className="chat-caution">{turn.uncertainty}</small>
                )}
              </article>
            ))}
            {pending && (
              <div className="chat-thinking" role="status">
                <span />
                <span />
                <span />
                <small>Reading the context…</small>
              </div>
            )}
          </div>
          {error && (
            <div className="chat-error" role="alert">
              {error}
              <button
                className="text-button"
                type="button"
                onClick={() => {
                  setMode("guide");
                  setError("");
                }}
              >
                Use App guide
              </button>
            </div>
          )}
          <form
            className="assistant-compose"
            onSubmit={(e) => {
              e.preventDefault();
              void send();
            }}
          >
            <label className="sr-only" htmlFor="assistant-input">
              Message Atlas
            </label>
            <textarea
              id="assistant-input"
              ref={input}
              value={draft}
              maxLength={2000}
              rows={2}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask a question about your review…"
              disabled={pending}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
            <div className="assistant-compose-actions">
              <label>
                <span className="sr-only">Assistant mode</span>
                <select
                  aria-label="Assistant mode"
                  value={live ? mode : "guide"}
                  onChange={(e) => setMode(e.target.value)}
                  disabled={pending}
                >
                  <option value="model" disabled={!live}>
                    Model chat
                  </option>
                  <option value="guide">App guide</option>
                </select>
              </label>
              {pending ? (
                <button className="button" type="button" onClick={stop}>
                  Stop response
                </button>
              ) : (
                <button
                  className="button primary"
                  aria-label="Send message"
                  disabled={!draft.trim()}
                >
                  <span>Send</span>
                  <span aria-hidden="true">↑</span>
                </button>
              )}
            </div>
            <p className="assistant-disclosure">
              {live && mode === "model"
                ? `Excerpts sent to ${provider}. Verify answers. Chat is not saved.`
                : "Built-in app help. Chat is not saved."}
            </p>
          </form>
          {!turns.length && (
            <button
              type="button"
              className="assistant-workflow-link"
              onClick={() => {
                navigate("Sources");
                if (innerWidth < 800) close();
              }}
            >
              Go to Sources <span aria-hidden="true">↗</span>
            </button>
          )}
        </section>
      )}
      <button
        ref={trigger}
        className={"assistant-launcher " + (open ? "is-open" : "")}
        type="button"
        data-help="assistant"
        aria-label={open ? "Hide assistant" : "Open assistant"}
        aria-expanded={open}
        onClick={() => (open ? close() : setOpen(true))}
      >
        <span aria-hidden="true">{open ? "×" : "✦"}</span>
        <span>Ask Atlas</span>
      </button>
    </div>
  );
}
