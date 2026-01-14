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

import { useEffect, useState } from "react";
import { SearchRagScope } from "../components/chatbot/user_input/types.ts";
import { SearchPolicyName } from "../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

export type InitialChatPrefs = {
  documentLibraryIds: string[];
  promptResourceIds: string[];
  templateResourceIds: string[];
  searchPolicy: SearchPolicyName;
  searchRagScope?: SearchRagScope;
  deepSearch?: boolean;
};

/**
 * Manages pre-session (draft) chat input defaults per user and agent.
 * - Resets to sensible defaults on agent change.
 *
 * This hook is intentionally session-agnostic and does not persist locally.
 * Per-session persistence stays in UserInput / backend.
 */
export function useInitialChatInputContext(
  agentName: string,
  sessionId?: string,
  defaults: Partial<InitialChatPrefs> = {},
) {
  const baseDefaults: InitialChatPrefs = {
    documentLibraryIds: [],
    promptResourceIds: [],
    templateResourceIds: [],
    searchPolicy: "semantic",
    ...defaults,
  };

  const [prefs, setPrefs] = useState<InitialChatPrefs>(baseDefaults);

  // If agent changes, reset to base defaults (will be overridden by stored values on next effect run).
  useEffect(() => {
    if (sessionId) return;
    setPrefs(baseDefaults);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentName, sessionId]);

  const resetToDefaults = () => setPrefs(baseDefaults);

  return { prefs, setPrefs, resetToDefaults };
}
