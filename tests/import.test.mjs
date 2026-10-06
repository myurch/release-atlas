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
  assert(html.length < 500000);
});
