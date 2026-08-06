import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";

const host = "127.0.0.1";
const port = Number(process.env.E2E_FIXTURE_PORT ?? 4174);
const widgetRoot = join(process.cwd(), "packages", "widget", "dist");

const page = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Widget E2E host</title></head>
<body><main><h1>Merchant fixture</h1><p>This host intentionally has unrelated page styles.</p></main>
<script>
  const params = new URLSearchParams(location.search);
  const loader = document.createElement("script");
  loader.async = true;
  loader.src = "/loader.js";
  loader.dataset.apiBase = params.get("api") || "http://127.0.0.1:8000";
  loader.dataset.publishableKey = params.get("key") || "";
  loader.dataset.title = "E2E Support";
  loader.dataset.welcome = "How can we help in E2E?";
  loader.dataset.accent = "#194f46";
  document.body.append(loader);
</script></body></html>`;

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://${host}:${port}`);
  if (url.pathname === "/health") {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end('{"status":"ok"}');
    return;
  }
  if (url.pathname === "/") {
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(page);
    return;
  }
  const relativePath = normalize(url.pathname).replace(/^[/\\]+/, "");
  const filePath = join(widgetRoot, relativePath);
  if (!filePath.startsWith(widgetRoot) || ![".js", ".json"].includes(extname(filePath))) {
    response.writeHead(404).end();
    return;
  }
  try {
    const metadata = await stat(filePath);
    if (!metadata.isFile()) throw new Error("not a file");
    response.writeHead(200, {
      "Content-Type": extname(filePath) === ".js" ? "text/javascript; charset=utf-8" : "application/json",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store",
    });
    createReadStream(filePath).pipe(response);
  } catch {
    response.writeHead(404).end();
  }
});

server.listen(port, host, () => {
  console.log(`E2E widget fixture listening on http://${host}:${port}`);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
