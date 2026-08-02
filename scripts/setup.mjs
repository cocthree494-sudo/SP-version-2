import { copyFile, mkdir, stat } from "node:fs/promises";
import { constants } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";

async function exists(filePath) {
  try {
    await stat(filePath, { bigint: false });
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

async function ensureEnvironment() {
  const envPath = path.join(root, ".env");
  if (!(await exists(envPath))) {
    await copyFile(path.join(root, ".env.example"), envPath, constants.COPYFILE_EXCL);
    console.log("Created .env from .env.example");
  }

  await mkdir(path.join(root, ".data", "uploads"), { recursive: true });
}

async function main() {
  await ensureEnvironment();

  const npm = isWindows ? "npm.cmd" : "npm";
  console.log("Installing JavaScript workspace dependencies...");
  await run(npm, ["install"]);

  console.log("Installing the Python 3.12 API environment...");
  await run("uv", ["sync", "--project", "apps/api", "--python", "3.12"]);

  console.log("Setup complete. Run: npm run dev");
}

main().catch((error) => {
  console.error(`Setup failed: ${error.message}`);
  process.exitCode = 1;
});
