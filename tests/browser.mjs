import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import {
  mkdtempSync,
  readFileSync,
  writeFileSync,
  mkdirSync,
  existsSync,
} from "node:fs";
import path from "node:path";
import os from "node:os";
import assert from "node:assert/strict";

const root = process.cwd();
const work = os.tmpdir();
const temp = mkdtempSync(path.join(work, "atlas-browser-"));
const port = 18876;
const base = `http://127.0.0.1:${port}`;
const code = "isolated-browser-fixture";
const server = spawn(path.join(root, ".venv/bin/python"), ["-m", "backend"], {
  cwd: root,
  env: {
    ...process.env,
    PYTHONDONTWRITEBYTECODE: "1",
    ATLAS_DATA_DIR: temp,
    ATLAS_PORT: String(port),
    ATLAS_ORIGINS: base,
    ATLAS_ACCESS_CODE: code,
    ATLAS_AUTH_ENABLED: "1",
  },
  stdio: ["ignore", "pipe", "pipe"],
});
let serverLog = "";
server.stdout.on("data", (b) => (serverLog += b));
server.stderr.on("data", (b) => (serverLog += b));
let browser;
let demoServer;
let directServer;
const checks = [];
const errors = [];
function observe(page) {
  page.on("pageerror", (e) => errors.push(e.message));
}
async function login(page, name) {
  await page.goto(base);
  await page.getByLabel("Display name").fill(name);
  await page.getByLabel("Workspace access code", { exact: true }).fill(code);
  await page.getByLabel("Display name", { exact: true }).focus();
  await page.getByLabel("Workspace access code", { exact: true }).focus();
  // Let field help open so this catches tooltips that intercept the submit button.
  await page.getByRole("tooltip").waitFor();
  await page.getByRole("button", { name: "Enter workspace" }).click();
  await page.getByRole("dialog").waitFor({ state: "hidden" });
}
try {
  let ready = false;
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(base + "/api/health")).ok) {
        ready = true;
        break;
      }
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  assert(ready, "Server failed to start: " + serverLog);
  const chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  browser = await chromium.launch({
    headless: true,
    ...(existsSync(chrome) ? { executablePath: chrome } : {}),
  });
  const a = await browser.newContext({
    viewport: { width: 1440, height: 1080 },
    acceptDownloads: true,
  });
  const b = await browser.newContext({
    viewport: { width: 1280, height: 900 },
  });
  const page = await a.newPage();
  observe(page);
  await login(page, "Alex");
  const tutorialBefore = await page.request.get(base + "/api/state");
  const tutorialSnapshot = await tutorialBefore.json();
  await page
    .getByRole("button", { name: "Beginner tutorial", exact: true })
    .click();
  while (
    await page.getByRole("button", { name: "Next", exact: true }).count()
  ) {
    await page.getByRole("button", { name: "Next", exact: true }).click();
  }
  await page.getByRole("button", { name: "Finish tutorial" }).click();
  assert.deepEqual(
    await (await page.request.get(base + "/api/state")).json(),
    tutorialSnapshot,
  );
  checks.push(
    "All beginner tutorial steps complete without changing the real workspace",
  );
  await page.request.post(base + "/api/demo", {
    data: { revision: 0 },
    headers: { Origin: base },
  });
  await page.reload();
  await page
    .getByRole("heading", {
      name: "Understand the docs. Trace the evidence.",
      exact: true,
    })
    .waitFor();
  mkdirSync("validation/screenshots", { recursive: true });
  await page.screenshot({
    path: "validation/screenshots/desktop.png",
    fullPage: true,
  });
  checks.push("Startup, login, original synthetic demo and overview");
  await page.getByLabel("Appearance", { exact: true }).selectOption("dark");
  await page.waitForFunction(
    () => getComputedStyle(document.body).backgroundColor === "rgb(9, 9, 11)",
  );
  const hint = page.getByRole("button", {
    name: "About Analyzed passages",
    exact: true,
  });
  await hint.focus();
  await page.getByRole("tooltip").waitFor();
  assert.match(await page.getByRole("tooltip").innerText(), /WHY IT MATTERS/);
  assert(await hint.getAttribute("aria-describedby"));
  await page.keyboard.press("Escape");
  await page.getByRole("tooltip").waitFor({ state: "hidden" });
  assert.equal(await hint.getAttribute("aria-describedby"), null);
  await page.getByLabel("Appearance", { exact: true }).selectOption("light");
  await page.waitForFunction(
    () =>
      getComputedStyle(document.body).backgroundColor === "rgb(245, 246, 248)",
  );
  await page.getByLabel("Appearance", { exact: true }).selectOption("dark");
  await page.emulateMedia({ reducedMotion: "reduce" });
  assert.equal(
    await page
      .locator(".stat")
      .first()
      .evaluate((el) => getComputedStyle(el).animationName),
    "none",
  );
  await page.emulateMedia({ reducedMotion: "no-preference" });
  checks.push(
    "Neutral dark/light themes, accessible help dismissal and reduced-motion preference",
  );

  const chatBefore = await (await page.request.get(base + "/api/state")).json();
  await page
    .getByRole("button", { name: "Open assistant", exact: true })
    .click();
  await page
    .getByLabel("Assistant mode", { exact: true })
    .selectOption("guide");
  await page
    .getByRole("button", { name: "What should I do next?", exact: true })
    .click();
  await page.getByText("Atlas · App guide", { exact: true }).waitFor();
  for (const title of [
    "Sources",
    "Graph",
    "Activity",
    "Evidence",
    "Overview",
  ]) {
    await page.getByRole("button", { name: title, exact: true }).click();
    assert.equal(await page.locator(".assistant-panel").isVisible(), true);
    assert.equal(await page.locator(".chat-turn").count(), 2);
  }
  assert.deepEqual(
    await (await page.request.get(base + "/api/state")).json(),
    chatBefore,
  );
  await page
    .getByRole("button", { name: "Close assistant", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Beginner tutorial", exact: true })
    .click();
  assert.equal(
    await page
      .getByRole("button", { name: "Open assistant", exact: true })
      .count(),
    0,
  );
  await page
    .getByRole("button", { name: "Exit tutorial", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Open assistant", exact: true })
    .click();
  assert.equal(await page.locator(".chat-turn").count(), 2);
  checks.push(
    "App guide persists across every page and tutorial round trip without workspace writes",
  );

  let chatRequest;
  const literalAnswer = "Check the source. <script>window.hacked=true</script>";
  await page.route("**/api/assistant", async (route) => {
    chatRequest = route.request().postDataJSON();
    await route.fulfill({
      json: {
        revision: chatRequest.revision,
        answer: literalAnswer,
        citations: [chatBefore.workspace.claims[0].id],
        uncertainty: "Verify the passage.",
      },
    });
  });
  await page
    .getByLabel("Assistant mode", { exact: true })
    .selectOption("model");
  await page
    .getByLabel("Message Atlas", { exact: true })
    .fill("Explain this evidence");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await page.getByText(literalAnswer, { exact: true }).waitFor();
  assert.equal(chatRequest.page, "Overview");
  assert.equal(chatRequest.history.length, 2);
  assert(!(await page.evaluate(() => window.hacked)));
  await page.locator(".assistant-panel .citation").click();
  await page
    .getByRole("heading", { name: "Explore the documentation." })
    .waitFor();
  assert.equal(await page.locator(".assistant-panel .chat-turn").count(), 4);
  await page
    .getByRole("button", { name: "Close assistant", exact: true })
    .click();
  await page.unroute("**/api/assistant");
  checks.push(
    "Model chat sends bounded page context, renders output as text and opens validated citations (mock provider)",
  );
  const peer = await b.newPage();
  observe(peer);
  await login(peer, "Blair");
  await peer.getByRole("button", { name: "Evidence", exact: true }).click();
  await page.getByRole("button", { name: "Evidence", exact: true }).click();
  await page.getByLabel("Review note").fill("Confirmed locally by Alex.");
  await page.getByRole("button", { name: "Save review", exact: true }).click();
  await peer.getByText("Last saved by Alex: needs investigation").waitFor();
  checks.push(
    "Two authenticated browser contexts observe a saved review through live revision events",
  );
  for (const label of ["Questions", "Import", "Export snapshot"])
    assert.equal(
      await page.getByRole("button", { name: label, exact: true }).count(),
      0,
    );
  const snapshot = (await (await page.request.get(base + "/api/state")).json())
    .workspace;
  assert(snapshot.audit.some((a) => a.by === "Alex"));
  const exportPath = path.join(temp, "snapshot.json");
  writeFileSync(exportPath, JSON.stringify(snapshot));
  checks.push(
    "Questions and snapshot buttons stay hidden; saved state retains review data",
  );
  const offline = await browser.newContext({
    viewport: { width: 390, height: 844 },
    acceptDownloads: true,
    offline: true,
  });
  const mobile = await offline.newPage();
  observe(mobile);
  const remoteRequests = [];
  mobile.on("request", (request) => {
    if (/^https?:/.test(request.url())) remoteRequests.push(request.url());
  });
  await mobile.goto("file://" + path.join(root, "dist/release-atlas.html"));
  await mobile
    .getByText("Understand the docs. Trace the evidence.", { exact: true })
    .waitFor();
  assert(
    await mobile.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
    "Mobile horizontal overflow",
  );
  await mobile.screenshot({
    path: "validation/screenshots/mobile.png",
    fullPage: true,
  });
  mobile.on("dialog", (dialog) => dialog.accept());
  await mobile.locator("input[type=file]").setInputFiles(exportPath);
  await mobile
    .getByText("Imported saved analysis.", { exact: false })
    .waitFor();
  await mobile.getByRole("button", { name: "Evidence", exact: true }).click();
  assert(
    await mobile
      .getByRole("button", { name: "Save review", exact: true })
      .isDisabled(),
  );
  checks.push(
    "Single HTML file works offline and retained import validation opens saved evidence without a backend",
  );
  assert.equal(
    remoteRequests.length,
    0,
    "Offline viewer must not request remote resources",
  );
  const forged = structuredClone(snapshot);
  forged.claims[0].quote = "<script>window.hacked=true</script>";
  const forgedPath = path.join(temp, "forged.json");
  writeFileSync(forgedPath, JSON.stringify(forged));
  await mobile.locator("input[type=file]").setInputFiles(forgedPath);
  await mobile
    .getByRole("alert")
    .filter({ hasText: "Invalid saved analysis" })
    .waitFor();
  assert(!(await mobile.evaluate(() => window.hacked)));
  checks.push(
    "Invalid citation snapshot rejected; imported text never executed",
  );
  for (const title of ["Overview", "Sources", "Graph", "Activity"]) {
    await mobile.getByRole("button", { name: title, exact: true }).click();
    assert(
      await mobile.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "Overflow on " + title,
    );
  }
  await mobile
    .getByRole("button", { name: "Open assistant", exact: true })
    .click();
  await mobile
    .getByRole("button", { name: "What should I do next?", exact: true })
    .click();
  await mobile.getByText("Atlas · App guide", { exact: true }).waitFor();
  assert.equal(await mobile.getByLabel("Assistant mode").inputValue(), "guide");
  assert(
    await mobile.locator(".assistant-panel").evaluate((el) => {
      const r = el.getBoundingClientRect();
      return (
        r.left >= 0 &&
        r.right <= innerWidth &&
        r.top >= 0 &&
        r.bottom <= innerHeight
      );
    }),
  );
  assert.equal(remoteRequests.length, 0);
  await mobile.screenshot({
    path: "validation/screenshots/mobile-assistant.png",
    fullPage: true,
  });
  checks.push(
    "Standalone mobile App guide fits the viewport and makes no remote requests",
  );

  let held;
  const requestArrived = new Promise((resolve) => {
    page.route("**/api/assistant", (route) => {
      held = route;
      resolve();
    });
  });
  await page
    .getByRole("button", { name: "Open assistant", exact: true })
    .click();
  await page
    .getByLabel("Message Atlas", { exact: true })
    .fill("Private old-workspace question");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  await requestArrived;
  const beforeSwitch = await (
    await page.request.get(base + "/api/state")
  ).json();
  await page.request.post(base + "/api/workspaces", {
    data: {
      revision: beforeSwitch.workspace.revision,
      title: "New isolated review",
    },
    headers: { Origin: base },
  });
  await page
    .getByText("New isolated review", { exact: true })
    .first()
    .waitFor();
  await page
    .getByRole("button", { name: "Open assistant", exact: true })
    .click();
  assert.equal(await page.locator(".chat-turn").count(), 0);
  assert.equal(await page.getByLabel("Message Atlas").inputValue(), "");
  await held
    .fulfill({
      json: {
        revision: beforeSwitch.workspace.revision,
        answer: "Old answer must not appear",
        citations: [],
      },
    })
    .catch(() => {});
  assert.equal(
    await page.getByText("Old answer must not appear", { exact: true }).count(),
    0,
  );
  await page.unroute("**/api/assistant");
  checks.push(
    "A workspace switch aborts pending chat and clears conversation/draft; stale replies cannot appear",
  );
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("button", { name: "Sign in to collaborate" }).click();
  await page.keyboard.press("Tab");
  assert(
    await page.evaluate(() => !!document.activeElement?.closest(".modal")),
    "Modal focus escaped",
  );
  await page.keyboard.press("Escape");
  if (await page.getByRole("dialog").isVisible())
    await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  checks.push(
    "Mobile primary screens fit at 390px; sign-in dialog supports keyboard containment and Escape",
  );
  {
    demoServer = createServer((request, response) => {
      if (request.url === "/") {
        response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
        response.end(readFileSync("dist/index.html"));
      } else {
        response.writeHead(404);
        response.end();
      }
    });
    await new Promise((resolve) => demoServer.listen(0, "127.0.0.1", resolve));
    const demoBase = `http://127.0.0.1:${demoServer.address().port}`;
    const hostedContext = await browser.newContext({
      viewport: { width: 1440, height: 1080 },
      acceptDownloads: true,
    });
    const hosted = await hostedContext.newPage();
    observe(hosted);
    const hostedRequests = [];
    hosted.on("request", (request) => {
      if (/^https?:/.test(request.url())) hostedRequests.push(request.url());
    });
    await hosted.goto(demoBase);
    await hosted
      .getByRole("heading", {
        name: "Understand the docs. Trace the evidence.",
        exact: true,
      })
      .waitFor();
    assert.equal(await hosted.getByRole("dialog").count(), 0);
    assert.equal(
      await hosted
        .getByRole("button", { name: "Sign in to collaborate", exact: true })
        .count(),
      0,
    );
    assert.equal(
      await hosted
        .getByRole("button", { name: "Analyze sources", exact: true })
        .count(),
      0,
    );
    await hosted.getByRole("button", { name: "Graph", exact: true }).click();
    assert.equal(
      await hosted.getByLabel("Focus on an entity or component").inputValue(),
      "e:legacy_auth",
    );
    await hosted.getByText("4 direct connections", { exact: true }).waitFor();
    assert.equal(
      await hosted
        .getByRole("button", { name: "Questions", exact: true })
        .count(),
      0,
    );
    await hosted.getByRole("button", { name: "Evidence", exact: true }).click();
    await hosted
      .getByRole("button", { name: "Save review", exact: true })
      .waitFor();
    assert(
      await hosted
        .getByRole("button", { name: "Save review", exact: true })
        .isDisabled(),
    );
    await hosted
      .getByRole("button", { name: "Open assistant", exact: true })
      .click();
    assert.equal(
      await hosted.getByLabel("Assistant mode", { exact: true }).inputValue(),
      "guide",
    );
    assert(
      await hosted
        .getByRole("option", { name: "Model chat", exact: true })
        .evaluate((option) => option.disabled),
    );
    await hosted
      .getByRole("button", { name: "What should I do next?", exact: true })
      .click();
    assert.match(
      await hosted
        .getByRole("log", { name: "Assistant conversation" })
        .innerText(),
      /full application/,
    );
    await hosted
      .getByRole("button", { name: "Close assistant", exact: true })
      .click();
    for (const name of ["Sources", "Evidence", "Graph", "Activity", "Overview"])
      await hosted.getByRole("button", { name, exact: true }).click();
    await hosted
      .getByRole("button", { name: "Beginner tutorial", exact: true })
      .click();
    while (
      await hosted.getByRole("button", { name: "Next", exact: true }).count()
    )
      await hosted.getByRole("button", { name: "Next", exact: true }).click();
    await hosted
      .getByRole("button", { name: "Finish tutorial", exact: true })
      .click();
    await hosted
      .getByRole("heading", {
        name: "Understand the docs. Trace the evidence.",
        exact: true,
      })
      .waitFor();
    assert.equal(
      await hosted
        .getByRole("button", { name: "Export snapshot", exact: false })
        .count(),
      0,
    );
    const exported = JSON.parse(
      readFileSync(path.join(root, "data/demo-snapshot.json"), "utf8"),
    );
    const importedPath = path.join(temp, "hosted-review.json");
    writeFileSync(
      importedPath,
      JSON.stringify({ ...exported, title: "Imported demonstration review" }),
    );
    hosted.once("dialog", (dialog) => dialog.accept());
    await hosted
      .getByLabel("Import saved analysis")
      .setInputFiles(importedPath);
    await hosted
      .getByRole("heading", {
        name: "Understand the docs. Trace the evidence.",
        exact: true,
      })
      .waitFor();
    await hosted
      .getByText(/Imported demonstration review/)
      .first()
      .waitFor();
    hosted.once("dialog", (dialog) => dialog.accept());
    await hosted
      .getByRole("button", { name: "Reset example", exact: true })
      .click();
    await hosted
      .getByRole("status")
      .filter({
        hasText: "The prepared Harbor SDK example is ready to explore.",
      })
      .waitFor();
    assert.equal(
      await hosted.getByText(/Imported demonstration review/).count(),
      0,
    );
    await hosted.setViewportSize({ width: 390, height: 844 });
    for (const name of [
      "Sources",
      "Evidence",
      "Graph",
      "Activity",
      "Overview",
    ]) {
      await hosted.getByRole("button", { name, exact: true }).click();
      assert(
        await hosted.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
        `Hosted ${name} overflows mobile`,
      );
    }
    await hosted.reload();
    await hosted
      .getByRole("heading", {
        name: "Understand the docs. Trace the evidence.",
        exact: true,
      })
      .waitFor();
    assert.deepEqual(
      hostedRequests.filter((url) => url !== demoBase + "/"),
      [],
      "Hosted demo must not request APIs, models or external runtime assets",
    );
    checks.push(
      "Hosted HTTP demo preloads the example, supports visible pages/tutorial/evidence/retained import/reset and mobile layout without API or model requests",
    );
  }
  // Exercise direct access separately so the existing suite still checks authentication.
  const directBase = "http://127.0.0.1:18878";
  const directData = path.join(temp, "direct");
  directServer = spawn(path.join(root, ".venv/bin/python"), ["-m", "backend"], {
    cwd: root,
    env: {
      ...process.env,
      PYTHONDONTWRITEBYTECODE: "1",
      ATLAS_AUTH_ENABLED: "0",
      ATLAS_DATA_DIR: directData,
      ATLAS_PORT: "18878",
      ATLAS_ORIGINS: directBase,
    },
    stdio: ["ignore", "pipe", "pipe"],
  });
  directServer.stdout.on("data", (b) => (serverLog += b));
  directServer.stderr.on("data", (b) => (serverLog += b));
  let directReady = false;
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(directBase + "/api/health")).ok) {
        directReady = true;
        break;
      }
    } catch {}
    await new Promise((r) => setTimeout(r, 100));
  }
  assert(directReady, "Direct-access server failed to start: " + serverLog);
  const direct = await a.newPage();
  observe(direct);
  await direct.goto(directBase);
  await direct.getByText("Local reviewer", { exact: true }).first().waitFor();
  assert.equal(await direct.getByRole("dialog").count(), 0);
  assert.equal(
    await direct.getByRole("button", { name: /Sign in|Sign out/ }).count(),
    0,
  );
  await direct.getByRole("button", { name: "Workspaces", exact: true }).click();
  await direct
    .getByLabel("New workspace name", { exact: true })
    .fill("Direct access review");
  await direct
    .getByRole("button", { name: "New empty workspace", exact: true })
    .click();
  await direct.getByRole("dialog").waitFor({ state: "hidden" });
  const directState = await (
    await direct.request.get(directBase + "/api/state")
  ).json();
  assert.equal(directState.workspace.title, "Direct access review");
  assert.equal(directState.workspace.audit.at(-1).by, "Local reviewer");
  await direct.reload();
  await direct.getByText("Local reviewer", { exact: true }).first().waitFor();
  await direct.setViewportSize({ width: 390, height: 844 });
  assert.equal(
    await direct.getByRole("button", { name: /Sign in|Sign out/ }).count(),
    0,
  );
  assert(!existsSync(path.join(directData, "access-code")));
  checks.push(
    "Sign-in disabled opens directly, saves a workspace as Local reviewer, survives reload and hides authentication controls on desktop/mobile",
  );
  await direct.getByRole("button", { name: "Sources", exact: true }).click();
  await direct
    .getByLabel("Source title", { exact: true })
    .fill("Disposable source");
  await direct.getByLabel("Version", { exact: true }).fill("1.0");
  await direct
    .getByLabel("License / permission", { exact: true })
    .fill("Synthetic test, MIT");
  await direct
    .getByLabel("Source text", { exact: true })
    .fill("Added `example_api` for synthetic source deletion testing.");
  await direct
    .getByRole("button", { name: "Save source", exact: true })
    .click();
  const deleteSource = direct.getByRole("button", {
    name: "Delete source Disposable source, version 1.0",
    exact: true,
  });
  await deleteSource.waitFor();
  await deleteSource.click();
  await direct.getByRole("button", { name: "Cancel", exact: true }).click();
  assert(await deleteSource.isVisible());
  await deleteSource.click();
  await direct
    .getByRole("button", { name: "Delete source", exact: true })
    .click();
  await deleteSource.waitFor({ state: "hidden" });
  await direct.getByText("No source snapshots yet.", { exact: true }).waitFor();
  await direct.reload();
  await direct.getByRole("button", { name: "Sources", exact: true }).click();
  await direct.getByText("No source snapshots yet.", { exact: true }).waitFor();
  const deletedState = await (
    await direct.request.get(directBase + "/api/state")
  ).json();
  assert.equal(deletedState.workspace.sources.length, 0);
  assert.equal(
    deletedState.workspace.audit.at(-1).action,
    "Deleted source: Disposable source",
  );
  checks.push(
    "Source trash icon supports cancelling and confirming deletion on mobile; removal survives reload and is audited",
  );
  assert.deepEqual(errors, []);
  writeFileSync(
    "validation/browser-results.json",
    JSON.stringify(
      {
        result: "PASS",
        browser: "Playwright Chromium or installed Google Chrome",
        viewports: ["1440x1080", "1280x900", "390x844"],
        checks,
        uncaught_errors: errors,
        offline_remote_requests: remoteRequests,
        limitations: [
          "Safari and Firefox not executed",
          "Basic keyboard/layout checks, not a complete WCAG audit",
          "LLM generation tested separately",
        ],
      },
      null,
      2,
    ) + "\n",
  );
  console.log(
    JSON.stringify({
      result: "PASS",
      checks: checks.length,
      uncaught_errors: errors.length,
    }),
  );
} catch (error) {
  console.error(error);
  console.error(serverLog.slice(-3000));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  if (demoServer) await new Promise((resolve) => demoServer.close(resolve));
  server.kill("SIGTERM");
  if (directServer) directServer.kill("SIGTERM");
}
