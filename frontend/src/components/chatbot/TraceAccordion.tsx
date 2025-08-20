// ReasoningTraceAccordion.tsx
// Clean, collapsible trace with minimal visuals + Monaco JSON drawer
import React, { useMemo, useState } from "react";
import {
  Accordion, AccordionSummary, AccordionDetails,
  Box, Drawer, IconButton, List, ListItemButton, ListItemText,
  Stack, Tooltip, Typography, Divider
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import Editor from "@monaco-editor/react";
import { AgenticFlow, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras, textPreview } from "./ChatBotUtils";

type Props = {
  steps: ChatMessage[];
  isOpenByDefault?: boolean;
  resolveAgent: (m: ChatMessage) => AgenticFlow | undefined;
};

const TRACE_CHANNELS = ["plan","thought","observation","tool_call","tool_result","system_note","error"] as const;

function severityIcon(m: ChatMessage) {
  if (m.channel === "error") return <ErrorOutlineIcon fontSize="small" color="error" />;
  if (m.channel === "tool_result") {
    const part: any = m.parts?.find(p => p.type === "tool_result") || {};
    if (part.ok === false) return <ErrorOutlineIcon fontSize="small" color="error" />;
    return <CheckCircleOutlineIcon fontSize="small" color="disabled" />;
  }
  return null;
}

function stepLabel(m: ChatMessage) {
  const ex = getExtras(m);
  if (ex?.node) return String(ex.node).replaceAll("_", " ");
  if (ex?.task) return String(ex.task);
  switch (m.channel) {
    case "plan": return "planning";
    case "thought": return "reasoning";
    case "observation": return "observation";
    case "tool_call": return "tool call";
    case "tool_result": return "tool result";
    case "system_note": return "system";
    case "error": return "error";
    default: return m.channel;
  }
}

function safeStringify(v: unknown, space = 2) {
  try { return JSON.stringify(v, null, space); } catch { return String(v); }
}

export default function ReasoningTraceAccordion({
  steps,
  isOpenByDefault = true, // kept to preserve prop shape; not used in the drawer
}: Props) {
  const ordered = useMemo(
    () => [...steps]
      .filter(m => TRACE_CHANNELS.includes(m.channel as any))
      .sort((a,b)=>a.rank-b.rank),
    [steps]
  );

  const digitCount = useMemo(() => String(Math.max(1, ordered.length)).length, [ordered.length]);
  const numberColWidth = `${Math.max(2, digitCount)}ch`;

  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState<ChatMessage | undefined>(undefined);

  const openDetails = (m: ChatMessage) => { setSelected(m); setOpen(true); };
  const closeDetails = () => { setOpen(false); setTimeout(() => setSelected(undefined), 200); };

  if (!ordered.length) return null;

  return (
    <>
      <Accordion defaultExpanded={isOpenByDefault} disableGutters sx={{ borderRadius: 1 }}>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Stack direction="row" spacing={1} alignItems="center">
            <InfoOutlinedIcon fontSize="small" color="disabled" />
            <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>Trace</Typography>
            <Typography variant="caption" color="text.secondary">
              {ordered.length} step{ordered.length === 1 ? "" : "s"}
            </Typography>
          </Stack>
        </AccordionSummary>

        <AccordionDetails>
          <Box sx={{ border: t => `1px solid ${t.palette.divider}`, borderRadius: 1, overflowX: "hidden" }}>
            <List dense disablePadding>
              {ordered.map((m, idx) => {
                const key = `${m.session_id}-${m.exchange_id}-${m.rank}`;
                const label = stepLabel(m);
                const preview = textPreview(m, 160);
                const icon = severityIcon(m);

                return (
                  <React.Fragment key={key}>
                    <ListItemButton
                      onClick={() => openDetails(m)}
                      sx={{
                        py: 0.75,
                        display: "grid",
                        gridTemplateColumns: `${numberColWidth} 20px 1fr`,
                        columnGap: 1,
                        alignItems: "center",
                      }}
                    >
                      {/* Number rail */}
                      <Box
                        sx={{
                          textAlign: "right",
                          pr: 1,
                          color: "text.disabled",
                          fontVariantNumeric: "tabular-nums",
                          whiteSpace: "nowrap",
                          fontFamily:
                            "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                        }}
                      >
                        {idx + 1}
                      </Box>

                      {/* Icon */}
                      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
                        {icon}
                      </Box>

                      {/* Text */}
                      <ListItemText
                        primaryTypographyProps={{ variant: "body2", noWrap: true }}
                        secondaryTypographyProps={{ variant: "caption", color: "text.secondary", noWrap: true }}
                        primary={preview || label}
                        secondary={preview ? label : undefined}
                      />
                    </ListItemButton>
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
        PaperProps={{ sx: { width: { xs: "100%", sm: 640 }, display: "flex" } }}
      >
        {/* Minimal header */}
        <Box sx={{ p: 2, borderBottom: (t) => `1px solid ${t.palette.divider}` }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Typography variant="h6" sx={{ flex: 1, minWidth: 0 }}>
              {selected ? stepLabel(selected) : "Details"}
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
