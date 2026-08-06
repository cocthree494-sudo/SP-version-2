import { gzipSync } from "node:zlib";
import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = new URL("../dist/", import.meta.url);
const rootPath = fileURLToPath(root);

async function files(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const output = [];
  for (const entry of entries) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) output.push(...await files(path));
    else if (entry.name !== "bundle-report.json") output.push(path);
  }
  return output;
}

const rows = [];
for (const path of await files(rootPath)) {
  const content = await readFile(path);
  rows.push({
    file: relative(rootPath, path).replaceAll("\\", "/"),
    bytes: content.byteLength,
    gzip_bytes: gzipSync(content).byteLength,
  });
}
rows.sort((left, right) => left.file.localeCompare(right.file));
const report = {
  generated_at: new Date().toISOString(),
  files: rows,
  total_bytes: rows.reduce((sum, row) => sum + row.bytes, 0),
  total_gzip_bytes: rows.reduce((sum, row) => sum + row.gzip_bytes, 0),
};
await writeFile(new URL("bundle-report.json", root), `${JSON.stringify(report, null, 2)}\n`);
console.log(`Widget bundle: ${report.total_bytes} bytes (${report.total_gzip_bytes} gzip)`);
