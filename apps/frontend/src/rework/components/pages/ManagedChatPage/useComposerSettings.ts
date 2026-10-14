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
import type { ChatControlDescriptor, EffectiveChatModel } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { currentModelRow, recommendedModelRow } from "../../../features/capabilities/modelChoice";
import { modelLabel } from "../../../features/capabilities/ReasoningChip";

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
  askUser: boolean;
  /** The conversation's model choice; null runs the agent's recommended model. */
  chatProfileId: string | null;
  /** Its display name, kept to name it once it is no longer offered. */
  chatModelLabel: string | null;
}

/** Reads a stock widget's `params.default` (RFC §3.3), e.g. `search_policy` /
 * `rag_scope`, from the ordered `chat_controls` list. */
function findDefault<T>(chatControls: readonly ChatControlDescriptor[], widget: string): T | undefined {
  const params = chatControls.find((c) => c.widget === widget)?.params as { default?: T } | undefined;
  return params?.default;
}

/** A remembered scope the `rag_scope` control no longer offers (e.g. "Your
 *  documents" on an attachments-only agent) falls back to the control default. */
function offeredRagScope(scope: RagScope, chatControls: readonly ChatControlDescriptor[]): RagScope {
  const params = chatControls.find((c) => c.widget === "rag_scope")?.params as
    | { default?: RagScope; options?: RagScope[] | null }
    | undefined;
  if (!params?.options || params.options.includes(scope)) return scope;
  return params.default ?? "hybrid";
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

function buildInitial(
  sessionId: string | null,
  chatControls: readonly ChatControlDescriptor[],
  effectiveModel: EffectiveChatModel | undefined,
): ComposerState {
  const defaults: ComposerState = {
    searchPolicy: findDefault<SearchPolicyName>(chatControls, "search_policy") ?? "hybrid",
    ragScope: findDefault<RagScope>(chatControls, "rag_scope") ?? "hybrid",
    selectedLibraryIds: [],
    selectedDocumentUids: [],
    // The team's reasoning default for the model the conversation starts on.
    reasoning: recommendedModelRow(effectiveModel)?.reasoning_default_on ?? false,
    askUser: findDefault<boolean>(chatControls, "ask_user_toggle") ?? true,
    chatProfileId: null,
    chatModelLabel: null,
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

/** `state` without a model choice `model` no longer offers, falling back to the
 *  recommended model; `dropped` names the lost choice. An empty list (locked
 *  choice, unreachable pod) proves nothing and keeps the choice. */
function withoutStaleChoice(
  state: ComposerState,
  model: EffectiveChatModel | undefined,
): { state: ComposerState; dropped: string | null } {
  const rows = model?.selectable_models ?? [];
  if (!state.chatProfileId || rows.length === 0 || rows.some((row) => row.profile_id === state.chatProfileId)) {
    return { state, dropped: null };
  }
  return {
    state: {
      ...state,
      chatProfileId: null,
      chatModelLabel: null,
      reasoning: recommendedModelRow(model)?.reasoning_default_on ?? false,
    },
    dropped: state.chatModelLabel ?? state.chatProfileId,
  };
}

/**
 * Owns the per-session composer settings: search policy, RAG scope,
 * library selection, selected documents, reasoning and the model choice.
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
export function useComposerSettings(
  sessionId: string | null,
  chatControls: readonly ChatControlDescriptor[],
  effectiveModel?: EffectiveChatModel,
  onChoiceDropped?: (modelLabel: string) => void,
) {
  const [state, setState] = useState<ComposerState>(() => buildInitial(sessionId, chatControls, effectiveModel));

  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = sessionId;
  const effectiveModelRef = useRef(effectiveModel);
  effectiveModelRef.current = effectiveModel;
  const onChoiceDroppedRef = useRef(onChoiceDropped);
  onChoiceDroppedRef.current = onChoiceDropped;

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
    setState(buildInitial(sessionIdRef.current, chatControls, effectiveModelRef.current));
  }, [chatControls]);

  // Drops a choice the current model list no longer offers, visibly; run when
  // the list refreshes and when another conversation's choice is loaded.
  const dropStaleChoice = useCallback((candidate: ComposerState, targetSessionId: string | null) => {
    const { state: checked, dropped } = withoutStaleChoice(candidate, effectiveModelRef.current);
    if (dropped === null) return candidate;
    if (targetSessionId) writeStorage(targetSessionId, checked);
    onChoiceDroppedRef.current?.(dropped);
    return checked;
  }, []);

  // The selectable models arrive (or refresh) after mount.
  useEffect(() => {
    if (!effectiveModel) return;
    const current = stateRef.current;
    const checked = dropStaleChoice(current, sessionIdRef.current);
    if (checked !== current) {
      setState(checked);
      return;
    }
    if (userEditedRef.current) return;
    if (Object.keys(readStorage(sessionIdRef.current)).length > 0) return;
    const seeded = currentModelRow(effectiveModel, current.chatProfileId)?.reasoning_default_on ?? false;
    setState((prev) => (prev.reasoning === seeded ? prev : { ...prev, reasoning: seeded }));
  }, [effectiveModel, dropStaleChoice]);

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

  const reset = useCallback(
    (nextSessionId: string | null, nextChatControls: readonly ChatControlDescriptor[]) => {
      userEditedRef.current = false;
      const initial = buildInitial(nextSessionId, nextChatControls, effectiveModelRef.current);
      setState(dropStaleChoice(initial, nextSessionId));
    },
    [dropStaleChoice],
  );

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
  const setAskUser = useCallback((value: boolean) => update({ askUser: value }), [update]);

  // Switching model restarts reasoning from the team's default for it; the
  // recommended model is stored as no choice, so later default changes apply.
  const setChatProfileId = useCallback(
    (profileId: string) => {
      const model = effectiveModelRef.current;
      const row = model?.selectable_models?.find((entry) => entry.profile_id === profileId);
      if (!row) return;
      const recommended = row === recommendedModelRow(model);
      update({
        chatProfileId: recommended ? null : row.profile_id,
        chatModelLabel: recommended ? null : modelLabel(row.display_name, row.name, row.capability_id),
        reasoning: row.reasoning_default_on ?? false,
      });
    },
    [update],
  );

  return {
    searchPolicy: state.searchPolicy,
    ragScope: offeredRagScope(state.ragScope, chatControls),
    selectedLibraryIds: state.selectedLibraryIds,
    selectedDocumentUids: state.selectedDocumentUids,
    reasoning: state.reasoning,
    setReasoning,
    askUser: state.askUser,
    setAskUser,
    chatProfileId: state.chatProfileId,
    setChatProfileId,
    setSearchPolicy,
    setRagScope,
    setSelectedLibraryIds,
    setSelectedDocumentUids,
    reset,
    bindSession,
  };
}
