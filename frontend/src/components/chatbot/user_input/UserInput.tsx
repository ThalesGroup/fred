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

import AddIcon from "@mui/icons-material/Add";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import StopIcon from "@mui/icons-material/Stop";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import { skipToken } from "@reduxjs/toolkit/query";
import React, { useEffect, useMemo, useRef, useState } from "react";
import AudioController from "../AudioController.tsx";
import AudioRecorder from "../AudioRecorder.tsx";

import { Box, Grid2, IconButton, InputBase, Stack, Tooltip, useTheme } from "@mui/material";

import { useTranslation } from "react-i18next";
import {
  Resource,
  SearchPolicyName,
  TagWithItemsId,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

// Import the new sub-components
import { AnyAgent } from "../../../common/agent.ts";
import {
  AgentChatOptions,
  useGetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetQuery,
  useGetSessionsAgenticV1ChatbotSessionsGetQuery,
  useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation,
} from "../../../slices/agentic/agenticOpenApi.ts";
import { AgentSelector } from "./AgentSelector.tsx";
import { UserInputAttachments } from "./UserInputAttachments.tsx";
import { UserInputDeepSearchToggle } from "./UserInputDeepSearchToggle.tsx";
import { UserInputPopover } from "./UserInputPopover.tsx";
import { UserInputRagScope } from "./UserInputRagScope.tsx";
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

type PersistedCtx = {
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

export default function UserInput({
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
}: {
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
}) {
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
  const supportsDeepSearchSelection = agentChatOptions?.deep_search_delegate === true;
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

  const hasPopoverContent = Boolean(
    agentChatOptions?.libraries_selection ||
      agentChatOptions?.search_policy_selection ||
      agentChatOptions?.record_audio_files,
  );

  const searchPolicyLabels: Record<SearchPolicyName, string> = {
    hybrid: t("search.hybrid", "Hybrid"),
    semantic: t("search.semantic", "Semantic"),
    strict: t("search.strict", "Strict"),
  };
  const defaultAgent = useMemo(() => (agents && agents.length > 0 ? agents[0] : undefined), [agents]);

  // User-facing setters
  const setLibs = (next: React.SetStateAction<string[]>) => {
    setSelectedDocumentLibrariesIdsState((prev) => (typeof next === "function" ? (next as any)(prev) : next));
  };
  const setPrompts = (next: React.SetStateAction<string[]>) => {
    setSelectedPromptResourceIdsState((prev) => (typeof next === "function" ? (next as any)(prev) : next));
  };
  const setTemplates = (next: React.SetStateAction<string[]>) => {
    setSelectedTemplateResourceIdsState((prev) => (typeof next === "function" ? (next as any)(prev) : next));
  };
  const setSearchPolicy = (next: React.SetStateAction<SearchPolicyName>) => {
    setSelectedSearchPolicyNameState((prev) => (typeof next === "function" ? (next as any)(prev) : next));
  };
  const setRagScope = (next: SearchRagScope) => {
    setSearchRagScopeState(next);
  };
  const setDeepSearch = (next: boolean) => {
    setDeepSearchEnabledState(next);
  };

  // “+” menu popover
  const [plusAnchor, setPlusAnchor] = useState<HTMLElement | null>(null);
  // Inline picker view inside the same popover (replaces the old Dialogs)
  // null -> root menu with sections; otherwise show the corresponding selector inline
  const [pickerView, setPickerView] = useState<null | "libraries" | "prompts" | "templates" | "search_policy">(null);
  const [internalAttachmentsPanelOpen, setInternalAttachmentsPanelOpen] = useState<boolean>(false);
  const attachmentsPanelOpen = attachmentsPanelOpenProp ?? internalAttachmentsPanelOpen;
  const setAttachmentsPanelOpen = (open: boolean) => {
    if (attachmentsPanelOpenProp === undefined) {
      setInternalAttachmentsPanelOpen(open);
    }
    onAttachmentsPanelOpenChange?.(open);
  };
  const [uploadDialogOpen, setUploadDialogOpen] = useState<boolean>(false);

  // --- Fetch resource/tag names so chips can display labels instead of raw IDs
  const { data: promptResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "prompt" });
  const { data: templateResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "template" });
  // Libraries are "document" tags in your UI
  const { data: documentTags = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" });

  // --- Session attachments for popover ---
  const { data: sessions = [], refetch: refetchSessions } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: false,
    refetchOnReconnect: true,
  });
  useEffect(() => {
    if (sessionId) refetchSessions();
  }, [attachmentsRefreshTick, sessionId, refetchSessions]);
  type AttachmentRef = { id: string; name: string };
  const attachmentSessionId = effectiveSessionId || sessionId;
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
  const hasAttachedFiles = sessionAttachments.length > 0 || (uploadingFiles?.length ?? 0) > 0;
  useEffect(() => {
    if (!hasAttachedFiles) {
      setAttachmentsPanelOpen(false);
    }
  }, [hasAttachedFiles]);
  useEffect(() => {
    onAttachmentCountChange?.(attachmentCount);
  }, [attachmentCount, onAttachmentCountChange]);

  // --- Session preferences (server-side) ---
  const {
    data: serverPrefs,
    refetch: refetchPrefs,
  } = useGetSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesGetQuery(
    attachmentSessionId ? { sessionId: attachmentSessionId } : skipToken,
    {
      refetchOnMountOrArgChange: true,
      refetchOnReconnect: true,
      refetchOnFocus: true,
    },
  );
  const [persistPrefs] = useUpdateSessionPreferencesAgenticV1ChatbotSessionSessionIdPreferencesPutMutation();

  // --- Synchronization Logic ---
  // Track which session's prefs are currently applied to local state.
  const [hydratedSessionId, setHydratedSessionId] = useState<string | undefined>(undefined);
  const prevSessionIdRef = useRef<string | undefined>(undefined);
  const lastSentJson = useRef<string>("");
  const forcePersistRef = useRef<boolean>(false);

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
      console.log("[PREFS] switched session; awaiting server prefs", { currentId });
      return;
    }

    // Apply server prefs once per session
    if (currentId && hydratedSessionId !== currentId && serverPrefs) {
      const p = (serverPrefs as PersistedCtx & { agent_name?: string }) || {};
      const isEmptyPrefs = Object.keys(p || {}).length === 0;
      setSelectedDocumentLibrariesIdsState(
        p.documentLibraryIds ?? initialDocumentLibraryIds ?? selectedDocumentLibrariesIds,
      );
      setSelectedPromptResourceIdsState(p.promptResourceIds ?? initialPromptResourceIds ?? selectedPromptResourceIds);
      setSelectedTemplateResourceIdsState(p.templateResourceIds ?? initialTemplateResourceIds ?? selectedTemplateResourceIds);
      setSelectedSearchPolicyNameState(p.searchPolicy ?? selectedSearchPolicyName);
      setSearchRagScopeState(p.searchRagScope ?? searchRagScope);
      setDeepSearchEnabledState(p.deepSearch ?? deepSearchEnabled);
      const desiredAgentName = p.agent_name ?? currentAgent?.name ?? defaultAgent?.name;
      if (desiredAgentName) {
        const found = agents.find((a) => a.name === desiredAgentName) ?? defaultAgent;
        if (found && found.name !== currentAgent?.name) {
          onSelectNewAgent(found);
        }
      }
      const json = serializePrefs({
        documentLibraryIds: p.documentLibraryIds ?? initialDocumentLibraryIds ?? [],
        promptResourceIds: p.promptResourceIds ?? initialPromptResourceIds ?? [],
        templateResourceIds: p.templateResourceIds ?? initialTemplateResourceIds ?? [],
        searchPolicy: p.searchPolicy ?? initialSearchPolicy,
        searchRagScope: p.searchRagScope ?? initialSearchRagScope ?? defaultRagScope,
        deepSearch: p.deepSearch ?? initialDeepSearch ?? false,
        agent_name: p.agent_name ?? currentAgent?.name ?? defaultAgent?.name,
      });
      forcePersistRef.current = isEmptyPrefs;
      lastSentJson.current = isEmptyPrefs ? "" : json;
      setHydratedSessionId(currentId);
      console.log("[PREFS] applied server prefs", { currentId, prefs: p });
    }
  }, [
    attachmentSessionId,
    hydratedSessionId,
    serverPrefs,
    initialDocumentLibraryIds,
    initialPromptResourceIds,
    initialTemplateResourceIds,
    initialSearchPolicy,
    initialSearchRagScope,
    initialDeepSearch,
    defaultRagScope,
    currentAgent,
    agents,
    onSelectNewAgent,
  ]);

  // 2. Persistence Effect
  // Only save if we are fully hydrated for the current session and user made a change.
  useEffect(() => {
    if (!attachmentSessionId || hydratedSessionId !== attachmentSessionId) return;

    const prefs: PersistedCtx & { agent_name?: string } = {
      documentLibraryIds: selectedDocumentLibrariesIds,
      promptResourceIds: selectedPromptResourceIds,
      templateResourceIds: selectedTemplateResourceIds,
      searchPolicy: selectedSearchPolicyName,
      searchRagScope: supportsRagScopeSelection ? searchRagScope : undefined,
      deepSearch: supportsDeepSearchSelection ? deepSearchEnabled : undefined,
      agent_name: currentAgent?.name ?? defaultAgent?.name,
    };

    const serialized = serializePrefs(prefs);
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
        console.log("[PREFS] persisted, refetching from backend", { session: attachmentSessionId });
        refetchPrefs();
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
    persistPrefs,
    refetchPrefs,
  ]);

  const promptNameById = useMemo(
    () => Object.fromEntries((promptResources as Resource[]).map((r) => [r.id, r.name])),
    [promptResources],
  );
  const templateNameById = useMemo(
    () => Object.fromEntries((templateResources as Resource[]).map((r) => [r.id, r.name])),
    [templateResources],
  );
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
      if (isWaiting || !canSend) {
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
    if (isWaiting || !canSend) return;
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
  const handleAudioRecorderDisplay = () => {
    setIsRecording((v) => !v);
    setDisplayAudioRecorder(true);
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
    <Grid2
      container
      sx={{ height: "100%", justifyContent: "flex-start", overflow: "hidden" }}
      size={12}
      display="flex"
    >
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
        <AgentSelector
          agents={agents}
          currentAgent={currentAgent}
          onSelectNewAgent={onSelectNewAgent}
          sx={{ alignSelf: "flex-start" }}
        />

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
              {supportsDeepSearchSelection && (
                <UserInputDeepSearchToggle value={deepSearchEnabled} onChange={setDeepSearch} disabled={isWaiting} />
              )}
              {supportsRagScopeSelection && (
                <UserInputRagScope value={searchRagScope} onChange={setRagScope} disabled={isWaiting} />
              )}
              {hasPopoverContent && (
                <Tooltip title={t("chatbot.menu.addToSetup")}>
                  <span>
                    <IconButton
                      aria-label="add-to-setup"
                      sx={{ fontSize: "1.6rem", p: "8px" }}
                      onClick={(e) => {
                        setPickerView(null);
                        setPlusAnchor(e.currentTarget);
                      }}
                      disabled={isWaiting}
                    >
                      <AddIcon fontSize="inherit" />
                    </IconButton>
                  </span>
                </Tooltip>
              )}
              {!isWaiting && (
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
                  fullWidth
                  multiline
                  maxRows={12}
                  placeholder={t("chatbot.input.placeholder")}
                  value={userInput}
                  onKeyDown={handleKeyDown}
                  onChange={(event) => setUserInput(event.target.value)}
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

          {/* Popover */}
          {hasPopoverContent && (
            <UserInputPopover
              plusAnchor={plusAnchor}
              pickerView={pickerView}
              isRecording={isRecording}
              selectedDocumentLibrariesIds={selectedDocumentLibrariesIds}
              selectedPromptResourceIds={selectedPromptResourceIds}
              selectedTemplateResourceIds={selectedTemplateResourceIds}
              selectedSearchPolicyName={selectedSearchPolicyName}
              libNameById={libNameById}
              promptNameById={promptNameById}
              templateNameById={templateNameById}
              searchPolicyLabels={searchPolicyLabels}
              setPickerView={setPickerView}
              setPlusAnchor={setPlusAnchor}
              setLibs={setLibs}
              setPrompts={setPrompts}
              setTemplates={setTemplates}
              setSearchPolicy={setSearchPolicy}
              onRemoveLib={(id) => setLibs((prev) => prev.filter((x) => x !== id))}
              onRemovePrompt={(id) => setPrompts((prev) => prev.filter((x) => x !== id))}
              onRemoveTemplate={(id) => setTemplates((prev) => prev.filter((x) => x !== id))}
              onRecordAudioClick={() => {
                handleAudioRecorderDisplay();
                setPickerView(null);
                setPlusAnchor(null);
              }}
              agentChatOptions={agentChatOptions}
            />
          )}
        </Grid2>
      </Box>

      <UserInputAttachments
        sessionId={attachmentSessionId}
        sessionAttachments={sessionAttachments}
        uploadingFileNames={uploadingFiles}
        files={null}
        audio={audioBlob}
        open={attachmentsPanelOpen}
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
      />
    </Grid2>
  );
}
