// TraceList.tsx
import { Box, List, ListItemButton, ListItemIcon, ListItemText, Chip, Stack, Tooltip } from "@mui/material";
import { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import { getExtras } from "./ChatBotUtils";
import { textPreview } from "./ReasoningTrace";

const TRACE_CHANNELS = ["plan","thought","observation","tool_call","tool_result","system_note","error"] as const;

const channelIcon = (ch: ChatMessage["channel"]) => {
  switch (ch) {
    case "plan": return "🗺️";
    case "thought": return "🧠";
    case "observation": return "👀";
    case "tool_call": return "🛠️";
    case "tool_result": return "✅";
    case "system_note": return "⚙️";
    case "error": return "❌";
    default: return "•";
  }
};

export type TraceListProps = {
  steps: ChatMessage[];                // flat, already filtered/sorted
  onOpenDetails: (m: ChatMessage) => void;
};

export default function TraceList({ steps, onOpenDetails }: TraceListProps) {
  if (!steps.length) return null;

  return (
    <Box sx={{ border: (t) => `1px solid ${t.palette.divider}`, borderRadius: 1 }}>
      <List dense disablePadding>
        {steps.map((m) => {
          const key = `${m.session_id}-${m.exchange_id}-${m.rank}`;
          const extras = getExtras(m);
          const preview = textPreview(m, 180);

          return (
            <ListItemButton key={key} onClick={() => onOpenDetails(m)} sx={{ py: 0.75 }}>
              <ListItemIcon sx={{ minWidth: 28, fontSize: 18 }}>
                {channelIcon(m.channel)}
              </ListItemIcon>
              <ListItemText
                primaryTypographyProps={{ variant: "body2", noWrap: true }}
                primary={preview}
                secondary={
                  <Stack direction="row" spacing={0.5} sx={{ mt: 0.25 }}>
                    {extras?.task && <Chip size="small" label={String(extras.task)} variant="outlined" />}
                    {extras?.node && <Chip size="small" label={String(extras.node)} variant="outlined" />}
                    {extras?.label && <Chip size="small" label={String(extras.label)} variant="outlined" />}
                  </Stack>
                }
              />
            </ListItemButton>
          );
        })}
      </List>
    </Box>
  );
}
