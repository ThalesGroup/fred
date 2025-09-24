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

import { Dialog, DialogTitle, DialogContent, DialogActions, Button, Typography, Stack } from "@mui/material";
import { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import MessageCard from "./MessageCard";
import { AnyAgent } from "../../common/agent";

function safeStringify(v: unknown, space = 2) {
  try {
    return JSON.stringify(v, null, space);
  } catch {
    return String(v);
  }
}

function ToolCall({ m }: { m: ChatMessage }) {
  const part = (m.parts?.find((p) => p.type === "tool_call") as any) || {};
  return (
    <Stack spacing={0.75}>
      <Typography variant="subtitle2">Tool call</Typography>
      <Typography variant="body2">
        <strong>name:</strong> {part?.name ?? "tool"}
      </Typography>
      <Typography variant="body2" component="pre" sx={{ whiteSpace: "pre-wrap", m: 0 }}>
        {safeStringify(part?.args ?? {}, 2)}
      </Typography>
    </Stack>
  );
}

function ToolResult({ m }: { m: ChatMessage }) {
  const part = (m.parts?.find((p) => p.type === "tool_result") as any) || {};
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
  resolveAgent,
}: {
  open: boolean;
  step?: ChatMessage;
  onClose: () => void;
  resolveAgent: (m: ChatMessage) => AnyAgent | undefined;
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
          <MessageCard message={step} agent={agent!} side="left" enableCopy />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} variant="contained">
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}
