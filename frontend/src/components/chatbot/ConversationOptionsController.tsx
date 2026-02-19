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

import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import { Box, IconButton } from "@mui/material";
import { useCallback, useEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import type { AnyAgent } from "../../common/agent.ts";
import ChatDocumentLibrariesWidget from "../../features/libraries/components/ChatDocumentLibrariesWidget.tsx";
import { useInitialChatInputContext, type InitialChatPrefs } from "../../hooks/useInitialChatInputContext.ts";
import type { RuntimeContext } from "../../slices/agentic/agenticOpenApi.ts";
import {
  useGetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetQuery,
  useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation,
} from "../../slices/agentic/agenticOpenApi.ts";
import type { Resource, SearchPolicyName, TagWithItemsId } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import ChatAttachmentsWidget from "./ChatAttachmentsWidget.tsx";
import ChatContextWidget from "./ChatContextWidget.tsx";
import ChatDeepSearchWidget from "./ChatDeepSearchWidget.tsx";
import ChatDocumentsWidget from "./ChatDocumentsWidget.tsx";
import ChatKnowledge from "./ChatKnowledge.tsx";
import ChatLogGeniusWidget from "./ChatLogGeniusWidget.tsx";
import ChatSearchOptionsWidget from "./ChatSearchOptionsWidget.tsx";

type SearchRagScope = NonNullable<RuntimeContext["search_rag_scope"]>;

export type ConversationPrefs = InitialChatPrefs & {
  chatContextIds: string[];
};

type PrefsLoadState = "idle" | "loading" | "hydrated";

type PersistedCtx = {
  chatContextIds?: string[];
  documentLibraryIds?: string[];
  documentUids?: string[];
  promptResourceIds?: string[];
  templateResourceIds?: string[];
  searchPolicy?: SearchPolicyName;
  searchRagScope?: SearchRagScope;
  deepSearch?: boolean;
  includeCorpusScope?: boolean;
  includeDocumentScope?: boolean;
  includeSessionScope?: boolean;
  ragKnowledgeScope?: SearchRagScope;
  skipRagSearch?: boolean;
  agent_id?: string;
  // Legacy fallback key kept for backward compatibility with previously persisted sessions.
  agent_name?: string;
};

const serializePrefs = (p: PersistedCtx) =>
  JSON.stringify(Object.fromEntries(Object.entries(p).sort(([a], [b]) => a.localeCompare(b))));

const asStringArray = (v: unknown, fallback: string[] = []): string[] => {
  if (!Array.isArray(v)) return fallback;
  return v.filter((x): x is string => typeof x === "string" && x.length > 0);
};

const asBoolean = (v: unknown, fallback: boolean): boolean => (typeof v === "boolean" ? v : fallback);

const resolvePreferredAgentId = (prefs: PersistedCtx): string | undefined => {
  if (typeof prefs.agent_id === "string" && prefs.agent_id.trim().length > 0) {
    return prefs.agent_id.trim();
  }
  if (typeof prefs.agent_name === "string" && prefs.agent_name.trim().length > 0) {
    return prefs.agent_name.trim();
  }
  return undefined;
};

type ControllerArgs = {
  chatSessionId?: string;
  prefsTargetSessionId?: string;
  agents: AnyAgent[];
  initialAgent?: AnyAgent;
};

export type ConversationOptionsState = {
  conversationPrefs: ConversationPrefs;
  currentAgent: AnyAgent;
  supportsRagScopeSelection: boolean;
  supportsSearchPolicySelection: boolean;
  supportsDeepSearchSelection: boolean;
  supportsAttachments: boolean;
  supportsLibrariesSelection: boolean;
  supportsDocumentsSelection: boolean;
  isHydratingSession: boolean;
  isSessionPrefsReady: boolean;
  prefsTargetSessionId?: string;
  prefsLoadState: PrefsLoadState;
  sessionPrefs?: PersistedCtx;
  isPrefsFetching: boolean;
  isPrefsError: boolean;
  prefsError: unknown;
  defaultSearchPolicy: SearchPolicyName;
  defaultRagScope: SearchRagScope;
  defaultSearchRagScope: SearchRagScope;
  displayChatContextIds: string[];
  displayDocumentLibraryIds: string[];
  displayDocumentUids: string[];
  chatContextWidgetOpenDisplay: boolean;
  attachmentsWidgetOpenDisplay: boolean;
  searchOptionsWidgetOpenDisplay: boolean;
  librariesWidgetOpenDisplay: boolean;
  documentsWidgetOpenDisplay: boolean;
  deepSearchWidgetOpenDisplay: boolean;
  logGeniusWidgetOpenDisplay: boolean;
  widgetsOpen: boolean;
  layout: {
    chatWidgetRail: string;
    chatWidgetGap: string;
    chatContentRightPadding: string;
    chatContentWidth: string;
    chatContentLeftPadding: number;
  };
  userInputContext: {
    documentLibraryIds: string[];
    documentUids: string[];
    promptResourceIds: string[];
    templateResourceIds: string[];
  };
  hasContext: boolean;
  contextOpen: boolean;
};

export type ConversationOptionsActions = {
  setSearchPolicy: (next: SetStateAction<SearchPolicyName>) => void;
  setSearchRagScope: (next: SearchRagScope) => void;
  setDeepSearchEnabled: (next: boolean) => void;
  setIncludeCorpusScope: (next: boolean) => void;
  setIncludeDocumentScope: (next: boolean) => void;
  setIncludeSessionScope: (next: boolean) => void;
  setChatContextIds: (ids: string[]) => void;
  setDocumentLibraryIds: (ids: string[]) => void;
  setDocumentUids: (ids: string[]) => void;
  selectAgent: (agent: AnyAgent) => Promise<void>;
  seedSessionPrefs: (chatSessionId: string, agentId?: string) => Promise<unknown>;
  setChatContextWidgetOpen: (open: boolean) => void;
  setAttachmentsWidgetOpen: (open: boolean) => void;
  setSearchOptionsWidgetOpen: (open: boolean) => void;
  setLibrariesWidgetOpen: (open: boolean) => void;
  setDocumentsWidgetOpen: (open: boolean) => void;
  setDeepSearchWidgetOpen: (open: boolean) => void;
  setLogGeniusWidgetOpen: (open: boolean) => void;
  setContextOpen: (open: boolean) => void;
};

export type ConversationOptionsController = {
  state: ConversationOptionsState;
  actions: ConversationOptionsActions;
};

export function useConversationOptionsController({
  chatSessionId,
  prefsTargetSessionId,
  agents,
  initialAgent,
}: ControllerArgs): ConversationOptionsController {
  // Use initialAgent from URL if provided, otherwise fallback to agents[0]
  const defaultAgent = useMemo(() => initialAgent ?? agents[0] ?? null, [initialAgent, agents]);
  const [currentAgent, setCurrentAgent] = useState<AnyAgent>(initialAgent ?? agents[0] ?? ({} as AnyAgent));

  useEffect(() => {
    if (defaultAgent && (!currentAgent || !currentAgent.id)) setCurrentAgent(defaultAgent);
  }, [currentAgent, defaultAgent]);

  const defaultRagScope: SearchRagScope = "hybrid";
  const { prefs: initialCtx, resetToDefaults } = useInitialChatInputContext(
    currentAgent?.id || "default",
    chatSessionId,
    {
      includeCorpusScope: currentAgent?.chat_options?.include_corpus_in_search ?? true,
    },
  );
  const defaultSearchPolicy: SearchPolicyName = initialCtx.searchPolicy ?? "semantic";
  const defaultSearchRagScope: SearchRagScope = initialCtx.searchRagScope ?? defaultRagScope;

  const [conversationPrefs, setConversationPrefs] = useState<ConversationPrefs>(() => ({
    chatContextIds: [],
    documentLibraryIds: initialCtx.documentLibraryIds,
    documentUids: initialCtx.documentUids,
    promptResourceIds: initialCtx.promptResourceIds,
    templateResourceIds: initialCtx.templateResourceIds,
    searchPolicy: initialCtx.searchPolicy,
    searchRagScope: initialCtx.searchRagScope ?? defaultRagScope,
    deepSearch: initialCtx.deepSearch ?? false,
    includeCorpusScope: initialCtx.includeCorpusScope ?? true,
    includeDocumentScope: initialCtx.includeDocumentScope ?? true,
    includeSessionScope: initialCtx.includeSessionScope ?? true,
  }));

  useEffect(() => {
    if (chatSessionId) return;
    setConversationPrefs((prev) => ({
      ...prev,
      chatContextIds: [],
      documentLibraryIds: initialCtx.documentLibraryIds,
      documentUids: initialCtx.documentUids,
      promptResourceIds: initialCtx.promptResourceIds,
      templateResourceIds: initialCtx.templateResourceIds,
      searchPolicy: initialCtx.searchPolicy,
      searchRagScope: initialCtx.searchRagScope ?? defaultRagScope,
      deepSearch: initialCtx.deepSearch ?? false,
      includeCorpusScope: initialCtx.includeCorpusScope ?? true,
      includeDocumentScope: initialCtx.includeDocumentScope ?? true,
      includeSessionScope: initialCtx.includeSessionScope ?? true,
    }));
  }, [chatSessionId, initialCtx, defaultRagScope]);

  const supportsRagScopeSelection = currentAgent?.chat_options?.search_rag_scoping === true;
  const supportsSearchPolicySelection = currentAgent?.chat_options?.search_policy_selection === true;
  const supportsDeepSearchSelection = currentAgent?.chat_options?.deep_search_delegate === true;
  const supportsAttachments = currentAgent?.chat_options?.attach_files === true;
  const supportsLibrariesSelection = currentAgent?.chat_options?.libraries_selection === true;
  const supportsDocumentsSelection = currentAgent?.chat_options?.documents_selection === true;

  const [persistSessionPrefs] = useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation();
  const {
    currentData: sessionPrefs,
    isFetching: isPrefsFetching,
    isError: isPrefsError,
    error: prefsError,
  } = useGetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetQuery(
    { sessionId: prefsTargetSessionId || "" },
    {
      skip: !prefsTargetSessionId,
      refetchOnMountOrArgChange: true,
      refetchOnReconnect: true,
      refetchOnFocus: true,
    },
  );

  const [chatContextWidgetOpen, setChatContextWidgetOpen] = useState<boolean>(false);
  const [attachmentsWidgetOpen, setAttachmentsWidgetOpen] = useState<boolean>(false);
  const [searchOptionsWidgetOpen, setSearchOptionsWidgetOpen] = useState<boolean>(false);
  const [librariesWidgetOpen, setLibrariesWidgetOpen] = useState<boolean>(false);
  const [documentsWidgetOpen, setDocumentsWidgetOpen] = useState<boolean>(false);
  const [deepSearchWidgetOpen, setDeepSearchWidgetOpen] = useState<boolean>(false);
  const [logGeniusWidgetOpen, setLogGeniusWidgetOpen] = useState<boolean>(false);
  const [contextOpen, setContextOpen] = useState<boolean>(false);

  const [prefsLoadState, setPrefsLoadState] = useState<PrefsLoadState>(() =>
    prefsTargetSessionId ? "loading" : "idle",
  );
  const prevPrefsTargetSessionIdRef = useRef<string | undefined>(undefined);
  const hydratedSessionIdRef = useRef<string | undefined>(undefined);
  const lastSentJson = useRef<string>("");
  const seededSessionRef = useRef<{ sessionId: string; prefs: PersistedCtx } | null>(null);
  const isSessionPrefsReady = prefsLoadState === "hydrated";

  const buildPersistedPrefs = useCallback(
    (prefs: ConversationPrefs, agentId?: string) => ({
      chatContextIds: prefs.chatContextIds,
      documentLibraryIds: prefs.documentLibraryIds,
      documentUids: supportsDocumentsSelection ? prefs.documentUids : undefined,
      promptResourceIds: prefs.promptResourceIds,
      templateResourceIds: prefs.templateResourceIds,
      searchPolicy: prefs.searchPolicy,
      searchRagScope: supportsRagScopeSelection ? prefs.searchRagScope : undefined,
      deepSearch: supportsDeepSearchSelection ? prefs.deepSearch : undefined,
      includeCorpusScope: supportsLibrariesSelection ? prefs.includeCorpusScope : undefined,
      includeDocumentScope: supportsDocumentsSelection ? prefs.includeDocumentScope : undefined,
      includeSessionScope: supportsAttachments ? prefs.includeSessionScope : undefined,
      agent_id: agentId ?? currentAgent?.id ?? defaultAgent?.id,
    }),
    [
      supportsRagScopeSelection,
      supportsDeepSearchSelection,
      supportsLibrariesSelection,
      supportsDocumentsSelection,
      supportsAttachments,
      currentAgent?.id,
      defaultAgent?.id,
    ],
  );

  const savePrefs = useCallback(
    (nextPrefs: ConversationPrefs, agentId?: string, opts: { force?: boolean } = {}) => {
      if (
        !prefsTargetSessionId ||
        prefsLoadState !== "hydrated" ||
        hydratedSessionIdRef.current !== prefsTargetSessionId
      ) {
        console.info("[PREFS] skip persist (prefs not hydrated)", {
          sessionId: prefsTargetSessionId ?? null,
          prefsLoadState,
          hydratedSessionId: hydratedSessionIdRef.current ?? null,
        });
        return;
      }
      const prefs = buildPersistedPrefs(nextPrefs, agentId);
      const serialized = serializePrefs(prefs);
      if (!opts.force && serialized === lastSentJson.current) return;
      lastSentJson.current = serialized;
      console.log("[PREFS] persisting to backend", { session: prefsTargetSessionId, prefs });
      persistSessionPrefs({
        sessionId: prefsTargetSessionId,
        sessionPreferencesPayload: { preferences: prefs },
      })
        .unwrap()
        .then(() => {
          console.log("[PREFS] persisted", { session: prefsTargetSessionId });
        })
        .catch((err) => {
          console.warn("[PREFS] persist failed", err);
        });
    },
    [prefsTargetSessionId, prefsLoadState, buildPersistedPrefs, persistSessionPrefs],
  );

  const seedSessionPrefs = useCallback(
    async (chatSessionIdToSeed: string, agentId?: string) => {
      const prefs = buildPersistedPrefs(conversationPrefs, agentId);
      console.log("[PREFS] seeding new session", { chatSessionId: chatSessionIdToSeed, prefs });
      const result = await persistSessionPrefs({
        sessionId: chatSessionIdToSeed,
        sessionPreferencesPayload: { preferences: prefs },
      }).unwrap();
      seededSessionRef.current = { sessionId: chatSessionIdToSeed, prefs };
      lastSentJson.current = serializePrefs(prefs);
      return result;
    },
    [buildPersistedPrefs, conversationPrefs, persistSessionPrefs],
  );

  const updatePrefs = useCallback((updater: (prev: ConversationPrefs) => ConversationPrefs) => {
    setConversationPrefs((prev) => updater(prev));
  }, []);

  const setSearchPolicy = useCallback(
    (next: SetStateAction<SearchPolicyName>) => {
      updatePrefs((prev) => ({
        ...prev,
        searchPolicy: typeof next === "function" ? next(prev.searchPolicy) : next,
      }));
    },
    [updatePrefs],
  );

  const setSearchRagScope = useCallback(
    (next: SearchRagScope) => {
      updatePrefs((prev) => ({
        ...prev,
        searchRagScope: next,
      }));
    },
    [updatePrefs],
  );

  const setDeepSearchEnabled = useCallback(
    (next: boolean) => {
      updatePrefs((prev) => ({
        ...prev,
        deepSearch: next,
      }));
    },
    [updatePrefs],
  );

  const setIncludeCorpusScope = useCallback(
    (next: boolean) => {
      updatePrefs((prev) => ({
        ...prev,
        includeCorpusScope: next,
      }));
    },
    [updatePrefs],
  );

  const setIncludeDocumentScope = useCallback(
    (next: boolean) => {
      updatePrefs((prev) => ({
        ...prev,
        includeDocumentScope: next,
      }));
    },
    [updatePrefs],
  );

  const setIncludeSessionScope = useCallback(
    (next: boolean) => {
      updatePrefs((prev) => ({
        ...prev,
        includeSessionScope: next,
      }));
    },
    [updatePrefs],
  );

  const setChatContextIds = useCallback(
    (ids: string[]) => {
      const uniqueIds = Array.from(new Set(ids));
      console.info("[PREFS][UI] chat contexts change", { sessionId: prefsTargetSessionId ?? null, ids: uniqueIds });
      updatePrefs((prev) => ({
        ...prev,
        chatContextIds: uniqueIds,
      }));
    },
    [updatePrefs, prefsTargetSessionId],
  );

  const setDocumentLibraryIds = useCallback(
    (ids: string[]) => {
      const uniqueIds = Array.from(new Set(ids));
      console.info("[PREFS][UI] libraries change", { sessionId: prefsTargetSessionId ?? null, ids: uniqueIds });
      updatePrefs((prev) => ({
        ...prev,
        documentLibraryIds: uniqueIds,
      }));
    },
    [updatePrefs, prefsTargetSessionId],
  );

  const setDocumentUids = useCallback(
    (ids: string[]) => {
      const uniqueIds = Array.from(new Set(ids));
      console.info("[PREFS][UI] documents change", { sessionId: prefsTargetSessionId ?? null, ids: uniqueIds });
      updatePrefs((prev) => ({
        ...prev,
        documentUids: uniqueIds,
      }));
    },
    [updatePrefs, prefsTargetSessionId],
  );

  const selectAgent = useCallback(
    async (agent: AnyAgent) => {
      setCurrentAgent(agent);
      if (
        !prefsTargetSessionId ||
        prefsLoadState !== "hydrated" ||
        hydratedSessionIdRef.current !== prefsTargetSessionId
      ) {
        console.info("[PREFS][AGENT] skip (prefs not hydrated)", {
          sessionId: prefsTargetSessionId ?? null,
          prefsLoadState,
          hydratedSessionId: hydratedSessionIdRef.current ?? null,
          agent: agent.id,
        });
        return;
      }
      const prefs = buildPersistedPrefs(conversationPrefs, agent.id);
      console.info("[PREFS][AGENT] saving", { sessionId: prefsTargetSessionId, agent: agent.id });
      try {
        await persistSessionPrefs({
          sessionId: prefsTargetSessionId,
          sessionPreferencesPayload: { preferences: prefs },
        }).unwrap();
        lastSentJson.current = serializePrefs(prefs);
        console.info("[PREFS][AGENT] saved", { sessionId: prefsTargetSessionId, agent: agent.id });
      } catch (err) {
        console.warn("[PREFS][AGENT] save failed", { sessionId: prefsTargetSessionId, agent: agent.id, error: err });
      }
    },
    [prefsTargetSessionId, prefsLoadState, buildPersistedPrefs, conversationPrefs, persistSessionPrefs],
  );

  // Prefs lifecycle:
  // - idle: no target session -> defaults
  // - loading: target session set, waiting for prefs -> reset UI
  // - hydrated: prefs applied for current session -> allow persistence
  useEffect(() => {
    const currentId = prefsTargetSessionId;
    const prevId = prevPrefsTargetSessionIdRef.current;
    prevPrefsTargetSessionIdRef.current = currentId;

    if (!currentId) {
      if (prefsLoadState !== "idle") {
        console.info("[PREFS][STATE] idle (no session)");
      }
      setPrefsLoadState("idle");
      hydratedSessionIdRef.current = undefined;
      lastSentJson.current = "";
      resetToDefaults();
      setContextOpen(false);
      setChatContextWidgetOpen(false);
      setAttachmentsWidgetOpen(false);
      setLibrariesWidgetOpen(false);
      setDocumentsWidgetOpen(false);
      setSearchOptionsWidgetOpen(false);
      setConversationPrefs((prev) => ({
        ...prev,
        chatContextIds: [],
        documentLibraryIds: initialCtx.documentLibraryIds,
        documentUids: initialCtx.documentUids,
        promptResourceIds: initialCtx.promptResourceIds,
        templateResourceIds: initialCtx.templateResourceIds,
        searchPolicy: initialCtx.searchPolicy,
        searchRagScope: initialCtx.searchRagScope ?? defaultRagScope,
        deepSearch: initialCtx.deepSearch ?? false,
        includeCorpusScope: initialCtx.includeCorpusScope ?? true,
        includeDocumentScope: initialCtx.includeDocumentScope ?? true,
        includeSessionScope: initialCtx.includeSessionScope ?? true,
      }));
      return;
    }

    if (!prevId || currentId !== prevId) {
      hydratedSessionIdRef.current = undefined;
      const seeded = seededSessionRef.current;
      if (seeded && seeded.sessionId === currentId) {
        const desiredAgentId = resolvePreferredAgentId(seeded.prefs);
        if (desiredAgentId) {
          const foundAgent = agents.find((a) => a.id === desiredAgentId);
          if (foundAgent && foundAgent.id !== currentAgent?.id) setCurrentAgent(foundAgent);
        }
        lastSentJson.current = serializePrefs(seeded.prefs);
        seededSessionRef.current = null;
        setPrefsLoadState("hydrated");
        hydratedSessionIdRef.current = currentId;
        console.info("[PREFS][STATE] hydrated (seeded)", { sessionId: currentId, agent: desiredAgentId ?? null });
        return;
      }
      console.info("[PREFS][STATE] loading (session switch)", { prevId: prevId ?? null, currentId });
      if (prefsLoadState !== "loading") setPrefsLoadState("loading");
      lastSentJson.current = "";
      setContextOpen(false);
      setChatContextWidgetOpen(false);
      setAttachmentsWidgetOpen(false);
      setLibrariesWidgetOpen(false);
      setDocumentsWidgetOpen(false);
      setSearchOptionsWidgetOpen(false);
      setConversationPrefs({
        chatContextIds: [],
        documentLibraryIds: [],
        documentUids: [],
        promptResourceIds: [],
        templateResourceIds: [],
        searchPolicy: initialCtx.searchPolicy,
        searchRagScope: initialCtx.searchRagScope ?? defaultRagScope,
        deepSearch: initialCtx.deepSearch ?? false,
        includeCorpusScope: initialCtx.includeCorpusScope ?? true,
        includeDocumentScope: initialCtx.includeDocumentScope ?? true,
        includeSessionScope: initialCtx.includeSessionScope ?? true,
      });
      return;
    }

    if (prefsLoadState === "loading" && sessionPrefs) {
      const p = (sessionPrefs as PersistedCtx) || {};
      const nextChatContextIds = asStringArray(p.chatContextIds, []);
      const nextLibs = asStringArray(p.documentLibraryIds, []);
      const nextDocUids = asStringArray(p.documentUids, []);
      const nextPrompts = asStringArray(p.promptResourceIds, []);
      const nextTemplates = asStringArray(p.templateResourceIds, []);
      const nextSearchPolicy = p.searchPolicy ?? initialCtx.searchPolicy;
      const nextRagScope = p.searchRagScope ?? p.ragKnowledgeScope ?? initialCtx.searchRagScope ?? defaultRagScope;
      const nextDeepSearch = p.deepSearch ?? initialCtx.deepSearch ?? false;
      const nextIncludeCorpusScope = asBoolean(p.includeCorpusScope, initialCtx.includeCorpusScope ?? true);
      const nextIncludeDocumentScope = asBoolean(p.includeDocumentScope, initialCtx.includeDocumentScope ?? true);
      const nextIncludeSessionScope = asBoolean(p.includeSessionScope, initialCtx.includeSessionScope ?? true);

      setConversationPrefs({
        chatContextIds: nextChatContextIds,
        documentLibraryIds: nextLibs,
        documentUids: nextDocUids,
        promptResourceIds: nextPrompts,
        templateResourceIds: nextTemplates,
        searchPolicy: nextSearchPolicy,
        searchRagScope: nextRagScope,
        deepSearch: nextDeepSearch,
        includeCorpusScope: nextIncludeCorpusScope,
        includeDocumentScope: nextIncludeDocumentScope,
        includeSessionScope: nextIncludeSessionScope,
      });
      setChatContextWidgetOpen(false);
      setAttachmentsWidgetOpen(false);
      setSearchOptionsWidgetOpen(false);
      setLibrariesWidgetOpen(false);
      setDocumentsWidgetOpen(false);

      const desiredAgentId = resolvePreferredAgentId(p);
      if (desiredAgentId) {
        const foundAgent = agents.find((a) => a.id === desiredAgentId);
        if (foundAgent && foundAgent.id !== currentAgent?.id) setCurrentAgent(foundAgent);
      }

      lastSentJson.current = serializePrefs({
        chatContextIds: nextChatContextIds,
        documentLibraryIds: nextLibs,
        documentUids: nextDocUids,
        promptResourceIds: nextPrompts,
        templateResourceIds: nextTemplates,
        searchPolicy: nextSearchPolicy,
        searchRagScope: nextRagScope,
        deepSearch: nextDeepSearch,
        includeCorpusScope: nextIncludeCorpusScope,
        includeDocumentScope: nextIncludeDocumentScope,
        includeSessionScope: nextIncludeSessionScope,
        agent_id: desiredAgentId,
      });
      setPrefsLoadState("hydrated");
      hydratedSessionIdRef.current = currentId;
      console.info("[PREFS][STATE] hydrated", {
        sessionId: currentId,
        agent: desiredAgentId ?? null,
        chatContextCount: nextChatContextIds.length,
        libraryCount: nextLibs.length,
        searchPolicy: nextSearchPolicy,
        searchRagScope: nextRagScope,
        deepSearch: nextDeepSearch,
        includeCorpusScope: nextIncludeCorpusScope,
        includeSessionScope: nextIncludeSessionScope,
      });
    }
  }, [
    prefsTargetSessionId,
    prefsLoadState,
    sessionPrefs,
    initialCtx,
    defaultRagScope,
    resetToDefaults,
    agents,
    currentAgent?.id,
  ]);

  useEffect(() => {
    // Persist only when session prefs are hydrated for the currently displayed session.
    if (!prefsTargetSessionId || prefsLoadState !== "hydrated") return;
    if (hydratedSessionIdRef.current !== prefsTargetSessionId) {
      console.info("[PREFS] skip persist (session transition in progress)", {
        sessionId: prefsTargetSessionId,
        hydratedSessionId: hydratedSessionIdRef.current ?? null,
      });
      return;
    }

    savePrefs(conversationPrefs, currentAgent?.id);
  }, [conversationPrefs, currentAgent?.id, prefsTargetSessionId, prefsLoadState, savePrefs]);

  const isHydratingSession = prefsLoadState === "loading" && !isPrefsError;
  const displayChatContextIds = isHydratingSession ? [] : conversationPrefs.chatContextIds;
  const displayDocumentLibraryIds = isHydratingSession ? [] : conversationPrefs.documentLibraryIds;
  const displayDocumentUids = isHydratingSession ? [] : conversationPrefs.documentUids;
  const documentsScopeActive =
    supportsDocumentsSelection && conversationPrefs.includeDocumentScope && conversationPrefs.documentUids.length > 0;
  const chatContextWidgetOpenDisplay = isHydratingSession ? false : chatContextWidgetOpen;
  const attachmentsWidgetOpenDisplay = isHydratingSession ? false : supportsAttachments && attachmentsWidgetOpen;
  const searchOptionsWidgetOpenDisplay = isHydratingSession
    ? false
    : (supportsRagScopeSelection || supportsSearchPolicySelection) && searchOptionsWidgetOpen;
  const librariesWidgetOpenDisplay = isHydratingSession
    ? false
    : supportsLibrariesSelection && librariesWidgetOpen && !documentsScopeActive;
  const documentsWidgetOpenDisplay = isHydratingSession ? false : supportsDocumentsSelection && documentsWidgetOpen;
  const deepSearchWidgetOpenDisplay = isHydratingSession ? false : supportsDeepSearchSelection && deepSearchWidgetOpen;
  const logGeniusWidgetOpenDisplay = isHydratingSession ? false : logGeniusWidgetOpen;
  const widgetsOpen =
    chatContextWidgetOpenDisplay ||
    librariesWidgetOpenDisplay ||
    documentsWidgetOpenDisplay ||
    attachmentsWidgetOpenDisplay ||
    searchOptionsWidgetOpenDisplay ||
    deepSearchWidgetOpenDisplay ||
    logGeniusWidgetOpenDisplay;
  const chatWidgetRail = widgetsOpen ? "18vw" : "0px";
  const chatWidgetGap = "12px";
  const chatContentRightPadding = widgetsOpen ? `calc(${chatWidgetRail} + ${chatWidgetGap})` : "0px";
  const chatContentWidth = widgetsOpen ? "100%" : "80%";
  const chatContentLeftPadding = 3;

  useEffect(() => {
    if (documentsScopeActive && librariesWidgetOpen) {
      setLibrariesWidgetOpen(false);
    }
  }, [documentsScopeActive, librariesWidgetOpen]);

  useEffect(() => {
    if (documentsScopeActive && conversationPrefs.includeCorpusScope === false) {
      updatePrefs((prev) => ({
        ...prev,
        includeCorpusScope: true,
      }));
    }
  }, [documentsScopeActive, conversationPrefs.includeCorpusScope, updatePrefs]);

  const effectiveDocumentLibraryIds = documentsScopeActive ? [] : conversationPrefs.documentLibraryIds;
  const effectiveDocumentUids = documentsScopeActive ? conversationPrefs.documentUids : [];

  const userInputContext = useMemo(
    () => ({
      documentLibraryIds: effectiveDocumentLibraryIds,
      documentUids: effectiveDocumentUids,
      promptResourceIds: conversationPrefs.promptResourceIds,
      templateResourceIds: conversationPrefs.templateResourceIds,
    }),
    [
      effectiveDocumentLibraryIds,
      effectiveDocumentUids,
      conversationPrefs.promptResourceIds,
      conversationPrefs.templateResourceIds,
    ],
  );
  const hasContext =
    effectiveDocumentLibraryIds.length > 0 ||
    effectiveDocumentUids.length > 0 ||
    conversationPrefs.promptResourceIds.length > 0 ||
    conversationPrefs.templateResourceIds.length > 0;

  return {
    state: {
      conversationPrefs,
      currentAgent,
      supportsRagScopeSelection,
      supportsSearchPolicySelection,
      supportsDeepSearchSelection,
      supportsAttachments,
      supportsLibrariesSelection,
      supportsDocumentsSelection,
      isHydratingSession,
      isSessionPrefsReady,
      prefsTargetSessionId,
      prefsLoadState,
      sessionPrefs: sessionPrefs as PersistedCtx | undefined,
      isPrefsFetching,
      isPrefsError,
      prefsError,
      defaultSearchPolicy,
      defaultRagScope,
      defaultSearchRagScope,
      displayChatContextIds,
      displayDocumentLibraryIds,
      displayDocumentUids,
      chatContextWidgetOpenDisplay,
      attachmentsWidgetOpenDisplay,
      searchOptionsWidgetOpenDisplay,
      librariesWidgetOpenDisplay,
      documentsWidgetOpenDisplay,
      deepSearchWidgetOpenDisplay,
      logGeniusWidgetOpenDisplay,
      widgetsOpen,
      layout: {
        chatWidgetRail,
        chatWidgetGap,
        chatContentRightPadding,
        chatContentWidth,
        chatContentLeftPadding,
      },
      userInputContext,
      hasContext,
      contextOpen,
    },
    actions: {
      setSearchPolicy,
      setSearchRagScope,
      setDeepSearchEnabled,
      setIncludeCorpusScope,
      setIncludeDocumentScope,
      setIncludeSessionScope,
      setChatContextIds,
      setDocumentLibraryIds,
      setDocumentUids,
      selectAgent,
      seedSessionPrefs,
      setChatContextWidgetOpen,
      setAttachmentsWidgetOpen,
      setSearchOptionsWidgetOpen,
      setLibrariesWidgetOpen,
      setDocumentsWidgetOpen,
      setDeepSearchWidgetOpen,
      setLogGeniusWidgetOpen,
      setContextOpen,
    },
  };
}

type ConversationOptionsPanelProps = {
  controller: ConversationOptionsController;
  attachmentSessionId?: string;
  sessionAttachments: { id: string; name: string }[];
  onAddAttachments: (files: File[]) => void;
  onAttachmentsUpdated: () => void;
  isUploadingAttachments: boolean;
  onRequestLogGenius?: () => void;
  libraryNameMap: Record<string, string>;
  libraryById: Record<string, TagWithItemsId | undefined>;
  promptNameMap: Record<string, string>;
  templateNameMap: Record<string, string>;
  chatContextNameMap: Record<string, string>;
  chatContextResourceMap: Record<string, Resource | undefined>;
};

export function ConversationOptionsPanel({
  controller,
  attachmentSessionId,
  sessionAttachments,
  onAddAttachments,
  onAttachmentsUpdated,
  isUploadingAttachments,
  onRequestLogGenius,
  libraryNameMap,
  libraryById,
  promptNameMap,
  templateNameMap,
  chatContextNameMap,
  chatContextResourceMap,
}: ConversationOptionsPanelProps) {
  const { t } = useTranslation();
  const {
    conversationPrefs,
    displayChatContextIds,
    displayDocumentLibraryIds,
    displayDocumentUids,
    chatContextWidgetOpenDisplay,
    attachmentsWidgetOpenDisplay,
    searchOptionsWidgetOpenDisplay,
    librariesWidgetOpenDisplay,
    documentsWidgetOpenDisplay,
    deepSearchWidgetOpenDisplay,
    logGeniusWidgetOpenDisplay,
    isHydratingSession,
    supportsLibrariesSelection,
    supportsDocumentsSelection,
    supportsAttachments,
    supportsRagScopeSelection,
    supportsSearchPolicySelection,
    supportsDeepSearchSelection,
    defaultSearchPolicy,
    defaultRagScope,
    defaultSearchRagScope,
    contextOpen,
    hasContext,
    userInputContext,
  } = controller.state;
  const {
    setChatContextIds,
    setDocumentLibraryIds,
    setDocumentUids,
    setSearchPolicy,
    setSearchRagScope,
    setDeepSearchEnabled,
    setIncludeCorpusScope,
    setIncludeDocumentScope,
    setIncludeSessionScope,
    setChatContextWidgetOpen,
    setAttachmentsWidgetOpen,
    setLibrariesWidgetOpen,
    setDocumentsWidgetOpen,
    setSearchOptionsWidgetOpen,
    setDeepSearchWidgetOpen,
    setLogGeniusWidgetOpen,
    setContextOpen,
  } = controller.actions;

  const documentsScopeActive =
    supportsDocumentsSelection && conversationPrefs.includeDocumentScope && conversationPrefs.documentUids.length > 0;
  const canOpenSearchOptions = supportsRagScopeSelection || supportsSearchPolicySelection;
  const showLogGenius = Boolean(onRequestLogGenius);
  const librariesDisabled = !supportsLibrariesSelection || documentsScopeActive;
  const librariesDisabledReason =
    documentsScopeActive && supportsLibrariesSelection
      ? t("chatbot.libraries.disabledByDocuments", "Document scoping is active. Disable documents to use libraries.")
      : undefined;
  const allWidgetsOpen =
    chatContextWidgetOpenDisplay &&
    (!supportsLibrariesSelection || documentsScopeActive || librariesWidgetOpenDisplay) &&
    (!supportsDocumentsSelection || documentsWidgetOpenDisplay) &&
    (!supportsAttachments || attachmentsWidgetOpenDisplay) &&
    (!canOpenSearchOptions || searchOptionsWidgetOpenDisplay) &&
    (!supportsDeepSearchSelection || deepSearchWidgetOpenDisplay) &&
    (!showLogGenius || logGeniusWidgetOpenDisplay);

  const setAllWidgetsOpen = (open: boolean) => {
    setChatContextWidgetOpen(open);
    setLibrariesWidgetOpen(open && supportsLibrariesSelection && !documentsScopeActive);
    setDocumentsWidgetOpen(open && supportsDocumentsSelection);
    setAttachmentsWidgetOpen(open && supportsAttachments);
    setSearchOptionsWidgetOpen(open && canOpenSearchOptions);
    setDeepSearchWidgetOpen(open && supportsDeepSearchSelection);
    setLogGeniusWidgetOpen(open && showLogGenius);
  };

  const openWidget = (
    target: "chat-context" | "libraries" | "documents" | "attachments" | "search" | "deep-search" | "log-genius",
  ) => {
    if (target === "chat-context") setChatContextWidgetOpen(true);
    if (target === "libraries" && supportsLibrariesSelection && !documentsScopeActive) setLibrariesWidgetOpen(true);
    if (target === "documents" && supportsDocumentsSelection) setDocumentsWidgetOpen(true);
    if (target === "attachments" && supportsAttachments) setAttachmentsWidgetOpen(true);
    if (target === "search" && canOpenSearchOptions) setSearchOptionsWidgetOpen(true);
    if (target === "deep-search" && supportsDeepSearchSelection) setDeepSearchWidgetOpen(true);
    if (target === "log-genius" && showLogGenius) setLogGeniusWidgetOpen(true);
  };
  const resetSearchOptions = () => {
    if (supportsSearchPolicySelection) setSearchPolicy(defaultSearchPolicy);
    if (supportsRagScopeSelection) setSearchRagScope(defaultSearchRagScope);
  };
  const deepSearchEnabled = Boolean(conversationPrefs.deepSearch);

  return (
    <>
      <Box
        sx={{
          position: "fixed",
          top: { xs: 8, md: 12 },
          right: { xs: 8, md: 16 },
          zIndex: 1200,
          width: {
            xs: "auto",
            md: controller.state.widgetsOpen ? controller.state.layout.chatWidgetRail : "auto",
          },
          display: { xs: "none", md: "block" },
        }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1, alignItems: "flex-end" }}>
          <span>
            <IconButton
              size="small"
              onClick={() => setAllWidgetsOpen(!allWidgetsOpen)}
              disabled={isHydratingSession}
              sx={{ alignSelf: "flex-end" }}
            >
              {allWidgetsOpen ? <ChevronRightIcon fontSize="small" /> : <ChevronLeftIcon fontSize="small" />}
            </IconButton>
          </span>
          <ChatContextWidget
            selectedChatContextIds={displayChatContextIds}
            onChangeSelectedChatContextIds={setChatContextIds}
            nameById={chatContextNameMap}
            resourceById={chatContextResourceMap}
            open={chatContextWidgetOpenDisplay}
            closeOnClickAway={false}
            onOpen={() => openWidget("chat-context")}
            onClose={() => setChatContextWidgetOpen(false)}
          />
          {supportsLibrariesSelection && (
            <ChatDocumentLibrariesWidget
              selectedLibraryIds={displayDocumentLibraryIds}
              onChangeSelectedLibraryIds={setDocumentLibraryIds}
              nameById={libraryNameMap}
              libraryById={libraryById}
              includeInSearch={conversationPrefs.includeCorpusScope}
              onIncludeInSearchChange={setIncludeCorpusScope}
              includeInSearchDisabled={isHydratingSession || documentsScopeActive}
              open={librariesWidgetOpenDisplay}
              closeOnClickAway={false}
              disabled={librariesDisabled}
              disabledReason={librariesDisabledReason}
              onOpen={() => openWidget("libraries")}
              onClose={() => setLibrariesWidgetOpen(false)}
            />
          )}
          {supportsDocumentsSelection && (
            <ChatDocumentsWidget
              selectedDocumentUids={displayDocumentUids}
              onChangeSelectedDocumentUids={setDocumentUids}
              includeInSearch={conversationPrefs.includeDocumentScope}
              onIncludeInSearchChange={setIncludeDocumentScope}
              includeInSearchDisabled={isHydratingSession}
              open={documentsWidgetOpenDisplay}
              closeOnClickAway={false}
              disabled={!supportsDocumentsSelection}
              onOpen={() => openWidget("documents")}
              onClose={() => setDocumentsWidgetOpen(false)}
            />
          )}
          {supportsAttachments && (
            <ChatAttachmentsWidget
              attachments={sessionAttachments}
              sessionId={attachmentSessionId}
              open={attachmentsWidgetOpenDisplay}
              closeOnClickAway={false}
              disabled={!supportsAttachments}
              isUploading={isUploadingAttachments}
              includeInSearch={conversationPrefs.includeSessionScope}
              onIncludeInSearchChange={setIncludeSessionScope}
              includeInSearchDisabled={isHydratingSession}
              onAddAttachments={onAddAttachments}
              onAttachmentsUpdated={onAttachmentsUpdated}
              onOpen={() => openWidget("attachments")}
              onClose={() => setAttachmentsWidgetOpen(false)}
            />
          )}
          {canOpenSearchOptions && (
            <ChatSearchOptionsWidget
              searchPolicy={conversationPrefs.searchPolicy ?? defaultSearchPolicy}
              onSearchPolicyChange={setSearchPolicy}
              defaultSearchPolicy={defaultSearchPolicy}
              searchRagScope={conversationPrefs.searchRagScope ?? defaultRagScope}
              onSearchRagScopeChange={setSearchRagScope}
              defaultRagScope={defaultSearchRagScope}
              ragScopeDisabled={!supportsRagScopeSelection}
              searchPolicyDisabled={!supportsSearchPolicySelection}
              open={searchOptionsWidgetOpenDisplay}
              closeOnClickAway={false}
              disabled={!supportsRagScopeSelection && !supportsSearchPolicySelection}
              onOpen={() => openWidget("search")}
              onClose={() => setSearchOptionsWidgetOpen(false)}
              onResetToDefaults={resetSearchOptions}
            />
          )}
          {supportsDeepSearchSelection && (
            <ChatDeepSearchWidget
              open={deepSearchWidgetOpenDisplay}
              closeOnClickAway={false}
              disabled={isHydratingSession}
              enabled={deepSearchEnabled}
              onToggle={setDeepSearchEnabled}
              onOpen={() => openWidget("deep-search")}
              onClose={() => setDeepSearchWidgetOpen(false)}
            />
          )}
          {showLogGenius && (
            <ChatLogGeniusWidget
              open={logGeniusWidgetOpenDisplay}
              closeOnClickAway={false}
              disabled={isHydratingSession}
              onRun={onRequestLogGenius}
              onOpen={() => {
                openWidget("log-genius");
              }}
              onClose={() => setLogGeniusWidgetOpen(false)}
            />
          )}
        </Box>
      </Box>

      <ChatKnowledge
        open={contextOpen}
        hasContext={hasContext}
        userInputContext={userInputContext}
        onClose={() => setContextOpen(false)}
        libraryNameMap={libraryNameMap}
        promptNameMap={promptNameMap}
        templateNameMap={templateNameMap}
      />
    </>
  );
}
