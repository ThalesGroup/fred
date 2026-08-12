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
type ReasoningEffort = "off" | "low" | "medium" | "high";
type ReasoningEffortLevel = Exclude<ReasoningEffort, "off">;

/** The platform's full closed set, low→high — narrowed per session by the
 *  reasoning control's `params.efforts` (the enable-time snapshot of what the
 *  enabled models' providers actually accept; absent = don't narrow). */
const ALL_EFFORT_LEVELS: readonly ReasoningEffortLevel[] = ["low", "medium", "high"];

/** Effort levels this session's picker may offer (level 4b narrowing). */
function offeredEffortLevels(chatControls: readonly ChatControlDescriptor[]): ReasoningEffortLevel[] {
  const control = chatControls.find((c) => c.widget === "reasoning_toggle");
  const efforts = (control?.params as { efforts?: unknown } | undefined)?.efforts;
  if (!Array.isArray(efforts)) return [...ALL_EFFORT_LEVELS];
  const narrowed = ALL_EFFORT_LEVELS.filter((level) => efforts.includes(level));
  // A malformed/empty narrowing must not kill the picker — the pod-side clamp
  // is the real guard, offering too much only makes a pick inert.
  return narrowed.length > 0 ? narrowed : [...ALL_EFFORT_LEVELS];
}

/** Seed for a `reasoning_toggle` whose `params.default` asked for reasoning
 *  on: the HIGHEST offered level — matches the ops-authored default of the
 *  only reasoning model in the catalog, so a default-on agent behaves exactly
 *  as before the picker existed. Also the clamp target for a stored level the
 *  session no longer offers ("on" intent preserved, valid value guaranteed). */
function defaultOnEffort(offered: readonly ReasoningEffortLevel[]): ReasoningEffort {
  return offered[offered.length - 1] ?? "high";
}

interface ComposerState {
  searchPolicy: SearchPolicyName;
  ragScope: RagScope;
  selectedLibraryIds: string[];
  selectedDocumentUids: string[];
  /** Per-question reasoning effort (REASON-01 level 4 + 4b, RFC §7.4). */
  reasoningEffort: ReasoningEffort;
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
  const offered = offeredEffortLevels(chatControls);
  const defaults: ComposerState = {
    searchPolicy: findDefault<SearchPolicyName>(chatControls, "search_policy") ?? "hybrid",
    ragScope: findDefault<RagScope>(chatControls, "rag_scope") ?? "hybrid",
    selectedLibraryIds: [],
    selectedDocumentUids: [],
    // Seeded from the `reasoning_toggle` widget's boolean `params.default`
    // like any other stock row. The backend ships `false` and that default is
    // a safety decision, not a style one (RFC §9): reasoning on a tool loop
    // was measured re-issuing duplicate tool calls. `?? false` also means a
    // frontend newer than the pod (no such widget) simply never reasons.
    reasoningEffort:
      (findDefault<boolean>(chatControls, "reasoning_toggle") ?? false) ? defaultOnEffort(offered) : "off",
  };
  const stored = readStorage(sessionId) as Partial<ComposerState> & { reasoning?: boolean };
  // Sessions stored before the effort picker carry the old boolean `reasoning`
  // key — map it once here rather than versioning the storage schema.
  if (stored.reasoningEffort === undefined && stored.reasoning !== undefined) {
    stored.reasoningEffort = stored.reasoning ? defaultOnEffort(offered) : "off";
  }
  delete stored.reasoning;
  // A stored level this session no longer offers (the enabled model changed,
  // or its efforts narrowed) clamps to the highest offered one — "on" intent
  // preserved, and the wire never carries a value the picker wouldn't show.
  if (
    stored.reasoningEffort !== undefined &&
    stored.reasoningEffort !== "off" &&
    !offered.includes(stored.reasoningEffort as ReasoningEffortLevel)
  ) {
    stored.reasoningEffort = defaultOnEffort(offered);
  }
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

  const setReasoningEffort = useCallback((value: ReasoningEffort) => update({ reasoningEffort: value }), [update]);

  return {
    searchPolicy: state.searchPolicy,
    ragScope: state.ragScope,
    selectedLibraryIds: state.selectedLibraryIds,
    selectedDocumentUids: state.selectedDocumentUids,
    reasoningEffort: state.reasoningEffort,
    reasoningEffortOptions: offeredEffortLevels(chatControls),
    setReasoningEffort,
    setSearchPolicy,
    setRagScope,
    setSelectedLibraryIds,
    setSelectedDocumentUids,
    reset,
  };
}
