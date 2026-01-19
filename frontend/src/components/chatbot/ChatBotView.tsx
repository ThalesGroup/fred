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

import { Box, CircularProgress, Grid2, Tooltip, Typography, useTheme } from "@mui/material";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type SetStateAction } from "react";
import { useTranslation } from "react-i18next";
import type { AnyAgent } from "../../common/agent.ts";
import { KeyCloakService } from "../../security/KeycloakService.ts";
import type { ChatMessage, RuntimeContext } from "../../slices/agentic/agenticOpenApi.ts";
import type { Resource, SearchPolicyName, TagWithItemsId } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import {
  ConversationOptionsPanel,
  type ConversationOptionsController,
  type ConversationPrefs,
} from "./ConversationOptionsController.tsx";
import { MessagesArea } from "./MessagesArea.tsx";
import UserInput, { type UserInputContent } from "./user_input/UserInput.tsx";

type SearchRagScope = NonNullable<RuntimeContext["search_rag_scope"]>;

type ChatBotViewProps = {
  chatSessionId?: string;
  options: ConversationOptionsController;
  attachmentSessionId?: string;
  sessionAttachments: { id: string; name: string }[];
  onAddAttachments: (files: File[]) => void;
  onAttachmentsUpdated: () => void;
  isUploadingAttachments: boolean;
  libraryNameMap: Record<string, string>;
  libraryById: Record<string, TagWithItemsId>;
  promptNameMap: Record<string, string>;
  templateNameMap: Record<string, string>;
  chatContextNameMap: Record<string, string>;
  chatContextResourceMap: Record<string, Resource>;
  isSessionLoadBlocked: boolean;
  loadError: boolean;
  showWelcome: boolean;
  showHistoryLoading: boolean;
  waitResponse: boolean;
  isHydratingSession: boolean;
  conversationPrefs: ConversationPrefs;
  currentAgent: AnyAgent;
  agents: AnyAgent[];
  messages: ChatMessage[];
  hiddenUserExchangeIds?: Set<string>;
  layout: {
    chatWidgetRail: string;
    chatWidgetGap: string;
    chatContentRightPadding: string;
    chatContentWidth: string;
    chatContentLeftPadding: number;
  };
  onSend: (content: UserInputContent) => void;
  onStop: () => void;
  onRequestLogGenius?: () => void;
  onSelectAgent: (agent: AnyAgent) => Promise<void> | void;
  setSearchPolicy: (next: SetStateAction<SearchPolicyName>) => void;
  setSearchRagScope: (next: SearchRagScope) => void;
  setDeepSearchEnabled: (next: boolean) => void;
};

const ChatBotView = ({
  chatSessionId,
  options,
  attachmentSessionId,
  sessionAttachments,
  onAddAttachments,
  onAttachmentsUpdated,
  isUploadingAttachments,
  libraryNameMap,
  libraryById,
  promptNameMap,
  templateNameMap,
  chatContextNameMap,
  chatContextResourceMap,
  isSessionLoadBlocked,
  loadError,
  showWelcome,
  showHistoryLoading,
  waitResponse,
  isHydratingSession,
  conversationPrefs,
  currentAgent,
  agents,
  messages,
  hiddenUserExchangeIds,
  layout,
  onSend,
  onStop,
  onRequestLogGenius,
  onSelectAgent,
  setSearchPolicy,
  setSearchRagScope,
  setDeepSearchEnabled,
}: ChatBotViewProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const username =
    KeyCloakService.GetUserGivenName?.() ||
    KeyCloakService.GetUserFullName?.() ||
    KeyCloakService.GetUserName?.() ||
    "";
  const greetingText = username ? t("chatbot.welcomeUser", { username }) : t("chatbot.welcomeFallback");
  const [typedGreeting, setTypedGreeting] = useState<string>(greetingText);
  useEffect(() => {
    setTypedGreeting(greetingText);
  }, [greetingText]);
  useEffect(() => {
    if (!showWelcome) return;
    setTypedGreeting(greetingText);
  }, [greetingText, showWelcome]);

  const scrollerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (showWelcome) return;
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => {
        bottomRef.current?.scrollIntoView({ block: "end" });
      });
    });
    return () => {
      cancelAnimationFrame(raf1);
      if (raf2) cancelAnimationFrame(raf2);
    };
  }, [messages.length, chatSessionId, showWelcome]);

  const { outputTokenCounts, inputTokenCounts } = useMemo(() => {
    if (!messages || messages.length === 0) return { outputTokenCounts: 0, inputTokenCounts: 0 };
    const output = messages.reduce((sum, msg) => sum + (msg.metadata?.token_usage?.output_tokens || 0), 0);
    const input = messages.reduce((sum, msg) => sum + (msg.metadata?.token_usage?.input_tokens || 0), 0);
    return { outputTokenCounts: output, inputTokenCounts: input };
  }, [messages]);

  const { chatContentRightPadding, chatContentWidth, chatContentLeftPadding } = layout;
  const userInputProps = {
    agentChatOptions: currentAgent.chat_options,
    isWaiting: waitResponse,
    isHydratingSession,
    onSend,
    onStop,
    searchPolicy: conversationPrefs.searchPolicy,
    onSearchPolicyChange: setSearchPolicy,
    searchRagScope: conversationPrefs.searchRagScope,
    onSearchRagScopeChange: setSearchRagScope,
    onDeepSearchEnabledChange: setDeepSearchEnabled,
    currentAgent,
    agents,
    onSelectNewAgent: onSelectAgent,
  };

  if (isSessionLoadBlocked) {
    return (
      <Box
        width="100%"
        height="100%"
        display="flex"
        alignItems="center"
        justifyContent="center"
        sx={{ minHeight: { xs: "50vh", md: "60vh" } }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
          <CircularProgress size={28} thickness={4} sx={{ color: theme.palette.text.secondary }} />
          <Typography variant="body2" color="text.secondary">
            {t("common.loading", "Loading")}...
          </Typography>
          {loadError && (
            <Typography variant="body2" color="error">
              {t("common.loadingError", "Load failed. See console for details.")}
            </Typography>
          )}
        </Box>
      </Box>
    );
  }

  return (
    <Box
      width={"100%"}
      height="100%"
      display="flex"
      flexDirection="column"
      alignItems="center"
      sx={{
        minHeight: 0,
        position: "relative",
      }}
    >
      <ConversationOptionsPanel
        controller={options}
        attachmentSessionId={attachmentSessionId}
        sessionAttachments={sessionAttachments}
        onAddAttachments={onAddAttachments}
        onAttachmentsUpdated={onAttachmentsUpdated}
        isUploadingAttachments={isUploadingAttachments}
        onRequestLogGenius={onRequestLogGenius}
        libraryNameMap={libraryNameMap}
        libraryById={libraryById}
        promptNameMap={promptNameMap}
        templateNameMap={templateNameMap}
        chatContextNameMap={chatContextNameMap}
        chatContextResourceMap={chatContextResourceMap}
      />
      {/* ===== Conversation header status =====
           Fred rationale:
           - Always show the conversation context so developers/users immediately
             understand if they're in a persisted session or a draft.
           - Avoid guesswork (messages length, etc.). Keep UX deterministic. */}

      {/* Chat context picker panel */}
      {/* (moved) Chat context is now in the top-right vertical toolbar */}

      <Box
        height="100vh"
        width="100%"
        display="flex"
        flexDirection="column"
        paddingBottom={1}
        sx={{
          minHeight: 0,
          overflow: "hidden",
        }}
      >
        {/*
          IMPORTANT: keep the scrollbar on the browser edge.
          - The scrollable container must be full-width (100%),
            while the conversation content stays centered (maxWidth).
        */}
        {showWelcome && (
          <Box
            sx={{
              width: "100%",
              pr: { xs: 0, md: chatContentRightPadding },
              pl: { xs: 0, md: chatContentLeftPadding },
            }}
          >
            <Box
              width={chatContentWidth}
              maxWidth={{ xs: "100%", md: "1200px", lg: "1400px", xl: "1750px" }}
              display="flex"
              flexDirection="column"
              alignItems="center"
              sx={{
                minHeight: 0,
                overflow: "hidden",
                mx: "auto",
                pl: { xs: 0, md: chatContentLeftPadding },
              }}
            >
              <Box
                sx={{
                  minHeight: "100vh",
                  width: "100%",
                  px: { xs: 2, sm: 3 },
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: { xs: "flex-start", md: "center" },
                  pt: { xs: 6, md: 8 },
                  gap: 3,
                }}
              >
                <Box
                  sx={{
                    width: "100%",
                    textAlign: "center",
                  }}
                >
                  <Typography
                    variant="h4"
                    sx={{
                      fontWeight: 700,
                      display: "inline-block",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      position: "relative",
                      background: theme.palette.primary.main,
                      backgroundSize: "200% 200%",
                      backgroundClip: "text",
                      WebkitTextFillColor: "transparent",
                      letterSpacing: 0.5,
                    }}
                  >
                    {typedGreeting}
                  </Typography>
                </Box>
                <Typography variant="h5" color="text.primary" sx={{ textAlign: "center" }}>
                  {t("chatbot.startNew", { name: currentAgent?.name ?? "assistant" })}
                </Typography>
                <Box sx={{ width: "min(900px, 100%)" }}>
                  <UserInput {...userInputProps} />
                </Box>
              </Box>
            </Box>
          </Box>
        )}

        {!showWelcome && (
          <>
            <Box
              ref={scrollerRef}
              sx={{
                flex: 1,
                minHeight: 0,
                width: "100%",
                overflowY: "auto",
                overflowX: "hidden",
                scrollbarWidth: "thin",
                "&::-webkit-scrollbar": {
                  width: "10px",
                },
                "&::-webkit-scrollbar-thumb": {
                  backgroundColor: theme.palette.divider,
                  borderRadius: "8px",
                },
                "&::-webkit-scrollbar-track": {
                  backgroundColor: "transparent",
                },
              }}
            >
              <Box
                sx={{
                  width: "100%",
                  pr: { xs: 0, md: chatContentRightPadding },
                  pl: { xs: 0, md: chatContentLeftPadding },
                }}
              >
                <Box
                  sx={{
                    width: chatContentWidth,
                    maxWidth: { xs: "100%", md: "1200px", lg: "1400px", xl: "1750px" },
                    mx: "auto",
                    p: 2,
                    wordBreak: "break-word",
                    alignContent: "center",
                    minHeight: 0,
                    pl: { xs: 0, md: chatContentLeftPadding },
                  }}
                >
                  <MessagesArea
                    messages={messages}
                    agents={agents}
                    currentAgent={currentAgent}
                    isWaiting={waitResponse}
                    libraryNameById={libraryNameMap}
                    chatContextNameById={chatContextNameMap}
                    hiddenUserExchangeIds={hiddenUserExchangeIds}
                  />
                  {showHistoryLoading && (
                    <Box mt={1} sx={{ display: "flex", justifyContent: "center" }}>
                      <CircularProgress size={18} thickness={4} sx={{ color: theme.palette.text.secondary }} />
                    </Box>
                  )}
                  <Box ref={bottomRef} />
                </Box>
              </Box>
            </Box>

            <Box
              sx={{
                width: "100%",
                pr: { xs: 0, md: chatContentRightPadding },
                pl: { xs: 0, md: chatContentLeftPadding },
              }}
            >
              <Box
                sx={{
                  width: chatContentWidth,
                  maxWidth: { xs: "100%", md: "1200px", lg: "1400px", xl: "1750px" },
                  mx: "auto",
                  pl: { xs: 0, md: chatContentLeftPadding },
                }}
              >
                <Grid2 container width="100%" alignContent="center">
                  <UserInput {...userInputProps} />
                </Grid2>

                <Grid2 container width="100%" display="flex" justifyContent="flex-end" marginTop={0.5}>
                  <Tooltip
                    title={t("chatbot.tooltip.tokenUsage", {
                      input: inputTokenCounts,
                      output: outputTokenCounts,
                    })}
                  >
                    <Typography fontSize="0.8rem" color={theme.palette.text.secondary} fontStyle="italic">
                      {t("chatbot.tooltip.tokenCount", {
                        total: outputTokenCounts + inputTokenCounts > 0 ? outputTokenCounts + inputTokenCounts : "...",
                      })}
                    </Typography>
                  </Tooltip>
                </Grid2>
              </Box>
            </Box>
          </>
        )}
      </Box>
    </Box>
  );
};

export default ChatBotView;
