// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

// User input component for the chatbot

import AddIcon from "@mui/icons-material/Add";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import StopIcon from "@mui/icons-material/Stop";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
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
import { AgentChatOptions } from "../../../slices/agentic/agenticOpenApi.ts";
import { AgentSelector } from "./AgentSelector.tsx";
import { UserInputAttachments } from "./UserInputAttachments.tsx";
import { UserInputPopover } from "./UserInputPopover.tsx";

export interface UserInputContent {
  text?: string;
  audio?: Blob;
  files?: File[];
  documentLibraryIds?: string[];
  promptResourceIds?: string[];
  templateResourceIds?: string[];
  profileResourceIds?: string[];
  searchPolicy?: SearchPolicyName;
}

type PersistedCtx = {
  documentLibraryIds?: string[];
  promptResourceIds?: string[];
  templateResourceIds?: string[];
  profileResourceIds?: string[];
  searchPolicy?: SearchPolicyName;
};

function makeStorageKey(sessionId?: string) {
  return sessionId ? `fred:userInput:ctx:${sessionId}` : "";
}

function loadSessionCtx(sessionId?: string): PersistedCtx | null {
  const key = makeStorageKey(sessionId);
  if (!key) return null;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as PersistedCtx) : null;
  } catch {
    return null;
  }
}

function saveSessionCtx(sessionId: string | undefined, ctx: PersistedCtx) {
  const key = makeStorageKey(sessionId);
  if (!key) return;
  try {
    localStorage.setItem(key, JSON.stringify(ctx));
  } catch {
    // storage may be unavailable (private mode/quotas) — fail quietly
  }
}

export default function UserInput({
  agentChatOptions,
  isWaiting = false,
  onSend = () => {},
  onStop,
  onContextChange,
  sessionId,
  initialDocumentLibraryIds,
  initialPromptResourceIds,
  initialTemplateResourceIds,
  initialSearchPolicy = "semantic",
  currentAgent,
  agents,
  onSelectNewAgent,
}: {
  agentChatOptions?: AgentChatOptions;
  isWaiting: boolean;
  onSend: (content: UserInputContent) => void;
  onStop?: () => void;
  onContextChange?: (ctx: UserInputContent) => void;
  sessionId?: string;
  initialDocumentLibraryIds?: string[];
  initialPromptResourceIds?: string[];
  initialTemplateResourceIds?: string[];
  initialSearchPolicy?: SearchPolicyName;
  currentAgent: AnyAgent;
  agents: AnyAgent[];
  onSelectNewAgent: (flow: AnyAgent) => void;
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
  const [filesBlob, setFilesBlob] = useState<File[] | null>(null);

  // --- Fred rationale ---
  // These three selections are *session-scoped context* (used by agents for retrieval/templates).
  // Rule: hydrate exactly once per session. Persist to localStorage to restore when returning.
  const [selectedDocumentLibrariesIds, setSelectedDocumentLibrariesIds] = useState<string[]>([]);
  const [selectedPromptResourceIds, setSelectedPromptResourceIds] = useState<string[]>([]);
  const [selectedTemplateResourceIds, setSelectedTemplateResourceIds] = useState<string[]>([]);
  const [selectedSearchPolicyName, setSelectedSearchPolicyName] = useState<SearchPolicyName>("semantic");
  const canSend = !!userInput.trim() || !!audioBlob || !!(filesBlob && filesBlob.length);

  // Selections made *before* we get a real sessionId (first question) — migrate them.
  const preSessionRef = useRef<PersistedCtx>({});

  // Capture pre-session picks while sessionId is undefined.
  useEffect(() => {
    if (!sessionId) {
      preSessionRef.current = {
        documentLibraryIds: selectedDocumentLibrariesIds,
        promptResourceIds: selectedPromptResourceIds,
        templateResourceIds: selectedTemplateResourceIds,
        searchPolicy: selectedSearchPolicyName,
      };
    }
  }, [
    sessionId,
    selectedDocumentLibrariesIds,
    selectedPromptResourceIds,
    selectedTemplateResourceIds,
    selectedSearchPolicyName,
  ]);

  // Hydration guard: run at most once per session id.
  const hydratedForSession = useRef<string | undefined>(undefined);

  useEffect(() => {
    // Only attempt to hydrate when we *have* a session id.
    if (!sessionId) return;

    const isNewSession = hydratedForSession.current !== sessionId;
    if (!isNewSession) return;
    hydratedForSession.current = sessionId;

    // Priority to hydrate:
    // 1) localStorage (returning to a session)
    // 2) pre-session user picks (user acted before id assigned)
    // 3) initial* defaults
    const persisted = loadSessionCtx(sessionId) ?? {};
    const pre = preSessionRef.current ?? {};

    const libs = persisted.documentLibraryIds?.length
      ? persisted.documentLibraryIds
      : pre.documentLibraryIds?.length
        ? pre.documentLibraryIds
        : (initialDocumentLibraryIds ?? []);
    const prompts = persisted.promptResourceIds?.length
      ? persisted.promptResourceIds
      : pre.promptResourceIds?.length
        ? pre.promptResourceIds
        : (initialPromptResourceIds ?? []);
    const templates = persisted.templateResourceIds?.length
      ? persisted.templateResourceIds
      : pre.templateResourceIds?.length
        ? pre.templateResourceIds
        : (initialTemplateResourceIds ?? []);
    const searchPolicy = persisted.searchPolicy
      ? persisted.searchPolicy
      : pre.searchPolicy
        ? pre.searchPolicy
        : initialSearchPolicy;
    setSelectedSearchPolicyName(searchPolicy);
    setSelectedDocumentLibrariesIds(libs);
    setSelectedPromptResourceIds(prompts);
    setSelectedTemplateResourceIds(templates);

    // Save immediately so storage stays the source of truth for this session.
    saveSessionCtx(sessionId, {
      documentLibraryIds: libs,
      promptResourceIds: prompts,
      templateResourceIds: templates,
      searchPolicy: searchPolicy,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Wrap setters to persist to storage.
  const setLibs = (next: React.SetStateAction<string[]>) => {
    setSelectedDocumentLibrariesIds((prev) => {
      const value = typeof next === "function" ? (next as any)(prev) : next;
      if (sessionId)
        saveSessionCtx(sessionId, {
          documentLibraryIds: value,
          promptResourceIds: selectedPromptResourceIds,
          templateResourceIds: selectedTemplateResourceIds,
          searchPolicy: selectedSearchPolicyName,
        });
      return value;
    });
  };
  const setPrompts = (next: React.SetStateAction<string[]>) => {
    setSelectedPromptResourceIds((prev) => {
      const value = typeof next === "function" ? (next as any)(prev) : next;
      if (sessionId)
        saveSessionCtx(sessionId, {
          documentLibraryIds: selectedDocumentLibrariesIds,
          promptResourceIds: value,
          templateResourceIds: selectedTemplateResourceIds,
          searchPolicy: selectedSearchPolicyName,
        });
      return value;
    });
  };
  const setTemplates = (next: React.SetStateAction<string[]>) => {
    setSelectedTemplateResourceIds((prev) => {
      const value = typeof next === "function" ? (next as any)(prev) : next;
      if (sessionId)
        saveSessionCtx(sessionId, {
          documentLibraryIds: selectedDocumentLibrariesIds,
          promptResourceIds: selectedPromptResourceIds,
          templateResourceIds: value,
          searchPolicy: selectedSearchPolicyName,
        });
      return value;
    });
  };
  const setSearchPolicy = (next: React.SetStateAction<SearchPolicyName>) => {
    setSelectedSearchPolicyName((prev) => {
      const value = typeof next === "function" ? (next as any)(prev) : next;
      if (sessionId)
        saveSessionCtx(sessionId, {
          documentLibraryIds: selectedDocumentLibrariesIds,
          promptResourceIds: selectedPromptResourceIds,
          templateResourceIds: selectedTemplateResourceIds,
          searchPolicy: value,
        });
      return value;
    });
  };

  const searchPolicyLabels: Record<SearchPolicyName, string> = {
    hybrid: t("search.hybrid", "Hybrid"),
    semantic: t("search.semantic", "Semantic"),
    strict: t("search.strict", "Strict"),
  };

  // “+” menu popover
  const [plusAnchor, setPlusAnchor] = useState<HTMLElement | null>(null);
  // Inline picker view inside the same popover (replaces the old Dialogs)
  // null -> root menu with sections; otherwise show the corresponding selector inline
  const [pickerView, setPickerView] = useState<null | "libraries" | "prompts" | "templates" | "search_policy">(null);

  // --- Fetch resource/tag names so chips can display labels instead of raw IDs
  const { data: promptResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "prompt" });
  const { data: templateResources = [] } = useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "template" });
  // Libraries are "document" tags in your UI
  const { data: documentTags = [] } = useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" });

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
    });
  }, [
    filesBlob,
    audioBlob,
    selectedDocumentLibrariesIds,
    selectedPromptResourceIds,
    selectedTemplateResourceIds,
    selectedSearchPolicyName,
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
      files: filesBlob || undefined,
      documentLibraryIds: selectedDocumentLibrariesIds,
      promptResourceIds: selectedPromptResourceIds,
      templateResourceIds: selectedTemplateResourceIds,
      searchPolicy: selectedSearchPolicyName,
    });
    setUserInput("");
    setAudioBlob(null);
    setFilesBlob(null);
    // Keep libs/prompts/templates (session context)
  };

  // Files
  const handleFilesChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return;
    setFilesBlob((prev) => {
      const existing = prev ?? [];
      return [...existing, ...Array.from(e.target.files!)];
    });
    e.target.value = ""; // allow same files again later
  };
  const handleRemoveFile = (index: number) => {
    setFilesBlob((prev) => {
      const next = prev ? [...prev] : [];
      next.splice(index, 1);
      return next;
    });
  };

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

  // UI helpers — persist via wrapped setters
  const removeLib = (id: string) => setLibs((prev) => prev.filter((x) => x !== id));
  const removePrompt = (id: string) => setPrompts((prev) => prev.filter((x) => x !== id));
  const removeTemplate = (id: string) => setTemplates((prev) => prev.filter((x) => x !== id));

  return (
    <Grid2 container sx={{ height: "100%", justifyContent: "flex-start", overflow: "hidden" }} size={12} display="flex">
      {/* Attachments strip - now a dedicated component */}
      <UserInputAttachments
        files={filesBlob}
        audio={audioBlob}
        onRemoveFile={handleRemoveFile}
        onShowAudioController={() => setDisplayAudioController(true)}
        onRemoveAudio={() => setAudioBlob(null)}
      />

      <AgentSelector agents={agents} currentAgent={currentAgent} onSelectNewAgent={onSelectNewAgent} />

      {/* Only the inner rounded input remains visible */}
      <Grid2 container size={12} alignItems="center" sx={{ p: 0, gap: 0, backgroundColor: "transparent" }}>
        {/* Single rounded input with the "+" inside (bottom-left) */}
        <Box sx={{ position: "relative", width: "100%" }}>
          {/* + anchored inside the input, bottom-left */}
          <Box sx={{ position: "absolute", right: 8, bottom: 6, zIndex: 1, display: "flex", gap: 0.75 }}>
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

        {/* Popover - now a dedicated component */}
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
          onRemoveLib={removeLib}
          onRemovePrompt={removePrompt}
          onRemoveTemplate={removeTemplate}
          onAttachFileClick={() => {
            fileInputRef.current?.click();
            setPickerView(null);
            setPlusAnchor(null);
            requestAnimationFrame(() => inputRef.current?.focus());
          }}
          onRecordAudioClick={() => {
            handleAudioRecorderDisplay();
            setPickerView(null);
            setPlusAnchor(null);
          }}
          agentChatOptions={agentChatOptions}
          filesBlob={filesBlob}
        />
      </Grid2>
    </Grid2>
  );
}
