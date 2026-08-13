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
  /** Per-question reasoning activation (REASON-01 level 4, RFC §7.4). On/off
   *  only — the effort a reasoning turn runs with is the ops-authored
   *  `reasoning_effort` of the routed profile, never a user pick. */
  reasoning: boolean;
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
    // Seeded from the `reasoning_toggle` widget's `params.default` like any
    // other stock row. The backend ships `false` and that default is a safety
    // decision, not a style one (RFC §9): reasoning on a tool loop was
    // measured re-issuing duplicate tool calls. `?? false` also means a
    // frontend newer than the pod (no such widget) simply never reasons.
    reasoning: findDefault<boolean>(chatControls, "reasoning_toggle") ?? false,
  };
  const stored = readStorage(sessionId) as Partial<ComposerState> & { reasoningEffort?: string };
  // Sessions stored by the short-lived effort-picker build (2026-08-12, dev
  // only) carry a `reasoningEffort` string instead of the boolean — map it
  // back once rather than versioning the storage schema.
  if (stored.reasoning === undefined && stored.reasoningEffort !== undefined) {
    stored.reasoning = stored.reasoningEffort !== "off";
  }
  delete stored.reasoningEffort;
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
 * Call reset() when the session changes to reinitialise from storage/defaults,
 * and bindSession() when a session id is minted for a conversation that had
 * none — that is the moment a pick made before the first message becomes
 * durable (#2369).
 */
export function useComposerSettings(sessionId: string | null, chatControls: readonly ChatControlDescriptor[]) {
  const [state, setState] = useState<ComposerState>(() => buildInitial(sessionId, chatControls));

  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;

  // Read by bindSession() below, which fires from a callback and so cannot
  // close over the render-time state.
  const stateRef = useRef(state);
  stateRef.current = state;

  // True as soon as the user picks anything; cleared by reset() (a genuine
  // entry into a new or different session). #2369: sessionStorage alone cannot
  // stand in for it. A pick made in a brand-new conversation happens while
  // `sessionId` is still null, so update() below writes nothing — and
  // prepare-execution hands back a FRESH chat_controls array on every send(),
  // which re-runs the effect below. Without this flag the first send reverted
  // the user's own reasoning pick (and search policy, RAG scope, library and
  // document selection) to the widget defaults, mid-conversation.
  const userEditedRef = useRef(false);

  // chatControls arrives async (an eager prepare-execution call, RFC §3.7). If
  // it was empty at mount and no sessionStorage data exists for this session,
  // apply the resolved defaults now. Defaults only ever fill a gap: a resolved
  // value the user chose themselves outranks them.
  useEffect(() => {
    if (chatControls.length === 0) return;
    if (userEditedRef.current) return;
    if (Object.keys(readStorage(sessionIdRef.current)).length > 0) return;
    setState(buildInitial(sessionIdRef.current, chatControls));
  }, [chatControls]);

  const update = useCallback(
    (patch: Partial<ComposerState>) => {
      userEditedRef.current = true;
      setState((prev) => {
        const next = { ...prev, ...patch };
        if (sessionId) writeStorage(sessionId, next);
        return next;
      });
    },
    [sessionId],
  );

  const reset = useCallback((nextSessionId: string | null, nextChatControls: readonly ChatControlDescriptor[]) => {
    userEditedRef.current = false;
    setState(buildInitial(nextSessionId, nextChatControls));
  }, []);

  // Called by the caller that MINTS a session id for a conversation that had
  // none (#2369) — the flag above keeps the pick alive for the rest of the
  // mount, this is what makes it durable. Until the id exists update() has
  // nowhere to write, so without this a reasoning pick made before the first
  // message was gone the next time the user entered that very session (reload,
  // or leaving and coming back), reverting to the widget default one
  // navigation later. Only a real pick is written: seeding storage with
  // untouched defaults would freeze them against a later chat_controls
  // refresh, which is exactly what the storage guard above is there to allow.
  const bindSession = useCallback((nextSessionId: string) => {
    if (!userEditedRef.current) return;
    writeStorage(nextSessionId, stateRef.current);
  }, []);

  const setSearchPolicy = useCallback((p: SearchPolicyName) => update({ searchPolicy: p }), [update]);

  const setRagScope = useCallback((s: RagScope) => update({ ragScope: s }), [update]);

  const setSelectedLibraryIds = useCallback((ids: string[]) => update({ selectedLibraryIds: ids }), [update]);

  const setSelectedDocumentUids = useCallback((uids: string[]) => update({ selectedDocumentUids: uids }), [update]);

  const setReasoning = useCallback((value: boolean) => update({ reasoning: value }), [update]);

  return {
    searchPolicy: state.searchPolicy,
    ragScope: state.ragScope,
    selectedLibraryIds: state.selectedLibraryIds,
    selectedDocumentUids: state.selectedDocumentUids,
    reasoning: state.reasoning,
    setReasoning,
    setSearchPolicy,
    setRagScope,
    setSelectedLibraryIds,
    setSelectedDocumentUids,
    reset,
    bindSession,
  };
}
