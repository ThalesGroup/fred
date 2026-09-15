import { resolve } from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        attacker: resolve(import.meta.dirname, "attacker.html"),
        child: resolve(import.meta.dirname, "child.html"),
        host: resolve(import.meta.dirname, "index.html"),
      },
    },
    target: "es2022",
  },
});
