// Copyright Thales 2025
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

import { getConfig } from "../common/config";
import type { Properties } from "../slices/agentic/agenticOpenApi";

/**
 * Custom hook to access frontend properties from the bootstrapped frontend configuration.
 *
 * Why this exists:
 * - Frontend properties are already loaded by `loadConfig()` before React mounts.
 * - Reading the bootstrapped config avoids a second async fetch and removes first-render races in navigation components.
 *
 * How to use it:
 * - Call the hook inside a React component and destructure the properties you need.
 * - The hook returns the same backend-provided properties stored in the shared frontend config.
 *
 * Example:
 * - `const { agentsNicknamePlural, siteDisplayName } = useFrontendProperties();`
 *
 * @returns The frontend properties object containing configuration like agentsNickname, etc.
 */
export function useFrontendProperties(): Properties {
  return getConfig().properties;
}
