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
 * - Controlled UI for composing a message and managing input-adjacent controls.
 * - Receives conversation preferences as props and emits changes upward.
 * - Does not fetch or persist session preferences.
 */

import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import MicIcon from "@mui/icons-material/Mic";
import StopIcon from "@mui/icons-material/Stop";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import React, { forwardRef, useCallback, useImperativeHandle, useRef, useState, type SetStateAction } from "react";
import AudioController from "../AudioController.tsx";
import AudioRecorder from "../AudioRecorder.tsx";

import { Box, Grid2, IconButton, Paper, Stack, TextField, useTheme } from "@mui/material";

import { useTranslation } from "react-i18next";
import { SearchPolicyName } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

// Import the new sub-components
import { AnyAgent } from "../../../common/agent.ts";
import { useFrontendProperties } from "../../../hooks/useFrontendProperties.ts";
import { SimpleTooltip } from "../../../shared/ui/tooltips/Tooltips.tsx";
import { AgentChatOptions, type RuntimeContext } from "../../../slices/agentic/agenticOpenApi.ts";
import { AgentSelector } from "./AgentSelector.tsx";
type SearchRagScope = NonNullable<RuntimeContext["search_rag_scope"]>;

export interface UserInputContent {
  text?: string;
  audio?: Blob;
  files?: File[];
}

export type UserInputHandle = {
  setDeepSearchEnabled: (next: boolean) => void;
};

type UserInputProps = {
  agentChatOptions?: AgentChatOptions;
  isWaiting: boolean;
  onSend: (content: UserInputContent) => void;
  onStop?: () => void;
  isHydratingSession?: boolean;
  searchPolicy: SearchPolicyName;
  onSearchPolicyChange?: (value: SetStateAction<SearchPolicyName>) => void;
  searchRagScope?: SearchRagScope;
  onSearchRagScopeChange?: (value: SearchRagScope) => void;
  onDeepSearchEnabledChange?: (enabled: boolean) => void;
  currentAgent: AnyAgent;
  agents: AnyAgent[];
  onSelectNewAgent: (flow: AnyAgent) => void;
};

function UserInput(
  {
    agentChatOptions,
    isWaiting = false,
    onSend = () => {},
    onStop,
    isHydratingSession = false,
    onDeepSearchEnabledChange,
    currentAgent,
    agents,
    onSelectNewAgent,
  }: UserInputProps,
  ref: React.ForwardedRef<UserInputHandle>,
) {
  const theme = useTheme();
  const { t } = useTranslation();

  // Refs
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null);

  // Message + attachments (per-message, not persisted across messages)
  const [userInput, setUserInput] = useState<string>("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [displayAudioRecorder, setDisplayAudioRecorder] = useState<boolean>(false);
  const [displayAudioController, setDisplayAudioController] = useState<boolean>(false);
  const [isRecording, setIsRecording] = useState<boolean>(false);
  // Only show the selector when the agent explicitly opts in via config (new flag, fallback to old).
  const supportsAudioRecording = agentChatOptions?.record_audio_files === true;
  const canSend = !!userInput.trim() || !!audioBlob; // files upload immediately now

  const setDeepSearch = useCallback(
    (next: boolean) => {
      onDeepSearchEnabledChange?.(next);
    },
    [onDeepSearchEnabledChange],
  );

  useImperativeHandle(
    ref,
    () => ({
      setDeepSearchEnabled: (next: boolean) => {
        setDeepSearch(next);
      },
    }),
    [setDeepSearch],
  );

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
    });
    setUserInput("");
    setAudioBlob(null);
  };

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

  const { allowAgentSwitchInOneConversation } = useFrontendProperties();

  return (
    <Grid2 container sx={{ height: "100%", justifyContent: "flex-start", overflow: "hidden" }} size={12} display="flex">
      <Box
        sx={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          gap: 1,
        }}
      >
        {allowAgentSwitchInOneConversation && (
          <>
            {isHydratingSession ? (
              <Box
                sx={{
                  border: `1px solid ${theme.palette.divider}`,
                  borderRadius: "16px",
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
                onSelectNewAgent={(agent) => onSelectNewAgent(agent)}
                sx={{ alignSelf: "flex-start" }}
              />
            )}
          </>
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
              {supportsAudioRecording && (
                <SimpleTooltip title={isRecording ? t("chatbot.stopRecording") : t("chatbot.recordAudio")}>
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
                </SimpleTooltip>
              )}
              {!isWaiting && !isHydratingSession && (
                <SimpleTooltip title={t("chatbot.sendMessage", "Send message")}>
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
                </SimpleTooltip>
              )}
              {isWaiting && onStop && (
                <>
                  <SimpleTooltip title={t("chatbot.stopResponse", "Stop response")}>
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
                  </SimpleTooltip>
                </>
              )}
            </Box>

            {/* Rounded input surface */}
            <Box
              sx={{
                borderRadius: 4,
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
                  <SimpleTooltip title={t("chatbot.hideAudio")}>
                    <IconButton aria-label="hide-audio" onClick={() => setDisplayAudioController(false)}>
                      <VisibilityOffIcon />
                    </IconButton>
                  </SimpleTooltip>
                </Stack>
              ) : (
                <Paper elevation={2} sx={{ px: 2, pt: 1.5, pb: 7 }}>
                  <TextField
                    hiddenLabel
                    variant="standard"
                    InputProps={{
                      disableUnderline: true,
                    }}
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
                    }}
                  />
                </Paper>
              )}
            </Box>
          </Box>
        </Grid2>
      </Box>
    </Grid2>
  );
}

export default forwardRef<UserInputHandle, UserInputProps>(UserInput);
