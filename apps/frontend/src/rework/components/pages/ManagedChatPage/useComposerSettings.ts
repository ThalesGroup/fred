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

import { useCallback, useEffect, useState } from "react";
import type { SearchPolicyName } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { EffectiveChatOptions } from "../../../../slices/controlPlane/controlPlaneOpenApi";

type RagScope = "corpus_only" | "hybrid" | "general_only";

interface ComposerState {
  searchPolicy: SearchPolicyName;
  ragScope: RagScope;
  selectedLibraryIds: string[];
}

function storageKey(sessionId: string): string {
  return `chat.composer.${sessionId}`;
}

function readStorage(sessionId: string | null): Partial<ComposerState> {
  if (!sessionId) return {};
  try {
    const raw = sessionStorage.getItem(storageKey(sessionId));
    return raw ? (JSON.parse(raw) as Partial<ComposerState>) : {};
  } catch {
    return {};
  }
}

function writeStorage(sessionId: string, state: ComposerState): void {
  try {
    sessionStorage.setItem(storageKey(sessionId), JSON.stringify(state));
  } catch {
    // sessionStorage quota exceeded — silently ignore
  }
}

function buildInitial(sessionId: string | null, agentOptions: EffectiveChatOptions | null): ComposerState {
  const defaults: ComposerState = {
    searchPolicy: agentOptions?.default_search_policy ?? "hybrid",
    ragScope: agentOptions?.default_search_rag_scope ?? "hybrid",
    selectedLibraryIds: [],
  };
  const stored = readStorage(sessionId);
  return { ...defaults, ...stored };
}

/**
 * Owns the three per-session composer settings: search policy, RAG scope,
 * and library selection.
 *
 * Initialises from sessionStorage (keyed by sessionId) when available,
 * otherwise from the agent's effective_chat_options defaults.
 * Writes through to sessionStorage on every change so state survives
 * navigation within the same browser tab.
 *
 * Call reset() when the session changes to reinitialise from storage/defaults.
 */
export function useComposerSettings(sessionId: string | null, agentOptions: EffectiveChatOptions | null) {
  const [state, setState] = useState<ComposerState>(() => buildInitial(sessionId, agentOptions));

  // agentOptions arrives async (RTK Query). If it was null at mount and no
  // sessionStorage data exists for this session, apply the agent defaults now.
  useEffect(() => {
    if (!agentOptions) return;
    if (Object.keys(readStorage(sessionId)).length > 0) return;
    setState(buildInitial(sessionId, agentOptions));
  }, [agentOptions]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = useCallback(
    (patch: Partial<ComposerState>) => {
      setState((prev) => {
        const next = { ...prev, ...patch };
        if (sessionId) writeStorage(sessionId, next);
        return next;
      });
    },
    [sessionId],
  );

  const reset = useCallback((nextSessionId: string | null, nextAgentOptions: EffectiveChatOptions | null) => {
    setState(buildInitial(nextSessionId, nextAgentOptions));
  }, []);

  const setSearchPolicy = useCallback((p: SearchPolicyName) => update({ searchPolicy: p }), [update]);

  const setRagScope = useCallback((s: RagScope) => update({ ragScope: s }), [update]);

  const setSelectedLibraryIds = useCallback((ids: string[]) => update({ selectedLibraryIds: ids }), [update]);

  return {
    searchPolicy: state.searchPolicy,
    ragScope: state.ragScope,
    selectedLibraryIds: state.selectedLibraryIds,
    setSearchPolicy,
    setRagScope,
    setSelectedLibraryIds,
    reset,
  };
}
