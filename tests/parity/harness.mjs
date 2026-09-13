// Shared helpers for T46 parity tests.
import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const FIXTURE = join(ROOT, "fixtures/public/mapping-control.pdf");
export const PLANNING_VECTORS = join(ROOT, "planning/contracts/hash-vectors.json");
export const ARTIFACTS = join(ROOT, "artifacts/P15");
export const NATIVE_PYTHON = join(ROOT, "native/.venv/bin/python");
export const PDFJS_BRIDGE = join(ROOT, "packages/readers-pdfjs/node/bridge.mjs");

export const MAPPING_CONTROL_SHA =
  "19031ea006214acdd5ae3191ff74a2976736314faf139f44c93d2b3a0bb7c6ed";

export function sha256File(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

export function which(bin) {
  const proc = spawnSync("sh", ["-c", `command -v ${bin}`], { encoding: "utf8" });
  return proc.status === 0 ? proc.stdout.trim() : "";
}

export function nativePython() {
  if (existsSync(NATIVE_PYTHON)) return NATIVE_PYTHON;
  return which("python3") || "python3";
}

export function run(argv, opts = {}) {
  const env = {
    ...process.env,
    PYTHONPATH: join(ROOT, "native"),
    ...(opts.env || {}),
  };
  const proc = spawnSync(argv[0], argv.slice(1), {
    cwd: opts.cwd || ROOT,
    encoding: "utf8",
    env,
    timeout: opts.timeout ?? 60_000,
    input: opts.input,
  });
  return proc;
}

export function nativeInspect(pdf, out, extra = []) {
  mkdirSync(dirname(out), { recursive: true });
  const proc = run(
    [nativePython(), "-m", "inkflip.cli", "inspect", pdf, "--out", out, "--pages", "1", "--replace-output", ...extra],
  );
  return proc;
}

export function pdfjsExtract(pdf) {
  const proc = run(["node", PDFJS_BRIDGE], {
    input: JSON.stringify({ action: "extract", pdf_path: pdf, pages: [0] }),
  });
  if (proc.status !== 0) return { ok: false, error: proc.stderr || proc.stdout, status: proc.status };
  try {
    return JSON.parse(proc.stdout);
  } catch (err) {
    return { ok: false, error: String(err), raw: proc.stdout };
  }
}

export function writeJson(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, JSON.stringify(value, null, 2) + "\n");
}

export function hostManifest() {
  const uname = run(["uname", "-sm"]);
  const py = run([nativePython(), "-c", "import platform,sys; print(sys.version.split()[0]); print(platform.platform())"]);
  const node = run(["node", "-v"]);
  return {
    os: (uname.stdout || "").trim(),
    python: (py.stdout || "").trim().split("\n"),
    node: (node.stdout || "").trim(),
    cpu: process.arch,
    model: process.env.CPU_BRAND || null,
  };
}
