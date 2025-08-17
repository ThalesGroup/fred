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

import { Box, Grid2, IconButton, Tooltip, Chip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { useState } from "react";
import RateReviewIcon from "@mui/icons-material/RateReview";
import VolumeUpIcon from "@mui/icons-material/VolumeUp";
import ClearIcon from "@mui/icons-material/Clear";
import { usePostSpeechTextMutation } from "../../frugalit/slices/api.tsx";
import { AgenticFlow } from "../../pages/Chat.tsx";
import { getAgentBadge } from "../../utils/avatar.tsx";
import { FeedbackDialog } from "../../frugalit/component/FeedbackDialog.tsx";
import { useToast } from "../ToastProvider.tsx";
import { extractHttpErrorMessage } from "../../utils/extractHttpErrorMessage.tsx";
import CustomMarkdownRenderer from "../markdown/CustomMarkdownRenderer.tsx";
import { ChatMessagePayload, usePostFeedbackAgenticV1ChatbotFeedbackPostMutation } from "../../slices/agentic/agenticOpenApi.ts";

export default function Message({
  message,
  agenticFlow,
  side,
  enableCopy = false,
  enableThumbs = false,
  enableAudio = false,
  currentAgenticFlow,
}: {
  message: ChatMessagePayload;
  agenticFlow: AgenticFlow;
  side: string;
  enableCopy?: boolean;
  enableThumbs?: boolean;
  enableAudio?: boolean;
  currentAgenticFlow: AgenticFlow;
}) {
  const theme = useTheme();
  const { showError, showInfo } = useToast(); // Use the toast hook

  const [postSpeechText] = usePostSpeechTextMutation();
  const [postFeedback] = usePostFeedbackAgenticV1ChatbotFeedbackPostMutation();

  const [audioToSpeech, setAudioToSpeech] = useState<HTMLAudioElement>(null);
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

  // Function to start speaking the message content
  const handleStartSpeaking = (message: string) => {
    postSpeechText(message).then((response) => {
      if (response.data) {
        const audioBlob = response.data as Blob;
        const audioUrl = URL.createObjectURL(audioBlob);
        const audioToSpeech = new Audio(audioUrl);
        setAudioToSpeech(audioToSpeech);
        audioToSpeech
          .play()
          .then(() => {
            // Stop the audio after it finishes playing
            audioToSpeech.onended = () => {
              setAudioToSpeech(null);
            };
          })
          .catch((error) => {
            console.error("Failed to play audio:", error);
          });
      } else {
        console.error("No audio data in response");
      }
    });
  };

  // Function to stop the audio from playing
  const handleStopSpeaking = () => {
    // Stop the audio
    if (audioToSpeech) {
      audioToSpeech.pause();
      setAudioToSpeech(null);
    }
  };

  // Function to copy the message content to the clipboard
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      console.log("Copied to clipboard");
    });
  };
  return (
    <>
      <Grid2 container marginBottom={1}>
        {/* Display the avatar for message on the right side */}
        {side === "left" && agenticFlow && (
          <Grid2 size="auto" paddingTop={2}>
            <Tooltip title={`${agenticFlow.nickname}: ${agenticFlow.role}`}>
              <Box sx={{ mr: 2, mb: 2 }}>{getAgentBadge(agenticFlow.nickname)}</Box>
            </Tooltip>
          </Grid2>
        )}
        <Grid2 container size="grow" display="flex" justifyContent={side}>
          {/* Display the event content only if it is not null */}
          {message && (
            <>
              <Grid2>
                <Box
                  sx={{
                    display: "flex",
                    flexDirection: "column",
                    backgroundColor:
                      side === "right" ? theme.palette.background.paper : theme.palette.background.default,
                    padding: side === "right" ? "0.8em 16px 0 16px" : "0.8em 0 0 0", // consistent top padding, conditional horizontal
                    marginTop: side === "right" ? 1 : 0,
                    borderRadius: 3,
                    wordBreak: "break-word",
                  }}
                >
                  <CustomMarkdownRenderer
                    content={message.content as string}
                    size="medium"
                    //  enableEmojiSubstitution={side === "left"} // only apply for assistant replies
                  />
                </Box>
              </Grid2>
              {side === "left" ? (
                <Grid2 size={12} display="flex" alignItems="center" gap={1} flexWrap="wrap">
                  {enableCopy && (
                    <IconButton
                      aria-label="delete"
                      size="small"
                      onClick={() => copyToClipboard(message.content as string)}
                    >
                      <ContentCopyIcon fontSize="medium" color="inherit" />
                    </IconButton>
                  )}
                  {enableThumbs && (
                    <>
                      <IconButton
                        aria-label="thumb up"
                        size="small"
                        onClick={() => {
                          setFeedbackOpen(true);
                        }}
                      >
                        <RateReviewIcon fontSize="medium" color="inherit" />
                      </IconButton>
                    </>
                  )}
                  {enableAudio && (
                    <IconButton
                      aria-label="up"
                      size="small"
                      onClick={() => {
                        if (audioToSpeech) {
                          handleStopSpeaking();
                        } else {
                          handleStartSpeaking(message.content as string);
                        }
                      }}
                    >
                      {audioToSpeech ? (
                        <ClearIcon fontSize="medium" color="inherit" />
                      ) : (
                        <VolumeUpIcon fontSize="medium" color="inherit" />
                      )}
                    </IconButton>
                  )}
                  {message.metadata && (
                    <Tooltip
                      title={`This question used ${message.metadata.token_usage?.input_tokens} tokens and the response used ${message.metadata.token_usage?.output_tokens} tokens`}
                      placement="top"
                    >
                      <Typography color={theme.palette.text.secondary} fontSize=".7rem" sx={{ wordBreak: "normal" }}>
                        {message.metadata.token_usage?.output_tokens} tokens
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
                <Grid2 height="30px"></Grid2>
              )}
            </>
          )}
        </Grid2>
      </Grid2>
      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} onSubmit={handleFeedbackSubmit} />
    </>
  );
}
