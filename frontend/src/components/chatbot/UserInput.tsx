// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// ...

// User input component for the chatbot

import AttachFileIcon from "@mui/icons-material/AttachFile";
import MicIcon from "@mui/icons-material/Mic";
import StopIcon from "@mui/icons-material/Stop";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import AddIcon from "@mui/icons-material/Add";
import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import AutoFixHighIcon from "@mui/icons-material/AutoFixHigh";
import DescriptionIcon from "@mui/icons-material/Description";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import React, { useEffect, useMemo, useRef, useState } from "react";
import AudioController from "./AudioController.tsx";
import AudioRecorder from "./AudioRecorder.tsx";

import {
  Grid2,
  IconButton,
  InputBase,
  Tooltip,
  useTheme,
  Box,
  Chip,
  Popover,
  Typography,
  Stack,
  Divider,
  MenuList,
  MenuItem,
  ListItemIcon,
  ListItemText,
} from "@mui/material";
import { ChatResourcesSelectionCard } from "./ChatResourcesSelectionCard.tsx";
import { ChatDocumentLibrariesSelectionCard } from "./ChatDocumentLibrariesSelectionCard.tsx";
import {
  Resource,
  TagWithItemsId,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { useTranslation } from "react-i18next";

export interface UserInputContent {
  text?: string;
  audio?: Blob;
  files?: File[];
  documentLibraryIds?: string[];
  promptResourceIds?: string[];
  templateResourceIds?: string[];
}

type PersistedCtx = {
  documentLibraryIds?: string[];
  promptResourceIds?: string[];
  templateResourceIds?: string[];
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
  enableFilesAttachment = false,
  enableAudioAttachment = false,
  isWaiting = false,
  onSend = () => {},
  onContextChange,
  sessionId, // current conversation id from backend
  // initial* are defaults only — used once when a session starts and nothing is yet persisted/selected
  initialDocumentLibraryIds,
  initialPromptResourceIds,
  initialTemplateResourceIds,
}: {
  enableFilesAttachment: boolean;
  enableAudioAttachment: boolean;
  isWaiting: boolean;
  onSend: (content: UserInputContent) => void;
  onContextChange?: (ctx: UserInputContent) => void;
  sessionId?: string;
  initialDocumentLibraryIds?: string[];
  initialPromptResourceIds?: string[];
  initialTemplateResourceIds?: string[];
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

  // Selections made *before* we get a real sessionId (first question) — migrate them.
  const preSessionRef = useRef<PersistedCtx>({});

  // Capture pre-session picks while sessionId is undefined.
  useEffect(() => {
    if (!sessionId) {
      preSessionRef.current = {
        documentLibraryIds: selectedDocumentLibrariesIds,
        promptResourceIds: selectedPromptResourceIds,
        templateResourceIds: selectedTemplateResourceIds,
      };
    }
  }, [
    sessionId,
    selectedDocumentLibrariesIds,
    selectedPromptResourceIds,
    selectedTemplateResourceIds,
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

    const libs =
      persisted.documentLibraryIds?.length
        ? persisted.documentLibraryIds
        : pre.documentLibraryIds?.length
        ? pre.documentLibraryIds
        : initialDocumentLibraryIds ?? [];
    const prompts =
      persisted.promptResourceIds?.length
        ? persisted.promptResourceIds
        : pre.promptResourceIds?.length
        ? pre.promptResourceIds
        : initialPromptResourceIds ?? [];
    const templates =
      persisted.templateResourceIds?.length
        ? persisted.templateResourceIds
        : pre.templateResourceIds?.length
        ? pre.templateResourceIds
        : initialTemplateResourceIds ?? [];

    setSelectedDocumentLibrariesIds(libs);
    setSelectedPromptResourceIds(prompts);
    setSelectedTemplateResourceIds(templates);

    // Save immediately so storage stays the source of truth for this session.
    saveSessionCtx(sessionId, {
      documentLibraryIds: libs,
      promptResourceIds: prompts,
      templateResourceIds: templates,
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
        });
      return value;
    });
  };

  // “+” menu popover
  const [plusAnchor, setPlusAnchor] = useState<HTMLElement | null>(null);
  const plusOpen = Boolean(plusAnchor);

  // Inline picker view inside the same popover (replaces the old Dialogs)
  // null -> root menu with sections; otherwise show the corresponding selector inline
  const [pickerView, setPickerView] = useState<null | "libraries" | "prompts" | "templates">(null);

  // --- Fetch resource/tag names so chips can display labels instead of raw IDs
  const { data: promptResources = [] } =
    useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "prompt" });
  const { data: templateResources = [] } =
    useListResourcesByKindKnowledgeFlowV1ResourcesGetQuery({ kind: "template" });
  // Libraries are "document" tags in your UI
  const { data: documentTags = [] } =
    useListAllTagsKnowledgeFlowV1TagsGetQuery({ type: "document" });

  const promptNameById = useMemo(
    () => Object.fromEntries((promptResources as Resource[]).map((r) => [r.id, r.name])),
    [promptResources]
  );
  const templateNameById = useMemo(
    () => Object.fromEntries((templateResources as Resource[]).map((r) => [r.id, r.name])),
    [templateResources]
  );
  const libNameById = useMemo(
    () => Object.fromEntries((documentTags as TagWithItemsId[]).map((t) => [t.id, t.name])),
    [documentTags]
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
    });
  }, [
    filesBlob,
    audioBlob,
    selectedDocumentLibrariesIds,
    selectedPromptResourceIds,
    selectedTemplateResourceIds,
    onContextChange,
  ]);

  // Enter sends; Shift+Enter newline
  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter") {
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
    onSend({
      text: userInput,
      audio: audioBlob || undefined,
      files: filesBlob || undefined,
      documentLibraryIds: selectedDocumentLibrariesIds,
      promptResourceIds: selectedPromptResourceIds,
      templateResourceIds: selectedTemplateResourceIds,
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

  // Small count chip
  const countChip = (n: number) =>
    n > 0 ? <Chip size="small" label={n} sx={{ height: 20, borderRadius: "999px", fontSize: "0.7rem" }} /> : null;

  // Section header (root popover)
  const sectionHeader = (
    icon: React.ReactNode,
    label: string,
    count: number,
    onAdd: () => void,
    onClear?: () => void,
  ) => (
    <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 0.75 }}>
      <Stack direction="row" alignItems="center" spacing={1}>
        {icon}
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {label}
        </Typography>
        {countChip(count)}
      </Stack>
      <Stack direction="row" alignItems="center" spacing={0.5}>
        {onClear && count > 0 && (
          <Tooltip title={t("documentLibrary.clearSelection")}>
            <IconButton
              size="small"
              onClick={() => {
                // clear via wrappers so storage updates
                if (label === t("knowledge.viewSelector.libraries")) setLibs([]);
                if (label === t("knowledge.viewSelector.prompts")) setPrompts([]);
                if (label === t("knowledge.viewSelector.templates")) setTemplates([]);
              }}
            >
              <DeleteOutlineIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title={t("common.add")}>
          <IconButton size="small" onClick={onAdd}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Stack>
    </Stack>
  );

  return (
    <Grid2 container sx={{ height: "100%", justifyContent: "flex-end", overflow: "hidden" }} size={12} display="flex">
      {/* Attachments strip */}
      {((filesBlob && filesBlob.length > 0) || audioBlob) && (
        <Grid2
          container
          size={12}
          height="40px"
          overflow="auto"
          paddingBottom={1}
          display="flex"
          justifyContent="center"
          gap={1}
        >
          {filesBlob &&
            filesBlob.map((f, i) => (
              <Grid2 size="auto" key={`${(f as File).name}-${i}`}>
                <Chip
                  label={(f as File).name.replace(/\.[^/.]+$/, "")}
                  color="primary"
                  variant="outlined"
                  sx={{ height: 32, fontSize: "1.0rem" }}
                  onDelete={() => handleRemoveFile(i)}
                />
              </Grid2>
            ))}
          {audioBlob && (
            <Chip
              label={t("chatbot.audioChip", "Audio recording")}
              color="error"
              variant="outlined"
              sx={{ height: 32, fontSize: "1.0rem" }}
              onClick={() => setDisplayAudioController(true)}
              onDelete={() => setAudioBlob(null)}
            />
          )}
        </Grid2>
      )}

      {/* Only the inner rounded input remains visible */}
      <Grid2 container size={12} alignItems="center" sx={{ p: 0, gap: 0, backgroundColor: "transparent" }}>
        {/* Single rounded input with the "+" inside (bottom-left) */}
        <Box sx={{ position: "relative", width: "100%" }}>
          {/* + anchored inside the input, bottom-left */}
          <Box sx={{ position: "absolute", right: 8, bottom: 6, zIndex: 1 }}>
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
                    paddingBottom: "56px", // gutter for the "+" button
                    paddingRight: "16px",
                    paddingLeft: "12px",
                  },
                }}
              />
            )}
          </Box>
        </Box>

        {/* Popover: root sections OR inline selector (no intermediate dialog, no Clear/Done footer) */}
        <Popover
          open={plusOpen}
          anchorEl={plusAnchor}
          onClose={() => {
            setPickerView(null);
            setPlusAnchor(null);
          }}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          transformOrigin={{ vertical: "top", horizontal: "right" }}
          slotProps={{
            paper: {
              sx: {
                width: pickerView ? 520 : 420,
                maxHeight: "70vh",
                p: 1.25,
                overflow: "hidden",
              },
            },
          }}
        >
          {/* === Root view: sections with chips and quick actions === */}
          {!pickerView && (
            <Box sx={{ display: "flex", flexDirection: "column" }}>
              {/* Libraries */}
              {sectionHeader(
                <LibraryBooksIcon fontSize="small" />,
                t("knowledge.viewSelector.libraries"),
                selectedDocumentLibrariesIds.length,
                () => setPickerView("libraries"),
                () => setLibs([]),
              )}
              <Box sx={{ mb: 1 }}>
                {selectedDocumentLibrariesIds.length ? (
                  <Stack direction="row" flexWrap="wrap" gap={0.75}>
                    {selectedDocumentLibrariesIds.map((id) => (
                      <Chip key={id} size="small" label={libNameById[id] ?? id} onDelete={() => removeLib(id)} />
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    {t("common.noneSelected")}
                  </Typography>
                )}
              </Box>
              <Divider sx={{ my: 1 }} />

              {/* Prompts */}
              {sectionHeader(
                <AutoFixHighIcon fontSize="small" />,
                t("knowledge.viewSelector.prompts"),
                selectedPromptResourceIds.length,
                () => setPickerView("prompts"),
                () => setPrompts([]),
              )}
              <Box sx={{ mb: 1 }}>
                {selectedPromptResourceIds.length ? (
                  <Stack direction="row" flexWrap="wrap" gap={0.75}>
                    {selectedPromptResourceIds.map((id) => (
                      <Chip key={id} size="small" label={promptNameById[id] ?? id} onDelete={() => removePrompt(id)} />
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    {t("common.noneSelected")}
                  </Typography>
                )}
              </Box>
              <Divider sx={{ my: 1 }} />

              {/* Templates */}
              {sectionHeader(
                <DescriptionIcon fontSize="small" />,
                t("knowledge.viewSelector.templates"),
                selectedTemplateResourceIds.length,
                () => setPickerView("templates"),
                () => setTemplates([]),
              )}
              <Box sx={{ mb: 1 }}>
                {selectedTemplateResourceIds.length ? (
                  <Stack direction="row" flexWrap="wrap" gap={0.75}>
                    {selectedTemplateResourceIds.map((id) => (
                      <Chip key={id} size="small" label={templateNameById[id] ?? id} onDelete={() => removeTemplate(id)} />
                    ))}
                  </Stack>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    {t("common.noneSelected")}
                  </Typography>
                )}
              </Box>
              <Divider sx={{ my: 1 }} />

              {/* Attach / Audio */}
              <MenuList dense sx={{ py: 0.25 }}>
                {enableFilesAttachment && (
                  <MenuItem
                    onClick={() => {
                      fileInputRef.current?.click();
                      setPickerView(null);
                      setPlusAnchor(null);
                      requestAnimationFrame(() => inputRef.current?.focus());
                    }}
                  >
                    <ListItemIcon>
                      <AttachFileIcon fontSize="small" />
                    </ListItemIcon>
                    <ListItemText
                      primary={t("chatbot.attachFiles")}
                      secondary={
                        filesBlob?.length
                          ? t("chatbot.attachments.count", {
                              count: filesBlob.length,
                            })
                          : undefined
                      }
                    />
                  </MenuItem>
                )}
                {enableAudioAttachment && (
                  <MenuItem
                    onClick={() => {
                      handleAudioRecorderDisplay();
                      setPickerView(null);
                      setPlusAnchor(null);
                    }}
                  >
                    <ListItemIcon>
                      {isRecording ? <StopIcon fontSize="small" /> : <MicIcon fontSize="small" />}
                    </ListItemIcon>
                    <ListItemText primary={isRecording ? t("chatbot.stopRecording") : t("chatbot.recordAudio")} />
                  </MenuItem>
                )}
              </MenuList>
            </Box>
          )}

          {/* === Inline picker views (direct cards; no header/footer) === */}
          {pickerView && (
            <Box sx={{ height: "60vh", overflow: "auto", pr: 0.5 }}>
              {pickerView === "libraries" && (
                <ChatDocumentLibrariesSelectionCard
                  selectedLibrariesIds={selectedDocumentLibrariesIds}
                  setSelectedLibrariesIds={setLibs} // wrapped setter (persist)
                  libraryType="document"
                />
              )}
              {pickerView === "prompts" && (
                <ChatResourcesSelectionCard
                  libraryType="prompt"
                  selectedResourceIds={selectedPromptResourceIds}
                  setSelectedResourceIds={setPrompts} // wrapped setter (persist)
                />
              )}
              {pickerView === "templates" && (
                <ChatResourcesSelectionCard
                  libraryType="template"
                  selectedResourceIds={selectedTemplateResourceIds}
                  setSelectedResourceIds={setTemplates} // wrapped setter (persist)
                />
              )}
            </Box>
          )}
        </Popover>
      </Grid2>
    </Grid2>
  );
}
