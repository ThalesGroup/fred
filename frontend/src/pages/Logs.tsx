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

// Purpose (Fred): Rolling or fixed log workspace with a compact date-range header.
// Notes:
// - Parent owns time window; tile stays presentational.
// - Live mode: sliding window → end=undefined (backend reads "until now").
// - Fixed mode: frozen start/end from pickers (shareable investigations).
import { useMemo, useState, useEffect } from "react";
import { Box, FormControlLabel, Switch } from "@mui/material";
import dayjs, { Dayjs } from "dayjs";
import { alignDateRangeToPrecision, getPrecisionForRange, TimePrecision } from "../components/monitoring/timeAxis";
import { LogConsoleTile } from "../components/monitoring/logs/LogConsoleTile";
import { SHORT_QUICK_RANGES } from "../components/monitoring/common/dateRangeControlPresets";
import DateRangeControl from "../components/monitoring/common/DateRangeControl";
import { TopBar } from "../common/TopBar";
import { useTranslation } from "react-i18next";

export default function Logs() {
  const { t } = useTranslation();
  const [live, setLive] = useState(true);
  const [startDate, setStartDate] = useState<Dayjs>(() => dayjs().subtract(2, "hours"));
  const [endDate, setEndDate] = useState<Dayjs>(() => dayjs());

  // 🔁 Tick only when live → drives sliding window
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => setTick((t) => t + 1), 5_000);
    return () => clearInterval(id);
  }, [live]);

  // 🕒 Keep the duration the user chose (default 2h) for sliding math
  const durationMs = useMemo(() => Math.max(endDate.diff(startDate), 60_000), [startDate, endDate]);

  // 🔧 Compute raw window (only the parent knows "live" vs "fixed")
  const now = useMemo(() => dayjs(), [tick]);
  const rawEnd: Dayjs = live ? now : endDate; // true "now" in live mode
  const rawStart: Dayjs = live ? rawEnd.subtract(durationMs, "millisecond") : startDate;

  // 📏 Align only the start to bucket boundaries (do NOT snap the end)
  const precision: TimePrecision = useMemo(
    () => getPrecisionForRange(rawStart.toDate(), rawEnd.toDate()),
    [rawStart, rawEnd],
  );
  const [alignedStartIso /* , alignedEndIso */] = useMemo(() => {
    const [alignedStart /*, alignedEnd*/] = alignDateRangeToPrecision(rawStart, rawEnd, precision);
    return [alignedStart /*, alignedEnd*/];
  }, [rawStart, rawEnd, precision]);

  return (
    <>
      <TopBar title={t("logs.title")} description={t("logs.description")} />
      <Box
        flexDirection="column"
        gap={1}
        p={2}
        sx={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          p: 2,
          gap: 1,
        }}
      >
        {/* Header: date range + Live toggle */}
        <Box display="flex" alignItems="center" justifyContent="space-between" gap={1} flexWrap="wrap">
          <DateRangeControl
            startDate={startDate}
            endDate={endDate}
            setStartDate={setStartDate}
            setEndDate={(d) => {
              setEndDate(d);
              setLive(false); // picker → fixed window
            }}
            quickRanges={SHORT_QUICK_RANGES}
            toleranceMs={90_000} // tighter match for short windows
            onQuickRangePick={() => setLive(false)} // quick range → live sliding
          />
          <FormControlLabel
            control={<Switch checked={live} onChange={(_, v) => setLive(v)} />}
            label={t("logs.live")}
          />
        </Box>

        <LogConsoleTile
          start={new Date(alignedStartIso)}
          end={rawEnd.toDate()}
          height={560}
          defaultService="knowledge-flow"
          devTail={false}
          fillParent={true}
        />
      </Box>
    </>
  );
}
