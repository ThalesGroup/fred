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
import LibraryBooksOutlinedIcon from "@mui/icons-material/LibraryBooksOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import { useState, useMemo, type ReactNode } from "react";
import RateReviewIcon from "@mui/icons-material/RateReview";
import { getAgentBadge } from "../../utils/avatar.tsx";
import { useToast } from "../ToastProvider.tsx";
import { extractHttpErrorMessage } from "../../utils/extractHttpErrorMessage.tsx";
import CustomMarkdownRenderer from "../markdown/CustomMarkdownRenderer.tsx";
import {
  AgenticFlow,
  ChatMessage,
  usePostFeedbackAgenticV1ChatbotFeedbackPostMutation,
} from "../../slices/agentic/agenticOpenApi.ts";
import { toCopyText, toMarkdown } from "./messageParts.ts";
import { getExtras, isToolCall, isToolResult } from "./ChatBotUtils.tsx";
import { FeedbackDialog } from "../feedback/FeedbackDialog.tsx";

/**
 * Backend "plugins" payload carried under message.metadata.extras.plugins.
 * Only the keys we keep in the UI (libraries/templates/prompts + search/temperature).
 */
type PluginsUsed = {
  libraries?: string[];
  templates?: string[];
  prompts?: string[]; // optional, may mirror metadata.prompts
  search_policy?: string;
  temperature?: number;
};

export default function MessageCard({
  message,
  agenticFlow,
  side,
  enableCopy = false,
  enableThumbs = false,
  currentAgenticFlow,
  pending = false,
  showMetaChips = true,
  suppressText = false,
  onCitationHover,
  onCitationClick,

  // id -> human label maps
  libraryNameById,
  templateNameById,
  promptNameById,

  // current UI selections (to complement snapshot)
  currentLibraryIds,
  currentTemplateIds,
  currentPromptIds,
}: {
  message: ChatMessage;
  agenticFlow: AgenticFlow;
  side: "left" | "right";
  enableCopy?: boolean;
  enableThumbs?: boolean;
  currentAgenticFlow: AgenticFlow;
  pending?: boolean;
  showMetaChips?: boolean;
  suppressText?: boolean;
  onCitationHover?: (uid: string | null) => void;
  onCitationClick?: (uid: string | null) => void;

  libraryNameById?: Record<string, string>;
  templateNameById?: Record<string, string>;
  promptNameById?: Record<string, string>;

  currentLibraryIds?: string[];
  currentTemplateIds?: string[];
  currentPromptIds?: string[];
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

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
  };

  const extras = getExtras(message);
  const isCall = isToolCall(message);
  const isResult = isToolResult(message);

  // Build the markdown content once (optionally filtering out text parts)
  const mdContent = useMemo(() => {
    const parts = suppressText ? (message.parts || []).filter((p: any) => p?.type !== "text") : message.parts || [];
    return toMarkdown(parts);
  }, [message.parts, suppressText]);

  // --- METADATA EXTRACTION ---
  const meta: any = (message.metadata as any) ?? {};
  const plugins: PluginsUsed = (meta?.extras?.plugins as PluginsUsed) ?? {};

  const modelName: string | undefined = meta.model ?? undefined;
  const latencyMs: number | undefined =
    meta.latency_ms ?? meta?.timings?.durationMs ?? meta?.latency?.ms ?? undefined;

  // Snapshot ids from backend (what was actually applied for this message)
  const snapLibs: string[] = plugins.libraries ?? [];
  const snapTemplates: string[] = plugins.templates ?? [];
  const snapPrompts: string[] =
    (Array.isArray(meta.prompts) && meta.prompts.length ? meta.prompts : undefined) ??
    (plugins.prompts && plugins.prompts.length ? plugins.prompts : []) ??
    [];

  // Current selections (from UI, may be empty)
  const curLibs = currentLibraryIds ?? [];
  const curTemplates = currentTemplateIds ?? [];
  const curPrompts = currentPromptIds ?? [];

  // Search policy & temperature (if provided)
  const searchPolicy: string | undefined = plugins.search_policy;
  const usedTemperature: number | undefined =
    typeof plugins.temperature === "number" ? plugins.temperature : undefined;

  const inTokens = message.metadata?.token_usage?.input_tokens;
  const outTokens = message.metadata?.token_usage?.output_tokens;

  // ---- Label helpers & mix logic ----
  const uniq = (arr: string[]) => Array.from(new Set(arr.filter(Boolean)));

  /**
   * Returns labels for union(snapshot, current). Items present only in current
   * are suffixed with " (current)" to avoid misleading the user.
   */
  const mixWithBadge = (
    snap: string[],
    cur: string[],
    names?: Record<string, string>,
  ): string[] => {
    const all = uniq([...snap, ...cur]);
    return all.map((id) => {
      const label = names?.[id] || id;
      const onlyCurrent = !snap.includes(id) && cur.includes(id);
      return onlyCurrent ? `${label}` : label;
    });
  };

  // Final labeled lists used in the UI
  const libsLabeled = mixWithBadge(snapLibs, curLibs, libraryNameById);
  const templatesLabeled = mixWithBadge(snapTemplates, curTemplates, templateNameById);
  const promptsLabeled = mixWithBadge(snapPrompts, curPrompts, promptNameById);

  const noSnapshot =
    snapLibs.length === 0 && snapTemplates.length === 0 && snapPrompts.length === 0;
  const hasCurrentOnly =
    noSnapshot && (curLibs.length > 0 || curTemplates.length > 0 || curPrompts.length > 0);

  // --- Indicator pills (hover toolbar on assistant messages) ---
  type Indicator = { key: string; label: string; enabled: boolean; icon: ReactNode };
  const pluginIndicators: Indicator[] = [
    {
      key: "libraries",
      label: "Libraries",
      enabled: libsLabeled.length > 0,
      icon: <LibraryBooksOutlinedIcon sx={{ fontSize: 14 }} />,
    },
    {
      key: "templates",
      label: "Templates",
      enabled: templatesLabeled.length > 0,
      icon: <DescriptionOutlinedIcon sx={{ fontSize: 14 }} />,
    },
    {
      key: "prompts",
      label: "Prompts",
      enabled: promptsLabeled.length > 0 || !!meta.prompt_pack || !!meta.system_prompt,
      icon: <PsychologyOutlinedIcon sx={{ fontSize: 14 }} />,
    },
  ];

  const SectionRow = ({ label, value }: { label: string; value?: string | number }) =>
    value === undefined || value === null || value === "" ? null : (
      <Box display="flex" justifyContent="space-between" gap={1}>
        <Typography variant="caption" sx={{ opacity: 0.7 }}>
          {label}
        </Typography>
        <Typography variant="caption" fontWeight={500}>
          {String(value)}
        </Typography>
      </Box>
    );

  const PillRow = ({ items }: { items?: (string | undefined)[] }) =>
    !items || items.filter(Boolean).length === 0 ? null : (
      <Box display="flex" gap={0.5} flexWrap="wrap">
        {items.filter(Boolean).map((x, i) => (
          <Chip key={i} size="small" label={x} variant="outlined" />
        ))}
      </Box>
    );

  const hasPluginsInfo =
    libsLabeled.length > 0 ||
    templatesLabeled.length > 0 ||
    promptsLabeled.length > 0 ||
    modelName ||
    latencyMs ||
    typeof usedTemperature === "number" ||
    searchPolicy;

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

                      {/* Hover indicators (assistant only) */}
                      {isAssistant && hasPluginsInfo && (
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
                          {pluginIndicators.map((ind) => (
                            <Tooltip key={ind.key} title={`${ind.label}${ind.enabled ? " enabled" : " disabled"}`}>
                              <Box
                                sx={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: 0.5,
                                  px: 0.75,
                                  py: 0.25,
                                  borderRadius: 1,
                                  border: `1px solid ${theme.palette.divider}`,
                                  opacity: ind.enabled ? 0.9 : 0.35,
                                }}
                              >
                                {ind.icon}
                                <Typography variant="caption" sx={{ lineHeight: 1 }}>
                                  {ind.label}
                                </Typography>
                              </Box>
                            </Tooltip>
                          ))}

                          {/* Info popover */}
                          <Box
                            onMouseEnter={(e) => openInsights(e.currentTarget as HTMLElement)}
                            onMouseLeave={closeInsights}
                            sx={{ display: "inline-flex" }}
                          >
                            <Tooltip title="Message insights" placement="top">
                              <IconButton size="small" sx={{ ml: 0.5 }} aria-label="message-insights">
                                <InfoOutlinedIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>

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
                                    <Box display="flex" gap={1}>
                                      <SectionRow label="In" value={inTokens} />
                                      <SectionRow label="Out" value={outTokens} />
                                    </Box>
                                    <Box display="flex" gap={1}>
                                      <SectionRow label="Latency" value={latencyMs ? `${latencyMs} ms` : undefined} />
                                      <SectionRow label="Search" value={searchPolicy} />
                                      <SectionRow
                                        label="Temp"
                                        value={typeof usedTemperature === "number" ? usedTemperature : undefined}
                                      />
                                    </Box>

                                    {(libsLabeled.length || templatesLabeled.length || promptsLabeled.length) ? (
                                      <Divider flexItem />
                                    ) : null}

                                    {hasCurrentOnly && (
                                      <Typography variant="caption" sx={{ opacity: 0.7 }}>
                                        current settings (not snapshot)
                                      </Typography>
                                    )}

                                    {libsLabeled.length ? (
                                      <>
                                        <Typography variant="overline" sx={{ opacity: 0.7 }}>
                                          Libraries
                                        </Typography>
                                        <PillRow items={libsLabeled} />
                                      </>
                                    ) : null}

                                    {templatesLabeled.length ? (
                                      <>
                                        <Typography variant="overline" sx={{ opacity: 0.7 }}>
                                          Templates
                                        </Typography>
                                        <PillRow items={templatesLabeled} />
                                      </>
                                    ) : null}

                                    {promptsLabeled.length ? (
                                      <>
                                        <Typography variant="overline" sx={{ opacity: 0.7 }}>
                                          Prompts
                                        </Typography>
                                        <PillRow items={promptsLabeled} />
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

                  {/* Main content: ALWAYS markdown */}
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
