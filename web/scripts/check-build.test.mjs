import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import zlib from "node:zlib";
import { afterEach, describe, expect, it } from "vitest";

const script = path.join(import.meta.dirname, "check-build.mjs");
const INDEX_HTML = `<!doctype html>
<html lang="en">
  <head>
    <script type="module" crossorigin src="/assets/index.js"></script>
    <link rel="stylesheet" crossorigin href="/assets/index.css">
  </head>
  <body><div id="root"></div></body>
</html>
`;

const tempDirs = [];

function incompressible(size) {
  const bytes = Buffer.alloc(size);
  let state = 1;
  for (let i = 0; i < size; i += 1) {
    state = (Math.imul(state, 1103515245) + 12345) >>> 0;
    bytes[i] = state >>> 24;
  }
  return bytes;
}

function gzipSize(content) {
  return zlib.gzipSync(content, { level: 9 }).length;
}

function makeDist({ manifest, files }) {
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), "check-build-"));
  tempDirs.push(dist);
  const all = {
    "index.html": INDEX_HTML,
    "assets/index.js": "console.log('app');\n",
    "assets/index.css": "body { margin: 0; }\n",
    ...files,
  };
  if (manifest !== null) {
    all[".vite/manifest.json"] = JSON.stringify(
      manifest ?? { "index.html": { file: "assets/index.js", isEntry: true } },
    );
  }
  for (const [name, content] of Object.entries(all)) {
    const file = path.join(dist, name);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, content);
  }
  return dist;
}

function run(dist) {
  const result = spawnSync(process.execPath, [script, dist], { encoding: "utf8" });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

afterEach(() => {
  for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

describe("check-build", () => {
  it("passes a compliant dist and prints both measures", () => {
    const { status, stdout } = run(makeDist({}));
    expect(status).toBe(0);
    expect(stdout).toMatch(/^js-initial \d+\/100000$/m);
    expect(stdout).toMatch(/^css-total \d+\/20000$/m);
  });

  it("fails when the initial JS exceeds the budget", () => {
    const { status, stdout } = run(
      makeDist({ files: { "assets/index.js": incompressible(120000) } }),
    );
    expect(status).toBe(1);
    expect(stdout).toMatch(/^js-initial \d{6}\/100000$/m);
  });

  it("fails when the total CSS exceeds the budget", () => {
    const { status } = run(
      makeDist({ files: { "assets/nested/extra.css": incompressible(25000) } }),
    );
    expect(status).toBe(1);
  });

  it("sums transitive static imports and excludes dynamic imports", () => {
    const entry = "console.log('entry');\n";
    const vendor = "export const vendor = 1;\n";
    const shared = "export const shared = 2;\n";
    const lazy = incompressible(150000);
    const dist = makeDist({
      manifest: {
        "index.html": {
          file: "assets/index.js",
          isEntry: true,
          imports: ["_vendor.js"],
          dynamicImports: ["src/views/Lazy.tsx"],
        },
        "_vendor.js": { file: "assets/vendor.js", imports: ["_shared.js"] },
        "_shared.js": { file: "assets/shared.js" },
        "src/views/Lazy.tsx": {
          file: "assets/lazy.js",
          isDynamicEntry: true,
          imports: ["_vendor.js"],
        },
      },
      files: {
        "assets/index.js": entry,
        "assets/vendor.js": vendor,
        "assets/shared.js": shared,
        "assets/lazy.js": lazy,
      },
    });
    const { status, stdout } = run(dist);
    expect(status).toBe(0);
    const expected = gzipSize(entry) + gzipSize(vendor) + gzipSize(shared);
    expect(stdout).toContain(`js-initial ${expected}/100000`);
  });

  it("fails on an inline <script>", () => {
    const html = INDEX_HTML.replace("<body>", "<body><script>window.x = 1;</script>");
    expect(run(makeDist({ files: { "index.html": html } })).status).toBe(1);
  });

  it("fails on an on*= event handler attribute", () => {
    const html = INDEX_HTML.replace('<div id="root">', '<div id="root" onclick="go()">');
    expect(run(makeDist({ files: { "index.html": html } })).status).toBe(1);
  });

  it("fails when the manifest is missing", () => {
    const { status, stderr } = run(makeDist({ manifest: null }));
    expect(status).toBe(1);
    expect(stderr).toMatch(/manifest\.json/);
  });

  it.each([
    ["index.html", INDEX_HTML.replace("/assets/index.css", "https://cdn.example.com/a.css")],
    ["assets/index.css", "@import 'https://fonts.example.com/f.css';\n"],
    ["assets/index.css", "body { background: url(http://cdn.example.com/bg.png); }\n"],
    ["assets/index.js", 'el.innerHTML = "<img src=\\"https://cdn.example.com/x.png\\">";\n'],
  ])("fails on an external origin reference in %s", (name, content) => {
    const { status, stderr } = run(makeDist({ files: { [name]: content } }));
    expect(status).toBe(1);
    expect(stderr).toContain("external origin");
  });

  it("allows external URLs outside src/href/@import/url( contexts", () => {
    const js = "const ns = `http://www.w3.org/2000/svg`;\nconst e = `https://react.dev/errors/`;\n";
    expect(run(makeDist({ files: { "assets/index.js": js } })).status).toBe(0);
  });
});
