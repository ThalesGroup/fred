import eslint from "@eslint/js";
import globals from "globals";

export default [
  {
    ignores: [
      "node_modules/**",
      "target/**",
      "design-tokens/dist/**",
      "design-tokens/licenses/**",
      "ui/.generated/**",
      "ui/dist/**",
      "ui/licenses/**",
      "iframe-sdk/.generated/**",
      "iframe-sdk/dist/**",
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
