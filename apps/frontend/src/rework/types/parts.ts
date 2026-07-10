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

// Raw chat-part carrier (#1977, AGENT-CAPABILITY-RFC §9 item 1).
//
// Why this exists:
// - the backend `UiPart` union is OPEN: capability packages extend it at pod
//   boot, so the set of kinds this frontend build knows is always a subset of
//   what a pod may emit
// - `ThreadMessage` therefore carries parts RAW (never pre-folded into
//   kind-specific fields, which was lossy); the part-renderer registry decides
//   at render time what it can draw, and silently skips the rest — unknown
//   kinds are skipped visually, never dropped from the data

/** One chat part as emitted on `ui_parts` — known kind or not. */
export interface RawUiPart {
  type: string;
  [key: string]: unknown;
}
