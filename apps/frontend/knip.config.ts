import type { KnipConfig } from "knip";

const config: KnipConfig = {
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
