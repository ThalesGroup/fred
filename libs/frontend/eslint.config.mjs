import eslint from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: [
      "node_modules/**",
      "target/**",
      "design-tokens/dist/**",
      "design-tokens/licenses/**",
    ],
  },
  eslint.configs.recommended,
  {
    files: ["**/*.mjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: globals.node,
    },
  },
  {
    files: ["scripts/browser-smoke.mjs"],
    languageOptions: {
      globals: globals.browser,
    },
  },
];
