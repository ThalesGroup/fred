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

/**
 * UserInput
 * ---------
 * - Manages per-session input context (libraries/prompts/templates/policies/rag scope/deep search/agent).
 * - Hydrates from backend session prefs, applies once per session, and persists only when state differs from last sent.
 * - No local “dirty” caches; one PUT per change, followed by a refetch to keep UI consistent with backend.
 * - Receives initial defaults from parent (for draft/no-session) but owns server-side prefs for active sessions.
 */

import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import MicIcon from "@mui/icons-material/Mic";
import StopIcon from "@mui/icons-material/Stop";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import React, { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import AudioController from "../AudioController.tsx";
import AudioRecorder from "../AudioRecorder.tsx";

import { Box, Grid2, IconButton, InputBase, Stack, Tooltip, useTheme } from "@mui/material";

import { useTranslation } from "react-i18next";
import {
  SearchPolicyName,
  TagWithItemsId,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

// Import the new sub-components
import { AnyAgent } from "../../../common/agent.ts";
import {
  AgentChatOptions,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation,
} from "../../../slices/agentic/agenticOpenApi.ts";
import { AgentSelector } from "./AgentSelector.tsx";
import { UserInputAttachments } from "./UserInputAttachments.tsx";
import { UserInputRagScope } from "./UserInputRagScope.tsx";
import { UserInputSearchPolicy } from "./UserInputSearchPolicy.tsx";
import { SearchRagScope } from "./types.ts";

export interface UserInputContent {
  text?: string;
  audio?: Blob;
  files?: File[];
  documentLibraryIds?: string[];
  promptResourceIds?: string[];
  templateResourceIds?: string[];
  profileResourceIds?: string[];
  searchPolicy?: SearchPolicyName;
  searchRagScope?: SearchRagScope;
  deepSearch?: boolean;
}

export type UserInputHandle = {
  setDeepSearchEnabled: (next: boolean) => void;
  markSessionPrefsDirty: () => void;
};

type ConversationPanelView = "chat_contexts" | "libraries" | "attachments";

type PersistedCtx = {
  chatContextIds?: string[];
  documentLibraryIds?: string[];
  promptResourceIds?: string[];
  templateResourceIds?: string[];
  profileResourceIds?: string[];
  searchPolicy?: SearchPolicyName;
  searchRagScope?: SearchRagScope;
  deepSearch?: boolean;
  ragKnowledgeScope?: SearchRagScope; // legacy persisted field
  skipRagSearch?: boolean; // legacy persisted flag
};

const serializePrefs = (p: PersistedCtx & { agent_name?: string }) =>
  JSON.stringify(Object.fromEntries(Object.entries(p).sort(([a], [b]) => a.localeCompare(b))));

const asStringArray = (v: unknown, fallback: string[] = []): string[] => {
  if (!Array.isArray(v)) return fallback;
  return v.filter((x): x is string => typeof x === "string" && x.length > 0);
};

type UserInputProps = {
  agentChatOptions?: AgentChatOptions;
  isWaiting: boolean;
  onSend: (content: UserInputContent) => void;
  onStop?: () => void;
  onContextChange?: (ctx: UserInputContent) => void;
  sessionId?: string;
  effectiveSessionId?: string;
  uploadingFiles?: string[];
  onFilesSelected?: (files: File[]) => void;
  attachmentsRefreshTick?: number;
  serverPrefs?: PersistedCtx & { agent_name?: string };
  refetchServerPrefs?: () => void;
  selectedChatContextIds?: string[];
  onSelectedChatContextIdsChange?: (ids: string[]) => void;
  chatContextNameById?: Record<string, string>;
  conversationPanelView?: ConversationPanelView;
  initialDocumentLibraryIds?: string[];
  initialPromptResourceIds?: string[];
  initialTemplateResourceIds?: string[];
  initialSearchPolicy?: SearchPolicyName;
  initialSearchRagScope?: SearchRagScope;
  initialDeepSearch?: boolean;
  currentAgent: AnyAgent;
  agents: AnyAgent[];
  onSelectNewAgent: (flow: AnyAgent) => void;
  attachmentsPanelOpen?: boolean;
  onAttachmentsPanelOpenChange?: (open: boolean) => void;
  onAttachmentCountChange?: (count: number) => void;
  onSelectedDocumentLibrariesIdsChange?: (ids: string[]) => void;
  onDeepSearchEnabledChange?: (enabled: boolean) => void;
};

function UserInput(
  {
    agentChatOptions,
    isWaiting = false,
    onSend = () => {},
    onStop,
    onContextChange,
    sessionId,
    effectiveSessionId,
    uploadingFiles,
    onFilesSelected,
	    attachmentsRefreshTick,
	    serverPrefs: serverPrefsProp,
	    refetchServerPrefs,
	    selectedChatContextIds,
	    onSelectedChatContextIdsChange,
      chatContextNameById,
      conversationPanelView = "attachments",
    initialDocumentLibraryIds,
    initialPromptResourceIds,
    initialTemplateResourceIds,
    initialSearchPolicy = "semantic",
    initialSearchRagScope,
    initialDeepSearch,
    currentAgent,
    agents,
    onSelectNewAgent,
    attachmentsPanelOpen: attachmentsPanelOpenProp,
    onAttachmentsPanelOpenChange,
    onAttachmentCountChange,
    onSelectedDocumentLibrariesIdsChange,
    onDeepSearchEnabledChange,
  }: UserInputProps,
  ref: React.ForwardedRef<UserInputHandle>,
) {
  const theme = useTheme();
  const { t } = useTranslation();

  // Refs
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Message + attachments (per-message, not persisted across messages)
  const [userInput, setUserInput] = useState<string>("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [displayAudioRecorder, setDisplayAudioRecorder] = useState<boolean>(false);
  const [displayAudioController, setDisplayAudioController] = useState<boolean>(false);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  // Deprecated for uploads: files are uploaded immediately; keep no per-message files
  const [filesBlob, setFilesBlob] = useState<File[] | null>(null);
  // Only show the selector when the agent explicitly opts in via config (new flag, fallback to old).
  const supportsRagScopeSelection = agentChatOptions?.search_rag_scoping === true;
  const supportsSearchPolicySelection = agentChatOptions?.search_policy_selection === true;
  const supportsDeepSearchSelection = agentChatOptions?.deep_search_delegate === true;
  const supportsAudioRecording = agentChatOptions?.record_audio_files === true;
  const defaultRagScope: SearchRagScope = "hybrid";

  const [searchRagScope, setSearchRagScopeState] = useState<SearchRagScope>(initialSearchRagScope ?? defaultRagScope);
  const [deepSearchEnabled, setDeepSearchEnabledState] = useState<boolean>(initialDeepSearch ?? false);

  // console.log("UserInput render", { searchRagScope, supportsRagScopeSelection });
  // console.log("Agent chat options", agentChatOptions);
  // --- Fred rationale ---
  // These three selections are *session-scoped context* (used by agents for retrieval/templates).
  // Rule: hydrate exactly once per session. Persist to localStorage to restore when returning.
  const [selectedDocumentLibrariesIds, setSelectedDocumentLibrariesIdsState] = useState<string[]>(
    initialDocumentLibraryIds ?? [],
  );
  const [selectedPromptResourceIds, setSelectedPromptResourceIdsState] = useState<string[]>(
    initialPromptResourceIds ?? [],
  );
  const [selectedTemplateResourceIds, setSelectedTemplateResourceIdsState] = useState<string[]>(
    initialTemplateResourceIds ?? [],
  );
  const [selectedSearchPolicyName, setSelectedSearchPolicyNameState] = useState<SearchPolicyName>(initialSearchPolicy);
  const canSend = !!userInput.trim() || !!audioBlob; // files upload immediately now
  const defaultAgent = useMemo(() => (agents && agents.length > 0 ? agents[0] : undefined), [agents]);

  const [prefsDirtyTick, setPrefsDirtyTick] = useState<number>(0);
  const lastProcessedDirtyTickRef = useRef<number>(0);
  const markPrefsDirty = useCallback(() => setPrefsDirtyTick((x) => x + 1), []);

  // User-facing setters
  const setChatContextIds = useCallback(
    (ids: string[]) => {
      if (!onSelectedChatContextIdsChange) return;
      markPrefsDirty();
      onSelectedChatContextIdsChange(Array.from(new Set(ids)));
    },
    [markPrefsDirty, onSelectedChatContextIdsChange],
  );
  const setLibs = (next: React.SetStateAction<string[]>) => {
    markPrefsDirty();
    setSelectedDocumentLibrariesIdsState((prev) => (typeof next === "function" ? (next as any)(prev) : next));
  };
  const setSearchPolicy = (next: React.SetStateAction<SearchPolicyName>) => {
    markPrefsDirty();
    setSelectedSearchPolicyNameState((prev) => (typeof next === "function" ? (next as any)(prev) : next));
  };
  const setRagScope = (next: SearchRagScope) => {
    markPrefsDirty();
    setSearchRagScopeState(next);
  };
  const setDeepSearch = (next: boolean) => {
    markPrefsDirty();
    setDeepSearchEnabledState(next);
  };

  const [internalAttachmentsPanelOpen, setInternalAttachmentsPanelOpen] = useState<boolean>(false);
  const attachmentsPanelOpen = attachmentsPanelOpenProp ?? internalAttachmentsPanelOpen;
  const setAttachmentsPanelOpen = (open: boolean) => {
    if (attachmentsPanelOpenProp === undefined) {
      setInternalAttachmentsPanelOpen(open);
    }
    onAttachmentsPanelOpenChange?.(open);
  };
  const [uploadDialogOpen, setUploadDialogOpen] = useState<boolean>(false);
  useEffect(() => {
    onSelectedDocumentLibrariesIdsChange?.(selectedDocumentLibrariesIds);
  }, [onSelectedDocumentLibrariesIdsChange, selectedDocumentLibrariesIds]);
  useEffect(() => {
    onDeepSearchEnabledChange?.(deepSearchEnabled);
  }, [deepSearchEnabled, onDeepSearchEnabledChange]);

  useImperativeHandle(
    ref,
    () => ({
      setDeepSearchEnabled: (next: boolean) => {
        setDeepSearch(next);
      },
      markSessionPrefsDirty: () => {
        markPrefsDirty();
      },
    }),
    [markPrefsDirty, setDeepSearch],
  );

  // --- Fetch resource/tag names so chips can display labels instead of raw IDs
  // Libraries are "document" tags in your UI
  const { data: documentTags = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" });

  // --- Session attachments for popover ---
  const { data: sessions = [], refetch: refetchSessions } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: false,
    refetchOnReconnect: true,
  });
  type AttachmentRef = { id: string; name: string };
  const attachmentSessionId = effectiveSessionId || sessionId;
  useEffect(() => {
    if (attachmentSessionId) {
      refetchSessions();
    }
  }, [attachmentsRefreshTick, attachmentSessionId, refetchSessions]);
  const sessionAttachments: AttachmentRef[] = useMemo(() => {
    if (!attachmentSessionId) return [];
    const s = (sessions as any[]).find((x) => x?.id === attachmentSessionId) as any | undefined;
    // Prefer new backend shape with IDs
    const att = s?.attachments;
    if (Array.isArray(att)) return att as AttachmentRef[];
    // Fallback to legacy file_names list if attachments not present
    const names = (s && (s.file_names as string[] | undefined)) || [];
    return Array.isArray(names) ? names.map((n) => ({ id: n, name: n })) : [];
  }, [sessions, attachmentSessionId]);
  const attachmentCount = sessionAttachments.length + (uploadingFiles?.length ?? 0);
  useEffect(() => {
    onAttachmentCountChange?.(attachmentCount);
  }, [attachmentCount, onAttachmentCountChange]);

  // --- Session preferences (server-side) ---
  const serverPrefs = serverPrefsProp;
  const [persistPrefs] = useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation();

  // --- Synchronization Logic ---
  // Track which session's prefs are currently applied to local state.
  const [hydratedSessionId, setHydratedSessionId] = useState<string | undefined>(undefined);
  const prevSessionIdRef = useRef<string | undefined>(undefined);
  const lastSentJson = useRef<string>("");
  const forcePersistRef = useRef<boolean>(false);
  const isHydratingSession = Boolean(attachmentSessionId && hydratedSessionId !== attachmentSessionId);

  // 1. Master Effect: Handle Session Switching & Hydration
  useEffect(() => {
    const currentId = attachmentSessionId;
    const prevId = prevSessionIdRef.current;
    prevSessionIdRef.current = currentId;

    // No session: clear markers
    if (!currentId) {
      setHydratedSessionId(undefined);
      lastSentJson.current = "";
      console.log("[PREFS] no session selected; cleared markers");
      return;
    }

    // New session selection or switch: clear markers and WAIT for server prefs (no default reset to avoid flicker)
    if (currentId && currentId !== prevId) {
      lastSentJson.current = "";
      setHydratedSessionId(undefined);
      // Important: avoid leaking selections from a previous session while the new session prefs are loading.
      setSelectedDocumentLibrariesIdsState([]);
      setSelectedPromptResourceIdsState([]);
      setSelectedTemplateResourceIdsState([]);
      setSelectedSearchPolicyNameState(initialSearchPolicy);
      setSearchRagScopeState(initialSearchRagScope ?? defaultRagScope);
      setDeepSearchEnabledState(initialDeepSearch ?? false);
      console.log("[PREFS] switched session; awaiting server prefs", { currentId });
      return;
    }

    // Apply server prefs once per session
    if (currentId && hydratedSessionId !== currentId && serverPrefs) {
      const p = (serverPrefs as PersistedCtx & { agent_name?: string }) || {};

      const nextChatContextIds = asStringArray(p.chatContextIds, []);
      const nextLibs = asStringArray(p.documentLibraryIds, []);
      const nextPrompts = asStringArray(p.promptResourceIds, []);
      const nextTemplates = asStringArray(p.templateResourceIds, []);
      const nextSearchPolicy = p.searchPolicy ?? initialSearchPolicy;
      const nextRagScope = p.searchRagScope ?? initialSearchRagScope ?? defaultRagScope;
      const nextDeepSearch = p.deepSearch ?? initialDeepSearch ?? false;

      if (onSelectedChatContextIdsChange) {
        const prev = selectedChatContextIds ?? [];
        const same =
          prev.length === nextChatContextIds.length && prev.every((id, i) => id === nextChatContextIds[i]);
        if (!same) onSelectedChatContextIdsChange(nextChatContextIds);
      }
      setSelectedDocumentLibrariesIdsState(nextLibs);
      setSelectedPromptResourceIdsState(nextPrompts);
      setSelectedTemplateResourceIdsState(nextTemplates);
      setSelectedSearchPolicyNameState(nextSearchPolicy);
      setSearchRagScopeState(nextRagScope);
      setDeepSearchEnabledState(nextDeepSearch);
      const desiredAgentName = typeof p.agent_name === "string" && p.agent_name.length ? p.agent_name : undefined;
      const json = serializePrefs({
        chatContextIds: nextChatContextIds,
        documentLibraryIds: nextLibs,
        promptResourceIds: nextPrompts,
        templateResourceIds: nextTemplates,
        searchPolicy: nextSearchPolicy,
        searchRagScope: nextRagScope,
        deepSearch: nextDeepSearch,
        agent_name: desiredAgentName,
      });
      // Do not trigger a write on hydration; only persist on explicit user changes.
      forcePersistRef.current = false;
      lastSentJson.current = json;
      setHydratedSessionId(currentId);
      console.log("[PREFS] applied server prefs", { currentId, prefs: p });
    }
  }, [
    attachmentSessionId,
    hydratedSessionId,
    serverPrefs,
    initialSearchPolicy,
    initialSearchRagScope,
    initialDeepSearch,
    defaultRagScope,
    onSelectedChatContextIdsChange,
    selectedChatContextIds,
  ]);

  // 2. Persistence Effect
  // Only save if we are fully hydrated for the current session and user made a change.
  useEffect(() => {
    if (!attachmentSessionId || hydratedSessionId !== attachmentSessionId) return;

    // Persist only in response to an explicit user action.
    // This prevents transient UI state during hydration/session switching from overwriting other sessions.
    if (prefsDirtyTick === lastProcessedDirtyTickRef.current) return;

    const prefs: PersistedCtx & { agent_name?: string } = {
      chatContextIds: selectedChatContextIds,
      documentLibraryIds: selectedDocumentLibrariesIds,
      promptResourceIds: selectedPromptResourceIds,
      templateResourceIds: selectedTemplateResourceIds,
      searchPolicy: selectedSearchPolicyName,
      searchRagScope: supportsRagScopeSelection ? searchRagScope : undefined,
      deepSearch: supportsDeepSearchSelection ? deepSearchEnabled : undefined,
      agent_name: currentAgent?.name ?? defaultAgent?.name,
    };

    const serialized = serializePrefs(prefs);
    // Mark this user-change as processed even if it ends up being a no-op persist.
    lastProcessedDirtyTickRef.current = prefsDirtyTick;
    if (serialized === lastSentJson.current && !forcePersistRef.current) return;

    lastSentJson.current = serialized;
    forcePersistRef.current = false;
    console.log("[PREFS] persisting to backend", { session: attachmentSessionId, prefs });
    persistPrefs({
      sessionId: attachmentSessionId,
      sessionPreferencesPayload: { preferences: prefs },
    })
      .unwrap()
      .then(() => {
        console.log("[PREFS] persisted", { session: attachmentSessionId });
        refetchServerPrefs?.();
      })
      .catch((err) => {
        console.warn("[PREFS] persist failed", err);
      });
  }, [
    attachmentSessionId,
    hydratedSessionId,
    selectedDocumentLibrariesIds,
    selectedPromptResourceIds,
    selectedTemplateResourceIds,
    selectedSearchPolicyName,
    searchRagScope,
    deepSearchEnabled,
    supportsRagScopeSelection,
    supportsDeepSearchSelection,
    currentAgent,
    selectedChatContextIds,
    prefsDirtyTick,
    persistPrefs,
    refetchServerPrefs,
  ]);

  const libNameById = useMemo(
    () => Object.fromEntries((documentTags as TagWithItemsId[]).map((t) => [t.id, t.name])),
    [documentTags],
  );

  // --- Fred rationale ---
  // Lift session context up so the parent can persist alongside messages.
  // This emits on any relevant change, but we *never* pull state back down except on session change.
  useEffect(() => {
    if (!onContextChange) return;
    onContextChange({
      files: filesBlob ?? undefined,
      audio: audioBlob ?? undefined,
      documentLibraryIds: selectedDocumentLibrariesIds.length ? selectedDocumentLibrariesIds : undefined,
      promptResourceIds: selectedPromptResourceIds.length ? selectedPromptResourceIds : undefined,
      templateResourceIds: selectedTemplateResourceIds.length ? selectedTemplateResourceIds : undefined,
      searchPolicy: selectedSearchPolicyName,
      searchRagScope: supportsRagScopeSelection ? searchRagScope : undefined,
      deepSearch: supportsDeepSearchSelection ? deepSearchEnabled : undefined,
    });
  }, [
    filesBlob,
    audioBlob,
    selectedDocumentLibrariesIds,
    selectedPromptResourceIds,
    selectedTemplateResourceIds,
    selectedSearchPolicyName,
    searchRagScope,
    deepSearchEnabled,
    supportsRagScopeSelection,
    supportsDeepSearchSelection,
    onContextChange,
  ]);

  // Enter sends; Shift+Enter newline
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter") {
      if (isWaiting || isHydratingSession || !canSend) {
        event.preventDefault();
        return;
      }
      if (event.shiftKey) {
        setUserInput((prev) => prev + "\n");
        event.preventDefault();
      } else {
        event.preventDefault();
        handleSend();
      }
    }
  };

  const handleSend = () => {
    if (isWaiting || isHydratingSession || !canSend) return;
    onSend({
      text: userInput,
      audio: audioBlob || undefined,
      documentLibraryIds: selectedDocumentLibrariesIds,
      promptResourceIds: selectedPromptResourceIds,
      templateResourceIds: selectedTemplateResourceIds,
      searchPolicy: selectedSearchPolicyName,
      searchRagScope: supportsRagScopeSelection ? searchRagScope : undefined,
      deepSearch: supportsDeepSearchSelection ? deepSearchEnabled : undefined,
    });
    setUserInput("");
    setAudioBlob(null);
    setFilesBlob(null);
    // Keep libs/prompts/templates (session context)
  };

  // Files
  const handleFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const list = e.target.files ? Array.from(e.target.files) : [];
    if (list.length) {
      onFilesSelected?.(list);
      setUploadDialogOpen(false);
      setAttachmentsPanelOpen(true);
    }
    // Do not keep files as message attachments; upload starts immediately
    setFilesBlob(null);
    e.target.value = ""; // allow same files again later
  };
  const handleRemoveFile = (index: number) => {
    setFilesBlob((prev) => {
      const next = prev ? [...prev] : [];
      next.splice(index, 1);
      return next;
    });
  };

  // No separate attachments popover (shown inside + menu)

  // Refresh session attachments after uploads/deletes
  useEffect(() => {
    if (attachmentSessionId) refetchSessions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attachmentsRefreshTick, attachmentSessionId]);

  // Audio
  const startAudioRecording = () => {
    setDisplayAudioController(false);
    setDisplayAudioRecorder(true);
    setIsRecording(true);
    inputRef.current?.focus();
  };
  const stopAudioRecording = () => {
    setIsRecording(false);
    inputRef.current?.focus();
  };
  const handleAudioChange = (content: Blob) => {
    setIsRecording(false);
    setDisplayAudioRecorder(false);
    setAudioBlob(content);
    setDisplayAudioController(true);
    inputRef.current?.focus();
  };
  return (
    <Grid2 container sx={{ height: "100%", justifyContent: "flex-start", overflow: "hidden" }} size={12} display="flex">
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          gap: 0,
          pr: { xs: 0, md: attachmentsPanelOpen ? 1.5 : 0 },
        }}
      >
        {attachmentSessionId && hydratedSessionId !== attachmentSessionId ? (
          <Box
            sx={{
              border: `1px solid ${theme.palette.divider}`,
              borderBottom: "0px",
              borderTopLeftRadius: "16px",
              borderTopRightRadius: "16px",
              background: theme.palette.background.paper,
              paddingX: 2,
              paddingY: 0.5,
              display: "flex",
              gap: 1,
              alignItems: "center",
              justifyContent: "center",
              alignSelf: "flex-start",
              color: theme.palette.text.secondary,
            }}
          >
            {t("common.loading", "Loading")}…
          </Box>
        ) : (
          <AgentSelector
            agents={agents}
            currentAgent={currentAgent}
            onSelectNewAgent={(agent) => {
              markPrefsDirty();
              onSelectNewAgent(agent);
            }}
            sx={{ alignSelf: "flex-start" }}
          />
        )}

        <Grid2 container size={12} alignItems="center" sx={{ p: 0, gap: 0, backgroundColor: "transparent" }}>
          {/* Single rounded input with the "+" inside (bottom-left) */}
          <Box sx={{ position: "relative", width: "100%" }}>
            {/* + anchored inside the input, bottom-left */}
            <Box
              sx={{
                position: "absolute",
                right: 8,
                bottom: 6,
                zIndex: 1,
                display: "flex",
                gap: 0.75,
                alignItems: "center",
              }}
            >
              {supportsRagScopeSelection && (
                <UserInputRagScope value={searchRagScope} onChange={setRagScope} disabled={isWaiting || isHydratingSession} />
              )}
              {supportsSearchPolicySelection && (
                <UserInputSearchPolicy
                  value={selectedSearchPolicyName}
                  onChange={(next) => setSearchPolicy(next)}
                  disabled={isWaiting || isHydratingSession}
                />
              )}
              {supportsAudioRecording && (
                <Tooltip title={isRecording ? t("chatbot.stopRecording") : t("chatbot.recordAudio")}>
                  <span>
                    <IconButton
                      aria-label="record-audio"
                      size="small"
                      onClick={() => (isRecording ? stopAudioRecording() : startAudioRecording())}
                      disabled={isWaiting || isHydratingSession}
                      color={isRecording ? "error" : "default"}
                    >
                      {isRecording ? <StopIcon fontSize="small" /> : <MicIcon fontSize="small" />}
                    </IconButton>
                  </span>
                </Tooltip>
              )}
              {!isWaiting && !isHydratingSession && (
                <Tooltip title={t("chatbot.sendMessage", "Send message")}>
                  <span>
                    <IconButton
                      aria-label="send-message"
                      sx={{ fontSize: "1.6rem", p: "8px" }}
                      onClick={handleSend}
                      disabled={!canSend}
                      color="primary"
                    >
                      <ArrowUpwardIcon fontSize="inherit" />
                    </IconButton>
                  </span>
                </Tooltip>
              )}
              {isWaiting && onStop && (
                <>
                  <Tooltip title={t("chatbot.stopResponse", "Stop response")}>
                    <span>
                      <IconButton
                        aria-label="stop-response"
                        sx={{ fontSize: "1.6rem", p: "8px" }}
                        onClick={onStop}
                        color="error"
                      >
                        <StopIcon fontSize="inherit" />
                      </IconButton>
                    </span>
                  </Tooltip>
                </>
              )}
            </Box>

            {/* Hidden native file input */}
            <input type="file" style={{ display: "none" }} multiple onChange={handleFilesChange} ref={fileInputRef} />

            {/* Rounded input surface */}
            <Box
              sx={{
                borderRadius: 4,
                borderTopLeftRadius: 0,
                border: `1px solid ${theme.palette.divider}`,
                background:
                  theme.palette.mode === "light" ? theme.palette.common.white : theme.palette.background.default,
                p: 0,
                overflow: "hidden",
              }}
            >
              {displayAudioRecorder ? (
                <Box sx={{ px: "12px", pt: "6px", pb: "56px" }}>
                  <AudioRecorder
                    height="40px"
                    width="100%"
                    waveWidth={1}
                    color={theme.palette.text.primary}
                    isRecording={isRecording}
                    onRecordingComplete={(blob: Blob) => {
                      handleAudioChange(blob);
                    }}
                    downloadOnSavePress={false}
                    downloadFileExtension="mp3"
                  />
                </Box>
              ) : audioBlob && displayAudioController ? (
                <Stack direction="row" alignItems="center" spacing={1} sx={{ px: "12px", pt: "6px", pb: "56px" }}>
                  <AudioController audioUrl={URL.createObjectURL(audioBlob)} color={theme.palette.text.primary} />
                  <Tooltip title={t("chatbot.hideAudio")}>
                    <IconButton aria-label="hide-audio" onClick={() => setDisplayAudioController(false)}>
                      <VisibilityOffIcon />
                    </IconButton>
                  </Tooltip>
                </Stack>
              ) : (
                <InputBase
                  autoFocus
                  fullWidth
                  multiline
                  maxRows={12}
                  placeholder={t("chatbot.input.placeholder")}
                  value={userInput}
                  onKeyDown={handleKeyDown}
                  onChange={(event) => setUserInput(event.target.value)}
                  disabled={isWaiting || isHydratingSession}
                  inputRef={inputRef}
                  sx={{
                    fontSize: "1rem",
                    maxHeight: 600,
                    overflow: "auto",
                    "& .MuiInputBase-input, & .MuiInputBase-inputMultiline": {
                      paddingTop: "12px",
                      paddingBottom: "56px",
                      paddingRight: "16px",
                      paddingLeft: "12px",
                    },
                  }}
                />
              )}
            </Box>
          </Box>

        </Grid2>
      </Box>

      <UserInputAttachments
        sessionId={attachmentSessionId}
        sessionAttachments={sessionAttachments}
        uploadingFileNames={uploadingFiles}
        files={null}
        audio={audioBlob}
        open={attachmentsPanelOpen}
        view={conversationPanelView}
        attachmentsActionsEnabled={Boolean(onFilesSelected)}
        librariesActionsEnabled={agentChatOptions?.libraries_selection === true}
        uploadDialogOpen={uploadDialogOpen}
        onToggleOpen={(open) => setAttachmentsPanelOpen(open)}
        onOpenUploadDialog={() => setUploadDialogOpen(true)}
        onCloseUploadDialog={() => setUploadDialogOpen(false)}
        onFilesDropped={(dropped) => {
          if (dropped.length) {
            onFilesSelected?.(dropped);
            setUploadDialogOpen(false);
            setAttachmentsPanelOpen(true);
          }
        }}
        onRemoveFile={handleRemoveFile}
        onShowAudioController={() => setDisplayAudioController(true)}
        onRemoveAudio={() => setAudioBlob(null)}
        onAttachFileClick={() => {
          setAttachmentsPanelOpen(true);
          setUploadDialogOpen(true);
          fileInputRef.current?.click();
          requestAnimationFrame(() => inputRef.current?.focus());
        }}
        onRefreshSessionAttachments={() => {
          refetchSessions();
        }}
        selectedChatContextIds={selectedChatContextIds}
        chatContextNameById={chatContextNameById}
        onSelectedChatContextIdsChange={setChatContextIds}
        selectedDocumentLibrariesIds={selectedDocumentLibrariesIds}
        documentLibraryNameById={libNameById}
        onSelectedDocumentLibrariesIdsChange={setLibs}
      />
    </Grid2>
  );
}

export default forwardRef<UserInputHandle, UserInputProps>(UserInput);
