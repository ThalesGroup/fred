// ReasoningTrace.tsx — compact, icon-led trace (no MessageCard)
// Copyright Thales 2025
// Licensed under the Apache License, Version 2.0

import {
  Accordion, AccordionSummary, AccordionDetails,
  Box, Stack, Typography, Chip, Tooltip
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";

// Icons
import PsychologyAltOutlinedIcon from "@mui/icons-material/PsychologyAltOutlined";
import BuildCircleOutlinedIcon from "@mui/icons-material/BuildCircleOutlined";
import TaskAltOutlinedIcon from "@mui/icons-material/TaskAltOutlined";
import EventNoteOutlinedIcon from "@mui/icons-material/EventNoteOutlined";
import BugReportOutlinedIcon from "@mui/icons-material/BugReportOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import { AgenticFlow, ChatMessage } from "../../slices/agentic/agenticOpenApi";

type Props = {
  messages: ChatMessage[];                 // flat list of reasoning/tool messages for ONE exchange
  isOpenByDefault?: boolean;
  resolveAgent?: (msg: ChatMessage) => AgenticFlow | undefined;
  includeObservationsWithText?: boolean;   // default: false (keeps things clean)
};

const hasNonEmptyText = (m: ChatMessage) =>
  (m.parts ?? []).some(p => p.type === "text" && p.text && p.text.trim().length > 0);

const getExtras = (m: ChatMessage) => (m.metadata?.extras ?? {}) as Record<string, any>;

const iconForChannel = (ch: ChatMessage["channel"]) => {
  switch (ch) {
    case "plan":        return <EventNoteOutlinedIcon fontSize="small" />;
    case "thought":     return <PsychologyAltOutlinedIcon fontSize="small" />;
    case "observation": return <InfoOutlinedIcon fontSize="small" />;
    case "tool_call":   return <BuildCircleOutlinedIcon fontSize="small" />;
    case "tool_result": return <TaskAltOutlinedIcon fontSize="small" />;
    case "error":       return <BugReportOutlinedIcon fontSize="small" />;
    default:            return <InfoOutlinedIcon fontSize="small" />;
  }
};

function groupKey(_m: ChatMessage) {
  return "Agent trace"; // single accordion section
}

// Adjust these types if your SDK exports them
type Part =
  | ({ type: "text"; text: string } & Record<string, unknown>)
  | ({ type: "code"; code: string; language?: string } & Record<string, unknown>)
  | ({ type: "image_url"; url: string; alt?: string } & Record<string, unknown>)
  | ({ type: "tool_call"; name: string; args?: unknown } & Record<string, unknown>)
  | ({ type: "tool_result"; ok?: boolean; content?: string } & Record<string, unknown>);

const isTextPart = (p: Part): p is Extract<Part, { type: "text" }> => p.type === "text";
const isToolCallPart = (p: Part): p is Extract<Part, { type: "tool_call" }> => p.type === "tool_call";
const isToolResultPart = (p: Part): p is Extract<Part, { type: "tool_result" }> => p.type === "tool_result";

/** Safe truncate helper */
const ellipsize = (s: string, max: number) => (s.length > max ? `${s.slice(0, max)}…` : s);

export function textPreview(m: ChatMessage, max = 280) {
  const parts = (m.parts ?? []) as Part[];

  // Prefer concatenated text parts
  const txt = parts
    .filter(isTextPart)
    .map(p => (p.text ?? "").trim())
    .filter(Boolean)
    .join(" ");

  if (txt) return ellipsize(txt, max);

  // Tool call / result quick previews
  const p0 = parts[0];

  if (p0 && isToolCallPart(p0)) {
    const name = p0.name || "tool";
    const argsStr = p0.args !== undefined ? JSON.stringify(p0.args) : "";
    return `${name}(${ellipsize(argsStr, 120)})`;
  }

  if (p0 && isToolResultPart(p0)) {
    const ok = p0.ok;
    const content = p0.content ?? "";
    return `${ok === false ? "❌" : "✅"} ${ellipsize(content, 160)}`;
  }

  // Fallbacks by channel
  switch (m.channel) {
    case "plan": return "Plan";
    case "thought": return "Thought";
    case "observation": return "Observation";
    case "tool_call": return "Tool call";
    case "tool_result": return "Tool result";
    case "system_note": return "System note";
    case "error": return "Error";
    default: return m.channel;
  }
}


export default function ReasoningTrace({
  messages,
  isOpenByDefault = true,
  resolveAgent,
  includeObservationsWithText = false,
}: Props) {
  // 1) filter to the channels we care about
  const TRACE_CHANNELS = new Set([
    "plan","thought","observation","tool_call","tool_result","system_note","error"
  ]);

  const filtered = messages
    .filter(m => TRACE_CHANNELS.has(m.channel as any))
    .filter(m => m.channel !== "observation" || includeObservationsWithText ? true : hasNonEmptyText(m))
    .sort((a, b) => a.rank - b.rank);

  if (!filtered.length) return null;

  // 2) group by task/node/label
  const groups: Record<string, ChatMessage[]> = {};
  for (const m of filtered) {
    const k = groupKey(m);
    (groups[k] ||= []).push(m);
  }

  // 3) render
  return (
    <Stack spacing={1.25} sx={{ my: 1 }}>
      {Object.entries(groups).map(([label, items]) => {
        const first = items[0];
        const agent = resolveAgent?.(first);

        return (
          <Accordion key={label} defaultExpanded={isOpenByDefault} disableGutters>
            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                  {label}
                </Typography>
                {agent && (
                  <Chip size="small" label={agent.nickname} variant="outlined" />
                )}
                <Typography variant="caption" color="text.secondary">
                  {items.length} step{items.length === 1 ? "" : "s"}
                </Typography>
              </Stack>
            </AccordionSummary>
            <AccordionDetails>
              <Stack spacing={1}>
                {items.map((m) => (
                  <Box
                    key={`trace-${m.session_id}-${m.exchange_id}-${m.rank}`}
                    sx={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 1,
                      px: 1,
                      py: 0.5,
                      borderLeft: "2px solid",
                      borderColor: "divider",
                    }}
                  >
                    <Box sx={{ mt: "2px" }}>{iconForChannel(m.channel)}</Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                        {textPreview(m)}
                      </Typography>
                      {/* Small meta line (optional) */}
                      <TraceMeta m={m} />
                    </Box>
                  </Box>
                ))}
              </Stack>
            </AccordionDetails>
          </Accordion>
        );
      })}
    </Stack>
  );
}

function TraceMeta({ m }: { m: ChatMessage }) {
  const x = getExtras(m);
  if (!x?.task && !x?.node) return null;
  return (
    <Stack direction="row" spacing={1} sx={{ mt: 0.25 }}>
      {x.task && (
          <Chip size="small" label={String(x.task)} variant="outlined" />
      )}
      {x.node && (
          <Chip size="small" label={String(x.node)} variant="outlined" />
      )}
    </Stack>
  );
}
