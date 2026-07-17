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

import { useCallback, useEffect, useRef, useState } from "react";
import type { SearchPolicyName } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { ChatControlDescriptor } from "../../../../slices/controlPlane/controlPlaneOpenApi";

type RagScope = "corpus_only" | "hybrid" | "general_only";

interface ComposerState {
  searchPolicy: SearchPolicyName;
  ragScope: RagScope;
  selectedLibraryIds: string[];
  selectedDocumentUids: string[];
}

/** Reads a stock widget's `params.default` (RFC §3.3), e.g. `search_policy` /
 * `rag_scope`, from the ordered `chat_controls` list. */
function findDefault<T>(chatControls: readonly ChatControlDescriptor[], widget: string): T | undefined {
  const params = chatControls.find((c) => c.widget === widget)?.params as { default?: T } | undefined;
  return params?.default;
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

function buildInitial(sessionId: string | null, chatControls: readonly ChatControlDescriptor[]): ComposerState {
  const defaults: ComposerState = {
    searchPolicy: findDefault<SearchPolicyName>(chatControls, "search_policy") ?? "hybrid",
    ragScope: findDefault<RagScope>(chatControls, "rag_scope") ?? "hybrid",
    selectedLibraryIds: [],
    selectedDocumentUids: [],
  };
  const stored = readStorage(sessionId);
  return { ...defaults, ...stored };
}

/**
 * Owns the per-session composer settings: search policy, RAG scope,
 * library selection, and selected documents.
 *
 * Initialises from sessionStorage (keyed by sessionId) when available,
 * otherwise from the `search_policy`/`rag_scope` chat-control descriptors'
 * `params.default` (CAPAB-01 #1976 — supersedes the retired
 * `EffectiveChatOptions.default_search_policy`/`default_search_rag_scope`).
 * Writes through to sessionStorage on every change so state survives
 * navigation within the same browser tab.
 *
 * Call reset() when the session changes to reinitialise from storage/defaults.
 */
export function useComposerSettings(sessionId: string | null, chatControls: readonly ChatControlDescriptor[]) {
  const [state, setState] = useState<ComposerState>(() => buildInitial(sessionId, chatControls));

  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  // chatControls arrives async (an eager prepare-execution call, RFC §3.7). If
  // it was empty at mount and no sessionStorage data exists for this session,
  // apply the resolved defaults now.
  useEffect(() => {
    if (chatControls.length === 0) return;
    if (Object.keys(readStorage(sessionIdRef.current)).length > 0) return;
    setState(buildInitial(sessionIdRef.current, chatControls));
  }, [chatControls]);

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

  const reset = useCallback((nextSessionId: string | null, nextChatControls: readonly ChatControlDescriptor[]) => {
    setState(buildInitial(nextSessionId, nextChatControls));
  }, []);

  const setSearchPolicy = useCallback((p: SearchPolicyName) => update({ searchPolicy: p }), [update]);

  const setRagScope = useCallback((s: RagScope) => update({ ragScope: s }), [update]);

  const setSelectedLibraryIds = useCallback((ids: string[]) => update({ selectedLibraryIds: ids }), [update]);

  const setSelectedDocumentUids = useCallback((uids: string[]) => update({ selectedDocumentUids: uids }), [update]);

  return {
    searchPolicy: state.searchPolicy,
    ragScope: state.ragScope,
    selectedLibraryIds: state.selectedLibraryIds,
    selectedDocumentUids: state.selectedDocumentUids,
    setSearchPolicy,
    setRagScope,
    setSelectedLibraryIds,
    setSelectedDocumentUids,
    reset,
  };
}
