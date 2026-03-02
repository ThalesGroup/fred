// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// You may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import Editor from "@monaco-editor/react";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  Stack,
  Typography,
  useTheme,
} from "@mui/material";
import React, { useMemo, useState } from "react";

import { AnyAgent } from "../../common/agent";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";
import { Channel, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras, isToolCall, isToolResult, textPreview, toolId } from "./ChatBotUtils";
import ReasoningStepBadge from "./ReasoningStepBadge";

type Props = {
  steps: ChatMessage[];
  isOpenByDefault?: boolean;
  resolveAgent: (m: ChatMessage) => AnyAgent | undefined;
};

// pretty-print channel names without duplicating enums
const formatChannel = (c: Channel) => c.replaceAll("_", " ");

// channels to show in the trace (type-safe subset of Channel)
const TRACE_CHANNELS: Channel[] = [
  "plan",
  "thought",
  "observation",
  "tool_call",
  "tool_result",
  "system_note",
  "error",
];

type TraceEntry = { kind: "solo"; message: ChatMessage } | { kind: "combo"; call: ChatMessage; result?: ChatMessage };

// helpers kept local (can be moved to a shared traceUtils.ts if reused elsewhere)
const toolName = (m: ChatMessage): string | undefined => {
  const p = m.parts.find((p) => p.type === "tool_call") as
    | Extract<ChatMessage["parts"][number], { type: "tool_call" }>
    | undefined;
  return p?.name;
};

const okFlag = (m: ChatMessage): boolean | undefined => {
  const p = m.parts.find((p) => p.type === "tool_result") as
    | Extract<ChatMessage["parts"][number], { type: "tool_result" }>
    | undefined;
  return p?.ok ?? undefined;
};

function safeStringify(v: unknown, space = 2) {
  try {
    return JSON.stringify(v, null, space);
  } catch {
    return String(v);
  }
}

function asPlainText(v: unknown, max = 120): string | undefined {
  if (v == null) return undefined;
  if (typeof v === "string") return v.length > max ? v.slice(0, max) + "…" : v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  // Object/Array → JSON (bounded)
  const s = safeStringify(v, 2);
  return s.length > max ? s.slice(0, max) + "…" : s;
}

function formatLatencyMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms / 1000)}s`;
}

function extrasSummary(m: ChatMessage): string | undefined {
  const ex = getExtras(m);
  const summary = ex?.summary;
  if (typeof summary !== "string") return undefined;
  const trimmed = summary.trim();
  return trimmed || undefined;
}

function summarizeToolResultCompact(m: ChatMessage): string | undefined {
  const explicitSummary = extrasSummary(m);
  if (explicitSummary) return explicitSummary;

  const p = m.parts.find((part) => part.type === "tool_result") as
    | Extract<ChatMessage["parts"][number], { type: "tool_result" }>
    | undefined;
  if (!p) return undefined;

  const sourceCount = Array.isArray(m.metadata?.sources) ? m.metadata.sources.length : 0;
  const latencyMs =
    typeof p.latency_ms === "number"
      ? p.latency_ms
      : typeof m.metadata?.latency_ms === "number"
        ? m.metadata.latency_ms
        : undefined;

  if (sourceCount > 0 && typeof latencyMs === "number") {
    return `${sourceCount} result${sourceCount > 1 ? "s" : ""} in ${formatLatencyMs(latencyMs)}`;
  }
  if (sourceCount > 0) {
    return `${sourceCount} result${sourceCount > 1 ? "s" : ""}`;
  }
  if (typeof latencyMs === "number") {
    return `${p.ok === false ? "Failed" : "Completed"} in ${formatLatencyMs(latencyMs)}`;
  }
  return p.ok === false ? "Failed" : "Completed";
}

export default function ReasoningTraceAccordion({ steps, isOpenByDefault = false }: Props) {
  const theme = useTheme();
  const ordered = useMemo(() => {
    const filtered = steps.filter((m) => TRACE_CHANNELS.includes(m.channel)).sort((a, b) => a.rank - b.rank);
    const entries: TraceEntry[] = [];
    const pendingCombos = new Map<string, { kind: "combo"; call: ChatMessage; result?: ChatMessage }>();

    for (const msg of filtered) {
      if (isToolCall(msg)) {
        const combo: TraceEntry = { kind: "combo", call: msg, result: undefined };
        entries.push(combo);
        const id = toolId(msg);
        if (id) pendingCombos.set(id, combo);
        continue;
      }

      if (isToolResult(msg)) {
        const id = toolId(msg);
        const combo = id ? pendingCombos.get(id) : undefined;
        if (combo && combo.kind === "combo") {
          combo.result = msg;
          pendingCombos.delete(id);
        } else {
          entries.push({ kind: "solo", message: msg });
        }
        continue;
      }

      entries.push({ kind: "solo", message: msg });
    }

    return entries;
  }, [steps]);

  const digitCount = useMemo(() => String(Math.max(1, ordered.length)).length, [ordered.length]);
  const numberColWidth = `${Math.max(2, digitCount)}ch`;

  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<TraceEntry | undefined>(undefined);

  const openDetails = (entry: TraceEntry) => {
    setSelected(entry);
    setOpen(true);
  };
  const closeDetails = () => {
    setOpen(false);
    setTimeout(() => setSelected(undefined), 200);
  };

  if (!ordered.length) return null;

  return (
    <>
      <Accordion defaultExpanded={isOpenByDefault} disableGutters sx={{ borderRadius: 1 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Stack direction="row" spacing={1} alignItems="center">
            <InfoOutlinedIcon fontSize="small" color="disabled" />
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
              Trace
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {ordered.length} step{ordered.length === 1 ? "" : "s"}
            </Typography>
          </Stack>
        </AccordionSummary>

        <AccordionDetails>
          <Box sx={{ border: (t) => `1px solid ${t.palette.divider}`, borderRadius: 1, overflowX: "hidden" }}>
            <List dense disablePadding>
              {ordered.map((entry, idx) => {
                const key =
                  entry.kind === "combo"
                    ? `combo-${entry.call.session_id}-${entry.call.exchange_id}-${entry.call.rank}`
                    : `solo-${entry.message.session_id}-${entry.message.exchange_id}-${entry.message.rank}`;

                const message = entry.kind === "combo" ? entry.call : entry.message;

                const previewRaw = textPreview(message);
                const previewText = asPlainText(previewRaw); // prevents [object Object]

                const ex = getExtras(message);

                // Only accept strings for node/task; otherwise ignore to avoid [object Object]
                const nodeRaw = ex?.node;
                const taskRaw = ex?.task;
                const chipNode = typeof nodeRaw === "string" ? nodeRaw.replaceAll("_", " ") : undefined;
                const chipTask = !chipNode && typeof taskRaw === "string" ? taskRaw : undefined;
                const chipChannel = formatChannel(message.channel);

                const primarySolo =
                  message.channel === "tool_result"
                    ? summarizeToolResultCompact(message) || chipChannel
                    : previewText || chipNode || chipTask || chipChannel;

                const resultSummary =
                  entry.kind === "combo" && entry.result ? summarizeToolResultCompact(entry.result) : undefined;
                const pendingResult = entry.kind === "combo" && !entry.result ? "waiting for result…" : undefined;
                const primary =
                  entry.kind === "combo"
                    ? resultSummary || pendingResult || chipChannel
                    : primarySolo;
                const primaryTooltip = undefined;

                const secondary = entry.kind === "combo" ? undefined : undefined;
                const secondaryTooltip = undefined;
                const resultOk =
                  entry.kind === "combo" && entry.result
                    ? okFlag(entry.result)
                    : entry.kind === "combo"
                      ? undefined
                      : okFlag(message);

                const collapsedStatus =
                  entry.kind === "combo"
                    ? entry.result
                      ? typeof resultOk === "boolean"
                        ? resultOk
                          ? "ok"
                          : "error"
                        : undefined
                      : "pending"
                    : message.channel === "tool_result"
                      ? typeof resultOk === "boolean"
                        ? resultOk
                          ? "ok"
                          : "error"
                        : undefined
                      : undefined;

                return (
                  <React.Fragment key={key}>
                    <ReasoningStepBadge
                      message={message}
                      indexLabel={idx + 1}
                      numberColWidth={numberColWidth}
                      onToggleDetails={() => openDetails(entry)}
                      statusLabel={collapsedStatus}
                      primaryText={primary}
                      primaryTooltip={primaryTooltip}
                      secondaryText={secondary}
                      secondaryTooltip={secondaryTooltip}
                      chipChannel={chipChannel}
                      chipNode={chipNode}
                      chipTask={chipTask}
                      toolName={toolName(entry.kind === "combo" ? entry.call : message)}
                      resultOk={resultOk}
                    />
                    {idx < ordered.length - 1 && <Divider component="li" />}
                  </React.Fragment>
                );
              })}
            </List>
          </Box>
        </AccordionDetails>
      </Accordion>

      <Drawer
        anchor="right"
        open={open}
        onClose={closeDetails}
        slotProps={{
          paper: {
            sx: () => ({
              width: { xs: "100%", sm: 640 },
              display: "flex",
            }),
          },
        }}
      >
        {/* Minimal header */}
        <Box
          sx={(t) => ({
            p: 2,
            borderBottom: `1px solid ${t.palette.divider}`,
            background: t.palette.background.paper, // solid readable surface
            color: t.palette.text.primary, // ensure text color is primary
          })}
        >
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="subtitle1" sx={{ flex: 1, minWidth: 0, fontWeight: 600, color: "inherit" }} noWrap>
              {(() => {
                if (!selected) return "Details";
                if (selected.kind === "combo") {
                  const extras = getExtras(selected.call);
                  const parts = [
                    formatChannel(selected.call.channel),
                    toolName(selected.call),
                    extras?.node?.toString().replaceAll("_", " ") || extras?.task,
                  ]
                    .filter(Boolean)
                    .map(String);
                  if (selected.result) {
                    parts.push(formatChannel(selected.result.channel));
                  }
                  return parts.join(" · ");
                }
                const extras = getExtras(selected.message);
                return [
                  formatChannel(selected.message.channel),
                  extras?.node?.toString().replaceAll("_", " ") || extras?.task,
                ]
                  .filter(Boolean)
                  .join(" · ");
              })()}
            </Typography>
            <SimpleTooltip title="Close">
              <IconButton onClick={closeDetails} size="small" sx={{ color: "inherit" }}>
                <ExpandMoreIcon sx={{ transform: "rotate(90deg)" }} />
              </IconButton>
            </SimpleTooltip>
          </Stack>
        </Box>

        {/* Editor container should inherit a dark-ish surface */}
        <Box sx={(t) => ({ flex: 1, minHeight: 0, background: t.palette.background.default })}>
          <Editor
            height="100%"
            defaultLanguage="json"
            value={safeStringify(
              selected
                ? selected.kind === "combo"
                  ? { tool_call: selected.call, tool_result: selected.result ?? null }
                  : selected.message
                : {},
              2,
            )}
            // Fred rationale:
            // Monaco defaults to light ("vs"). Switch with the MUI palette.
            theme={theme.palette.mode === "dark" ? "vs-dark" : "vs"}
            options={{
              readOnly: true,
              wordWrap: "on",
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              lineNumbers: "on",
              automaticLayout: true,
            }}
          />
        </Box>
      </Drawer>
    </>
  );
}
