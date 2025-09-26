// Logs.tsx
// Purpose (Fred): rolling 2h log workspace tied to "now", NOT a frozen interval.
// Why: "last-2h" must keep sliding; snapping the end down clips the most recent minutes.

import { useMemo, useState, useEffect } from "react";
import { Box } from "@mui/material";
import dayjs, { Dayjs } from "dayjs";
import { alignDateRangeToPrecision, getPrecisionForRange, TimePrecision } from "../components/monitoring/timeAxis";
import { LogConsoleTile } from "../components/monitoring/LogConsoleTile";

export default function Logs() {
  // 🔁 Tick drives a rolling window; we recompute "now" every few seconds.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 5_000); // 5s feels live without spamming
    return () => clearInterval(id);
  }, []);

  // ⏱️ Recompute window on each tick → sliding "last 2h"
  const now = useMemo(() => dayjs(), [tick]);
  const rawStart: Dayjs = useMemo(() => now.subtract(2, "hours"), [now]);
  const rawEnd: Dayjs = now; // IMPORTANT: true "now", not aligned/snap-down

  // 📏 Precision is still useful for charts, but we only align the *start*.
  const precision: TimePrecision = useMemo(
    () => getPrecisionForRange(rawStart.toDate(), rawEnd.toDate()),
    [rawStart, rawEnd],
  );

  // ⚠️ Do NOT align the end; that’s what produced 12:54:59.999Z.
  const [alignedStartIso /* , alignedEndIso */] = useMemo(
    () => {
      const [alignedStart /*, alignedEnd*/] = alignDateRangeToPrecision(rawStart, rawEnd, precision);
      return [alignedStart /*, alignedEnd*/];
    },
    [rawStart, rawEnd, precision],
  );

  return (
    <Box
      flexDirection="column"
      gap={1}
      p={2}
      sx={{
        height: "100vh",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        p: 2,
        gap: 1,
      }}
    >
      <LogConsoleTile
        // ✅ Start aligned to bucket boundaries (cheap histograms, stable pages)
        start={new Date(alignedStartIso)}
        // ✅ End is true "now" → backend can omit lte (open-ended) or use lt(now+1ms)
        // end={rawEnd.toDate()}
        height={560}
        defaultService="knowledge-flow"
        devTail={false}
        // (Optional) If your tile supports it, you can pass end={undefined} to mean "until now"
        // and let the backend omit the lte filter.
      />
    </Box>
  );
}
