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

// - Dedicated, distraction-free log workspace.
// - Reuses shared DateRangeControls + LogConsoleTile.
// - Keeps URL-routable so on-calls can share a link.

import { useMemo, useState, useEffect } from "react";
import { Box } from "@mui/material";
import dayjs, { Dayjs } from "dayjs";
import { alignDateRangeToPrecision, getPrecisionForRange, TimePrecision } from "../components/monitoring/timeAxis";
import { LogConsoleTile } from "../components/monitoring/LogConsoleTile";


export default function Logs() {
  const now = dayjs();
  const [startDate] = useState<Dayjs>(now.subtract(2, "hours"));
  const [endDate] = useState<Dayjs>(now);

  const precision: TimePrecision = useMemo(
    () => getPrecisionForRange(startDate.toDate(), endDate.toDate()),
    [startDate, endDate],
  );
  const [alignedStartIso, alignedEndIso] = useMemo(
    () => alignDateRangeToPrecision(startDate, endDate, precision),
    [startDate, endDate, precision],
  );

  useEffect(() => {
    // noop, but kept to mirror MonitoringOverview style
  }, []);

  return (
    <Box flexDirection="column" gap={1} p={2}
    sx={{
        height: "100vh",            // full viewport
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",         // ← important: trap scroll inside children
        p: 2,
        gap: 1,
      }}
    >
      <LogConsoleTile
        start={new Date(alignedStartIso)}
        end={new Date(alignedEndIso)}
        height={560}
        defaultService="knowledge-flow"
        devTail={false}
      />
    </Box>
  );
}
