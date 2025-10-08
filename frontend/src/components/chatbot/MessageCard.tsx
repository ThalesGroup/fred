// MessageCard.tsx
// Copyright Thales 2025
// Licensed under the Apache License, Version 2.0

import {
  Box,
  Chip,
  Grid2,
  IconButton,
  Tooltip,
  Typography,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import RateReviewIcon from "@mui/icons-material/RateReview";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { getAgentBadge } from "../../utils/avatar.tsx";
import { useToast } from "../ToastProvider.tsx";
import { extractHttpErrorMessage } from "../../utils/extractHttpErrorMessage.tsx";
import CustomMarkdownRenderer from "../markdown/CustomMarkdownRenderer.tsx";
import {
  ChatMessage,
  usePostFeedbackAgenticV1ChatbotFeedbackPostMutation,
} from "../../slices/agentic/agenticOpenApi.ts";
import { toCopyText, toMarkdown } from "./messageParts.ts";
import { getExtras, isToolCall, isToolResult } from "./ChatBotUtils.tsx";
import { FeedbackDialog } from "../feedback/FeedbackDialog.tsx";
import { AnyAgent } from "../../common/agent.ts";
import MessageRuntimeContextHeader from "./MessageRuntimeContextHeader.tsx";

export default function MessageCard({
  message,
  agent,
  side,
  enableCopy = false,
  enableThumbs = false,
  pending = false,
  showMetaChips = true,
  suppressText = false,
  onCitationHover,
  onCitationClick,
  libraryNameById,
  profileNameById,
}: {
  message: ChatMessage;
  agent: AnyAgent;
  side: "left" | "right";
  enableCopy?: boolean;
  enableThumbs?: boolean;
  pending?: boolean;
  showMetaChips?: boolean;
  suppressText?: boolean;
  onCitationHover?: (uid: string | null) => void;
  onCitationClick?: (uid: string | null) => void;

  libraryNameById?: Record<string, string>;
  profileNameById?: Record<string, string>;
}) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { showError, showInfo } = useToast();

  const [postFeedback] = usePostFeedbackAgenticV1ChatbotFeedbackPostMutation();
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  // Header hover state (controls header indicators visibility)
  const [bubbleHover, setBubbleHover] = useState(false);
  const isAssistant = side === "left";

  const handleFeedbackSubmit = (rating: number, comment?: string) => {
    postFeedback({
      feedbackPayload: {
        rating,
        comment,
        messageId: message.exchange_id,
        sessionId: message.session_id,
        agentName: agent.name ?? t("chat.common.unknown"),
      },
    }).then((result) => {
      if (result.error) {
        showError({
          summary: t("chat.feedback.error"),
          detail: extractHttpErrorMessage(result.error),
        });
      } else {
        showInfo({ summary: t("chat.feedback.submitted"), detail: t("chat.feedback.thanks") });
      }
    });
    setFeedbackOpen(false);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  const extras = getExtras(message);
  const isCall = isToolCall(message);
  const isResult = isToolResult(message);

  // Build markdown once
  const mdContent = useMemo(() => {
    const parts = suppressText ? (message.parts || []).filter((p: any) => p?.type !== "text") : message.parts || [];
    return toMarkdown(parts);
  }, [message.parts, suppressText]);

  return (
    <>
      <Grid2 container marginBottom={1}>
        {/* Assistant avatar on the left */}
        {side === "left" && agent && (
          <Grid2 size="auto" paddingTop={2}>
            <Tooltip title={`${agent.name}: ${agent.role}`}>
              <Box sx={{ mr: 2, mb: 2 }}>{getAgentBadge(agent.name, agent.type === "leader")}</Box>
            </Tooltip>
          </Grid2>
        )}

        <Grid2 container size="grow" display="flex" justifyContent={side}>
          {message && (
            <>
              <Grid2>
                <Box
                  onMouseEnter={() => setBubbleHover(true)}
                  onMouseLeave={() => setBubbleHover(false)}
                  sx={{
                    display: "flex",
                    flexDirection: "column",
                    backgroundColor:
                      side === "right" ? theme.palette.background.paper : theme.palette.background.default,
                    padding: side === "right" ? "0.8em 16px 0 16px" : "0.8em 0 0 0",
                    marginTop: side === "right" ? 1 : 0,
                    borderRadius: 3,
                    wordBreak: "break-word",
                  }}
                >
                  {/* Header: task chips + indicators */}
                  {(showMetaChips || isCall || isResult) && (
                    <Box display="flex" alignItems="center" gap={1} px={side === "right" ? 0 : 1} pb={0.5}>
                      {showMetaChips && extras?.task && (
                        <Tooltip title={t("chat.labels.task")}>
                          <Typography variant="caption" sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1, px: 0.75, py: 0.25 }}>
                            {String(extras.task)}
                          </Typography>
                        </Tooltip>
                      )}
                      {showMetaChips && extras?.node && (
                        <Tooltip title={t("chat.labels.node")}>
                          <Typography variant="caption" sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1, px: 0.75, py: 0.25 }}>
                            {String(extras.node)}
                          </Typography>
                        </Tooltip>
                      )}
                      {showMetaChips && extras?.label && (
                        <Typography variant="caption" sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1, px: 0.75, py: 0.25 }}>
                          {String(extras.label)}
                        </Typography>
                      )}
                      {isCall && pending && (
                        <Typography fontSize=".8rem" sx={{ opacity: 0.7 }}>
                          ⏳ {t("chat.message.waiting")}
                        </Typography>
                      )}
                      {isResult && (
                        <Typography fontSize=".8rem" sx={{ opacity: 0.7 }}>
                          ✅ {t("chat.message.toolResult")}
                        </Typography>
                      )}

                      {/* Runtime context header (indicators + popover trigger) */}
                      {isAssistant && (
                        <MessageRuntimeContextHeader
                          message={message}
                          visible={bubbleHover}
                          libraryNameById={libraryNameById}
                          profileNameById={profileNameById}
                        />
                      )}
                    </Box>
                  )}

                  {/* tool_call compact args */}
                  {isCall && message.parts?.[0]?.type === "tool_call" && (
                    <Box px={side === "right" ? 0 : 1} pb={0.5} sx={{ opacity: 0.8 }}>
                      <Typography fontSize=".8rem">
                        <b>{(message.parts[0] as any).name}</b>
                        {": "}
                        <code style={{ whiteSpace: "pre-wrap" }}>
                          {JSON.stringify((message.parts[0] as any).args ?? {}, null, 0)}
                        </code>
                      </Typography>
                    </Box>
                  )}

                  {/* Main content */}
                  <Box px={side === "right" ? 0 : 1} pb={0.5}>
                    <CustomMarkdownRenderer
                      content={mdContent}
                      size="medium"
                      citations={{
                        getUidForNumber: (n) => {
                          const src = (message.metadata?.sources as any[]) || [];
                          const ordered = [...src].sort((a, b) => (a?.rank ?? 1e9) - (b?.rank ?? 1e9));
                          const hit = ordered[n - 1];
                          return hit?.uid ?? null;
                        },
                        onHover: onCitationHover,
                        onClick: onCitationClick,
                      }}
                    />
                  </Box>
                </Box>
              </Grid2>

              {/* Footer controls (assistant side) */}
              {side === "left" ? (
                <Grid2 size={12} display="flex" alignItems="center" gap={1} flexWrap="wrap">
                  {enableCopy && (
                    <IconButton
                      size="small"
                      onClick={() => copyToClipboard(toCopyText(message.parts))}
                      aria-label={t("chat.actions.copyMessage")}
                    >
                      <ContentCopyIcon fontSize="medium" color="inherit" />
                    </IconButton>
                  )}

                  {enableThumbs && (
                    <IconButton
                      size="small"
                      onClick={() => setFeedbackOpen(true)}
                      aria-label={t("chat.actions.openFeedback")}
                    >
                      <RateReviewIcon fontSize="medium" color="inherit" />
                    </IconButton>
                  )}

                  {message.metadata?.token_usage && (
                    <Tooltip
                      title={`In: ${message.metadata.token_usage?.input_tokens ?? 0} · Out: ${message.metadata.token_usage?.output_tokens ?? 0}`}
                      placement="top"
                    >
                      <Typography color={theme.palette.text.secondary} fontSize=".7rem" sx={{ wordBreak: "normal" }}>
                        {message.metadata.token_usage?.output_tokens ?? 0} tokens
                      </Typography>
                    </Tooltip>
                  )}

                  <Chip
                    label="AI content may be incorrect, please double-check responses"
                    size="small"
                    variant="outlined"
                    sx={{
                      fontSize: "0.7rem",
                      height: "24px",
                      borderColor: theme.palette.divider,
                      color: theme.palette.text.primary,
                    }}
                  />
                </Grid2>
              ) : (
                <Grid2 height="30px" />
              )}
            </>
          )}
        </Grid2>
      </Grid2>

      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} onSubmit={handleFeedbackSubmit} />
    </>
  );
}
