import type { KnipConfig } from "knip";

const config: KnipConfig = {
  // The frontend bootstraps from index.tsx, then loads the router lazily from App.tsx.
  // Without an explicit entrypoint, Knip underestimates the live import graph.
  entry: ["src/index.tsx"],
  project: ["src/**/*.{ts,tsx}"],
  ignore: [
    // Generated API slices — unused exports are expected
    "src/slices/**/*OpenApi.ts",
  ],
  rules: {
    // Exporting props and types for potential reuse is intentional
    exports: "off",
    types: "off",
  },
};

export default config;
