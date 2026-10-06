import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
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
test("original generated snapshot round trips including graph, quotes and identifiers", async () => {
  assert.deepEqual(
    await validateSnapshot(JSON.parse(JSON.stringify(demo))),
    demo,
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
  };
  claim.end = 2 + Array.from(quote).length;
  const snapshot = {
    ...demo,
    sources: [source],
    claims: [claim],
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
