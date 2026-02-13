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
import { Box, Button, Chip, Grid2, IconButton, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
//import VolumeUpIcon from "@mui/icons-material/VolumeUp";
//import ClearIcon from "@mui/icons-material/Clear";
import { Download as DownloadIcon } from "@mui/icons-material";
import FeedbackOutlinedIcon from "@mui/icons-material/FeedbackOutlined";
import { AnyAgent } from "../../common/agent.ts";
import { AgentChipMini } from "../../common/AgentChip.tsx";
import DotsLoader from "../../common/DotsLoader.tsx";
import { usePdfDocumentViewer } from "../../common/usePdfDocumentViewer";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips.tsx";
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
import { MessagePart, toCopyText, toMarkdown, toPlainText } from "./messageParts.ts";
import MessageRuntimeContextHeader from "./MessageRuntimeContextHeader.tsx";
import { useMessageContentPagination } from "./useMessageContentPagination.tsx";
import { workspaceUserFileDownloader } from "./workspaceUserFileDownloader.tsx";

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
  const isAssistant = side === "left";

  const handleFeedbackSubmit = (rating: number, comment?: string) => {
    postFeedback({
      feedbackPayload: {
        rating,
        comment,
        messageId: message.exchange_id,
        sessionId: message.session_id,
        agentName: agent.id ?? t("chat.common.unknown"),
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

  const onLoadError = (err: unknown) => {
    showError({
      summary: t("chat.message.loadError", "Failed to load full message"),
      detail: err instanceof Error ? err.message : String(err),
    });
  };

  const textPagination = (message.metadata?.extras as any)?.text_pagination as
    | { offset?: number; limit?: number; total?: number; has_more?: boolean }
    | undefined;
  const paginationHasMore = Boolean(textPagination?.has_more);
  const { renderMessage, isExpanded, isLoadingFullText, toggleExpanded } = useMessageContentPagination({
    message,
    paginationHasMore,
    onError: onLoadError,
  });

  const extras = getExtras(renderMessage);
  const { downloadLink } = workspaceUserFileDownloader();
  const isCall = isToolCall(renderMessage);
  const isResult = isToolResult(renderMessage);

  // Build the message parts once (optionally filtering out text parts)
  const { processedParts, downloadLinkPart, viewLinkPart, geoPart } = useMemo(() => {
    const allParts = renderMessage.parts || [];
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
      processedParts,
      downloadLinkPart: linkPart,
      viewLinkPart: viewPart,
      geoPart: mapPart,
    };
  }, [renderMessage.parts, suppressText]);

  const plainText = useMemo(() => toPlainText(processedParts), [processedParts]);

  const collapsedCharThreshold = 1200;
  const collapsedMaxHeight = 320;
  const effectiveLimit = typeof textPagination?.limit === "number" ? textPagination.limit : collapsedCharThreshold;
  const shouldCollapse =
    !suppressText && side === "right" && (paginationHasMore || plainText.trim().length > effectiveLimit);
  const isCollapsed = shouldCollapse && !isExpanded;
  const userBubbleBackground = theme.palette.mode === "dark" ? theme.palette.grey[800] : theme.palette.grey[100];
  const bubbleBackground = side === "right" ? userBubbleBackground : theme.palette.background.default;
  const mdContent = useMemo(() => toMarkdown(processedParts), [processedParts]);
  const toggleButtonSx = {
    minWidth: "unset",
    px: 1,
    textTransform: "none",
    borderRadius: "8px",
  };
  const toggleEdgeSx = side === "right" ? { right: 8 } : { left: 8 };
  const showLessSticky = shouldCollapse && isExpanded;

  return (
    <>
      <Grid2 container marginBottom={1} sx={{ position: "relative" }}>
        {/* Assistant avatar on the left */}
        {side === "left" && agent && (
          <Grid2 size="auto" paddingTop={2}>
            <SimpleTooltip title={`${agent.id}: ${agent.tuning.role}`}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                <AgentChipMini agent={agent} />
                {pending && (
                  <Box sx={{ display: "flex", alignItems: "center", transform: "translateY(1px) scale(0.9)" }}>
                    <DotsLoader dotSize="4px" dotColor={theme.palette.text.secondary} />
                  </Box>
                )}
              </Box>
            </SimpleTooltip>
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
                    backgroundColor: side === "right" ? userBubbleBackground : theme.palette.background.default,
                    padding: side === "right" ? "0.55em 14px" : "0.8em 14px",
                    marginTop: side === "right" ? 1 : 0,
                    borderRadius: 3,
                    border: side === "right" ? `1px solid ${theme.palette.divider}` : "none",
                    maxWidth: side === "right" ? "72ch" : "100%",
                    width: side === "right" ? "fit-content" : "100%",
                    textAlign: "left",
                    wordBreak: "break-word",
                  }}
                >
                  {/* Header: task chips + indicators */}
                  {(showMetaChips || isCall || isResult) && (
                    <Box display="flex" alignItems="center" gap={1} px={0} pb={0.5}>
                      {showMetaChips && extras?.task && (
                        <SimpleTooltip title={t("chat.labels.task")}>
                          <Typography
                            variant="caption"
                            sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1, px: 0.75, py: 0.25 }}
                          >
                            {String(extras.task)}
                          </Typography>
                        </SimpleTooltip>
                      )}
                      {showMetaChips && extras?.node && (
                        <SimpleTooltip title={t("chat.labels.node")}>
                          <Typography
                            variant="caption"
                            sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1, px: 0.75, py: 0.25 }}
                          >
                            {String(extras.node)}
                          </Typography>
                        </SimpleTooltip>
                      )}
                      {showMetaChips && extras?.label && (
                        <Typography
                          variant="caption"
                          sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1, px: 0.75, py: 0.25 }}
                        >
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
                    </Box>
                  )}

                  {/* tool_call compact args */}
                  {isCall && renderMessage.parts?.[0]?.type === "tool_call" && (
                    <Box px={0} pb={0.25} sx={{ opacity: 0.8 }}>
                      <Typography fontSize=".8rem">
                        <b>{(renderMessage.parts[0] as any).name}</b>
                        {": "}
                        <code style={{ whiteSpace: "pre-wrap" }}>
                          {JSON.stringify((renderMessage.parts[0] as any).args ?? {}, null, 0)}
                        </code>
                      </Typography>
                    </Box>
                  )}

                  {/* Main content */}
                  <Box
                    px={0}
                    pb={side === "right" ? 0 : 0.25}
                    sx={{ display: "flex", flexDirection: "column", position: "relative" }}
                  >
                    {showLessSticky && (
                      <Box
                        sx={{
                          position: "sticky",
                          top: 0,
                          zIndex: 1,
                          height: 0,
                          overflow: "visible",
                        }}
                      >
                        <Button
                          size="small"
                          variant="contained"
                          color="primary"
                          onClick={toggleExpanded}
                          aria-expanded={isExpanded}
                          disabled={isLoadingFullText}
                          sx={{
                            position: "absolute",
                            top: 0,
                            ...toggleEdgeSx,
                            ...toggleButtonSx,
                          }}
                        >
                          {t("chat.message.showLess")}
                        </Button>
                      </Box>
                    )}
                    <Box
                      sx={{
                        position: "relative",
                        mt: side === "right" ? 0 : showMetaChips || isCall || isResult ? 3 : 0.8,
                        ...(isCollapsed && {
                          maxHeight: collapsedMaxHeight,
                          overflow: "hidden",
                          "&::after": {
                            content: '""',
                            position: "absolute",
                            left: 0,
                            right: 0,
                            bottom: 0,
                            height: 48,
                            background: `linear-gradient(transparent, ${bubbleBackground})`,
                          },
                        }),
                      }}
                    >
                      {side === "right" ? (
                        <Typography
                          variant="body1"
                          sx={{
                            whiteSpace: "pre-wrap",
                            wordBreak: "break-word",
                            lineHeight: 1.6,
                          }}
                        >
                          {plainText}
                        </Typography>
                      ) : (
                        <MarkdownRenderer
                          content={mdContent}
                          size="medium"
                          citations={{
                            getUidForNumber: (n) => {
                              const src = (renderMessage.metadata?.sources as any[]) || [];
                              const ordered = [...src].sort((a, b) => (a?.rank ?? 1e9) - (b?.rank ?? 1e9));
                              const hit = ordered[n - 1];
                              return hit?.uid ?? null;
                            },
                            onHover: onCitationHover,
                            onClick: onCitationClick,
                          }}
                        />
                      )}
                    </Box>
                    {shouldCollapse && !isExpanded && (
                      <Box
                        sx={{
                          position: "absolute",
                          right: 8,
                          bottom: 8,
                          zIndex: 1,
                        }}
                      >
                        <Button
                          size="small"
                          variant="contained"
                          color="primary"
                          onClick={toggleExpanded}
                          aria-expanded={isExpanded}
                          disabled={isLoadingFullText}
                          sx={{
                            ...toggleButtonSx,
                            ...toggleEdgeSx,
                            bottom: 8,
                          }}
                        >
                          {t("chat.message.showMore")}
                        </Button>
                      </Box>
                    )}
                  </Box>
                  {geoPart && (
                    <Box px={0} pt={0.5} pb={1}>
                      <GeoMapRenderer part={geoPart} />
                    </Box>
                  )}
                  {/* 🌟 DOWNLOAD / VIEW LINKS 🌟 */}
                  {(downloadLinkPart || viewLinkPart) && (
                    <Box px={0} pt={0.5} pb={1} display="flex" gap={1} flexWrap="wrap">
                      {downloadLinkPart && (
                        <Chip
                          icon={<DownloadIcon />}
                          label={downloadLinkPart.title || "Download File"}
                          onClick={() => downloadLink(downloadLinkPart)}
                          clickable={Boolean(downloadLinkPart.href)}
                          color="primary"
                          variant="filled"
                          size="medium"
                          sx={{ fontWeight: "bold" }}
                        />
                      )}
                      {viewLinkPart && (
                        <SimpleTooltip title="Open PDF preview in viewer">
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
                        </SimpleTooltip>
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
                      onClick={() => copyToClipboard(toCopyText(renderMessage.parts))}
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
                      <FeedbackOutlinedIcon fontSize="small" color="inherit" />
                    </IconButton>
                  )}

                  {renderMessage.metadata?.token_usage && (
                    <SimpleTooltip
                      title={`In: ${renderMessage.metadata.token_usage?.input_tokens ?? 0} · Out: ${renderMessage.metadata.token_usage?.output_tokens ?? 0}`}
                      placement="top"
                    >
                      <Typography color={theme.palette.text.secondary} fontSize=".7rem" sx={{ wordBreak: "normal" }}>
                        {renderMessage.metadata.token_usage?.output_tokens ?? 0} tokens
                      </Typography>
                    </SimpleTooltip>
                  )}

                  {/* <Chip
                    label="AI content may be incorrect, please double-check responses"
                    size="small"
                    variant="outlined"
                    sx={{
                      fontSize: "0.7rem",
                      height: "24px",
                      borderColor: theme.palette.divider,
                      color: theme.palette.text.primary,
                    }}
                  /> */}
                </Grid2>
              ) : (
                <Grid2 height="30px" />
              )}
            </>
          )}
        </Grid2>
        {isAssistant && (
          <Box sx={{ position: "absolute", right: 0, top: "0.8em", zIndex: 1 }}>
            <MessageRuntimeContextHeader
              message={renderMessage}
              libraryNameById={libraryNameById}
              chatContextNameById={chatContextNameById}
            />
          </Box>
        )}
      </Grid2>

      <FeedbackDialog open={feedbackOpen} onClose={() => setFeedbackOpen(false)} onSubmit={handleFeedbackSubmit} />
    </>
  );
}
