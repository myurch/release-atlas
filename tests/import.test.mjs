import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { build } from "esbuild";
const result = await build({
  entryPoints: ["frontend/import.ts"],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const { validateSnapshot } = await import(
  "data:text/javascript;base64," +
    Buffer.from(result.outputFiles[0].text).toString("base64")
);
const demo = JSON.parse(readFileSync("data/demo-snapshot.json", "utf8"));
const hash = (s) => createHash("sha256").update(s).digest("hex");
test("source action previews reject unsupported operations, stale revisions and altered delete targets", async () => {
  const bundled = await build({
    entryPoints: ["frontend/source-actions.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const { validatedSourceAction } = await import(
    "data:text/javascript;base64," +
      Buffer.from(bundled.outputFiles[0].text).toString("base64")
  );
  const source = demo.sources[0];
  const plan = {
    action: "delete_source",
    source_id: source.id,
    source,
    removed_findings: 1,
    removed_answers: 0,
    token: "a".repeat(43),
    revision: demo.revision,
  };
  assert.equal(validatedSourceAction(null, demo), undefined);
  assert.deepEqual(validatedSourceAction(plan, demo), plan);
  for (const changes of [
    { action: "execute_sql" },
    { revision: demo.revision + 1 },
    { token: "bad" },
    { source_id: "s-" + "0".repeat(20) },
    { removed_findings: -1 },
    { source: { ...source, text: "Changed source" } },
  ])
    assert.throws(() => validatedSourceAction({ ...plan, ...changes }, demo));
});
test("original generated snapshot round trips including graph, quotes and identifiers", async () => {
  assert.deepEqual(
    await validateSnapshot(JSON.parse(JSON.stringify(demo))),
    demo,
  );
});
test("batch previews validate every item and reject duplicate or altered deletion targets", async () => {
  const bundled = await build({
    entryPoints: ["frontend/source-actions.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const { validatedSourceAction, sourceActionLabel } = await import(
    "data:text/javascript;base64," +
      Buffer.from(bundled.outputFiles[0].text).toString("base64")
  );
  const items = demo.sources
    .slice(0, 2)
    .map((source) => ({ source_id: source.id, source }));
  const plan = {
    ...items[0],
    action: "delete_source",
    items,
    match_text: "apples",
    removed_findings: 2,
    removed_answers: 1,
    token: "a".repeat(43),
    revision: demo.revision,
  };
  assert.deepEqual(validatedSourceAction(plan, demo), plan);
  assert.equal(sourceActionLabel(plan), "Delete 2 sources");
  for (const altered of [
    [],
    [items[0], items[0]],
    [items[1], items[0]],
    [
      items[0],
      { ...items[1], source: { ...items[1].source, text: "injected" } },
    ],
    [items[0], null],
    Array(31).fill(items[0]),
  ]) {
    assert.throws(() =>
      validatedSourceAction({ ...plan, items: altered }, demo),
    );
  }
});
test("README preview preserves exact text and draft metadata, rejects stale or unsafe responses, and explains service failures", async () => {
  const bundled = await build({
    entryPoints: ["frontend/readme.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const {
    validateReadmePreview,
    applyReadmeDraft,
    emptySourceDraft,
    readmeFailureMessage,
  } = await import(
    "data:text/javascript;base64," +
      Buffer.from(bundled.outputFiles[0].text).toString("base64")
  );
  const commit = "a".repeat(40);
  const value = {
    revision: 3,
    repository: "example/project",
    commit,
    path: "README.md",
    source: {
      title: "example/project README",
      version: "commit:" + commit,
      url: `https://github.com/example/project/blob/${commit}/README.md`,
      license: "User supplied; verify redistribution rights",
      text: "# 🧭 Café\r\n\t<script>inert()</script>\n",
    },
  };
  assert.equal(validateReadmePreview(value, 3), value);
  const empty = applyReadmeDraft(emptySourceDraft(), value);
  assert.equal(empty.text, value.source.text);
  assert.equal(empty.title, value.source.title);
  assert.equal(empty.version, value.source.version);
  assert.equal(
    empty.license,
    "",
    "Fetching must not assert permission on the user's behalf",
  );
  const draft = {
    title: "My title",
    version: "2",
    url: "https://example.org",
    text: "Keep me",
    license: "My permission",
  };
  const before = structuredClone(draft);
  const replaced = applyReadmeDraft(draft, value);
  assert.equal(replaced.title, draft.title);
  assert.equal(replaced.version, draft.version);
  assert.equal(replaced.license, draft.license);
  assert.equal(replaced.text, value.source.text);
  assert.equal(replaced.url, value.source.url);
  assert.deepEqual(draft, before);
  for (const changes of [
    { revision: 4 },
    { commit: "bad" },
    { source: { ...value.source, text: "bad\u0000" } },
    { source: { ...value.source, text: "x".repeat(12001) } },
    { source: { ...value.source, url: "http://127.0.0.1/private" } },
    { source: { ...value.source, version: "latest" } },
  ])
    assert.throws(() => validateReadmePreview({ ...value, ...changes }, 3));
  assert.match(readmeFailureMessage({ name: "AbortError" }), /took too long/);
  assert.match(
    readmeFailureMessage(new TypeError("sensitive network details")),
    /Atlas service/,
  );
  assert.doesNotMatch(
    readmeFailureMessage(new TypeError("sensitive network details")),
    /sensitive/,
  );
  assert.match(
    readmeFailureMessage(new Error("This repository has no README")),
    /no README/,
  );
  assert.match(readmeFailureMessage(null), /draft is unchanged/);
});
test("README controls appear only when live fetching is provided and never fetch automatically", async () => {
  const bundled = await build({
    stdin: {
      contents: `import React from "react"; import {renderToStaticMarkup} from "react-dom/server.node"; import {SourceForm} from "./frontend/SourceForm"; export const render = (props) => renderToStaticMarkup(React.createElement(SourceForm, props));`,
      resolveDir: process.cwd(),
      loader: "tsx",
    },
    bundle: true,
    write: false,
    platform: "node",
    format: "cjs",
    define: { "process.env.NODE_ENV": '"production"' },
  });
  const module = { exports: {} };
  // Execute only our locally bundled component, with Node's renderer so no
  // browser scheduler handles remain open after this static rendering check.
  new Function("require", "module", "exports", bundled.outputFiles[0].text)(
    createRequire(import.meta.url),
    module,
    module.exports,
  );
  const { render } = module.exports;
  let calls = 0;
  const html = render({
    disabled: false,
    revision: 0,
    save: async () => {},
    fetchReadme: async () => {
      calls++;
    },
  });
  assert.match(html, /<h2>Add Evidence<\/h2>/);
  assert.doesNotMatch(
    html,
    /A versioned source|name="license"|License \/ permission/,
  );
  assert.match(html, /Fetch a public GitHub README/);
  assert.match(html, /Public GitHub repository URL/);
  assert.match(html, /Fetching does not save/);
  assert.equal(calls, 0);
  const offline = render({ disabled: true, revision: 0, save: async () => {} });
  assert.doesNotMatch(
    offline,
    /Public GitHub repository URL|Fetch a public GitHub README/,
  );
});
test("reject altered citations, source hashes, identities, graph references and unsafe URLs", async () => {
  const mutations = [
    (s) => (s.claims[0].quote = "<script>alert(1)</script>"),
    (s) => (s.sources[0].text += "changed"),
    (s) => (s.claims[0].id = "fake"),
    (s) => (s.sources[0].url = "javascript:alert(1)"),
    (s) =>
      s.graph.nodes.push({
        id: "missing",
        kind: "claim",
        label: "fake",
        degree: 0,
      }),
    (s) =>
      s.answers.push({
        id: "a",
        question: "q",
        answer: "x",
        citations: ["fake"],
        uncertainty: "",
        method: "test",
        at: "",
      }),
    (s) => (s.usage[0].entity = "<bad>"),
    (s) => (s.claims[0].score = NaN),
    (s) => (s.sources[0].title = "\ud800"),
    (s) => (s.schema_version = 2),
    (s) => s.claims.push({ ...s.claims[0] }),
    (s) => (s.graph.edges[0].target = "missing"),
  ];
  for (const mutate of mutations) {
    const changed = structuredClone(demo);
    mutate(changed);
    await assert.rejects(validateSnapshot(changed), /Invalid saved analysis/);
  }
});
test("saved imports reject invalid controls while preserving literal SQL and code text", async () => {
  for (const control of ["\u0000", "\u0001", "\u000b", "\u001b", "\u007f"]) {
    const changed = structuredClone(demo);
    changed.title += control;
    await assert.rejects(validateSnapshot(changed), /Invalid saved analysis/);
  }
  const changed = structuredClone(demo);
  changed.title = "x'); DROP TABLE workspace; -- 🧭";
  assert.deepEqual(await validateSnapshot(changed), changed);
});
test("Unicode citation offsets use code points, not UTF-16 offsets", async () => {
  const text = "🧭\nAdded `new_api`.";
  const sha256 = hash(text);
  const source = {
    id: "s-" + hash("2\0" + sha256).slice(0, 20),
    title: "Unicode",
    version: "2",
    text,
    url: "",
    license: "original synthetic",
    sha256,
  };
  const quote = "Added `new_api`.";
  const claim = {
    ...demo.claims[0],
    id: "c-" + hash(source.id + "\0" + "2" + "\0" + quote).slice(0, 20),
    source_id: source.id,
    start: 2,
    end: 18,
    quote,
    entities: ["new_api"],
    conflicts: [],
    review: null,
    document: {
      ...demo.claims[0].document,
      mentions: [
        {
          name: "new_api",
          normalized: "new_api",
          kind: "api",
          start: 9,
          end: 16,
          rule: "quoted-identifier",
        },
      ],
    },
  };
  claim.end = 2 + Array.from(quote).length;
  const snapshot = {
    ...demo,
    sources: [source],
    claims: [claim],
    topics: [],
    analysis: null,
    graph: { nodes: [], edges: [] },
    answers: [],
  };
  assert.deepEqual(await validateSnapshot(snapshot), snapshot);
});
test("HTML contains inline runtime and styles with no external asset dependency", () => {
  const html = readFileSync("dist/release-atlas.html", "utf8");
  assert(!/<script[^>]+src\s*=/i.test(html));
  assert(!/<link[^>]+(?:stylesheet|preload)/i.test(html));
  assert(!/@import|url\(\s*['"]?https?:/i.test(html));
  assert(html.includes("SYNTHETIC EXAMPLE"));
  assert(html.length < 2000000);
});

test("appearance respects overrides and defaults dark when no host theme is available", async () => {
  const result = await build({
    entryPoints: ["frontend/theme.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const theme = await import(
    "data:text/javascript;base64," +
      Buffer.from(result.outputFiles[0].text).toString("base64")
  );
  assert.equal(theme.resolveTheme("system", false, false), "dark");
  assert.equal(theme.resolveTheme("system", true, false), "light");
  assert.equal(theme.resolveTheme("system", false, true), "dark");
  assert.equal(theme.resolveTheme("dark", true, false), "dark");
  assert.equal(theme.resolveTheme("light", false, true), "light");
  assert.equal(
    theme.readPreference({
      getItem: () => {
        throw new Error("unavailable");
      },
    }),
    "system",
  );
  assert.equal(theme.readPreference({ getItem: () => "unknown" }), "system");
  assert.equal(theme.readPreference({ getItem: () => "dark" }), "dark");
});

test("tutorial replay is deterministic and preserves the original workspace and valid citations", async () => {
  const bundled = await build({
    entryPoints: ["frontend/tutorial.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const tutorial = await import(
    "data:text/javascript;base64," +
      Buffer.from(bundled.outputFiles[0].text).toString("base64")
  );
  const original = JSON.stringify(demo);
  assert(tutorial.visibleTutorialSteps.length < tutorial.tutorialSteps.length);
  for (const [index, step] of tutorial.visibleTutorialSteps.entries()) {
    assert.notEqual(step.tab, "Questions");
    assert.doesNotMatch(step.target, /nav-Questions|edit-usage/);
    assert.doesNotMatch(step.after || "", /export|usage-editor|question-form/);
    const originalIndex = tutorial.tutorialStepIndex(index);
    assert(originalIndex >= 0);
    assert.equal(tutorial.tutorialSteps[originalIndex].target, step.target);
    await validateSnapshot(tutorial.tutorialWorkspace(demo, originalIndex));
  }
  assert.equal(
    tutorial.tutorialStepIndex(tutorial.visibleTutorialSteps.length - 1),
    tutorial.tutorialSteps.length - 1,
  );
  for (let step = 0; step < tutorial.tutorialSteps.length; step++) {
    const state = tutorial.tutorialWorkspace(demo, step);
    await validateSnapshot(state);
    assert.deepEqual(state, tutorial.tutorialWorkspace(demo, step));
    state.title = "Changed isolated state";
    state.claims[0].quote = "Changed isolated claim";
    assert.equal(JSON.stringify(demo), original);
  }
  const reviewed = tutorial.addTutorialReview(
    tutorial.tutorialWorkspace(demo, 8),
  );
  assert.equal(
    tutorial.tutorialClaim(reviewed).review.note,
    tutorial.REVIEW_NOTE,
  );
  const answered = tutorial.addTutorialAnswer(
    tutorial.tutorialWorkspace(demo, 11),
  );
  await validateSnapshot(answered);
  assert(
    answered.answers[0].citations.every((id) =>
      answered.claims.some((c) => c.id === id),
    ),
  );
  assert(answered.answers[0].method.includes("Prepared tutorial"));
  assert.equal(
    tutorial.tutorialWorkspace(demo, 7).claims.filter((c) => c.review).length,
    0,
  );
  assert.equal(
    tutorial.tutorialWorkspace(demo, 14).claims.filter((c) => c.review).length,
    1,
  );
  await validateSnapshot(tutorial.emptyWorkspace());
  assert.equal(JSON.stringify(demo), original);
});

test("built-in guide handles empty, unanalyzed and ready reviews without inventing model answers", async () => {
  const result = await build({
    entryPoints: ["frontend/guide.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const { guideReply } = await import(
    "data:text/javascript;base64," +
      Buffer.from(result.outputFiles[0].text).toString("base64")
  );
  const empty = { ...demo, sources: [], analysis: null };
  assert.match(
    guideReply("Overview", empty, "What should I do next?"),
    /add versioned release notes/,
  );
  assert.match(
    guideReply(
      "Sources",
      { ...demo, analysis: null },
      "What should I do next?",
    ),
    /Choose Analyze sources/,
  );
  assert.match(
    guideReply("Graph", demo, "Explain this page simply"),
    /Connections in the evidence/,
  );
  assert.match(
    guideReply("Questions", demo, "How does vector retrieval work?"),
    /statistical text similarity/,
  );
  assert.match(
    guideReply("Sources", demo, "Can I upload a PDF?"),
    /Paste text/,
  );
  assert.match(
    guideReply("Overview", demo, "What is the capital of France?"),
    /use Model chat/,
  );
  for (const question of [
    "What should I do next?",
    "Can I upload a PDF?",
    "How do I save a decision?",
    "Use a model",
  ])
    assert.match(
      guideReply("Overview", demo, question, true),
      /full application/,
    );
  assert.doesNotMatch(
    guideReply("Overview", demo, "What should I do next?", true),
    /Choose Analyze sources|save a decision with your reasoning/,
  );
  assert.match(
    guideReply("Overview", demo, "What is the capital of France?", true),
    /not live AI answers/,
  );
  const help = await build({
    entryPoints: ["frontend/help-content.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const content = await import(
    "data:text/javascript;base64," +
      Buffer.from(help.outputFiles[0].text).toString("base64")
  );
  for (const key of Object.values(content.helpLabels))
    assert(content.help[key], "Missing help: " + key);
});

test("help placement avoids the next form control and stays inside small viewports", async () => {
  const result = await build({
    entryPoints: ["frontend/help-layout.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const { placeHelp } = await import(
    "data:text/javascript;base64," +
      Buffer.from(result.outputFiles[0].text).toString("base64")
  );
  const field = { left: 400, right: 800, top: 500, bottom: 540 };
  const form = { left: 400, right: 800, top: 300, bottom: 650 };
  const right = placeHelp(field, form, 340, 210, 1440, 900);
  assert(right.x >= form.right + 12);
  const mobile = placeHelp(
    { left: 20, right: 370, top: 500, bottom: 540 },
    { left: 20, right: 370, top: 150, bottom: 650 },
    340,
    210,
    390,
    700,
  );
  assert(
    mobile.y + 210 < 500,
    "Mobile help should stay above the focused field and submit action",
  );
  for (const [w, h] of [
    [390, 844],
    [320, 480],
    [1440, 900],
  ]) {
    const pos = placeHelp(
      { left: 10, right: w - 10, top: h - 40, bottom: h - 10 },
      { left: 10, right: w - 10, top: 20, bottom: h - 10 },
      Math.min(340, w - 24),
      210,
      w,
      h,
    );
    assert(pos.x >= 12 && pos.y >= 12 && pos.y + 210 <= h - 12);
  }
});

test("source citations verify exact Unicode passages, source identity and bounds", async () => {
  const bundled = await build({
    entryPoints: ["frontend/source-citations.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const { validatedSourcePassages } = await import(
    "data:text/javascript;base64," +
      Buffer.from(bundled.outputFiles[0].text).toString("base64")
  );
  const source = { id: "s-synthetic", sha256: "hash", text: "🧭Résumé source" };
  const passage = {
    id: "p-s-synthetic-1-7",
    source_id: source.id,
    sha256: source.sha256,
    start: 1,
    end: 7,
    quote: "Résumé",
  };
  assert.deepEqual(validatedSourcePassages([passage], [passage.id], [source]), [
    passage,
  ]);
  for (const mutate of [
    (p) => (p.sha256 = "changed"),
    (p) => (p.source_id = "other-workspace"),
    (p) => (p.quote = "Invented text"),
    (p) => (p.start = -1),
    (p) => (p.end = 200),
    (p) => (p.id = "invented"),
  ]) {
    const changed = { ...passage };
    mutate(changed);
    assert.throws(() =>
      validatedSourcePassages([changed], [changed.id], [source]),
    );
  }
  assert.throws(() =>
    validatedSourcePassages([passage], ["unknown"], [source]),
  );
  assert.throws(() =>
    validatedSourcePassages(
      [passage, passage],
      [passage.id, passage.id],
      [source],
    ),
  );
});

test("pipeline filters compose exact section, topic membership, purpose and typed entity identity", async () => {
  const bundled = await build({
    entryPoints: ["frontend/pipeline.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const {
    emptyPassageFilters,
    matchesPassage,
    technicalInventory,
    sectionKey,
    entityKey,
  } = await import(
    "data:text/javascript;base64," +
      Buffer.from(bundled.outputFiles[0].text).toString("base64")
  );
  const claim = demo.claims.find(
    (c) => c.document?.mentions.length && c.topic > 0,
  );
  assert(claim, "Build the documentation pipeline snapshot before this check");
  const mention = claim.document.mentions[0];
  const filters = {
    ...emptyPassageFilters(),
    source: claim.source_id,
    section: sectionKey(claim),
    purpose: claim.document.purpose,
    entity: entityKey(mention),
    topic: claim.topic,
  };
  assert.equal(matchesPassage(claim, filters), true);
  assert.equal(
    matchesPassage(
      { ...claim, quote: "No topic keywords need to appear here" },
      filters,
    ),
    true,
  );
  for (const changed of [
    { source: "another-source" },
    { section: '["another section"]' },
    { purpose: "not-the-purpose" },
    { entity: "not-the-entity" },
    { topic: 999 },
  ])
    assert.equal(matchesPassage(claim, { ...filters, ...changed }), false);
  const inventory = technicalInventory(demo);
  const row = inventory.find((r) => r.key === entityKey(mention));
  assert(row.passageIds.has(claim.id));
  assert(row.sourceIds.has(claim.source_id));
  assert(row.mentions >= row.passageIds.size);
});

test("documentation imports validate typed spans and metrics while accepting legacy snapshots", async () => {
  const original = structuredClone(demo);
  assert(original.analysis.pipeline);
  await validateSnapshot(original);
  const claimIndex = demo.claims.findIndex((c) => c.document?.mentions.length);
  for (const mutate of [
    (s) => (s.claims[claimIndex].document.mentions[0].name = "fabricated"),
    (s) =>
      (s.claims[claimIndex].document.mentions[0].normalized = "fabricated"),
    (s) => (s.claims[claimIndex].document.mentions[0].start = 999999),
    (s) => (s.claims[claimIndex].document.mentions[0].kind = "execute"),
    (s) => (s.claims[claimIndex].document.alternatives[0].score = 2),
    (s) => (s.claims[claimIndex].document.headings = ["bad\u0000heading"]),
    (s) => (s.topics[0].representatives = ["missing-passage"]),
    (s) => (s.topics[0].weights = [-1]),
    (s) => (s.analysis.pipeline.evaluation.macro_f1 = 2),
  ]) {
    const changed = structuredClone(demo);
    mutate(changed);
    await assert.rejects(() => validateSnapshot(changed));
  }
  const legacy = structuredClone(demo);
  legacy.claims.forEach((c) => delete c.document);
  delete legacy.analysis.pipeline;
  legacy.topics.forEach((t) => {
    delete t.weights;
    delete t.representatives;
    delete t.source_count;
  });
  assert.equal(
    (await validateSnapshot(legacy)).claims.length,
    demo.claims.length,
  );
});

test("NLP explorer exposes all four stages, source structure and inspectable methods with escaped source metadata", async () => {
  const bundled = await build({
    stdin: {
      contents: `import React from "react"; import {renderToStaticMarkup} from "react-dom/server.node"; import {PipelineExplorer,PassageMethods} from "./frontend/PipelineExplorer"; export const explorer = (props) => renderToStaticMarkup(React.createElement(PipelineExplorer,props)); export const methods=(props)=>renderToStaticMarkup(React.createElement(PassageMethods,props));`,
      resolveDir: process.cwd(),
      loader: "tsx",
    },
    bundle: true,
    write: false,
    platform: "node",
    format: "cjs",
    define: { "process.env.NODE_ENV": '"production"' },
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", bundled.outputFiles[0].text)(
    createRequire(import.meta.url),
    module,
    module.exports,
  );
  const { explorer, methods } = module.exports;
  let calls = 0;
  const state = structuredClone(demo);
  state.sources[0].title = '<img src=x onerror="alert(1)">';
  const props = {
    workspace: state,
    filters: { source: "", section: "", purpose: "", entity: "", topic: null },
    setFilters: () => calls++,
    openPassage: () => calls++,
  };
  const html = explorer(props);
  for (const label of [
    "DOCUMENTATION NLP PIPELINE",
    "Text analytics",
    "Embedding classification",
    "Topic modeling",
    "Technical entities",
    "Document map",
    "Methods and limits",
    "Keyword baseline",
  ])
    assert(html.includes(label), label);
  assert(html.includes("&lt;img"));
  assert(!html.includes("<img src=x"));
  assert.equal(calls, 0);
  const detail = methods({
    claim: demo.claims.find((c) => c.document?.mentions.length),
  });
  assert(
    detail.includes("Competing purpose labels") &&
      detail.includes("Exact technical mentions"),
  );
  assert(detail.includes("cosine"));
  const legacy = { ...state, analysis: { ...state.analysis, pipeline: null } };
  assert(explorer({ ...props, workspace: legacy }).includes("Older snapshots"));
});

test("retrieved context verifies all selected source spans, reason allowlists and current workspace identities", async () => {
  const bundled = await build({
    entryPoints: ["frontend/retrieval.ts"],
    bundle: true,
    write: false,
    platform: "node",
    format: "esm",
  });
  const { validatedRetrieval } = await import(
    "data:text/javascript;base64," +
      Buffer.from(bundled.outputFiles[0].text).toString("base64")
  );
  const claim = demo.claims[0],
    source = demo.sources.find((s) => s.id === claim.source_id);
  const passage = {
    id: `p-${source.id}-${claim.start}-${claim.end}`,
    source_id: source.id,
    sha256: source.sha256,
    start: claim.start,
    end: claim.end,
    quote: claim.quote,
    reasons: ["semantic match", "related topic"],
  };
  const report = {
    encoder: "neural-minilm",
    mode: "focused",
    model: "MiniLM",
    included_sources: 1,
    total_sources: demo.sources.length,
    candidate_count: 12,
    partial: true,
    fallback: "",
    notices: [],
    passages: [passage],
  };
  assert.deepEqual(validatedRetrieval(report, demo.sources), report);
  assert.equal(validatedRetrieval(undefined, demo.sources), undefined);
  for (const change of [
    (r) => (r.passages[0].quote = "fabricated"),
    (r) => (r.passages[0].source_id = "other-workspace"),
    (r) => (r.passages[0].sha256 = "changed"),
    (r) => (r.passages[0].reasons = ["execute code"]),
    (r) => (r.passages[0].start = -1),
    (r) => (r.passages = [r.passages[0], r.passages[0]]),
    (r) => (r.candidate_count = 601),
    (r) => (r.included_sources = 2),
    (r) => (r.total_sources = 99),
    (r) => (r.notices = ["bad\u0000control"]),
    (r) => (r.encoder = "unverified-encoder"),
  ]) {
    const altered = structuredClone(report);
    change(altered);
    assert.throws(() => validatedRetrieval(altered, demo.sources));
  }
});

test("retrieval disclosure renders selected context and fallback visibly as escaped text without invoking navigation", async () => {
  const bundled = await build({
    stdin: {
      contents: `import React from "react"; import {renderToStaticMarkup} from "react-dom/server.node"; import {RetrievedContext} from "./frontend/RetrievedContext"; export const render=(props)=>renderToStaticMarkup(React.createElement(RetrievedContext,props));`,
      resolveDir: process.cwd(),
      loader: "tsx",
    },
    bundle: true,
    write: false,
    platform: "node",
    format: "cjs",
    define: { "process.env.NODE_ENV": '"production"' },
  });
  const module = { exports: {} };
  new Function("require", "module", "exports", bundled.outputFiles[0].text)(
    createRequire(import.meta.url),
    module,
    module.exports,
  );
  const source = {
    ...demo.sources[0],
    title: '<img src=x onerror="alert(1)">',
  };
  const report = {
    encoder: "statistical-lsa",
    mode: "focused",
    model: "local LSA",
    included_sources: 1,
    total_sources: 1,
    candidate_count: 2,
    partial: true,
    fallback: "Neural encoder unavailable.",
    notices: ["Topic model unavailable."],
    passages: [
      {
        id: "p",
        source_id: source.id,
        sha256: source.sha256,
        start: 0,
        end: 6,
        quote: "<script>alert(1)</script>",
        reasons: ["lexical match", "exact entity"],
      },
    ],
  };
  let calls = 0;
  const html = module.exports.render({
    report,
    sources: [source],
    openSource: () => calls++,
  });
  for (const label of [
    "Retrieved context",
    "Statistical fallback",
    "Neural encoder unavailable",
    "lexical match",
    "exact entity",
    "Only selected passages",
    "Topic model unavailable",
  ])
    assert(html.includes(label), label);
  assert(html.includes("&lt;script&gt;") && html.includes("&lt;img"));
  assert(!html.includes("<script>") && !html.includes("<img src=x"));
  assert.equal(calls, 0);
  assert(
    module.exports
      .render({
        report: {
          ...report,
          encoder: "neural-minilm",
          fallback: "",
          passages: [],
          included_sources: 0,
        },
        sources: [source],
        openSource: () => {},
      })
      .includes("No sufficiently relevant passages"),
  );
});
