import React, { useEffect, useRef } from "react";
export type WorkspaceEntry = {
  id: string;
  title: string;
  sources: number;
  claims: number;
  updated_at: string;
};
export function WorkspaceDialog({
  entries,
  active,
  busy,
  error,
  close,
  create,
  choose,
}: {
  entries: WorkspaceEntry[];
  active: string;
  busy: boolean;
  error: string;
  close: () => void;
  create: (title: string) => void;
  choose: (id: string) => void;
}) {
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.querySelector<HTMLInputElement>("input")?.focus();
    function key(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
      if (event.key !== "Tab") return;
      const controls = Array.from(
        panel.current?.querySelectorAll<HTMLElement>(
          "button:not([disabled]),input:not([disabled])",
        ) || [],
      );
      const first = controls[0],
        last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, []);
  return (
    <div className="modal-backdrop">
      <section
        ref={panel}
        className="modal workspace-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="workspace-title"
      >
        <button className="close" aria-label="Close workspaces" onClick={close}>
          ×
        </button>
        <h2 id="workspace-title">Your saved workspaces</h2>
        <p>
          Start fresh or return to a saved review. Creating or switching
          preserves saved work and changes the active workspace for everyone
          connected to this server. Unsaved form inputs in your current view
          will close.
        </p>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            create(String(form.get("title") || ""));
          }}
        >
          <label>
            New workspace name
            <input
              name="title"
              required
              maxLength={160}
              placeholder="My application: upgrade review"
              disabled={busy}
            />
          </label>
          <button
            className="button primary"
            disabled={busy || entries.length >= 30}
          >
            {busy ? "Saving…" : "New empty workspace"}
          </button>
        </form>
        <h3>
          Switch workspace{" "}
          <span className="small muted">{entries.length}/30 saved</span>
        </h3>
        {entries.length >= 30 && (
          <p className="small">
            The 30-workspace limit is reached. Existing workspaces remain
            available. See README for using another data directory.
          </p>
        )}
        <div className="workspace-list">
          {entries.map((entry) => (
            <button
              key={entry.id}
              className="workspace-choice"
              disabled={busy || entry.id === active}
              onClick={() => choose(entry.id)}
              aria-label={"Switch to " + entry.title}
            >
              <span>
                <strong>{entry.title}</strong>
                <small>
                  {entry.sources} sources · {entry.claims} evidence cards
                </small>
              </span>
              <span className="badge neutral">
                {entry.id === active ? "Current" : "Open"}
              </span>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
