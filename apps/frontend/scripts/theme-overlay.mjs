// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { execFile } from "node:child_process";
import { createReadStream } from "node:fs";
import { mkdtemp, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const install = promisify(execFile);
const installer = fileURLToPath(new URL("./theme-overlay.sh", import.meta.url));
const served =
  /^\/(?:images\/.+|contrib\/.+|[^/]+\.md|theme-custom\.css|theme-properties\.json|theme-catalog\.json|theme-translations\/(?:en|fr)\.json)$/;
const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".md": "text/markdown; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".avif": "image/avif",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".otf": "font/otf",
};

export function themeOverlayMiddleware(directory) {
  return (request, response, next) => {
    if (request.method !== "GET" && request.method !== "HEAD") return next();
    let pathname;
    try {
      pathname = decodeURIComponent((request.url ?? "").split("?")[0]);
    } catch {
      return next();
    }
    if (!served.test(pathname) || /[\\\0]/.test(pathname) || pathname.split("/").some((p) => p === ".." || p === ".")) {
      return next();
    }
    const file = path.resolve(directory, `.${pathname}`);
    if (!file.startsWith(`${directory}${path.sep}`)) return next();
    stat(file)
      .then((info) => {
        if (!info.isFile()) return next();
        response.setHeader(
          "Content-Type",
          contentTypes[path.extname(file).toLowerCase()] ?? "application/octet-stream",
        );
        response.setHeader("Content-Length", info.size);
        response.setHeader("Cache-Control", "no-cache");
        if (request.method === "HEAD") return response.end();
        const stream = createReadStream(file);
        stream.on("error", () => response.destroy());
        response.on("close", () => stream.destroy());
        stream.pipe(response);
      })
      .catch((error) => {
        if (error.code === "ENOENT" || error.code === "ENOTDIR") next();
        else next(error);
      });
  };
}

export function themeOverlayPlugin(environment) {
  return {
    name: "fred-theme-overlay",
    async configureServer(server) {
      if (!environment.FRONTEND_THEME_URL) return;
      const directory = await mkdtemp(path.join(tmpdir(), "fred-vite-theme-"));
      const cleanup = () => rm(directory, { recursive: true, force: true });
      try {
        const { stdout, stderr } = await install("sh", [installer, directory], {
          env: { ...process.env, ...environment },
          timeout: 25_000,
        });
        if (stdout.trim()) server.config.logger.info(stdout.trim());
        if (stderr.trim()) server.config.logger.warn(stderr.trim());
        server.middlewares.use(themeOverlayMiddleware(directory));
        server.httpServer?.once("close", () => void cleanup());
      } catch (error) {
        await cleanup();
        // Arguments contain only local paths; report the installer's sanitized
        // diagnostics instead of execFile's error, which can include curl output.
        throw new Error(error.stderr?.trim() || "Cannot prepare the frontend theme overlay");
      }
    },
  };
}
