import { createServer, type Server } from "node:http";
import { existsSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(here, "../..");
export const WEB_ROOT = join(ROOT, "apps/web");
export const DIST_DIR = join(WEB_ROOT, "dist");
/** The shared dist is never written by this harness; see startProdServer. */

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css",
  ".json": "application/json",
  ".pdf": "application/pdf",
  ".wasm": "application/wasm",
  ".bcmap": "application/octet-stream",
  ".traineddata": "application/octet-stream",
  ".pfb": "application/octet-stream",
  ".ttf": "font/ttf",
  ".icc": "application/vnd.iccprofile",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

function ext(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i) : "";
}

export interface BuildIdentity {
  indexHtmlSha256: string;
  distDir: string;
  /** Hash over every emitted build file, so the identity binds the bytes the
   *  page actually loads (JS/CSS/worker/wasm), not only index.html. */
  buildSha256: string;
  fileCount: number;
  /** True when the build directory is private to this run. */
  isolated: boolean;
}

function hashBuildTree(dir: string): { buildSha256: string; fileCount: number } {
  const files: string[] = [];
  const walk = (current: string, prefix: string) => {
    for (const entry of readdirSync(current, { withFileTypes: true }).sort((a, b) =>
      a.name < b.name ? -1 : a.name > b.name ? 1 : 0,
    )) {
      const next = join(current, entry.name);
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        walk(next, rel);
      } else if (entry.isFile()) {
        files.push(rel);
      }
    }
  };
  walk(dir, "");
  const digest = createHash("sha256");
  for (const rel of files) {
    digest.update(rel);
    digest.update("\0");
    digest.update(readFileSync(join(dir, rel)));
    digest.update("\0");
  }
  return { buildSha256: digest.digest("hex"), fileCount: files.length };
}

export interface ProdServerInstance {
  server: Server;
  baseUrl: string;
  buildIdentity: BuildIdentity;
  close: () => Promise<void>;
}

export async function startProdServer(): Promise<ProdServerInstance> {
  // 1. Production build with pinned NODE_ENV=production to avoid worker pollution
  const viteEntry = pathToFileURL(
    join(WEB_ROOT, "node_modules", "vite", "dist", "node", "index.js"),
  ).href;
  const vite = (await import(viteEntry)) as {
    build: (opts: Record<string, unknown>) => Promise<unknown>;
  };

  // Each run builds into its own disposable directory. Building into the shared
  // apps/web/dist with emptyOutDir:false let a stale asset from an earlier build
  // satisfy a later run, and made two suites share one output tree.
  const runDistDir = join(WEB_ROOT, `.harness-dist-${process.pid}-${Date.now().toString(36)}`);

  const prevEnv = process.env.NODE_ENV;
  process.env.NODE_ENV = "production";
  try {
    await vite.build({
      root: WEB_ROOT,
      configFile: join(WEB_ROOT, "vite.config.ts"),
      logLevel: "warn",
      build: {
        outDir: runDistDir,
        emptyOutDir: true,
      },
    });
  } finally {
    if (prevEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = prevEnv;
    }
  }

  // Build identity binds the whole emitted tree, not just index.html.
  const indexPath = join(runDistDir, "index.html");
  const indexBytes = readFileSync(indexPath);
  const indexHtmlSha256 = createHash("sha256").update(indexBytes).digest("hex");
  const { buildSha256, fileCount } = hashBuildTree(runDistDir);

  const distRoot = resolve(runDistDir) + sep;
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    let pathname = decodeURIComponent(url.pathname);
    if (pathname === "/") pathname = "/index.html";

    const headers: Record<string, string> = {
      "Content-Type": "text/html; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
    };

    if (pathname === "/favicon.ico") {
      res.writeHead(204, headers).end();
      return;
    }

    let file = normalize(join(runDistDir, pathname));
    // SPA fallback: if file does not exist and doesn't look like static file with extension, serve index.html
    if (!file.startsWith(distRoot) || !existsSync(file) || file.endsWith(sep)) {
      if (!pathname.slice(1).includes(".")) {
        file = join(runDistDir, "index.html");
      } else {
        res.writeHead(404, headers).end("not found");
        return;
      }
    }

    try {
      const body = readFileSync(file);
      res
        .writeHead(200, {
          ...headers,
          "Content-Type": MIME[ext(file)] ?? "application/octet-stream",
        })
        .end(body);
    } catch {
      res.writeHead(404, headers).end("not found");
    }
  });

  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  const port = (server.address() as { port: number }).port;
  const baseUrl = `http://127.0.0.1:${port}`;

  return {
    server,
    baseUrl,
    buildIdentity: {
      indexHtmlSha256,
      distDir: runDistDir,
      buildSha256,
      fileCount,
      isolated: true,
    },
    close: () =>
      new Promise((r) =>
        server.close(() => {
          // Dispose of this run's private build; the shared dist is untouched.
          rmSync(runDistDir, { recursive: true, force: true });
          r();
        }),
      ),
  };
}
