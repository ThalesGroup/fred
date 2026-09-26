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

import type { IconType } from "./Type";

/** The four-value severity vocabulary shared by every notice surface. */
export type Severity = "info" | "warning" | "error" | "success";

/**
 * Severity → icon, one map for every surface that shows a severity.
 *
 * Shared so an announcement banner and an upload warning cannot drift into
 * showing different icons for the same severity. The accent colour stays in
 * each surface's stylesheet (`--success` / `--error` / `--warning` /
 * `--secondary`), since CSS custom properties cannot be handed over from here.
 */
export const SEVERITY_ICONS: Record<Severity, IconType> = {
  info: "info",
  warning: "warning",
  error: "error",
  success: "check_circle",
};

/** Most severe first — the order banners stack in. */
export const SEVERITY_RANK: Record<Severity, number> = {
  error: 0,
  warning: 1,
  success: 2,
  info: 3,
};
