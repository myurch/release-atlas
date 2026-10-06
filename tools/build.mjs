import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";

const python =
  process.env.ATLAS_PYTHON ||
  (process.platform === "win32"
    ? ".venv/Scripts/python.exe"
    : ".venv/bin/python");
execFileSync(python, ["tools/make_demo.py"], {
  stdio: "inherit",
  env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
});
const logo =
  "data:image/png;base64," +
  readFileSync("assets/release-atlas-logo.png").toString("base64");
const theme = await build({
  entryPoints: ["frontend/theme-bootstrap.ts"],
  bundle: true,
  minify: true,
  write: false,
  format: "iife",
  target: ["es2022"],
});
const themeScript = theme.outputFiles[0].text;
const demo = JSON.parse(readFileSync("data/demo-snapshot.json", "utf8"));
const result = await build({
  entryPoints: ["frontend/main.tsx"],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2022"],
  write: false,
  outdir: "dist",
  legalComments: "inline",
  define: {
    __DEMO__: JSON.stringify(demo),
    __LOGO__: JSON.stringify(logo),
    "process.env.NODE_ENV": '"production"',
  },
});
const script = result.outputFiles
  .find((f) => f.path.endsWith(".js"))
  .text.replace(/<\/script/gi, "<\\/script");
const css = result.outputFiles.find((f) => f.path.endsWith(".css")).text;
const html = `<!doctype html>\n<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><meta name="theme-color" content="#15211d"><meta name="description" content="Release Atlas helps teams review upgrade evidence, conflicting claims and their source snapshots."><title>Release Atlas | Upgrade evidence</title><link id="app-icon" rel="icon" type="image/png"><script>${themeScript}</script><style>${css}</style></head><body><div id="root"></div><noscript>Enable JavaScript to view this review.</noscript><script>${script}</script></body></html>\n`;
mkdirSync("dist", { recursive: true });
writeFileSync("dist/release-atlas.html", html);
if (/<script[^>]+src=|<link[^>]+href=["']https?:/i.test(html))
  throw Error("External runtime dependency in packed HTML");
console.log(
  `Built dist/release-atlas.html (${Buffer.byteLength(html).toLocaleString()} bytes), with all runtime assets embedded.`,
);
