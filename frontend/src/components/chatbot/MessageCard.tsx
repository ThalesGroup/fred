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

import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import RateReviewIcon from "@mui/icons-material/RateReview";
import { Box, Chip, Grid2, IconButton, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useMemo, useState } from "react";
//import VolumeUpIcon from "@mui/icons-material/VolumeUp";
//import ClearIcon from "@mui/icons-material/Clear";
import { AnyAgent } from "../../common/agent.ts";
import type { GeoPart, LinkPart } from "../../slices/agentic/agenticOpenApi.ts";
import {
  ChatMessage,
  usePostFeedbackAgenticV1ChatbotFeedbackPostMutation,
} from "../../slices/agentic/agenticOpenApi.ts";

import { Download as DownloadIcon } from "@mui/icons-material";
import { getAgentBadge } from "../../utils/avatar.tsx";
import { extractHttpErrorMessage } from "../../utils/extractHttpErrorMessage.tsx";
import { FeedbackDialog } from "../feedback/FeedbackDialog.tsx";
import MarkdownRenderer from "../markdown/MarkdownRenderer.tsx";
import { useToast } from "../ToastProvider.tsx";
import { getExtras, isToolCall, isToolResult } from "./ChatBotUtils.tsx";
import GeoMapRenderer from "./GeoMapRenderer.tsx";
import { MessagePart, toCopyText, toMarkdown } from "./messageParts.ts";
export default function MessageCard({
  message,
  agent,
  side,
  enableCopy = false,
  enableThumbs = false,
  // enableAudio = false,
  pending = false,
  showMetaChips = true,
  suppressText = false, // hides text parts when true (we still render non-text via markdown)
  onCitationHover, // optional: (uid|null) → let parent highlight Sources
  onCitationClick, // optional: (uid|null) → parent can open dialog
}: {
  message: ChatMessage;
  agent: AnyAgent;
  side: "left" | "right";
  enableCopy?: boolean;
  enableThumbs?: boolean;
  // enableAudio?: boolean;
  pending?: boolean;
  showMetaChips?: boolean;
  suppressText?: boolean;
  onCitationHover?: (uid: string | null) => void;
  onCitationClick?: (uid: string | null) => void;
}) {
  const theme = useTheme();
  const { showError, showInfo } = useToast();

  // const [postSpeechText] = usePostSpeechTextMutation();
  const [postFeedback] = usePostFeedbackAgenticV1ChatbotFeedbackPostMutation();

  // const [audioToSpeech, setAudioToSpeech] = useState<HTMLAudioElement | null>(null);
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  const handleFeedbackSubmit = (rating: number, comment?: string) => {
    postFeedback({
      feedbackPayload: {
        rating,
        comment,
        messageId: message.exchange_id,
        sessionId: message.session_id,
        agentName: agent.name ?? "unknown",
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

  // const handleStartSpeaking = (msgText: string) => {
  //   postSpeechText(msgText).then((response) => {
  //     if (response.data) {
  //       const audioBlob = response.data as Blob;
  //       const audioUrl = URL.createObjectURL(audioBlob);
  //       const a = new Audio(audioUrl);
  //       setAudioToSpeech(a);
  //       a.play()
  //         .then(() => {
  //           a.onended = () => setAudioToSpeech(null);
  //         })
  //         .catch((error) => {
  //           console.error("Failed to play audio:", error);
  //         });
  //     } else {
  //       console.error("No audio data in response");
  //     }
  //   });
  // };

  // const handleStopSpeaking = () => {
  //   if (audioToSpeech) {
  //     audioToSpeech.pause();
  //     setAudioToSpeech(null);
  //   }
  // };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  const extras = getExtras(message);
  const isCall = isToolCall(message);
  const isResult = isToolResult(message);

  // Build the markdown content once (optionally filtering out text parts)
  const { mdContent, downloadLinkPart, geoPart } = useMemo(() => {
    const allParts = message.parts || [];
    let linkPart: LinkPart | undefined = undefined;
    let mapPart: GeoPart | undefined = undefined; // 👈 1. Declare the new variable

    // Filter out the specific LinkPart and GeoPart we want to render separately
    const processedParts = allParts.filter((p: any) => {
      // Check for DOWNLOAD link
      if (p.type === "link" && p.kind === "download") {
        if (!linkPart) {
          linkPart = p as LinkPart;
          return false; // Exclude it from the Markdown content
        }
      }

      // 👈 2. Check for GEO part
      if (p.type === "geo") {
        if (!mapPart) {
          mapPart = p as GeoPart;
          return false; // Exclude it from the Markdown content
        }
      }

      // If suppressText is true, exclude all 'text' parts from the Markdown content
      if (suppressText && p.type === "text") {
        return false;
      }
      return true; // Include all other parts (text, code, citations, etc.)
    }) as MessagePart[];

    return {
      mdContent: toMarkdown(processedParts), // Convert remaining parts to markdown
      downloadLinkPart: linkPart,
      geoPart: mapPart, // 👈 3. Return the GeoPart
    };
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
                    <MarkdownRenderer
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
                        onHover: onCitationHover, // already coming from parent
                        onClick: onCitationClick, // optional
                      }}
                    />{" "}
                  </Box>
                  {geoPart && (
                    <Box px={side === "right" ? 0 : 1} pt={0.5} pb={1}>
                      <GeoMapRenderer part={geoPart} />
                    </Box>
                  )}
                  {/* 🌟 NEW: RENDER DOWNLOAD LINK SEPARATELY 🌟 */}
                  {downloadLinkPart && (
                    <Box px={side === "right" ? 0 : 1} pt={0.5} pb={1}>
                      <Tooltip title="Click to securely download asset. Requires valid authentication context.">
                        <Chip
                          icon={<DownloadIcon />}
                          // Display the title (filename)
                          label={downloadLinkPart.title || "Download File"}
                          // Use an anchor tag <a> for the Chip
                          component="a"
                          href={downloadLinkPart.href}
                          // Optional: open in new tab
                          target="_blank"
                          clickable
                          color="primary"
                          variant="filled"
                          size="medium"
                          sx={{ fontWeight: "bold" }}
                        />
                      </Tooltip>
                    </Box>
                  )}
                  {/* 🌟 END NEW 🌟 */}
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

                  {/* {enableAudio && (
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
                  )} */}

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
