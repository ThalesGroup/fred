// Copyright Thales 2025
// Licensed under the Apache License, Version 2.0

import { Box, Grid2, IconButton, Tooltip, Chip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { useState, useMemo } from "react";
import RateReviewIcon from "@mui/icons-material/RateReview";
import VolumeUpIcon from "@mui/icons-material/VolumeUp";
import ClearIcon from "@mui/icons-material/Clear";
import { usePostSpeechTextMutation } from "../../frugalit/slices/api.tsx";
import { getAgentBadge } from "../../utils/avatar.tsx";
import { FeedbackDialog } from "../../frugalit/component/FeedbackDialog.tsx";
import { useToast } from "../ToastProvider.tsx";
import { extractHttpErrorMessage } from "../../utils/extractHttpErrorMessage.tsx";
import CustomMarkdownRenderer from "../markdown/CustomMarkdownRenderer.tsx";
import {
  AgenticFlow,
  ChatMessage,
  usePostFeedbackAgenticV1ChatbotFeedbackPostMutation,
} from "../../slices/agentic/agenticOpenApi.ts";
import { toCopyText, toMarkdown, toSpeechText } from "./messageParts.ts";
import { getExtras, isToolCall, isToolResult } from "./ChatBotUtils.tsx";

export default function MessageCard({
  message,
  agenticFlow,
  side,
  enableCopy = false,
  enableThumbs = false,
  enableAudio = false,
  currentAgenticFlow,
  pending = false,
  showMetaChips = true,
  suppressText = false,                 // hides text parts when true (we still render non-text via markdown)
  onCitationHover,                      // optional: (uid|null) → let parent highlight Sources
  onCitationClick,                      // optional: (uid|null) → parent can open dialog
}: {
  message: ChatMessage;
  agenticFlow: AgenticFlow;
  side: "left" | "right";
  enableCopy?: boolean;
  enableThumbs?: boolean;
  enableAudio?: boolean;
  currentAgenticFlow: AgenticFlow;
  pending?: boolean;
  showMetaChips?: boolean;
  suppressText?: boolean;
  onCitationHover?: (uid: string | null) => void;
  onCitationClick?: (uid: string | null) => void;
}) {
  const theme = useTheme();
  const { showError, showInfo } = useToast();

  const [postSpeechText] = usePostSpeechTextMutation();
  const [postFeedback] = usePostFeedbackAgenticV1ChatbotFeedbackPostMutation();

  const [audioToSpeech, setAudioToSpeech] = useState<HTMLAudioElement | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  const handleFeedbackSubmit = (rating: number, comment?: string) => {
    postFeedback({
      feedbackPayload: {
        rating,
        comment,
        messageId: message.exchange_id,
        sessionId: message.session_id,
        agentName: currentAgenticFlow.name ?? "unknown",
      },
    }).then((result) => {
      if (result.error) {
        showError({
          summary: "Error submitting feedback",
          detail: extractHttpErrorMessage(result.error),
        });
      } else {
        showInfo({ summary: "Feedback submitted", detail: "Thank you!" });
      }
    });
    setFeedbackOpen(false);
  };

  const handleStartSpeaking = (msgText: string) => {
    postSpeechText(msgText).then((response) => {
      if (response.data) {
        const audioBlob = response.data as Blob;
        const audioUrl = URL.createObjectURL(audioBlob);
        const a = new Audio(audioUrl);
        setAudioToSpeech(a);
        a.play()
          .then(() => {
            a.onended = () => setAudioToSpeech(null);
          })
          .catch((error) => {
            console.error("Failed to play audio:", error);
          });
      } else {
        console.error("No audio data in response");
      }
    });
  };

  const handleStopSpeaking = () => {
    if (audioToSpeech) {
      audioToSpeech.pause();
      setAudioToSpeech(null);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  const extras = getExtras(message);
  const isCall = isToolCall(message);
  const isResult = isToolResult(message);

  // Build the markdown content once (optionally filtering out text parts)
  const mdContent = useMemo(() => {
    const parts = suppressText
      ? (message.parts || []).filter((p: any) => p?.type !== "text")
      : message.parts || [];
    return toMarkdown(parts);
  }, [message.parts, suppressText]);

  return (
    <>
      <Grid2 container marginBottom={1}>
        {/* Assistant avatar on the left */}
        {side === "left" && agenticFlow && (
          <Grid2 size="auto" paddingTop={2}>
            <Tooltip title={`${agenticFlow.nickname}: ${agenticFlow.role}`}>
              <Box sx={{ mr: 2, mb: 2 }}>{getAgentBadge(agenticFlow.nickname)}</Box>
            </Tooltip>
          </Grid2>
        )}

        <Grid2 container size="grow" display="flex" justifyContent={side}>
          {message && (
            <>
              <Grid2>
                <Box
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
                  {/* Header: task chips + tool-call indicators */}
                  {(showMetaChips || isCall || isResult) && (
                    <Box display="flex" alignItems="center" gap={1} px={side === "right" ? 0 : 1} pb={0.5}>
                      {showMetaChips && extras?.task && (
                        <Chip size="small" label={String(extras.task)} variant="outlined" />
                      )}
                      {showMetaChips && extras?.node && (
                        <Chip size="small" label={String(extras.node)} variant="outlined" />
                      )}
                      {showMetaChips && extras?.label && (
                        <Chip size="small" label={String(extras.label)} variant="outlined" />
                      )}
                      {isCall && pending && (
                        <Typography fontSize=".8rem" sx={{ opacity: 0.7 }}>
                          ⏳ waiting for result…
                        </Typography>
                      )}
                      {isResult && (
                        <Typography fontSize=".8rem" sx={{ opacity: 0.7 }}>
                          ✅ tool result
                        </Typography>
                      )}
                    </Box>
                  )}

                  {/* For tool_call: compact args preview */}
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

                  {/* Main content (single path): ALWAYS markdown, with optional citationMap */}
                  <Box px={side === "right" ? 0 : 1} pb={0.5}>
                    <CustomMarkdownRenderer
                      content={mdContent}
                      size="medium"
                      
                      citations={{
    getUidForNumber: (n) => {
      // Build once per message if you like, but simplest:
      const src = (message.metadata?.sources as any[]) || [];
      const ordered = [...src].sort((a, b) => (a?.rank ?? 1e9) - (b?.rank ?? 1e9));
      const hit = ordered[n - 1];
      return hit?.uid ?? null;
    },
    onHover: onCitationHover,  // already coming from parent
    onClick: onCitationClick,  // optional
  }}
                    />
                  </Box>
                </Box>
              </Grid2>

              {/* Footer controls (assistant side) */}
              {side === "left" ? (
                <Grid2 size={12} display="flex" alignItems="center" gap={1} flexWrap="wrap">
                  {enableCopy && (
                    <IconButton size="small" onClick={() => copyToClipboard(toCopyText(message.parts))}>
                      <ContentCopyIcon fontSize="medium" color="inherit" />
                    </IconButton>
                  )}

                  {enableThumbs && (
                    <IconButton size="small" onClick={() => setFeedbackOpen(true)}>
                      <RateReviewIcon fontSize="medium" color="inherit" />
                    </IconButton>
                  )}

                  {enableAudio && (
                    <IconButton
                      size="small"
                      onClick={() =>
                        audioToSpeech ? handleStopSpeaking() : handleStartSpeaking(toSpeechText(message.parts))
                      }
                    >
                      {audioToSpeech ? (
                        <ClearIcon fontSize="medium" color="inherit" />
                      ) : (
                        <VolumeUpIcon fontSize="medium" color="inherit" />
                      )}
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
