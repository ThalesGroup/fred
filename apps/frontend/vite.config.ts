// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { transformWithEsbuild } from "vite";
import svgr from "@svgr/rollup";
import path from "path";
import tsconfigPaths from "vite-tsconfig-paths";
import { visualizer } from "rollup-plugin-visualizer";

// https://vitejs.dev/config/
export default defineConfig({
  server: {
    host: "0.0.0.0",
    port: parseInt(process.env.VITE_PORT || "5173"),
    allowedHosts: (process.env.VITE_ALLOWED_HOSTS || "").split(",").filter(Boolean),
    proxy: {
      "/agentic": { target: process.env.VITE_BACKEND_URL || "http://localhost:8000", ws: true },
      "/fred": process.env.VITE_BACKEND_URL_FRED_AGENTS || "http://localhost:8000",
      "/knowledge-flow": process.env.VITE_BACKEND_URL_KNOWLEDGE || "http://localhost:8111",
      "/control-plane": process.env.VITE_BACKEND_URL_CONTROL_PLANE || "http://localhost:8222",
      "/samples": process.env.VITE_BACKEND_URL_SAMPLES || "http://localhost:8010",
    },
  },
  resolve: {
    alias: {
      src: path.resolve(__dirname, "./src"),
    },
  },
  plugins: [
    {
      name: "treat-js-files-as-jsx",
      async transform(code, id) {
        if (!id.match(/src\/.*\.js$/)) return null;

        // Use the exposed transform from vite, instead of directly
        // transforming with esbuild
        return transformWithEsbuild(code, id, {
          loader: "jsx",
          jsx: "automatic",
        });
      },
    },
    react(),
    svgr({ exportType: "named" }),
    tsconfigPaths(),
    visualizer({ open: false }),
  ],
  optimizeDeps: {
    force: true,
    // Pre-bundle mermaid (and crawl its dynamically imported diagram chunks,
    // e.g. flowDiagram) at startup. Without this, those sub-chunks are
    // discovered mid-session, triggering a dep re-optimization + reload that
    // invalidates the in-flight chunk hash and produces intermittent
    // "error loading dynamically imported module" failures in MermaidBlock.
    include: ["mermaid"],
    esbuildOptions: {
      loader: {
        ".js": "jsx",
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    coverage: {
      provider: "v8",
      reporter: ["text", "json-summary", "lcov"],
      reportsDirectory: "coverage",
      include: ["src/rework/**/*.ts", "src/rework/**/*.tsx"],
      exclude: ["src/rework/**/*.test.ts", "src/rework/**/*.test.tsx", "src/rework/types/**"],
    },
  },
});
