// Copyright Thales 2026
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

// ESLint flat config (v9+/v10). Scope kept deliberately narrow — see docs/CONVENTIONS.md
// entry for `apps/frontend` code-quality — rather than adopting a full recommended
// rule set (which would require baselining a large pre-existing surface), each rule
// here was validated to produce zero findings on the current apps/frontend/src tree
// before being enabled, so `make code-quality` can treat any violation as a hard
// failure with no baseline/ignore mechanism needed.
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  {
    files: ["src/**/*.ts", "src/**/*.tsx"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      "@typescript-eslint": tsPlugin,
      // Registered (not enabled) only so the pre-existing
      // `eslint-disable-next-line react-hooks/exhaustive-deps` comments in this
      // codebase resolve to a known rule instead of erroring as undefined.
      "react-hooks": reactHooks,
    },
    linterOptions: {
      reportUnusedDisableDirectives: "off",
    },
    rules: {
      // Catches CodeQL's "Expression has no effect" (js/useless-expression) class
      // of bug locally instead of only via a GitHub Code Quality scan.
      "@typescript-eslint/no-unused-expressions": "error",
    },
  },
];
