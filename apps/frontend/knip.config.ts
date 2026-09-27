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

import type { KnipConfig } from "knip";

const config: KnipConfig = {
  // index.tsx is the application entry; plugins also discover test/config entrypoints.
  // Without an explicit entrypoint, Knip underestimates the live import graph.
  entry: ["src/index.tsx", "scripts/**/*.mjs"],
  project: ["src/**/*.{ts,tsx,js,jsx}", "scripts/**/*.mjs"],
  // Invoked by Makefile update-*-api targets, outside the import graph.
  ignoreDependencies: ["@rtk-query/codegen-openapi"],
  ignore: [
    // Generated API slices — unused exports are expected
    "src/**/*OpenApi.ts",
  ],
  rules: {
    // Diagnostic candidates: verify consumers before any deletion.
    exports: "warn",
    types: "warn",
  },
};

export default config;
