// MessageCard.tsx
// Copyright Thales 2025
// Licensed under the Apache License, Version 2.0

import {
  Box,
  Grid2,
  IconButton,
  Tooltip,
  Chip,
  Typography,
  Popper,
  Paper,
  Stack,
  Divider,
  ClickAwayListener,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import PersonOutlinedIcon from "@mui/icons-material/PersonOutline";
import LibraryBooksOutlinedIcon from "@mui/icons-material/LibraryBooksOutlined";
import { useState, useMemo } from "react";
import RateReviewIcon from "@mui/icons-material/RateReview";
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

type PluginsUsed = {
  libraries?: string[];
  profiles?: string[];
  search_policy?: string;
  temperature?: number;
};

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
  const { showError, showInfo } = useToast();

  const [postFeedback] = usePostFeedbackAgenticV1ChatbotFeedbackPostMutation();
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  // --- INSIGHTS (assistant side only) ---
  const [insightAnchorEl, setInsightAnchorEl] = useState<HTMLElement | null>(null);
  const [insightOpen, setInsightOpen] = useState(false);
  const [bubbleHover, setBubbleHover] = useState(false);
  const isAssistant = side === "left";

  const openInsights = (el: HTMLElement | null) => {
    setInsightAnchorEl(el);
    setInsightOpen(true);
  };
  const closeInsights = () => setInsightOpen(false);

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

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => { });
  };

  const extras = getExtras(message);
  const isCall = isToolCall(message);
  const isResult = isToolResult(message);

  // Build markdown once
  const mdContent = useMemo(() => {
    const parts = suppressText ? (message.parts || []).filter((p: any) => p?.type !== "text") : message.parts || [];
    return toMarkdown(parts);
  }, [message.parts, suppressText]);

  // --- METADATA snapshot (per message) ---
  const meta: any = (message.metadata as any) ?? {};
  const plugins: PluginsUsed = (meta?.extras?.plugins as PluginsUsed) ?? {};

  const modelName: string | undefined = meta.model ?? undefined;
  const latencyMs: number | undefined =
    meta.latency_ms ?? meta?.timings?.durationMs ?? meta?.latency?.ms ?? undefined;

  // IDs actually used for THIS message
  const libsIds = Array.isArray(plugins.libraries) ? plugins.libraries : [];
  const prfIds = Array.isArray(plugins.profiles) ? plugins.profiles : [];

  const searchPolicy: string | undefined = plugins.search_policy;
  const usedTemperature: number | undefined =
    typeof (meta?.temperature ?? plugins.temperature) === "number"
      ? (meta?.temperature ?? plugins.temperature)
      : undefined;

  const inTokens = message.metadata?.token_usage?.input_tokens;
  const outTokens = message.metadata?.token_usage?.output_tokens;

  // Label helpers
  const labelize = (ids: string[] | undefined, map?: Record<string, string>) =>
    (ids ?? []).filter(Boolean).map((id) => map?.[id] || id);

  const libsLabeled = labelize(libsIds, libraryNameById);
  const prfsLabeled = labelize(prfIds, profileNameById);

  // Indicators: only when something is active
  const showLibs = libsLabeled.length > 0;
  const showProfile = prfsLabeled.length > 0;

  // Explicit lines (names)
  const libsTextFull = libsLabeled.join(", ");
  const profileTextFull = prfsLabeled.join(", ");
  const profileLabel = prfsLabeled.length > 1 ? "Profiles" : "Profile";
  const librariesLabel = libsLabeled.length > 1 ? "Libraries" : "Library";

  // Row component
  const SectionRow = ({
    label,
    value,
    fullWidth = false,
  }: {
    label: string;
    value?: string | number;
    fullWidth?: boolean;
  }) =>
    value === undefined || value === null || value === "" ? null : (
      <Box display="flex" justifyContent="space-between" gap={1} sx={{ flex: fullWidth ? 1 : undefined }}>
        <Typography variant="caption" sx={{ opacity: 0.7 }}>
          {label}
        </Typography>
        <Typography variant="caption" fontWeight={500} textAlign="right">
          {String(value)}
        </Typography>
      </Box>
    );

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

                      {/* Hover indicators (assistant only; show only when present) */}
                      {isAssistant && (showLibs || showProfile) && (
                        <Box
                          sx={{
                            ml: "auto",
                            display: "flex",
                            alignItems: "center",
                            gap: 0.5,
                            opacity: bubbleHover || insightOpen ? 1 : 0,
                            transition: "opacity .15s ease",
                          }}
                        >
                          {showLibs && (
                            <Tooltip
                              title={
                                <Box>
                                  <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mb: 0.25 }}>
                                    {librariesLabel}
                                  </Typography>
                                  <Typography variant="caption">{libsTextFull}</Typography>
                                </Box>
                              }
                            >
                              <Box
                                sx={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: 0.5,
                                  px: 0.75,
                                  py: 0.25,
                                  borderRadius: 1,
                                  border: `1px solid ${theme.palette.divider}`,
                                  maxWidth: 320,
                                }}
                              >
                                <LibraryBooksOutlinedIcon sx={{ fontSize: 14 }} />
                                <Typography
                                  variant="caption"
                                  sx={{
                                    lineHeight: 1,
                                    whiteSpace: "nowrap",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                  }}
                                >
                                  {`${librariesLabel}: ${libsTextFull}`}
                                </Typography>
                              </Box>
                            </Tooltip>
                          )}

                          {showProfile && (
                            <Tooltip
                              title={
                                <Box>
                                  <Typography variant="caption" sx={{ opacity: 0.7, display: "block", mb: 0.25 }}>
                                    {profileLabel}
                                  </Typography>
                                  <Typography variant="caption">{profileTextFull}</Typography>
                                </Box>
                              }
                            >
                              <Box
                                sx={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: 0.5,
                                  px: 0.75,
                                  py: 0.25,
                                  borderRadius: 1,
                                  border: `1px solid ${theme.palette.divider}`,
                                  maxWidth: 320,
                                }}
                              >
                                <PersonOutlinedIcon sx={{ fontSize: 14 }} />
                                <Typography
                                  variant="caption"
                                  sx={{
                                    lineHeight: 1,
                                    whiteSpace: "nowrap",
                                    overflow: "hidden",
                                    textOverflow: "ellipsis",
                                  }}
                                >
                                  {`${profileLabel}: ${profileTextFull}`}
                                </Typography>
                              </Box>
                            </Tooltip>
                          )}

                          {/* Info popover */}
                          <Box
                            onMouseEnter={(e) => openInsights(e.currentTarget as HTMLElement)}
                            onMouseLeave={closeInsights}
                            sx={{ display: "inline-flex" }}
                          >
                            <IconButton size="small" sx={{ ml: 0.5 }} aria-label="message-insights">
                              <InfoOutlinedIcon fontSize="small" />
                            </IconButton>

                            <Popper
                              open={insightOpen}
                              anchorEl={insightAnchorEl}
                              placement="bottom-end"
                              modifiers={[{ name: "offset", options: { offset: [0, 8] } }]}
                              sx={{ zIndex: (t) => t.zIndex.tooltip + 1 }}
                            >
                              <ClickAwayListener onClickAway={closeInsights}>
                                <Paper
                                  elevation={6}
                                  onMouseEnter={() => setInsightOpen(true)}
                                  onMouseLeave={closeInsights}
                                  sx={{
                                    p: 1.25,
                                    minWidth: 260,
                                    maxWidth: 360,
                                    borderRadius: 2,
                                    bgcolor:
                                      theme.palette.mode === "dark"
                                        ? theme.palette.background.paper
                                        : theme.palette.grey[50],
                                    border: `1px solid ${theme.palette.divider}`,
                                  }}
                                  role="dialog"
                                  aria-label="Message details"
                                >
                                  <Stack spacing={1}>
                                    <Typography variant="overline" sx={{ opacity: 0.7, letterSpacing: 0.6 }}>
                                      Overview
                                    </Typography>

                                    <SectionRow label="Task" value={extras?.task as any} />
                                    <SectionRow label="Node" value={extras?.node as any} />
                                    <SectionRow label="Model" value={modelName} />

                                    {/* Tokens */}
                                    {(() => {
                                      const inTok = Math.max(0, Number(inTokens ?? 0));
                                      const outTok = Math.max(0, Number(outTokens ?? 0));
                                      const totalTok = inTok + outTok;
                                      const fmt = (n: number) => n.toLocaleString();

                                      return (
                                        <>
                                          <SectionRow label="Tokens used" value={fmt(totalTok)} />
                                          <Stack spacing={0.25} sx={{ pl: 1.5, mt: 0 }}>
                                            <SectionRow label="From user (prompt+context)" value={fmt(inTok)} />
                                            <SectionRow label="From model (response)" value={fmt(outTok)} />
                                          </Stack>
                                        </>
                                      );
                                    })()}

                                    <Box display="flex" gap={1}>
                                      <SectionRow
                                        label="Latency"
                                        value={latencyMs != null ? `${latencyMs.toLocaleString()} ms` : undefined}
                                      />
                                      <SectionRow label="Search" value={searchPolicy} />
                                      <SectionRow
                                        label="Temp"
                                        value={typeof usedTemperature === "number" ? usedTemperature : undefined}
                                      />
                                    </Box>

                                    {(libsLabeled.length || prfsLabeled.length) ? <Divider flexItem /> : null}

                                    {libsLabeled.length ? (
                                      <>
                                        <Typography variant="overline" sx={{ opacity: 0.7 }}>
                                          {libsLabeled.length > 1 ? "LIBRARIES" : "LIBRARY"}
                                        </Typography>
                                        <Typography variant="caption" fontWeight={500} sx={{ display: "block" }}>
                                          {libsLabeled.join(", ")}
                                        </Typography>
                                      </>
                                    ) : null}

                                    {prfsLabeled.length ? (
                                      <>
                                        <Typography variant="overline" sx={{ opacity: 0.7 }}>
                                          {prfsLabeled.length > 1 ? "PROFILES" : "PROFILE"}
                                        </Typography>
                                        <Typography variant="caption" fontWeight={500} sx={{ display: "block" }}>
                                          {prfsLabeled.join(", ")}
                                        </Typography>
                                      </>
                                    ) : null}

                                    <Divider flexItem />
                                    <Typography variant="caption" sx={{ opacity: 0.7 }}>
                                      AI content may be incorrect.
                                    </Typography>
                                  </Stack>
                                </Paper>
                              </ClickAwayListener>
                            </Popper>
                          </Box>
                        </Box>
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
                    <IconButton size="small" onClick={() => copyToClipboard(toCopyText(message.parts))} aria-label="copy-message">
                      <ContentCopyIcon fontSize="medium" color="inherit" />
                    </IconButton>
                  )}

                  {enableThumbs && (
                    <IconButton size="small" onClick={() => setFeedbackOpen(true)} aria-label="open-feedback">
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
