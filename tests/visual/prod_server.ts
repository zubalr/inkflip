import { createServer, type Server } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
export const ROOT = resolve(here, "../..");
export const WEB_ROOT = join(ROOT, "apps/web");
export const DIST_DIR = join(WEB_ROOT, "dist");

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

  const prevEnv = process.env.NODE_ENV;
  process.env.NODE_ENV = "production";
  try {
    await vite.build({
      root: WEB_ROOT,
      configFile: join(WEB_ROOT, "vite.config.ts"),
      logLevel: "warn",
      build: {
        outDir: DIST_DIR,
        emptyOutDir: false,
      },
    });
  } finally {
    if (prevEnv === undefined) {
      delete process.env.NODE_ENV;
    } else {
      process.env.NODE_ENV = prevEnv;
    }
  }

  // Calculate build identity from index.html
  const indexPath = join(DIST_DIR, "index.html");
  const indexBytes = readFileSync(indexPath);
  const indexHtmlSha256 = createHash("sha256").update(indexBytes).digest("hex");

  const distRoot = resolve(DIST_DIR) + sep;
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

    let file = normalize(join(DIST_DIR, pathname));
    // SPA fallback: if file does not exist and doesn't look like static file with extension, serve index.html
    if (!file.startsWith(distRoot) || !existsSync(file) || file.endsWith(sep)) {
      if (!pathname.slice(1).includes(".")) {
        file = join(DIST_DIR, "index.html");
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
      distDir: DIST_DIR,
    },
    close: () => new Promise((r) => server.close(() => r())),
  };
}
