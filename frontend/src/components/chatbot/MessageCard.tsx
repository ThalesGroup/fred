// MessageCard.tsx
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
import PreviewIcon from "@mui/icons-material/Preview";
import RateReviewIcon from "@mui/icons-material/RateReview";
import { Box, Chip, Grid2, IconButton, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
//import VolumeUpIcon from "@mui/icons-material/VolumeUp";
//import ClearIcon from "@mui/icons-material/Clear";
import { Download as DownloadIcon } from "@mui/icons-material";
import { AnyAgent } from "../../common/agent.ts";
import { AgentChipMini } from "../../common/AgentChip.tsx";
import { usePdfDocumentViewer } from "../../common/usePdfDocumentViewer";
import type { GeoPart, LinkPart } from "../../slices/agentic/agenticOpenApi.ts";
import {
  ChatMessage,
  usePostFeedbackAgenticV1ChatbotFeedbackPostMutation,
} from "../../slices/agentic/agenticOpenApi.ts";
import { extractHttpErrorMessage } from "../../utils/extractHttpErrorMessage.tsx";
import { FeedbackDialog } from "../feedback/FeedbackDialog.tsx";
import MarkdownRenderer from "../markdown/MarkdownRenderer.tsx";
import { useToast } from "../ToastProvider.tsx";
import { getExtras, isToolCall, isToolResult } from "./ChatBotUtils.tsx";
import GeoMapRenderer from "./GeoMapRenderer.tsx";
import { MessagePart, toCopyText, toMarkdown } from "./messageParts.ts";
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
  chatContextNameById,
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
  chatContextNameById?: Record<string, string>;
}) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { openPdfDocument } = usePdfDocumentViewer();
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

  // Build the markdown content once (optionally filtering out text parts)
  const { mdContent, downloadLinkPart, viewLinkPart, geoPart } = useMemo(() => {
    const allParts = message.parts || [];
    let linkPart: LinkPart | undefined = undefined;
    let viewPart: LinkPart | undefined = undefined;
    let mapPart: GeoPart | undefined = undefined;

    const processedParts = allParts.filter((p: any) => {
      // DOWNLOAD link
      if (p.type === "link" && p.kind === "download") {
        if (!linkPart) {
          linkPart = p as LinkPart;
          return false;
        }
      }

      // VIEW link (PDF preview)
      if (p.type === "link" && p.kind === "view") {
        if (!viewPart) {
          viewPart = p as LinkPart;
          return false;
        }
      }

      // GEO part
      if (p.type === "geo") {
        if (!mapPart) {
          mapPart = p as GeoPart;
          return false;
        }
      }

      if (suppressText && p.type === "text") return false;
      return true;
    }) as MessagePart[];

    return {
      mdContent: toMarkdown(processedParts),
      downloadLinkPart: linkPart,
      viewLinkPart: viewPart,
      geoPart: mapPart,
    };
  }, [message.parts, suppressText]);

  return (
    <>
      <Grid2 container marginBottom={1}>
        {/* Assistant avatar on the left */}
        {side === "left" && agent && (
          <Grid2 size="auto" paddingTop={2}>
            <Tooltip title={`${agent.name}: ${agent.tuning.role}`}>
              <AgentChipMini agent={agent} />
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
                          chatContextNameById={chatContextNameById}
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
                    <MarkdownRenderer
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
                  {geoPart && (
                    <Box px={side === "right" ? 0 : 1} pt={0.5} pb={1}>
                      <GeoMapRenderer part={geoPart} />
                    </Box>
                  )}
                  {/* 🌟 DOWNLOAD / VIEW LINKS 🌟 */}
                  {(downloadLinkPart || viewLinkPart) && (
                    <Box px={side === "right" ? 0 : 1} pt={0.5} pb={1} display="flex" gap={1} flexWrap="wrap">
                      {downloadLinkPart && (
                        <Tooltip title="Click to securely download the PowerPoint file">
                          <Chip
                            icon={<DownloadIcon />}
                            label={downloadLinkPart.title || "Download File"}
                            component="a"
                            href={downloadLinkPart.href}
                            target="_blank"
                            clickable
                            color="primary"
                            variant="filled"
                            size="medium"
                            sx={{ fontWeight: "bold" }}
                          />
                        </Tooltip>
                      )}
                      {viewLinkPart && (
                        <Tooltip title="Open PDF preview in viewer">
                          <Chip
                            icon={<PreviewIcon />}
                            label={viewLinkPart.title || "View PDF"}
                            clickable
                            color="secondary"
                            variant="outlined"
                            size="medium"
                            sx={{ fontWeight: "bold" }}
                            onClick={() => {
                              if (viewLinkPart.document_uid) {
                                openPdfDocument({
                                  document_uid: viewLinkPart.document_uid,
                                  file_name: viewLinkPart.file_name,
                                });
                              } else if (viewLinkPart.href) {
                                window.open(viewLinkPart.href, "_blank");
                              }
                            }}
                          />
                        </Tooltip>
                      )}
                    </Box>
                  )}
                  {/* 🌟 END LINKS 🌟 */}
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
