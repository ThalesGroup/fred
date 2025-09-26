// Copyright Thales 2025
//
// Purpose (Fred):
// - Lightweight "Kibana-lite" console for recent logs.
// - Uses the *structured* /logs/query for filters and the *file tail* for raw dev tails.
// - Obeys the page's global date range (start/end) but offers an "Auto-refresh" for recent windows.
// - Frameless by design; host it inside <FramelessTile> like other minis.
//
// How it fits Fred:
// - Same data flow as KPI tiles: parent owns time range; tile is presentational + fetch logic.
// - Uses RTK OpenAPI hooks you already generated: useQueryLogs... + useTailLogsFile...
// - Minimal UI plumbing: level floor, service filter, logger contains, text contains.

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Stack, IconButton, Tooltip, Divider, Chip, useTheme } from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";

import {
  LogEventDto,
  LogQuery,
  useQueryLogsKnowledgeFlowV1LogsQueryPostMutation,
  useTailLogsFileKnowledgeFlowV1LogsTailGetQuery,
} from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import dayjs from "dayjs";
import { LogControls } from "./LogControls";
import { useQueryLogsAgenticV1LogsQueryPostMutation } from "../../slices/agentic/agenticOpenApi";

import type { ServiceId } from "./logType";
type Level = LogEventDto["level"];
const levelColor: Record<Level, "default" | "success" | "info" | "warning" | "error"> = {
  DEBUG: "default",
  INFO: "info",
  WARNING: "warning",
  ERROR: "error",
  CRITICAL: "error",
};
const MAX_EVENTS = 1000;
const BOTTOM_STICKY_THRESHOLD_PX = 60; // "near bottom" tolerance

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

function useAutoRefresh(enabled: boolean, everyMs: number, fn: () => void) {
  const saved = useRef(fn);
  useEffect(() => {
    saved.current = fn;
  }, [fn]);
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => saved.current(), everyMs);
    return () => clearInterval(id);
  }, [enabled, everyMs]);
}

// Simple pretty-date that matches your KPI ticks
const fmtTs = (ts: number) => dayjs(ts).format("YYYY-MM-DD HH:mm:ss");

const MemoizedLogRow = memo(function LogRow({ e }: { e: LogEventDto }) {
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
        <IconButton size="small" onClick={copy} sx={{ p: 0.25 }}>
          <ContentCopyIcon fontSize="inherit" />
        </IconButton>
      </Tooltip>
    </Stack>
  );
});

function useDebounced<T>(value: T, delay = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return v;
}


function useLogApis(service: ServiceId, useTail: boolean) {
  // --- KNOWLEDGE FLOW (KF) ---
  const [postQueryKF, queryStateKF] = useQueryLogsKnowledgeFlowV1LogsQueryPostMutation();
  const { data: tailDataKF, refetch: refetchTailKF } = useTailLogsFileKnowledgeFlowV1LogsTailGetQuery(
    { service: "knowledge-flow", bytesBack: 100000 },
    { skip: service !== "knowledge-flow" || !useTail },
  );

  // --- AGENTIC BACKEND (AB) ---
  const [postQueryAB, queryStateAB] = useQueryLogsAgenticV1LogsQueryPostMutation();
  const { data: tailDataAB, refetch: refetchTailAB } = useTailLogsFileKnowledgeFlowV1LogsTailGetQuery(
    { service: "agentic", bytesBack: 100000 },
    { skip: service !== "agentic" || !useTail },
  );

  // Return the appropriate functions/data based on the current service
  const postQuery = service === "knowledge-flow" ? postQueryKF : postQueryAB;
  const queryState = service === "knowledge-flow" ? queryStateKF : queryStateAB;
  const tailData = service === "knowledge-flow" ? tailDataKF : tailDataAB;
  const refetchTail = service === "knowledge-flow" ? refetchTailKF : refetchTailAB;

  return { postQuery, queryState, tailData, refetchTail };
}


export function LogConsoleTile({
  start,
  end,
  height = 260,
  defaultService = "knowledge-flow",
  devTail = false, // if true, show the file tail mode by default (nice in dev)
  fillParent = true,
}: {
  start: Date;
  end?: Date; // if undefined it means until "now"
  height?: number;
  defaultService?: string;
  devTail?: boolean;
  fillParent?: boolean;
}) {
  // ---- UI state (filters) ----
  const [minLevel, setMinLevel] = useState<Level>("INFO");
  const [service, setService] = useState<ServiceId>(defaultService as ServiceId);
  const [loggerLike, setLoggerLike] = useState<string>("");
  const [textLike, setTextLike] = useState<string>("");
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [useTail, setUseTail] = useState<boolean>(devTail);
  const dLoggerLike = useDebounced(loggerLike, 350);
  const dTextLike = useDebounced(textLike, 350);
  // ---- API hooks ----
  const { postQuery, queryState, tailData, refetchTail } = useLogApis(service, useTail);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [userAnchoredBottom, setUserAnchoredBottom] = useState(true);

  const updateAnchored = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.clientHeight - el.scrollTop;
    setUserAnchoredBottom(distance < BOTTOM_STICKY_THRESHOLD_PX);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => updateAnchored();
    el.addEventListener("scroll", onScroll, { passive: true });
    // initialize
    updateAnchored();
    return () => el.removeEventListener("scroll", onScroll);
  }, [updateAnchored]);

  // Construct query body that the backend expects
  const body: LogQuery = useMemo(
    () => ({
      since: start.toISOString(),
      ...(end ? { until: end.toISOString() } : {}),
      limit: 500,
      order: "desc",
      filters: {
        level_at_least: minLevel,
        service: service || undefined,
        logger_like: dLoggerLike || undefined,
        text_like: dTextLike || undefined,
      },
    }),
    // FIX 1: Change dependencies to use the DEBOUNCED values
    [start, end, minLevel, service, dLoggerLike, dTextLike],
  );

  const fetchQuery = useCallback(() => {
    if (useTail) {
      refetchTail();
    } else {
      postQuery({ logQuery: body }).catch(() => {});
    }
  }, [useTail, refetchTail, postQuery, body]);

  // COMBINED EFFECT: Runs when the query parameters (body) change or when useTail changes.
  // The 'body' depends on start, end, minLevel, service, dLoggerLike, and dTextLike.
  // This ensures:
  // 1. **Immediate Fetch:** when start/end change (because fetchQuery changes).
  // 2. **Debounced Fetch:** when minLevel/service/dLoggerLike/dTextLike change (because fetchQuery changes, but dLoggerLike/dTextLike only change after a 350ms delay).
  useEffect(() => {
    fetchQuery();

    // Dependencies are the function itself (which only changes when its dependencies change)
  }, [fetchQuery]);

  // Keep useAutoRefresh, it correctly uses the fetchQuery function
  useAutoRefresh(autoRefresh, 5000, fetchQuery);
  // Normalize results
  // normalize results — always return ASC (oldest -> newest), then cap
  const events: LogEventDto[] = useMemo(() => {
    let out: LogEventDto[] = [];
    if (useTail) {
      const lines = tailData?.lines ?? [];
      const parsed: LogEventDto[] = [];
      for (const ln of lines) {
        try {
          const obj = JSON.parse(ln);
          parsed.push({
            ts: Number(obj.ts ?? 0),
            level: obj.level,
            logger: obj.logger,
            file: obj.file,
            line: Number(obj.line ?? 0),
            msg: obj.msg,
            service: obj.service,
            extra: obj.extra ?? null,
          });
        } catch {}
      }
      out = parsed.sort((a, b) => a.ts - b.ts); // ASC
    } else {
      out = (queryState.data?.events ?? []).slice().sort((a, b) => a.ts - b.ts); // ASC
    }
    // keep only the last N
    if (out.length > MAX_EVENTS) out = out.slice(out.length - MAX_EVENTS);
    return out;
  }, [useTail, tailData, queryState.data]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (userAnchoredBottom) {
      // jump to bottom (smooth for small deltas)
      el.scrollTop = el.scrollHeight;
    }
  }, [events, userAnchoredBottom]);

  return (
    <Stack
      gap={1}
      sx={{
        display: "flex",
        flexDirection: "column",
        height: fillParent ? "100%" : undefined, // ← fills parent
        minHeight: 0, // ← allow child to shrink inside flex
      }}
    >
      {/* Controls row */}
      <Stack
        direction="row"
        gap={1}
        alignItems="center"
        flexWrap="wrap"
        sx={{ "& .MuiInputBase-root": { height: 34 } }}
      >
        <LogControls
          minLevel={minLevel}
          setMinLevel={(v) => setMinLevel(v)}
          service={service}
          setService={(v) => setService(v)}
          loggerLike={loggerLike}
          setLoggerLike={setLoggerLike}
          textLike={textLike}
          setTextLike={setTextLike}
          autoRefresh={autoRefresh}
          setAutoRefresh={setAutoRefresh}
          useTail={useTail}
          setUseTail={setUseTail}
          onRefresh={fetchQuery}
        />
      </Stack>
      <Divider />

      {/* Scroll area */}
      <Box
        ref={scrollRef}
        sx={{
          flex: fillParent ? 1 : undefined,
          height: fillParent ? undefined : height,
          minHeight: 0,
          overflowY: "auto",
          borderRadius: 1,
          border: (t) => `1px solid ${t.palette.divider}`,
          bgcolor: "transparent",
          scrollbarGutter: "stable", // prevent layout shift on scrollbar appearance
        }}
      >
        {events.length === 0 ? (
          <Box sx={{ p: 1, fontSize: (t) => t.typography.caption.fontSize, color: "text.secondary" }}>
            No logs in this window.
          </Box>
        ) : (
          <Stack divider={<Divider />} sx={{ py: 0.25 }}>
            {events.map((e, i) => (
              <MemoizedLogRow key={`${e.ts}-${e.file}-${e.line}-${i}`} e={e} />
            ))}
          </Stack>
        )}
      </Box>
    </Stack>
  );
}
