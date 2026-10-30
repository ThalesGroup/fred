// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";
import svgr from "@svgr/rollup";

// Separate origin, no backend proxy, no shared app cache and no HMR network traffic.
export default defineConfig({
  plugins: [react(), svgr({ exportType: "named" }), tsconfigPaths()],
  server: { host: "127.0.0.1", port: 5174, strictPort: true, hmr: false },
  optimizeDeps: { include: ["react", "react-dom/client", "react-dropzone"] },
});
