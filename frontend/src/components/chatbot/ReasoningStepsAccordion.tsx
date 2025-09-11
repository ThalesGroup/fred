import React, { useMemo, useState } from "react";
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Box,
  Drawer,
  IconButton,
  List,
  Stack,
  Tooltip,
  Typography,
  Divider,
  useTheme,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import Editor from "@monaco-editor/react";

import { AgenticFlow, Channel, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras, textPreview } from "./ChatBotUtils";
import ReasoningStepBadge from "./ReasoningStepBadge";

type Props = {
  steps: ChatMessage[];
  isOpenByDefault?: boolean;
  resolveAgent: (m: ChatMessage) => AgenticFlow | undefined;
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

function summarizeToolResult(m: ChatMessage): string | undefined {
  const p = m.parts.find((p) => p.type === "tool_result") as
    | Extract<ChatMessage["parts"][number], { type: "tool_result" }>
    | undefined;
  if (!p) return undefined;

  // content might already be a stringified JSON
  let data: any = p.content;
  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch {
      /* keep raw string */
    }
  }

  // Prefer a compact, human hint
  if (data && typeof data === "object") {
    if (data.error) return `error: ${asPlainText(data.error, 80)}`;
    if (Array.isArray(data.rows)) return `rows: ${data.rows.length}`;
    if (data.sql_query) return asPlainText(data.sql_query, 100);
  }
  return asPlainText(p.content, 60);
}

export default function ReasoningTraceAccordion({ steps, isOpenByDefault = false }: Props) {
  const theme = useTheme();
  const ordered = useMemo(
    () => steps.filter((m) => TRACE_CHANNELS.includes(m.channel)).sort((a, b) => a.rank - b.rank),
    [steps],
  );

  const digitCount = useMemo(() => String(Math.max(1, ordered.length)).length, [ordered.length]);
  const numberColWidth = `${Math.max(2, digitCount)}ch`;

  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<ChatMessage | undefined>(undefined);

  const openDetails = (m: ChatMessage) => {
    setSelected(m);
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
              {ordered.map((m, idx) => {
                const key = `${m.session_id}-${m.exchange_id}-${m.rank}`;

                const previewRaw = textPreview(m);
                const previewText = asPlainText(previewRaw); // prevents [object Object]

                const ex = getExtras(m);

                // Only accept strings for node/task; otherwise ignore to avoid [object Object]
                const nodeRaw = ex?.node;
                const taskRaw = ex?.task;
                const chipNode = typeof nodeRaw === "string" ? nodeRaw.replaceAll("_", " ") : undefined;
                const chipTask = !chipNode && typeof taskRaw === "string" ? taskRaw : undefined;
                const chipChannel = formatChannel(m.channel);

                // Prefer tool_result summary when available; else preview/node/task/channel
                const primary = summarizeToolResult(m) || previewText || chipNode || chipTask || chipChannel;

                // Optional tiny debug to catch unexpected objects in extras/preview
                if (
                  (nodeRaw && typeof nodeRaw !== "string") ||
                  (taskRaw && typeof taskRaw !== "string") ||
                  (previewRaw && typeof previewRaw !== "string")
                ) {
                  // eslint-disable-next-line no-console
                  console.warn("Trace value was non-string → stringified", {
                    rank: m.rank,
                    channel: m.channel,
                    nodeType: typeof nodeRaw,
                    taskType: typeof taskRaw,
                    previewType: typeof previewRaw,
                  });
                }

                return (
                  <React.Fragment key={key}>
                    <ReasoningStepBadge
                      message={m}
                      indexLabel={idx + 1}
                      numberColWidth={numberColWidth}
                      onClick={() => openDetails(m)}
                      primaryText={primary}
                      chipChannel={chipChannel}
                      chipNode={chipNode}
                      chipTask={chipTask}
                      toolName={toolName(m)}
                      resultOk={okFlag(m)}
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
            sx: (t) => ({
              width: { xs: "100%", sm: 640 },
              display: "flex",
              // Fred rationale:
              // Ensure paper picks up dark surface even if a global override is missed.
              background: t.palette.surfaces.soft,
              // For a RIGHT drawer, the divider should be on the LEFT:
              borderLeft: `1px solid ${t.palette.divider}`,
              borderRight: "none",
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
              {selected
                ? [
                    formatChannel(selected.channel),
                    getExtras(selected)?.node?.toString().replaceAll("_", " ") || getExtras(selected)?.task,
                  ]
                    .filter(Boolean)
                    .join(" · ")
                : "Details"}
            </Typography>
            <Tooltip title="Close">
              <IconButton onClick={closeDetails} size="small" sx={{ color: "inherit" }}>
                <ExpandMoreIcon sx={{ transform: "rotate(90deg)" }} />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>

        {/* Editor container should inherit a dark-ish surface */}
        <Box sx={(t) => ({ flex: 1, minHeight: 0, background: t.palette.surfaces.soft })}>
          <Editor
            height="100%"
            defaultLanguage="json"
            value={safeStringify(selected ?? {}, 2)}
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
