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

//
// Purpose (Fred):
// - Lightweight "Kibana-lite" console for recent logs.
// - Obeys the page's global date range (start/end) but offers an "Auto-refresh" for recent windows.
// - Frameless by design; host it inside <FramelessTile> like other minis.
//
// How it fits Fred:
// - Same data flow as KPI tiles: parent owns time range; tile is presentational + fetch logic.
// - Uses RTK OpenAPI hooks you already generated: useQueryLogs... + useTailLogsFile...
// - Minimal UI plumbing: level floor, service filter, logger contains, text contains.

import { useCallback, useState } from "react";
import { Box, Stack, IconButton, Tooltip, Chip, useTheme } from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";

import { LogEventDto } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import dayjs from "dayjs";

type Level = LogEventDto["level"];
const levelColor: Record<Level, "default" | "success" | "info" | "warning" | "error"> = {
  DEBUG: "default",
  INFO: "info",
  WARNING: "warning",
  ERROR: "error",
  CRITICAL: "error",
};

function LvlChip({ lvl }: { lvl: Level }) {
  // compact, outlined, consistent with theme colors
  return (
    <Chip
      size="small"
      variant="outlined"
      color={levelColor[lvl]}
      label={lvl}
      sx={{
        height: 18,
        "& .MuiChip-label": { px: 0.5, py: 0, fontSize: (t) => t.typography.caption.fontSize, fontWeight: 600 },
      }}
    />
  );
}

const fmtTs = (ts: number) => dayjs(ts).format("YYYY-MM-DD HH:mm:ss");

export function LogRow({ e }: { e: LogEventDto }) {
  const theme = useTheme();
  const [open, setOpen] = useState(false);
  const copy = useCallback(() => navigator.clipboard.writeText(e.msg), [e.msg]);

  // prefer theme monospace if you’ve defined one; else fall back
  const monoFamily =
    // @ts-ignore — allow custom typography extension if you added one
    theme.typography?.fontFamilyMono ||
    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace";

  const caption = theme.typography.caption;

  return (
    <Stack
      direction="row"
      gap={0.75}
      alignItems="flex-start"
      sx={{
        py: 0.25,
        px: 0.75,
        "&:hover": { backgroundColor: theme.palette.action.hover },
      }}
    >
      {/* timestamp */}
      <Box
        sx={{
          minWidth: 150,
          color: "text.secondary",
          fontFamily: monoFamily,
          fontSize: caption.fontSize,
          lineHeight: 1.4,
        }}
      >
        {fmtTs(e.ts * 1000)}
      </Box>

      {/* level */}
      <Box sx={{ minWidth: 64, display: "flex", alignItems: "center" }}>
        <LvlChip lvl={e.level} />
      </Box>

      {/* origin */}
      <Box
        sx={{
          minWidth: 150,
          color: "text.secondary",
          fontSize: caption.fontSize,
          lineHeight: 1.4,
          whiteSpace: "nowrap",
          textOverflow: "ellipsis",
          overflow: "hidden",
        }}
        title={`${e.file}:${e.line}`}
      >
        {e.file}:{e.line}
      </Box>

      {/* message + extra */}
      <Box
        sx={{
          flex: 1,
          fontSize: caption.fontSize,
          lineHeight: 1.35,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {e.msg}
        {e.extra && (
          <Box sx={{ mt: 0.25 }}>
            <Tooltip title={open ? "Hide extra" : "Show extra"}>
              <IconButton size="small" onClick={() => setOpen((v) => !v)} sx={{ p: 0.25 }}>
                {open ? <ExpandLessIcon fontSize="inherit" /> : <ExpandMoreIcon fontSize="inherit" />}
              </IconButton>
            </Tooltip>
            {open && (
              <Box
                component="pre"
                sx={{
                  m: 0,
                  mt: 0.25,
                  p: 0.75,
                  bgcolor: "background.default",
                  borderRadius: 1,
                  border: (t) => `1px solid ${t.palette.divider}`,
                  fontSize: caption.fontSize,
                  lineHeight: 1.35,
                  overflowX: "auto",
                }}
              >
                {JSON.stringify(e.extra, null, 2)}
              </Box>
            )}
          </Box>
        )}
      </Box>

      {/* copy */}
      <Tooltip title="Copy message">
        <IconButton size="small" onClick={copy} sx={{ p: 0.25, color: "text.secondary" }}>
          <ContentCopyIcon fontSize="inherit" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
}
