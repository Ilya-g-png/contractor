import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const JS_BUDGET = 100000;
const CSS_BUDGET = 20000;
const SCRIPT_TAG = /<script\b([^>]*)>/gi;
const SRC_ATTR = /\ssrc\s*=/i;
const EVENT_HANDLER_ATTR = /\son[a-z]+\s*=/i;
const EXTERNAL_REF =
  /(?:\b(?:src|href)\s*=\s*|@import\s+(?:url\(\s*)?|\burl\(\s*)\\?["'`]?https?:\/\//i;

const distDir = path.resolve(process.argv[2] ?? "dist");
const manifestPath = path.join(distDir, ".vite", "manifest.json");
const indexPath = path.join(distDir, "index.html");

function gzipSize(file) {
  return zlib.gzipSync(fs.readFileSync(file), { level: 9 }).length;
}

function listFiles(dir) {
  return fs
    .readdirSync(dir, { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => path.join(entry.parentPath, entry.name));
}

function initialJsFiles(manifest, errors) {
  const entry = manifest["index.html"];
  if (!entry?.isEntry) {
    errors.push("manifest has no isEntry chunk for index.html");
    return [];
  }
  const files = new Set();
  const seen = new Set();
  const pending = ["index.html"];
  while (pending.length > 0) {
    const key = pending.pop();
    if (seen.has(key)) continue;
    seen.add(key);
    const chunk = manifest[key];
    if (!chunk) {
      errors.push(`manifest import ${key} has no entry`);
      continue;
    }
    files.add(chunk.file);
    pending.push(...(chunk.imports ?? []));
  }
  return [...files];
}

if (!fs.existsSync(manifestPath)) {
  console.error(`check-build: missing ${manifestPath}`);
  process.exit(1);
}

const errors = [];
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const distFiles = listFiles(distDir);

const jsTotal = initialJsFiles(manifest, errors).reduce(
  (sum, file) => sum + gzipSize(path.join(distDir, file)),
  0,
);
const cssTotal = distFiles
  .filter((file) => file.endsWith(".css"))
  .reduce((sum, file) => sum + gzipSize(file), 0);

console.log(`js-initial ${jsTotal}/${JS_BUDGET}`);
console.log(`css-total ${cssTotal}/${CSS_BUDGET}`);

if (jsTotal > JS_BUDGET) errors.push(`initial JS ${jsTotal} B gzip exceeds ${JS_BUDGET} B`);
if (cssTotal > CSS_BUDGET) errors.push(`total CSS ${cssTotal} B gzip exceeds ${CSS_BUDGET} B`);

if (fs.existsSync(indexPath)) {
  const html = fs.readFileSync(indexPath, "utf8");
  for (const [, attrs] of html.matchAll(SCRIPT_TAG)) {
    if (!SRC_ATTR.test(attrs)) errors.push("index.html contains an inline <script>");
  }
  if (EVENT_HANDLER_ATTR.test(html)) errors.push("index.html contains an on*= attribute");
} else {
  errors.push("missing index.html");
}

for (const file of distFiles) {
  if (EXTERNAL_REF.test(fs.readFileSync(file, "utf8"))) {
    errors.push(`${path.relative(distDir, file)} references an external origin`);
  }
}

for (const error of errors) console.error(`check-build: ${error}`);
process.exit(errors.length > 0 ? 1 : 0);
