import React, { useEffect, useRef, useState } from "react";
import { Workspace } from "./types";
import { guideReply } from "./guide";

export type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  citations?: string[];
  uncertainty?: string;
  guide?: boolean;
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
  onAuthExpired,
  refresh,
  blocked = false,
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
  onAuthExpired: () => void;
  refresh: () => Promise<unknown>;
  blocked?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [mode, setMode] = useState(live ? "model" : "guide");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);
  const sequence = useRef(0);
  const transcript = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const current = useRef({ revision: workspace.revision, live, blocked });
  current.current = { revision: workspace.revision, live, blocked };
  const close = () => {
    setOpen(false);
    trigger.current?.focus();
  };
  const stop = () => {
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
    if (!message || pending || message.length > 2000) return;
    setError("");
    const previous = turns
      .slice(-10)
      .map(({ role, content }) => ({ role, content }));
    const user: ChatTurn = { role: "user", content: message };
    setTurns((t) => [...t.slice(-38), user]);
    if (mode === "guide" || !live) {
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
    try {
      const response = await fetch("/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
      const value = await response.json();
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
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          content: value.answer,
          citations: value.citations,
          uncertainty: value.uncertainty,
        },
      ]);
      setDraft("");
    } catch (e) {
      if (run === sequence.current && (e as Error).name !== "AbortError")
        setError((e as Error).message);
    } finally {
      if (run === sequence.current) {
        setPending(false);
        abort.current = null;
      }
    }
  }
  const chosen = workspace.claims.find((c) => c.id === claimId);
  const selectedSource = workspace.sources.find((s) => s.id === sourceId);
  return (
    <div className="assistant-host" hidden={blocked}>
      {open && (
        <section className="assistant-panel" aria-label="Atlas assistant">
          <header className="assistant-heading">
            <div className="assistant-emblem" aria-hidden="true">
              ✦
            </div>
            <div>
              <h2>Ask Atlas</h2>
              <span>Your review companion</span>
            </div>
            <button
              type="button"
              className="icon-button"
              data-help="clearChat"
              aria-label="Clear conversation"
              disabled={pending || !turns.length}
              onClick={() => {
                setTurns([]);
                setError("");
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
          <div className="assistant-context">
            <span className="context-dot" />
            {page}
            <span>·</span>
            <strong title={workspace.title}>{workspace.title}</strong>
            {chosen && (
              <small>
                Selected: {chosen.entities.join(", ") || "Evidence card"}
              </small>
            )}
            {selectedSource && !chosen && (
              <small>Source: {selectedSource.title}</small>
            )}
          </div>
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
                <span className="assistant-welcome-mark" aria-hidden="true">
                  ✦
                </span>
                <h3>
                  A little clarity,
                  <br />
                  right when you need it.
                </h3>
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
              rows={3}
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
                ? `Uses ${provider} with this page and relevant workspace text. Verify model answers against sources.`
                : live
                  ? "Built-in workflow help. Switch to Model chat for a generated answer."
                  : "Built-in workflow help. Live AI answers are not enabled in this viewer."}{" "}
              Conversation stays in this open view; it is not saved with the
              review.
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
