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

import { useCallback, useEffect, useMemo, useState } from "react";
import type { RuntimeContext } from "../slices/agentic/agenticOpenApi.ts";
import { SearchPolicyName } from "../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

type SearchRagScope = NonNullable<RuntimeContext["search_rag_scope"]>;

export type InitialChatPrefs = {
  documentLibraryIds: string[];
  promptResourceIds: string[];
  templateResourceIds: string[];
  searchPolicy: SearchPolicyName;
  searchRagScope?: SearchRagScope;
  deepSearch?: boolean;
  includeCorpusScope: boolean;
  includeSessionScope: boolean;
};

const EMPTY_STRING_ARRAY: string[] = [];

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
  const baseDefaults = useMemo<InitialChatPrefs>(
    () => ({
      documentLibraryIds: defaults.documentLibraryIds ?? EMPTY_STRING_ARRAY,
      promptResourceIds: defaults.promptResourceIds ?? EMPTY_STRING_ARRAY,
      templateResourceIds: defaults.templateResourceIds ?? EMPTY_STRING_ARRAY,
      searchPolicy: defaults.searchPolicy ?? "semantic",
      searchRagScope: defaults.searchRagScope,
      deepSearch: defaults.deepSearch,
      includeCorpusScope: defaults.includeCorpusScope ?? true,
      includeSessionScope: defaults.includeSessionScope ?? true,
    }),
    [
      defaults.documentLibraryIds,
      defaults.promptResourceIds,
      defaults.templateResourceIds,
      defaults.searchPolicy,
      defaults.searchRagScope,
      defaults.deepSearch,
      defaults.includeCorpusScope,
      defaults.includeSessionScope,
    ],
  );

  const [prefs, setPrefs] = useState<InitialChatPrefs>(baseDefaults);

  // If agent changes, reset to base defaults (will be overridden by stored values on next effect run).
  useEffect(() => {
    if (sessionId) return;
    setPrefs(baseDefaults);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentName, sessionId, baseDefaults]);

  const resetToDefaults = useCallback(() => setPrefs(baseDefaults), [baseDefaults]);

  return { prefs, setPrefs, resetToDefaults };
}
