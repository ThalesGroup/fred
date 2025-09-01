// TraceDetailsDialog.tsx
import {
  Dialog, DialogTitle, DialogContent, DialogActions,
  Button, Typography, Stack
} from "@mui/material";
import { AgenticFlow, ChatMessage } from "../../slices/agentic/agenticOpenApi";
import MessageCard from "./MessageCard";

function safeStringify(v: unknown, space = 2) {
  try { return JSON.stringify(v, null, space); } catch { return String(v); }
}

function ToolCall({ m }: { m: ChatMessage }) {
  const part = (m.parts?.find(p => p.type === "tool_call") as any) || {};
  return (
    <Stack spacing={0.75}>
      <Typography variant="subtitle2">Tool call</Typography>
      <Typography variant="body2"><strong>name:</strong> {part?.name ?? "tool"}</Typography>
      <Typography variant="body2" component="pre" sx={{ whiteSpace: "pre-wrap", m: 0 }}>
        {safeStringify(part?.args ?? {}, 2)}
      </Typography>
    </Stack>
  );
}

function ToolResult({ m }: { m: ChatMessage }) {
  const part = (m.parts?.find(p => p.type === "tool_result") as any) || {};
  const ok = part?.ok;
  return (
    <Stack spacing={0.75}>
      <Typography variant="subtitle2">Tool result {ok === false ? "❌" : "✅"}</Typography>
      {part?.content && (
        <Typography variant="body2" component="pre" sx={{ whiteSpace: "pre-wrap", m: 0 }}>
          {String(part.content)}
        </Typography>
      )}
      {typeof part?.latency_ms === "number" && (
        <Typography variant="caption" color="text.secondary">
          latency: {part.latency_ms} ms
        </Typography>
      )}
    </Stack>
  );
}

export default function TraceDetailsDialog({
  open,
  step,
  onClose,
  resolveAgent
}: {
  open: boolean;
  step?: ChatMessage;
  onClose: () => void;
  resolveAgent: (m: ChatMessage) => AgenticFlow | undefined;
}) {
  if (!step) return null;

  const title = `${step.channel}`;
  const agent = resolveAgent(step);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent dividers>
        {step.channel === "tool_call" && <ToolCall m={step} />}
        {step.channel === "tool_result" && <ToolResult m={step} />}
        {step.channel !== "tool_call" && step.channel !== "tool_result" && (
          <MessageCard
            message={step}
            agenticFlow={agent!}
            currentAgenticFlow={agent!}
            side="left"
            enableCopy
          />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} variant="contained">Close</Button>
      </DialogActions>
    </Dialog>
  );
}
