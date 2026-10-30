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

import type { DocumentLibrarySelection } from "@shared/molecules/DocumentLibraryScopePicker/documentLibrarySelection";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { useCallback, useEffect, useRef, useState } from "react";
import type { SearchPolicyName } from "../../../../slices/legacyKnowledgeFlow/knowledgeFlowOpenApi";
import type { ChatControlDescriptor, PreparationModels } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { modelChoiceKey, offerLabel } from "../../../features/capabilities/modelChoice";

type RagScope = "corpus_only" | "hybrid" | "general_only";

interface ComposerState {
  agentConfigurationRevision: number | null;
  searchPolicy: SearchPolicyName;
  ragScope: RagScope;
  /** null inherits the agent scope; empty arrays deliberately select nothing. */
  documentSelection: DocumentLibrarySelection | null;
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
  return `chat.composer.${KeyCloakService.GetSessionIdentity()}.${sessionId}`;
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
    agentConfigurationRevision: null,
    searchPolicy: findDefault<SearchPolicyName>(chatControls, "search_policy") ?? "hybrid",
    ragScope: findDefault<RagScope>(chatControls, "rag_scope") ?? "hybrid",
    documentSelection: null,
    // The team's reasoning default for the model the conversation starts on.
    reasoning: findDefault<boolean>(chatControls, "reasoning_toggle") ?? false,
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

/**
 * Owns the per-session composer settings: search policy, RAG scope,
 * library selection, selected documents, reasoning and the model choice.
 *
 * Initialises from sessionStorage (user, space, agent, session or draft) when available,
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
  effectiveModel?: PreparationModels,
  scopeKey = "",
) {
  const scopedSession = useCallback((id: string | null) => `${scopeKey}:${id ?? "draft"}`, [scopeKey]);
  const [state, setState] = useState<ComposerState>(() => buildInitial(scopedSession(sessionId), chatControls));

  const sessionIdRef = useRef(sessionId);
  sessionIdRef.current = scopedSession(sessionId);
  const effectiveModelRef = useRef(effectiveModel);
  effectiveModelRef.current = effectiveModel;
  // Read by bindSession() below, which fires from a callback and so cannot
  // close over the render-time state.
  const stateRef = useRef(state);
  stateRef.current = state;

  // Fresh preparation descriptors must not overwrite an explicit choice,
  // including one made before the first session id exists.
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
      const next = { ...stateRef.current, ...patch };
      stateRef.current = next;
      writeStorage(scopedSession(sessionId), next);
      setState(next);
    },
    [sessionId, scopedSession],
  );

  const reset = useCallback(
    (nextSessionId: string | null, nextChatControls: readonly ChatControlDescriptor[]) => {
      userEditedRef.current = false;
      sessionIdRef.current = scopedSession(nextSessionId);
      const initial = buildInitial(scopedSession(nextSessionId), nextChatControls);
      stateRef.current = initial;
      setState(initial);
    },
    [scopedSession],
  );

  const acceptPreparation = useCallback((revision: number, controls: readonly ChatControlDescriptor[]) => {
    const previous = stateRef.current.agentConfigurationRevision;
    if (previous !== null && previous !== revision) {
      throw { status: 409, data: { code: "agent_configuration_changed" } };
    }
    if (previous !== null) return;
    const next = {
      ...(!userEditedRef.current && Object.keys(readStorage(sessionIdRef.current)).length === 0
        ? buildInitial(null, controls)
        : stateRef.current),
      agentConfigurationRevision: revision,
    };
    stateRef.current = next;
    if (sessionIdRef.current) writeStorage(sessionIdRef.current, next);
    setState(next);
  }, []);

  const discardDraft = useCallback(() => {
    try {
      sessionStorage.removeItem(storageKey(scopedSession(null)));
    } catch {
      // Same best-effort browser persistence as readStorage/writeStorage.
    }
  }, [scopedSession]);

  // Move the scoped draft to its assigned session before router binding.
  // An untouched draft must not freeze asynchronous control defaults.
  const bindSession = useCallback(
    (nextSessionId: string) => {
      if (!userEditedRef.current && Object.keys(readStorage(scopedSession(null))).length === 0) return;
      writeStorage(scopedSession(nextSessionId), stateRef.current);
      discardDraft();
    },
    [scopedSession, discardDraft],
  );

  const setSearchPolicy = useCallback((p: SearchPolicyName) => update({ searchPolicy: p }), [update]);

  const setRagScope = useCallback((s: RagScope) => update({ ragScope: s }), [update]);

  const setDocumentSelection = useCallback(
    (selection: DocumentLibrarySelection | null) => update({ documentSelection: selection }),
    [update],
  );

  const setReasoning = useCallback((value: boolean) => update({ reasoning: value }), [update]);
  const setAskUser = useCallback((value: boolean) => update({ askUser: value }), [update]);

  // Switching model restarts reasoning from the team's default for it; the
  // recommended model is stored as no choice, so later default changes apply.
  const setChatProfileId = useCallback(
    (profileId: string) => {
      const model = effectiveModelRef.current;
      const row = model?.offers.find((entry) => modelChoiceKey(entry.key) === profileId && entry.selectable);
      if (!row) return;
      update({ chatProfileId: modelChoiceKey(row.key), chatModelLabel: offerLabel(row), reasoning: false });
    },
    [update],
  );

  return {
    agentConfigurationRevision: state.agentConfigurationRevision,
    acceptPreparation,
    searchPolicy: state.searchPolicy,
    ragScope: offeredRagScope(state.ragScope, chatControls),
    documentSelection: state.documentSelection,
    reasoning: state.reasoning,
    setReasoning,
    askUser: state.askUser,
    setAskUser,
    chatProfileId: state.chatProfileId,
    setChatProfileId,
    setSearchPolicy,
    setRagScope,
    setDocumentSelection,
    reset,
    bindSession,
    discardDraft,
  };
}
