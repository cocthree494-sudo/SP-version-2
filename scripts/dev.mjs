import { access, copyFile } from "node:fs/promises";
import { constants } from "node:fs";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";
const npm = isWindows ? "npm.cmd" : "npm";

async function exists(filePath) {
  try {
    await access(filePath, constants.F_OK);
    return true;
  } catch {
    return false;
  }
}

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      stdio: "inherit",
      shell: isWindows && command.endsWith(".cmd"),
    });
    child.once("error", reject);
    child.once("exit", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`${command} exited with code ${code ?? "unknown"}`));
      }
    });
  });
}

async function ensureSetup() {
  if (!(await exists(path.join(root, ".env")))) {
    await copyFile(path.join(root, ".env.example"), path.join(root, ".env"));
    console.log("Created .env from .env.example");
  }

  const concurrently = isWindows
    ? path.join(root, "node_modules", ".bin", "concurrently.cmd")
    : path.join(root, "node_modules", ".bin", "concurrently");

  if (!(await exists(concurrently))) {
    console.log("JavaScript dependencies are missing; running setup...");
    await run(npm, ["run", "setup"]);
  }

  if (!(await exists(path.join(root, "apps", "api", ".venv")))) {
    console.log("Python environment is missing; running setup...");
    await run(npm, ["run", "setup"]);
  }
}

function requireDocker() {
  const result = spawnSync("docker", ["compose", "version"], {
    cwd: root,
    encoding: "utf8",
    shell: isWindows,
  });

  if (result.status !== 0) {
    throw new Error(
      "Docker Compose is required for PostgreSQL and Redis. Install/start Docker Desktop, then rerun npm run dev.",
    );
  }
}

async function main() {
  await ensureSetup();
  requireDocker();

  console.log("Starting PostgreSQL and Redis...");
  await run(npm, ["run", "infra:up"]);

  console.log("Starting API, dashboard, and widget development servers...");
  const apps = spawn(npm, ["run", "dev:apps"], {
    cwd: root,
    stdio: "inherit",
    shell: isWindows,
  });
  apps.once("error", (error) => {
    console.error(`Unable to start applications: ${error.message}`);
    process.exitCode = 1;
  });
  apps.once("exit", (code) => {
    process.exitCode = code ?? 1;
  });
}

main().catch((error) => {
  console.error(`Development startup failed: ${error.message}`);
  process.exitCode = 1;
});
