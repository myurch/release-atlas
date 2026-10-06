import { chromium } from "playwright";
import { spawn } from "node:child_process";
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
  },
  stdio: ["ignore", "pipe", "pipe"],
});
let serverLog = "";
server.stdout.on("data", (b) => (serverLog += b));
server.stderr.on("data", (b) => (serverLog += b));
let browser;
const checks = [];
const errors = [];
function observe(page) {
  page.on("pageerror", (e) => errors.push(e.message));
}
async function login(page, name) {
  await page.goto(base);
  await page.getByLabel("Display name").fill(name);
  await page.getByLabel("Workspace access code", { exact: true }).fill(code);
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
  for (let i = 0; i < 14; i++) {
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
  await page.getByText("The sources disagree.", { exact: true }).waitFor();
  mkdirSync("validation/screenshots", { recursive: true });
  await page.screenshot({
    path: "validation/screenshots/desktop.png",
    fullPage: true,
  });
  checks.push("Startup, login, original synthetic demo and overview");
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
  await page.getByRole("button", { name: "Questions", exact: true }).click();
  await page.getByRole("button", { name: "Ask the evidence" }).click();
  await page.locator(".answer").first().waitFor();
  assert((await page.locator(".citation").count()) > 0);
  checks.push("Graph-assisted question produces source-linked evidence");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export snapshot" }).click();
  const download = await downloadPromise;
  const exportPath = path.join(temp, "snapshot.json");
  await download.saveAs(exportPath);
  const snapshot = JSON.parse(readFileSync(exportPath, "utf8"));
  assert(
    snapshot.answers.length === 1 &&
      snapshot.audit.some((a) => a.by === "Alex"),
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
    .getByText("Know what changes. Decide together.", { exact: true })
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
  await mobile.getByRole("button", { name: "Questions", exact: true }).click();
  await mobile.locator(".answer").first().waitFor();
  assert(await mobile.locator(".answer-text").innerText());
  await mobile.locator(".citation").first().click();
  await mobile.getByRole("heading", { name: "Follow the evidence." }).waitFor();
  assert(
    await mobile
      .getByRole("button", { name: "Save review", exact: true })
      .isDisabled(),
  );
  checks.push(
    "Single HTML file works offline, imports saved analysis and follows saved citations without a backend",
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
  for (const title of [
    "Overview",
    "Sources",
    "Graph",
    "Questions",
    "Activity",
  ]) {
    await mobile.getByRole("button", { name: title, exact: true }).click();
    assert(
      await mobile.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "Overflow on " + title,
    );
  }
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("button", { name: "Sign in to collaborate" }).click();
  await page.keyboard.press("Tab");
  assert(
    await page.evaluate(() => !!document.activeElement?.closest(".modal")),
    "Modal focus escaped",
  );
  await page.keyboard.press("Escape");
  await page.getByRole("dialog").waitFor({ state: "hidden" });
  checks.push(
    "Mobile primary screens fit at 390px; sign-in dialog supports keyboard containment and Escape",
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
  server.kill("SIGTERM");
}
