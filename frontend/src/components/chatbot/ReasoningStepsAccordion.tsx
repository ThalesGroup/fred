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

export default function ReasoningTraceAccordion({
  steps,
  isOpenByDefault = true,
}: Props) {
  const ordered = useMemo(
    () =>
      steps
        .filter((m) => TRACE_CHANNELS.includes(m.channel))
        .sort((a, b) => a.rank - b.rank),
    [steps]
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
                const preview = textPreview(m, 160);
                const ex = getExtras(m);

                const chipChannel = formatChannel(m.channel);
                const chipNode = ex?.node ? String(ex.node).replaceAll("_", " ") : undefined;
                const chipTask = !chipNode && ex?.task ? String(ex.task) : undefined;

                return (
                  <React.Fragment key={key}>
                    <ReasoningStepBadge
                      message={m}
                      indexLabel={idx + 1}
                      numberColWidth={numberColWidth}
                      onClick={() => openDetails(m)}
                      primaryText={preview || chipNode || chipTask || chipChannel}
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

      {/* Right drawer with Monaco JSON viewer */}
      <Drawer
        anchor="right"
        open={open}
        onClose={closeDetails}
        slotProps={{
          paper: { sx: { width: { xs: "100%", sm: 640 }, display: "flex" } },
        }}
      >
        {/* Minimal header */}
        <Box sx={{ p: 2, borderBottom: (t) => `1px solid ${t.palette.divider}` }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="h6" sx={{ flex: 1, minWidth: 0 }}>
              {selected
                ? [
                    formatChannel(selected.channel),
                    getExtras(selected)?.node?.toString().replaceAll("_", " ") ||
                      getExtras(selected)?.task,
                  ]
                    .filter(Boolean)
                    .join(" · ")
                : "Details"}
            </Typography>
            <Tooltip title="Close">
              <IconButton onClick={closeDetails} size="small">
                <ExpandMoreIcon sx={{ transform: "rotate(90deg)" }} />
              </IconButton>
            </Tooltip>
          </Stack>
        </Box>

        {/* Monaco fills available space */}
        <Box sx={{ flex: 1, minHeight: 0 }}>
          <Editor
            height="100%"
            defaultLanguage="json"
            value={safeStringify(selected ?? {}, 2)}
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
