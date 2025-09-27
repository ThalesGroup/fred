// LogConsoleTile.tsx (simplified, robust)
// Purpose (Fred):
// - Presentational + fetch-on-props-change.
// - Parent owns time (incl. "Live"); tile never polls on its own.

import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, Stack, Divider } from "@mui/material";

import {
  LogEventDto,
  LogQuery,
  useQueryLogsKnowledgeFlowV1LogsQueryPostMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useQueryLogsAgenticV1LogsQueryPostMutation } from "../../../slices/agentic/agenticOpenApi";

import { LogControls } from "./LogControls";
import type { ServiceId } from "./logType";
import { LogRow } from "./LogRow";

type Level = LogEventDto["level"];
const MAX_EVENTS = 1000;
const BOTTOM_STICKY_THRESHOLD_PX = 60;

const MemoizedLogRow = memo(LogRow);

function useDebounced<T>(value: T, delay = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setV(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return v;
}

function useLogApis(service: ServiceId) {
  const [postQueryKF, queryStateKF] = useQueryLogsKnowledgeFlowV1LogsQueryPostMutation();
  const [postQueryAB, queryStateAB] = useQueryLogsAgenticV1LogsQueryPostMutation();
  const postQuery = service === "knowledge-flow" ? postQueryKF : postQueryAB;
  const queryState = service === "knowledge-flow" ? queryStateKF : queryStateAB;
  return { postQuery, queryState };
}

export function LogConsoleTile({
  start,
  end,                         // ← now REQUIRED
  height = 260,
  defaultService = "knowledge-flow",
  fillParent = true,
}: {
  start: Date;
  end: Date;                   // ← no "until now" here; parent always passes a value
  height?: number;
  defaultService?: string;
  devTail?: boolean;
  fillParent?: boolean;
}) {
  // ---- UI filter state ----
  const [minLevel, setMinLevel] = useState<Level>("INFO");
  const [service, setService] = useState<ServiceId>(defaultService as ServiceId);
  const [loggerLike, setLoggerLike] = useState("");
  const [textLike, setTextLike] = useState("");
  const dLoggerLike = useDebounced(loggerLike, 350);
  const dTextLike = useDebounced(textLike, 350);

  // ---- API ----
  const { postQuery, queryState } = useLogApis(service);

  // ---- Sticky scroll-to-bottom ----
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
    updateAnchored();
    return () => el.removeEventListener("scroll", onScroll);
  }, [updateAnchored]);

  // ---- Build query body ----
  const body: LogQuery = useMemo(
    () => ({
      since: start.toISOString(),
      until: end.toISOString(),
      limit: 500,
      order: "desc",
      filters: {
        level_at_least: minLevel,
        service: service || undefined,
        logger_like: dLoggerLike || undefined,
        text_like: dTextLike || undefined,
      },
    }),
    [start, end, minLevel, service, dLoggerLike, dTextLike],
  );

  const fetchQuery = useCallback(() => {
    postQuery({ logQuery: body }).catch(() => {});
  }, [postQuery, body]);

  // ← Single mechanism: refetch whenever inputs (body) change
  useEffect(() => {
    fetchQuery();
  }, [fetchQuery]);

  // ---- Normalize results (ASC) + cap ----
  const events: LogEventDto[] = useMemo(() => {
    const src = queryState.data?.events ?? [];
    const asc = src.slice().sort((a, b) => a.ts - b.ts);
    return asc.length > MAX_EVENTS ? asc.slice(asc.length - MAX_EVENTS) : asc;
  }, [queryState.data]);

  // ---- Stick to bottom on new data if user is near bottom ----
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (userAnchoredBottom) el.scrollTop = el.scrollHeight;
  }, [events, userAnchoredBottom]);

  return (
    <Stack
      gap={1}
      sx={{
        display: "flex",
        flexDirection: "column",
        height: fillParent ? "100%" : undefined,
        minHeight: 0,
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
          // Fred: filters live here; parent owns time window
          minLevel={minLevel}
          setMinLevel={setMinLevel}
          service={service}
          setService={setService}
          loggerLike={loggerLike}
          setLoggerLike={setLoggerLike}
          textLike={textLike}
          setTextLike={setTextLike}
          onRefresh={fetchQuery}   // manual refresh remains available
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
          scrollbarGutter: "stable",
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
