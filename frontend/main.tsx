import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import { Claim, Workspace } from "./types";
import { validateSnapshot } from "./import";
import "./style.css";
import "./design.css";
import { Tutorial } from "./TutorialGuide";
import {
  emptyWorkspace,
  tutorialSteps,
  tutorialWorkspace,
  tutorialClaim,
  addTutorialReview,
  addTutorialAnswer,
  REVIEW_NOTE,
} from "./tutorial";
import { Assistant } from "./Assistant";
import { ContextHelp, HelpHint } from "./ContextHelp";
import { helpLabels } from "./help-content";
import { WorkspaceDialog, WorkspaceEntry } from "./WorkspaceDialog";
import {
  applyTheme,
  currentPreference,
  THEME_KEY,
  ThemePreference,
} from "./theme";

declare const __DEMO__: Workspace;
declare const __LOGO__: string;
declare const __HOSTED_DEMO__: boolean;
const demo = __DEMO__;
const logo = __LOGO__;
document.getElementById("app-icon")?.setAttribute("href", logo);
const tabs = [
  "Overview",
  "Evidence",
  "Sources",
  "Graph",
  "Questions",
  "Activity",
] as const;
type Tab = (typeof tabs)[number];
const isServer =
  !__HOSTED_DEMO__ &&
  (location.protocol === "http:" || location.protocol === "https:");
const exampleWorkspace = () =>
  tutorialWorkspace(demo, tutorialSteps.length - 1);
const categories = [
  "breaking",
  "deprecation",
  "security",
  "feature",
  "fix",
  "other",
];
const stamp = (at: string) =>
  new Date(at).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
const human = (s: string) => s.replaceAll("-", " ");

function Icon({ name = "grid" }: { name?: string }) {
  const paths: Record<string, React.ReactNode> = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    Evidence: (
      <>
        <path d="M6 3h12v18H6zM9 8h6M9 12h6M9 16h4" />
      </>
    ),
    Sources: (
      <>
        <path d="M4 5h6l2 2h8v13H4zM4 10h16" />
      </>
    ),
    Graph: (
      <>
        <circle cx="12" cy="5" r="3" />
        <circle cx="5" cy="18" r="3" />
        <circle cx="19" cy="18" r="3" />
        <path d="m10 8-4 7m8-7 4 7M8 18h8" />
      </>
    ),
    Questions: (
      <>
        <path d="M4 4h16v12H9l-5 4zM8 8h8M8 12h5" />
      </>
    ),
    Activity: (
      <>
        <path d="M3 12h4l3-8 4 16 3-8h4" />
      </>
    ),
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
  };
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.grid}
    </svg>
  );
}

function Appearance() {
  const [preference, setPreference] =
    useState<ThemePreference>(currentPreference);
  useEffect(() => {
    applyTheme(preference);
    const light = window.matchMedia?.("(prefers-color-scheme: light)");
    const dark = window.matchMedia?.("(prefers-color-scheme: dark)");
    const update = () => applyTheme(preference);
    light?.addEventListener?.("change", update);
    dark?.addEventListener?.("change", update);
    const storage = (event: StorageEvent) => {
      if (event.key === THEME_KEY || event.key === null)
        setPreference(currentPreference());
    };
    window.addEventListener("storage", storage);
    return () => {
      light?.removeEventListener?.("change", update);
      dark?.removeEventListener?.("change", update);
      window.removeEventListener("storage", storage);
    };
  }, [preference]);
  return (
    <label className="appearance">
      <span className="sr-only">Appearance</span>
      <select
        aria-label="Appearance"
        value={preference}
        onChange={(event) => {
          const next = event.target.value as ThemePreference;
          setPreference(next);
          try {
            localStorage.setItem(THEME_KEY, next);
          } catch {
            /* Choice still works for this open view. */
          }
        }}
      >
        <option value="system">System theme</option>
        <option value="dark">Dark theme</option>
        <option value="light">Light theme</option>
      </select>
    </label>
  );
}

function App() {
  const [showTutorial, setShowTutorial] = useState(false);
  const previous = useRef<HTMLElement | null>(null);
  const scroll = useRef(0);
  const start = useCallback(() => {
    previous.current = document.activeElement as HTMLElement;
    scroll.current = window.scrollY;
    setShowTutorial(true);
    window.scrollTo(0, 0);
  }, []);
  const exit = useCallback(() => {
    setShowTutorial(false);
    requestAnimationFrame(() => {
      window.scrollTo(0, scroll.current);
      previous.current?.focus();
    });
  }, []);
  return (
    <>
      <ContextHelp enabled={!showTutorial} />
      <div hidden={showTutorial}>
        <Workbench startTutorial={start} suspended={showTutorial} />
      </div>
      {showTutorial && (
        <Workbench tutorial startTutorial={start} exitTutorial={exit} />
      )}
    </>
  );
}
function Workbench({
  tutorial = false,
  suspended = false,
  startTutorial,
  exitTutorial = () => {},
}: {
  tutorial?: boolean;
  suspended?: boolean;
  startTutorial: () => void;
  exitTutorial?: () => void;
}) {
  const [workspace, setWorkspace] = useState<Workspace>(() =>
    tutorial
      ? tutorialWorkspace(demo, 0)
      : __HOSTED_DEMO__
        ? exampleWorkspace()
        : emptyWorkspace(),
  );
  const root = useRef<HTMLDivElement>(null);
  const [tourStep, setTourStep] = useState(0);
  const [tourRun, setTourRun] = useState(0);
  const [manager, setManager] = useState(false);
  const [catalog, setCatalog] = useState<WorkspaceEntry[]>([]);
  const [activeId, setActiveId] = useState("");
  const activeRef = useRef("");
  const [viewKey, setViewKey] = useState(0);
  const managerRevision = useRef(0);

  const [tab, setTab] = useState<Tab>("Overview");
  const [user, setUser] = useState("");
  const [login, setLogin] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [connected, setConnected] = useState(false);
  const [provider, setProvider] = useState("gpt-oss:20b");
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [scope, setScope] = useState("all");
  const [sourceId, setSourceId] = useState("");
  const importRef = useRef<HTMLInputElement>(null);
  const revision = useRef(workspace.revision);
  const live = !tutorial && isServer && !!user;
  const editable = live || tutorial;
  const adopt = (state: Workspace) => {
    if (live && state.revision < revision.current) return;
    revision.current = state.revision;
    setWorkspace(state);
  };

  async function api(path: string, body?: unknown, method = "POST") {
    if (tutorial || !isServer)
      throw new Error("This view cannot contact the workspace service.");
    const response = await fetch("/api/" + path, {
      method: body === undefined ? "GET" : method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const value = await response.json();
    if (!response.ok) {
      if (response.status === 401) {
        setUser("");
        setLogin(true);
      }
      if (response.status === 409 && path !== "state") await refresh();
      const detail =
        typeof value.detail === "string"
          ? value.detail
          : "Check the input fields and supported limits.";
      throw new Error(detail);
    }
    return value;
  }

  async function refresh() {
    try {
      const value = await api("state");
      if (value.workspace.revision >= revision.current || !user) {
        adopt(value.workspace);
        setCatalog(value.workspaces);
        setActiveId(value.active_id);
        if (activeRef.current && activeRef.current !== value.active_id) {
          setViewKey((k) => k + 1);
          setSelected("");
          setSourceId("");
          setTab("Overview");
          setNotice(
            "Active workspace changed. Your previous saved review is available in Workspaces.",
          );
        }
        activeRef.current = value.active_id;
      }
      setUser(value.user);
      setProvider(value.provider.model);
      return value.workspace as Workspace;
    } catch (e) {
      if (user) setError((e as Error).message);
    }
  }

  useEffect(() => {
    if (!login || suspended) return;
    const previous = document.activeElement as HTMLElement | null;
    function trap(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setLogin(false);
        return;
      }
      if (event.key !== "Tab") return;
      const dialog = document.querySelector(".modal");
      const controls = Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          "button:not([disabled]),input:not([disabled]),a[href]",
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
    document.addEventListener("keydown", trap);
    return () => {
      document.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [login, suspended]);
  useEffect(() => {
    if (isServer && !tutorial) {
      revision.current = -1;
      void refresh();
    }
  }, []);
  useEffect(() => {
    if (!live) return;
    const events = new EventSource("/api/events");
    events.onopen = () => setConnected(true);
    events.onerror = () => setConnected(false);
    events.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.revision > revision.current) void refresh();
    };
    events.addEventListener("expired", () => {
      events.close();
      setUser("");
      setLogin(true);
    });
    return () => {
      events.close();
      setConnected(false);
    };
  }, [live]);

  async function act(label: string, task: () => Promise<unknown>) {
    if (busy) return;
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await task();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function mutate(
    path: string,
    data: Record<string, unknown> = {},
    method = "POST",
  ) {
    if (tutorial) {
      if (path === "analyze") {
        adopt(tutorialWorkspace(demo, tourStep));
        setNotice("Prepared tutorial analysis displayed.");
      } else if (path.startsWith("claims/")) {
        adopt(addTutorialReview(workspace));
      } else throw new Error("This action is not part of the tutorial.");
      return revision.current;
    }
    const saved: Workspace = await api(
      path,
      { revision: revision.current, ...data },
      method,
    );
    adopt(saved);
    return saved.revision;
  }
  function exportSnapshot() {
    if (tutorial) return;
    const blob = new Blob([JSON.stringify(workspace, null, 2)], {
      type: "application/json",
    });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = "release-atlas-review.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setNotice(
      "Saved analysis exported. It includes source text and review names, so check it before sharing.",
    );
  }
  async function importSnapshot(file: File) {
    await act("Importing", async () => {
      if (file.size > 2_000_000)
        throw new Error("Saved analysis must be smaller than 2 MB.");
      const state = await validateSnapshot(JSON.parse(await file.text()));
      if (
        !live &&
        !window.confirm(
          "Replace the current view with this saved analysis? Export current work first if you need to keep it.",
        )
      )
        return;
      if (live) {
        const names = new Set(catalog.map((entry) => entry.title));
        let title = state.title;
        for (let suffix = 1; names.has(title); suffix++)
          title = state.title.slice(0, 140) + " (import " + suffix + ")";
        await mutate("workspaces", { title, workspace: state });
        await refresh();
      } else {
        adopt(state);
        setViewKey((k) => k + 1);
      }
      setSelected("");
      setNotice(
        "Imported saved analysis. " +
          (live ? "Your previous workspace is preserved in Workspaces. " : "") +
          "Embedded review names are imported provenance, not verified identities.",
      );
    });
  }
  function openClaim(id: string) {
    setSelected(id);
    setSearch("");
    setCategory("all");
    setScope("all");
    setTab("Evidence");
  }
  function moveTutorial(step: number) {
    const item = tutorialSteps[step];
    if (!item) return;
    setTourStep(step);
    setTourRun((r) => r + 1);
    adopt(tutorialWorkspace(demo, step));
    setTab(item.tab);
    setSelected(tutorialClaim(demo).id);
    setSourceId("");
    setSearch("");
    setCategory("all");
    setScope("all");
    setNotice("");
    setError("");
  }
  function resetExample() {
    if (
      !window.confirm(
        "Restore the prepared example? Export first if you want to keep an imported review.",
      )
    )
      return;
    adopt(exampleWorkspace());
    setViewKey((k) => k + 1);
    setSelected("");
    setSourceId("");
    setSearch("");
    setCategory("all");
    setScope("all");
    setTab("Overview");
    setError("");
    setNotice("The prepared Harbor SDK example is ready to explore.");
  }
  async function openWorkspaces() {
    await act("Loading workspaces", async () => {
      if (!(await refresh())) return;
      managerRevision.current = revision.current;
      setManager(true);
    });
  }
  async function selectWorkspace(data: { id: string } | { title: string }) {
    await act("Saving workspace selection", async () => {
      try {
        await mutate("id" in data ? "workspaces/switch" : "workspaces", {
          ...data,
          revision: managerRevision.current,
        });
        await refresh();
        setManager(false);
      } finally {
        managerRevision.current = revision.current;
      }
    });
  }
  const reviewed = workspace.claims.filter((c) => c.review).length;
  const conflicts = workspace.claims.filter((c) => c.conflicts.length > 0);
  const applicable = workspace.claims.filter((c) => c.applicable).length;
  const filtered = workspace.claims.filter(
    (c) =>
      (category === "all" || c.category === category) &&
      (scope === "all" ||
        (scope === "used" && c.applicable) ||
        (scope === "conflicts" && c.conflicts.length) ||
        (scope === "unreviewed" && !c.review)) &&
      (c.quote + " " + c.entities.join(" "))
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const chosen = filtered.find((c) => c.id === selected) || filtered[0];
  const chosenSource =
    workspace.sources.find((s) => s.id === sourceId) || workspace.sources[0];
  const locked = !editable || !!busy;

  return (
    <div className={tutorial ? "tutorial-session" : ""}>
      <div
        className="app-shell"
        ref={root}
        inert={tutorial || manager || login || suspended || undefined}
      >
        <a className="skip" href={tutorial ? "#tutorial-main" : "#main"}>
          Skip to content
        </a>
        <aside className="sidebar">
          <a
            href="#"
            className="brand"
            onClick={(e) => {
              e.preventDefault();
              setTab("Overview");
            }}
            aria-label="Release Atlas overview"
          >
            <img
              className="brand-symbol"
              src={logo}
              alt=""
              width="38"
              height="38"
            />
            <span>
              release<span className="brand-light">atlas</span>
            </span>
          </a>
          <div className="workspace-label">
            {tutorial
              ? "TUTORIAL EXAMPLE"
              : __HOSTED_DEMO__
                ? "DEMO WORKSPACE"
                : "YOUR WORKSPACE"}
          </div>
          <div className="project-card">
            <span className="project-monogram">
              {workspace.title.slice(0, 1)}
            </span>
            <div>
              <strong>{workspace.title.split(":")[0]}</strong>
              <small>Upgrade evidence review</small>
            </div>
          </div>
          <nav aria-label="Main navigation">
            {tabs.map((item) => (
              <button
                key={item}
                aria-label={item}
                data-help={item}
                data-tour={"nav-" + item}
                className={tab === item ? "nav active" : "nav"}
                aria-current={tab === item ? "page" : undefined}
                onClick={() => setTab(item)}
              >
                <Icon name={item} />
                <span>{item}</span>
                {item === "Evidence" && (
                  <span className="nav-count">{workspace.claims.length}</span>
                )}
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="connection">
              <span className={"dot " + (live && connected ? "green" : "")} />
              {tutorial
                ? "Tutorial example"
                : live
                  ? connected
                    ? "Live workspace"
                    : "Reconnecting"
                  : __HOSTED_DEMO__
                    ? "Demo workspace"
                    : "Saved review"}
            </div>
            <p>
              Evidence informs the decision.
              <br />
              Your team makes the call.
            </p>
            {tutorial ? (
              <p className="small">Temporary example review</p>
            ) : live ? (
              <button
                className="identity"
                aria-label="Sign out"
                onClick={() =>
                  void act("Signing out", async () => {
                    await api("logout", {});
                    setUser("");
                  })
                }
              >
                <span className="avatar">{user.slice(0, 1).toUpperCase()}</span>
                {user}
                <small>Sign out</small>
              </button>
            ) : isServer ? (
              <button className="button" onClick={() => setLogin(true)}>
                Sign in to collaborate
              </button>
            ) : (
              <a
                className="button"
                href={
                  __HOSTED_DEMO__
                    ? "https://github.com/myurch/release-atlas"
                    : "http://127.0.0.1:8765"
                }
                target="_blank"
                rel="noreferrer"
              >
                {__HOSTED_DEMO__ ? "Get the full app" : "Open workspace"}{" "}
                <Icon name="arrow" />
              </a>
            )}
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <span>
              <span className="muted">Workspace</span>
              <span className="breadcrumb">/</span>
              {tab}
            </span>
            <div className="actions">
              <Appearance />
              {!tutorial && (
                <button
                  className="button"
                  onClick={startTutorial}
                  disabled={!!busy}
                >
                  Beginner tutorial
                </button>
              )}
              {__HOSTED_DEMO__ && !tutorial && (
                <button className="button" onClick={resetExample}>
                  Reset example
                </button>
              )}
              {live && (
                <button
                  className="button"
                  onClick={() => void openWorkspaces()}
                  disabled={!!busy}
                >
                  Workspaces
                </button>
              )}
              <button
                className="button subtle"
                onClick={() => importRef.current?.click()}
                disabled={!!busy || tutorial}
              >
                Import
              </button>
              <button
                className="button"
                data-tour="export"
                onClick={exportSnapshot}
                disabled={tutorial}
              >
                Export snapshot <span aria-hidden="true">↗</span>
              </button>
              <input
                ref={importRef}
                type="file"
                accept=".json,application/json"
                hidden
                aria-label="Import saved analysis"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) void importSnapshot(file);
                  e.target.value = "";
                }}
              />
            </div>
          </header>
          <main
            id={tutorial ? "tutorial-main" : "main"}
            tabIndex={-1}
            key={tutorial ? tourRun : viewKey}
          >
            <div className="mobile-session">
              {tutorial ? (
                <span>BEGINNER TUTORIAL · Temporary example</span>
              ) : live ? (
                <>
                  <span>
                    {user} · {connected ? "Live workspace" : "Reconnecting"}
                  </span>
                  <button
                    className="text-button"
                    onClick={() =>
                      void act("Signing out", async () => {
                        await api("logout", {});
                        setUser("");
                      })
                    }
                  >
                    Sign out
                  </button>
                </>
              ) : isServer ? (
                <button className="text-button" onClick={() => setLogin(true)}>
                  Sign in to collaborate
                </button>
              ) : (
                <a
                  href={
                    __HOSTED_DEMO__
                      ? "https://github.com/myurch/release-atlas"
                      : "http://127.0.0.1:8765"
                  }
                  target="_blank"
                  rel="noreferrer"
                >
                  {__HOSTED_DEMO__ ? "Get the full app" : "Open workspace"} ↗
                </a>
              )}
            </div>
            {!workspace.analysis && workspace.claims.length > 0 && (
              <div className="banner error" role="status">
                Sources or usage changed. Displayed evidence is from the
                previous analysis. Analyze sources before reviewing or asking
                new questions.
              </div>
            )}
            <div className="page-heading">
              <div>
                <div className="eyebrow">
                  UPGRADE REVIEW <span className="tiny-rule" /> REVISION{" "}
                  {workspace.revision}
                </div>
                <h1>
                  {tab === "Overview"
                    ? "Know what changes. Decide together."
                    : tab === "Evidence"
                      ? "Follow the evidence."
                      : tab === "Sources"
                        ? "Keep the original in view."
                        : tab === "Graph"
                          ? "See the connections."
                          : tab === "Questions"
                            ? "Ask with evidence."
                            : "A record of the review."}
                </h1>
                <p>
                  {workspace.title} <span className="separator">·</span>{" "}
                  {tab === "Overview"
                    ? "A shared picture of changes, conflicts and next steps."
                    : "Source snapshots stay attached to every finding."}
                </p>
              </div>
              {editable && (
                <button
                  data-tour="analyze"
                  className="button primary"
                  disabled={!!busy || !workspace.sources.length}
                  onClick={() =>
                    void act("Analyzing sources", () => mutate("analyze"))
                  }
                >
                  {busy === "Analyzing sources"
                    ? "Analyzing…"
                    : "Analyze sources"}
                  <Icon name="arrow" />
                </button>
              )}
            </div>
            {__HOSTED_DEMO__ && !tutorial && (
              <section className="demo-notice" aria-label="About this demo">
                <strong>Explore the sample review</strong>
                <p>
                  Browse prepared evidence, source documents, graphs and cited
                  answers. Try the beginner tutorial for a guided walkthrough.
                  Ask Atlas provides built-in App guide help. New analysis,
                  shared edits and live AI answers require the full application.
                </p>
              </section>
            )}
            {workspace.sources.some((s) => s.license.includes("synthetic")) && (
              <p className="demo-label">
                SYNTHETIC EXAMPLE{" "}
                <span>
                  Harbor SDK is fictional. These are demonstration documents,
                  not a real upgrade advisory.
                </span>
                {!tutorial && live && (
                  <button
                    className="text-button"
                    onClick={() => void openWorkspaces()}
                  >
                    Leave example / switch workspace
                  </button>
                )}
                {!tutorial && !live && !__HOSTED_DEMO__ && (
                  <button
                    className="text-button"
                    onClick={() => {
                      if (
                        window.confirm(
                          "Clear this view? Export first to keep this imported snapshot.",
                        )
                      ) {
                        adopt(emptyWorkspace());
                        setViewKey((k) => k + 1);
                      }
                    }}
                  >
                    Clear example view
                  </button>
                )}
              </p>
            )}
            {error && (
              <div className="banner error" role="alert">
                {error}
                <button aria-label="Dismiss error" onClick={() => setError("")}>
                  ×
                </button>
              </div>
            )}
            {notice && (
              <div className="banner success" role="status">
                {notice}
                <button
                  aria-label="Dismiss notice"
                  onClick={() => setNotice("")}
                >
                  ×
                </button>
              </div>
            )}
            {busy && (
              <div className="progress" role="status">
                <span className="spinner" />
                {busy}…
              </div>
            )}
            {tab === "Overview" && (
              <>
                <div className="stats">
                  <Stat
                    label="Evidence cards"
                    value={workspace.claims.length}
                    note={`${workspace.sources.length} source snapshots`}
                  />
                  <Stat
                    label="Match your usage"
                    value={applicable}
                    note="Potentially relevant changes"
                  />
                  <Stat
                    label="Conflicting claims"
                    value={conflicts.length}
                    note="Need a closer look"
                    warn
                  />
                  <Stat
                    label="Reviewed"
                    value={`${reviewed}/${workspace.claims.length}`}
                    note="Decisions recorded by the team"
                  />
                </div>
                <div className="overview-grid">
                  <section className="panel attention">
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">START HERE</span>
                        <h2>
                          What needs your attention{" "}
                          <HelpHint topic="conflicts" />
                        </h2>
                      </div>
                      <span className="badge amber">Human review</span>
                    </div>
                    {conflicts.length ? (
                      <>
                        <div className="conflict-feature">
                          <span className="conflict-icon">!</span>
                          <div>
                            <h3>The sources disagree.</h3>
                            <p>
                              {conflicts.length} claims give competing guidance
                              for the same version. Read both passages before
                              marking an upgrade task complete.
                            </p>
                          </div>
                        </div>
                        {conflicts.slice(0, 2).map((c) => (
                          <button
                            className="attention-row"
                            key={c.id}
                            onClick={() => openClaim(c.id)}
                          >
                            <div>
                              <strong>
                                {c.entities.join(", ") ||
                                  "Conflicting guidance"}
                              </strong>
                              <p>{c.quote}</p>
                            </div>
                            <Icon name="arrow" />
                          </button>
                        ))}
                      </>
                    ) : (
                      <div className="empty">
                        <h3>
                          {workspace.claims.length
                            ? "No conflict candidates found"
                            : "Start with a source"}
                        </h3>
                        <p>
                          {workspace.claims.length
                            ? "This is not proof the sources are consistent. Review important changes."
                            : "Add release notes and versioned documentation, then analyze them."}
                        </p>
                        {!workspace.sources.length && !tutorial && (
                          <div className="empty-actions">
                            <button
                              className="button primary"
                              onClick={startTutorial}
                            >
                              Start beginner tutorial
                            </button>
                            {live && (
                              <button
                                className="button"
                                onClick={() => setTab("Sources")}
                              >
                                Add your first source
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                    <button
                      className="text-button"
                      onClick={() => {
                        setTab("Evidence");
                        setScope("unreviewed");
                      }}
                    >
                      Review all open evidence <Icon name="arrow" />
                    </button>
                  </section>
                  <section className="panel">
                    <div className="section-heading">
                      <div>
                        <span className="eyebrow">IN YOUR APPLICATION</span>
                        <h2>
                          Usage profile <HelpHint topic="usage" />
                        </h2>
                      </div>
                    </div>
                    <p className="muted small">
                      Declared features connect changes to your application.
                      This is not a scan of your code.
                    </p>
                    <UsageForm
                      usage={workspace.usage}
                      revision={workspace.revision}
                      disabled={locked}
                      save={(usage, revision) =>
                        act("Saving profile", () =>
                          mutate("profile", { usage, revision }, "PUT"),
                        )
                      }
                    />
                  </section>
                </div>
                <section className="panel topics">
                  <div className="section-heading">
                    <div>
                      <span className="eyebrow">PATTERNS IN THE TEXT</span>
                      <h2>
                        Topics in this review <HelpHint topic="topics" />
                      </h2>
                    </div>
                    <span className="small muted">
                      Statistical grouping, not a risk score
                    </span>
                  </div>
                  <div className="topic-grid">
                    {workspace.topics.map((topic) => (
                      <button
                        key={topic.id}
                        className="topic"
                        onClick={() => {
                          setSearch(topic.terms[0]);
                          setTab("Evidence");
                        }}
                      >
                        <span className="topic-index">0{topic.id + 1}</span>
                        <strong>{topic.terms.slice(0, 3).join(" · ")}</strong>
                        <span>
                          {topic.count} passages <Icon name="arrow" />
                        </span>
                      </button>
                    ))}
                    {!workspace.topics.length && (
                      <p className="muted">Topics appear after analysis.</p>
                    )}
                  </div>
                </section>
              </>
            )}
            {tab === "Evidence" && (
              <>
                <div className="filterbar">
                  <label className="search">
                    <span className="sr-only">Search evidence</span>
                    <input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search APIs, settings or passages…"
                    />
                  </label>
                  <label>
                    <span className="sr-only">Category</span>
                    <select
                      value={category}
                      onChange={(e) => setCategory(e.target.value)}
                    >
                      <option value="all">All change types</option>
                      {categories.map((c) => (
                        <option key={c} value={c}>
                          {human(c)}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span className="sr-only">Evidence scope</span>
                    <select
                      value={scope}
                      onChange={(e) => setScope(e.target.value)}
                    >
                      <option value="all">All evidence</option>
                      <option value="used">Matches usage</option>
                      <option value="conflicts">Conflicting claims</option>
                      <option value="unreviewed">Unreviewed</option>
                    </select>
                  </label>
                  <span className="small muted">{filtered.length} results</span>
                </div>
                <div className="evidence-grid">
                  <div className="evidence-list">
                    {filtered.map((c) => (
                      <button
                        className={
                          "evidence-card " +
                          (chosen?.id === c.id ? "selected" : "")
                        }
                        key={c.id}
                        onClick={() => setSelected(c.id)}
                      >
                        <div className="chips">
                          <span className={"badge " + c.category}>
                            {c.category}
                          </span>
                          {c.conflicts.length > 0 && (
                            <span className="badge amber">Conflict</span>
                          )}
                          {c.applicable && (
                            <span
                              className="usage-dot"
                              title="Matches your usage profile"
                            />
                          )}
                        </div>
                        <p>{c.quote}</p>
                        <div className="card-meta">
                          <span>
                            {
                              workspace.sources.find(
                                (s) => s.id === c.source_id,
                              )?.title
                            }
                          </span>
                          <span>{c.review ? "Reviewed" : "Open"}</span>
                        </div>
                      </button>
                    ))}
                    {!filtered.length && (
                      <div className="panel empty">
                        <h3>No matching evidence</h3>
                        <p>
                          Try a different filter or add and analyze source text.
                        </p>
                      </div>
                    )}
                  </div>
                  {chosen && (
                    <ClaimDetail
                      key={
                        tutorial
                          ? chosen.id + ":" + workspace.revision
                          : chosen.id
                      }
                      initialNote={
                        tutorial && tourStep >= 7 ? REVIEW_NOTE : undefined
                      }
                      claim={chosen}
                      workspace={workspace}
                      disabled={locked || !workspace.analysis}
                      openClaim={openClaim}
                      source={() => {
                        setSourceId(chosen.source_id);
                        setTab("Sources");
                      }}
                      save={async (status, note, revision) => {
                        let savedRevision: number | undefined;
                        await act("Saving review", async () => {
                          savedRevision = await mutate(
                            `claims/${chosen.id}/review`,
                            { status, note, revision },
                            "PUT",
                          );
                        });
                        return savedRevision;
                      }}
                    />
                  )}
                </div>
              </>
            )}
            {tab === "Sources" && (
              <div className="source-grid">
                <section className="panel">
                  <div className="section-heading">
                    <h2>Source snapshots</h2>
                    <span className="badge neutral">
                      {workspace.sources.length}/30
                    </span>
                  </div>
                  <div className="source-list">
                    {workspace.sources.map((s) => (
                      <button
                        key={s.id}
                        className={
                          "source-item " +
                          (chosenSource?.id === s.id ? "selected" : "")
                        }
                        onClick={() => setSourceId(s.id)}
                      >
                        <Icon name="Sources" />
                        <span>
                          <strong>{s.title}</strong>
                          <small>Version {s.version}</small>
                        </span>
                      </button>
                    ))}
                  </div>
                  {chosenSource ? (
                    <>
                      <div className="source-meta">
                        <span className="badge neutral">
                          {chosenSource.version}
                        </span>
                        <span className="small muted">Saved snapshot</span>
                      </div>
                      <h3>{chosenSource.title}</h3>
                      <pre className="source-text">{chosenSource.text}</pre>
                      <p className="small muted">{chosenSource.license}</p>
                      {chosenSource.url && (
                        <a
                          href={chosenSource.url}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Open original source ↗
                        </a>
                      )}
                      <details>
                        <summary>Snapshot fingerprint</summary>
                        <code className="hash">{chosenSource.sha256}</code>
                      </details>
                    </>
                  ) : (
                    <div className="empty">No source snapshots yet.</div>
                  )}
                </section>
                <div>
                  <SourceForm
                    disabled={locked || tutorial}
                    save={(source) =>
                      act("Adding source", async () => {
                        await mutate("sources", { source });
                        setNotice(
                          "Source saved. Analyze sources to refresh evidence.",
                        );
                      })
                    }
                  />
                  <FeedForm
                    disabled={locked || tutorial}
                    save={(data) =>
                      act("Fetching releases", async () => {
                        await mutate("feeds/github", data);
                        setNotice(
                          "Release snapshots imported. Analyze sources to refresh evidence.",
                        );
                      })
                    }
                  />
                </div>
              </div>
            )}
            {tab === "Graph" && (
              <GraphView
                workspace={workspace}
                openClaim={openClaim}
                initialFocus={
                  tutorial
                    ? "u:Checkout service"
                    : __HOSTED_DEMO__
                      ? "e:legacy_auth"
                      : undefined
                }
              />
            )}
            {tab === "Questions" && (
              <section className="questions-layout">
                <div className="panel">
                  <span className="eyebrow">SOURCE-GROUNDED QUESTIONS</span>
                  <h2>Start with what you use.</h2>
                  <p className="muted">
                    {__HOSTED_DEMO__ && !tutorial
                      ? "Read the prepared example answer and follow its citations. New questions and model generation are available in the full application."
                      : "Try “What affects Checkout service?” Graph retrieval follows your usage profile to relevant passages."}
                  </p>
                  <QuestionForm
                    disabled={locked || !workspace.analysis}
                    provider={provider}
                    ask={(data) =>
                      act("Retrieving evidence", async () => {
                        if (tutorial) {
                          adopt(addTutorialAnswer(workspace));
                          return;
                        }
                        const result = await api("query", {
                          ...data,
                          revision: revision.current,
                        });
                        adopt(result.workspace);
                      })
                    }
                  />
                  <p className="small muted">
                    The answer is a review aid. Citations are checked against
                    retrieved evidence; that alone cannot establish factual
                    correctness.
                  </p>
                </div>
                <div className="answers">
                  {[...workspace.answers].reverse().map((a) => (
                    <article className="panel answer" key={a.id}>
                      <div className="eyebrow">{a.method}</div>
                      <h3>{a.question}</h3>
                      <p className="answer-text">{a.answer}</p>
                      <div className="citation-row">
                        {a.citations.map((id, i) => (
                          <button
                            className="citation"
                            key={id}
                            onClick={() => openClaim(id)}
                          >
                            Source {i + 1} ↗
                          </button>
                        ))}
                      </div>
                      <p className="uncertainty">{a.uncertainty}</p>
                      <small className="muted">{stamp(a.at)}</small>
                    </article>
                  ))}
                  {!workspace.answers.length && (
                    <div className="panel empty">
                      <Icon name="Questions" />
                      <h3>Your questions stay with the evidence.</h3>
                      <p>
                        Ask in the live workspace. Saved answers and their
                        citations stay with the exported review.
                      </p>
                    </div>
                  )}
                </div>
              </section>
            )}
            {tab === "Activity" && (
              <section className="panel">
                <div className="section-heading">
                  <h2>Review history</h2>
                  <span className="small muted">
                    Latest 200 workspace changes
                  </span>
                </div>
                <p className="small muted">
                  Display names identify shared-passcode sessions, not verified
                  accounts. Names in imported snapshots are unverified
                  provenance.
                </p>
                {[...workspace.audit].reverse().map((a, i) => (
                  <div className="activity-row" key={i}>
                    <span className="avatar">
                      {a.by.slice(0, 1).toUpperCase()}
                    </span>
                    <div>
                      <strong>{a.by}</strong> {a.action}
                      <small>
                        {stamp(a.at)} · Revision {a.revision}
                      </small>
                    </div>
                  </div>
                ))}
                {!workspace.audit.length && (
                  <div className="empty">
                    No team activity in this snapshot.
                  </div>
                )}
              </section>
            )}
            <footer>
              <span>
                Release Atlas <span className="muted">/</span> Evidence before
                action.
              </span>
              <span>
                v0.1 ·{" "}
                {workspace.analysis
                  ? "Analysis saved " + stamp(workspace.analysis.created_at)
                  : "Awaiting analysis"}
              </span>
            </footer>
          </main>
        </div>
      </div>
      {!tutorial && (
        <Assistant
          key={live ? user + ":" + activeId : "saved:" + viewKey}
          workspace={workspace}
          page={tab}
          claimId={tab === "Evidence" ? chosen?.id || "" : ""}
          sourceId={tab === "Sources" ? chosenSource?.id || "" : ""}
          live={live}
          provider={provider}
          navigate={setTab}
          openClaim={openClaim}
          onAuthExpired={() => {
            setUser("");
            setLogin(true);
          }}
          refresh={refresh}
          blocked={manager || login || suspended}
        />
      )}
      {tutorial && (
        <Tutorial
          step={tourStep}
          run={tourRun}
          root={root}
          move={moveTutorial}
          exit={exitTutorial}
        />
      )}
      {manager && (
        <WorkspaceDialog
          entries={catalog}
          active={activeId}
          busy={!!busy}
          error={error}
          close={() => setManager(false)}
          create={(title) => void selectWorkspace({ title })}
          choose={(id) => void selectWorkspace({ id })}
        />
      )}
      {login && !suspended && (
        <div className="modal-backdrop">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="login-title"
          >
            <button
              className="close"
              aria-label="Close sign in"
              onClick={() => setLogin(false)}
            >
              ×
            </button>
            <img
              className="brand-symbol modal-logo"
              src={logo}
              alt="Release Atlas"
              width="48"
              height="48"
            />
            <h2 id="login-title">Join the review.</h2>
            <p className="muted">
              Enter a display name and your local workspace access code. The
              code is saved in the server’s .atlas/access-code file.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const form = new FormData(e.currentTarget);
                void act("Signing in", async () => {
                  await api("login", {
                    name: form.get("name"),
                    passcode: form.get("passcode"),
                  });
                  revision.current = -1;
                  await refresh();
                  setLogin(false);
                });
              }}
            >
              <label>
                Display name
                <input
                  name="name"
                  required
                  maxLength={60}
                  autoFocus
                  autoComplete="nickname"
                />
              </label>
              <label>
                Workspace access code
                <input
                  name="passcode"
                  required
                  type="password"
                  autoComplete="current-password"
                  maxLength={200}
                />
              </label>
              {error && (
                <p className="form-error" role="alert">
                  {error}
                </p>
              )}
              <button className="button primary full" disabled={!!busy}>
                Enter workspace <Icon name="arrow" />
              </button>
            </form>
            <button
              className="text-button"
              onClick={() => {
                setLogin(false);
                startTutorial();
              }}
            >
              Try the beginner tutorial
            </button>
          </section>
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  note,
  warn = false,
}: {
  label: string;
  value: string | number;
  note: string;
  warn?: boolean;
}) {
  return (
    <div className={"stat " + (warn ? "warning" : "")}>
      <span>
        {label} <HelpHint topic={helpLabels[label]} label={label} />
      </span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
function UsageForm({
  usage,
  revision,
  disabled,
  save,
}: {
  usage: Workspace["usage"];
  revision: number;
  disabled: boolean;
  save: (v: Workspace["usage"], revision: number) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [draftRevision, setDraftRevision] = useState(revision);
  return (
    <>
      <div className="usage-list">
        {usage.map((u, i) => (
          <div className="usage-item" key={i}>
            <span className="small-icon">
              <Icon name="Graph" />
            </span>
            <span>
              <strong>{u.component}</strong>
              <code>{u.entity}</code>
            </span>
          </div>
        ))}
        {!usage.length && <p className="muted">No usage profile yet.</p>}
      </div>
      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const rows = text
              .split("\n")
              .filter((x) => x.trim())
              .map((row) => {
                const [component, ...entity] = row.split("|");
                return {
                  component: component.trim(),
                  entity: entity.join("|").trim(),
                };
              });
            void save(rows, draftRevision);
          }}
        >
          <p className="small muted">
            {draftRevision !== revision
              ? "Workspace changed. Close and reopen this editor to load the latest profile before saving."
              : "Changes invalidate the current analysis."}
          </p>
          <label>
            One component | identifier per line
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              data-tour="usage-editor"
              rows={5}
            />
          </label>
          <div className="actions">
            <button
              className="button primary"
              disabled={disabled || draftRevision !== revision}
            >
              Save profile
            </button>
            <button
              type="button"
              className="button subtle"
              onClick={() => setEditing(false)}
            >
              Close
            </button>
          </div>
        </form>
      ) : (
        <button
          className="text-button"
          disabled={disabled}
          data-tour="edit-usage"
          onClick={() => {
            setText(
              usage.map((u) => u.component + " | " + u.entity).join("\n"),
            );
            setDraftRevision(revision);
            setEditing(true);
          }}
        >
          Edit usage profile <Icon name="arrow" />
        </button>
      )}
    </>
  );
}
function ClaimDetail({
  claim,
  workspace,
  disabled,
  save,
  source,
  openClaim,
  initialNote,
}: {
  initialNote?: string;
  claim: Claim;
  workspace: Workspace;
  disabled: boolean;
  save: (
    status: string,
    note: string,
    revision: number,
  ) => Promise<number | undefined>;
  source: () => void;
  openClaim: (id: string) => void;
}) {
  const [status, setStatus] = useState(
    claim.review?.status || "needs-investigation",
  );
  const [note, setNote] = useState(initialNote ?? claim.review?.note ?? "");
  const [draftRevision, setDraftRevision] = useState(workspace.revision);
  const stale = draftRevision !== workspace.revision;
  const s = workspace.sources.find((s) => s.id === claim.source_id)!;
  return (
    <section className="panel claim-detail">
      <div className="section-heading">
        <span className="eyebrow">EVIDENCE DETAIL</span>
        <span className="badge neutral">v{s.version}</span>
      </div>
      <h2>{claim.entities.join(" · ") || "Source passage"}</h2>
      <blockquote>{claim.quote}</blockquote>
      <button className="source-link" onClick={source}>
        <Icon name="Sources" />
        {s.title}
        <span>↗</span>
      </button>
      <dl>
        <div>
          <dt>
            Change type <HelpHint topic="category" />
          </dt>
          <dd>{human(claim.category)}</dd>
        </div>
        <div>
          <dt>
            Usage match <HelpHint topic="usage" />
          </dt>
          <dd>
            {claim.applicable
              ? "Declared in your profile"
              : "No declared match"}
          </dd>
        </div>
        <div>
          <dt>
            Source position <HelpHint topic="sourcePosition" />
          </dt>
          <dd>
            Characters {claim.start + 1}–{claim.end}
          </dd>
        </div>
      </dl>
      {claim.conflicts.length > 0 && (
        <div className="conflict-note">
          <strong>Competing guidance for version {s.version}</strong>
          <p>
            Compare these passages. This is a conflict candidate, not a verified
            contradiction.
          </p>
          {claim.conflicts.map((id) => (
            <button
              className="text-button"
              key={id}
              data-tour="other-claim"
              onClick={() => openClaim(id)}
            >
              Read the other claim <Icon name="arrow" />
            </button>
          ))}
        </div>
      )}
      <div className="review-form">
        <h3>Record your review</h3>
        {stale && (
          <div className="draft-notice">
            <p className="small">
              Workspace changed since this draft opened. Your draft is
              preserved. Load the current review before saving.
            </p>
            <button
              className="text-button"
              onClick={() => {
                setStatus(claim.review?.status || "needs-investigation");
                setNote(claim.review?.note || "");
                setDraftRevision(workspace.revision);
              }}
            >
              Load current review
            </button>
          </div>
        )}
        {claim.review && (
          <p className="small muted" data-tour="saved-review">
            Last saved by {claim.review.by}: {human(claim.review.status)}
          </p>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save(status, note, draftRevision).then((savedRevision) => {
              if (savedRevision !== undefined) setDraftRevision(savedRevision);
            });
          }}
        >
          <label>
            Decision
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as typeof status)}
              disabled={disabled}
            >
              <option value="needs-investigation">Needs investigation</option>
              <option value="applicable">Applicable to our usage</option>
              <option value="not-applicable">
                Not applicable to our usage
              </option>
            </select>
          </label>
          <label>
            Review note
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="What did you verify? What remains unclear?"
              disabled={disabled}
            />
          </label>
          <button
            className="button primary full"
            data-tour="save-review"
            disabled={disabled || stale}
          >
            Save review
          </button>
          {disabled && (
            <p className="small muted">
              Reviews are saved in the live workspace.
            </p>
          )}
        </form>
      </div>
      <details>
        <summary>How this was produced</summary>
        <p className="small">
          A statistical classifier suggested the category (score{" "}
          {claim.score.toFixed(2)}). The score is not a calibrated risk
          probability. Entity matching and a conservative version-scoped rule
          suggest applicability and conflicts. Exact source passages are
          retained.
        </p>
      </details>
    </section>
  );
}
function SourceForm({
  disabled,
  save,
}: {
  disabled: boolean;
  save: (source: Record<string, string>) => Promise<void>;
}) {
  return (
    <section className="panel">
      <span className="eyebrow">ADD EVIDENCE</span>
      <h2>A versioned source.</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const data = Object.fromEntries(
            new FormData(e.currentTarget),
          ) as Record<string, string>;
          void save(data);
        }}
      >
        <label>
          Source title
          <input
            name="title"
            required
            maxLength={160}
            placeholder="Library 2.0 release notes"
            disabled={disabled}
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
              disabled={disabled}
            />
          </label>
          <label>
            Source URL (optional)
            <input
              name="url"
              type="url"
              maxLength={1000}
              placeholder="https://…"
              disabled={disabled}
            />
          </label>
        </div>
        <label>
          License / permission
          <input
            name="license"
            required
            maxLength={300}
            placeholder="MIT or your permission to use this text"
            disabled={disabled}
          />
        </label>
        <label>
          Source text
          <textarea
            name="text"
            required
            maxLength={12000}
            rows={7}
            placeholder="Paste release notes or documentation. One passage per line; keep identifiers in backticks when possible."
            disabled={disabled}
          />
        </label>
        <button className="button primary full" disabled={disabled}>
          Save source <Icon name="arrow" />
        </button>
        <p className="small muted">
          Source text stays in this workspace and its exports. Limit: 12,000
          characters per source.
        </p>
      </form>
    </section>
  );
}
function FeedForm({
  disabled,
  save,
}: {
  disabled: boolean;
  save: (data: Record<string, string>) => Promise<void>;
}) {
  return (
    <section className="panel feed">
      <details>
        <summary>Import a public GitHub release feed</summary>
        <p className="small muted">
          Fetch up to three releases. Confirm the content’s redistribution
          rights. No repository is changed.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void save(
              Object.fromEntries(new FormData(e.currentTarget)) as Record<
                string,
                string
              >,
            );
          }}
        >
          <label>
            Repository
            <input
              name="repository"
              required
              placeholder="owner/repository"
              pattern="[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
              disabled={disabled}
            />
          </label>
          <label>
            License or permission for the release text
            <input
              name="rights"
              required
              minLength={3}
              maxLength={300}
              disabled={disabled}
            />
          </label>
          <button className="button" disabled={disabled}>
            Fetch release snapshots
          </button>
        </form>
      </details>
    </section>
  );
}
function QuestionForm({
  disabled,
  provider,
  ask,
}: {
  disabled: boolean;
  provider: string;
  ask: (data: Record<string, unknown>) => Promise<void>;
}) {
  return (
    <form
      data-tour="question-form"
      onSubmit={(e) => {
        e.preventDefault();
        const d = new FormData(e.currentTarget);
        void ask({
          question: d.get("question"),
          mode: d.get("mode"),
          use_ai: d.get("use_ai") === "on",
        });
      }}
    >
      <label>
        Your question
        <textarea
          name="question"
          required
          maxLength={2000}
          rows={4}
          defaultValue="What affects Checkout service?"
          disabled={disabled}
        />
      </label>
      <label>
        Retrieval method
        <select name="mode" disabled={disabled}>
          <option value="graph">Graph + text evidence</option>
          <option value="vector">Text embeddings</option>
          <option value="lexical">Keyword baseline</option>
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          name="use_ai"
          data-help="generation"
          disabled={disabled}
        />
        Draft an answer with {provider}
      </label>
      <button
        className="button primary full"
        data-tour="ask"
        disabled={disabled}
      >
        Ask the evidence <Icon name="arrow" />
      </button>
    </form>
  );
}
function GraphView({
  workspace,
  openClaim,
  initialFocus,
}: {
  workspace: Workspace;
  openClaim: (id: string) => void;
  initialFocus?: string;
}) {
  const nodes = workspace.graph.nodes;
  const [focus, setFocus] = useState(initialFocus || "");
  const center =
    nodes.find((n) => n.id === focus) ||
    nodes.find((n) => n.kind === "entity") ||
    nodes[0];
  const related = useMemo(() => {
    if (!center) return [];
    const neighbors = new Set(
      workspace.graph.edges.flatMap((e) =>
        e.source === center.id
          ? [e.target]
          : e.target === center.id
            ? [e.source]
            : [],
      ),
    );
    return nodes.filter((n) => neighbors.has(n.id));
  }, [center, nodes, workspace.graph.edges]);
  const displayed = related.slice(0, 16);
  return (
    <div className="graph-layout">
      <section className="panel graph-panel">
        <div className="section-heading">
          <h2>Evidence neighborhood</h2>
          <span className="small muted">
            {nodes.length} nodes · {workspace.graph.edges.length} links
          </span>
        </div>
        <label>
          Focus on an entity or component
          <select
            value={center?.id || ""}
            onChange={(e) => setFocus(e.target.value)}
          >
            {nodes
              .filter((n) => n.kind === "entity" || n.kind === "component")
              .map((n) => (
                <option key={n.id} value={n.id}>
                  {n.label} ({n.kind})
                </option>
              ))}
          </select>
        </label>
        {center && (
          <svg
            className="graph-canvas"
            viewBox="0 0 620 420"
            role="img"
            aria-label={`Evidence connections for ${center.label}. The accessible list follows.`}
          >
            {displayed.map((n, i) => {
              const a = (i * 2 * Math.PI) / displayed.length;
              const x = 310 + 220 * Math.cos(a),
                y = 210 + 150 * Math.sin(a);
              return (
                <g key={n.id}>
                  <line x1="310" y1="210" x2={x} y2={y} stroke="#c8d5ce" />
                  <circle
                    cx={x}
                    cy={y}
                    r="12"
                    fill={
                      n.kind === "claim"
                        ? "#e5b975"
                        : n.kind === "component"
                          ? "#223d36"
                          : "#8ba998"
                    }
                  />
                  <text
                    x={x}
                    y={y + 29}
                    textAnchor="middle"
                    fill="#3b514a"
                    fontSize="11"
                  >
                    {n.label.slice(0, 24)}
                  </text>
                </g>
              );
            })}
            <circle cx="310" cy="210" r="42" fill="#1c5a49" />
            <text
              x="310"
              y="213"
              textAnchor="middle"
              fill="white"
              fontSize="12"
            >
              {center.label.slice(0, 20)}
            </text>
          </svg>
        )}
        <div className="graph-legend">
          <span>
            <i className="legend-claim" />
            Evidence
          </span>
          <span>
            <i className="legend-entity" />
            Entity / source
          </span>
          <span>
            <i className="legend-component" />
            Component
          </span>
        </div>
        <p className="small muted">
          The diagram shows up to 16 immediate neighbors. All neighbors appear
          in the list. A connection identifies cited evidence, not causation.
        </p>
      </section>
      <section className="panel">
        <span className="eyebrow">CONNECTED EVIDENCE</span>
        <h2>{center?.label || "No graph yet"}</h2>
        <p className="small muted">{related.length} direct connections</p>
        {related.map((n) => (
          <button
            className="graph-row"
            key={n.id}
            onClick={() =>
              n.kind === "claim" ? openClaim(n.id) : setFocus(n.id)
            }
          >
            <span className="badge neutral">{n.kind}</span>
            <span>{n.label}</span>
            <Icon name="arrow" />
          </button>
        ))}
      </section>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
