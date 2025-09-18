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

import { Box, ButtonGroup } from "@mui/material";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { DateTimePicker } from "@mui/x-date-pickers/DateTimePicker";
import dayjs, { Dayjs } from "dayjs";
import { useTranslation } from "react-i18next";
import QuickRangeButton, { QuickRangeType } from "./QuickRangeButton";

type Props = {
  startDate: Dayjs;
  endDate: Dayjs;
  setStartDate: (d: Dayjs) => void;
  setEndDate: (d: Dayjs) => void;
};

const CONTROL_H = 32; // keep all controls the same height
const BTN_FONT_SIZE = 13;
const TF_MIN_W = 160;

function isRangeSelected(type: QuickRangeType, startDate: Dayjs, endDate: Dayjs): boolean {
  const today = dayjs();
  const graceMs = 5 * 60 * 1000;
  switch (type) {
    case "today":
      return startDate.isSame(today.startOf("day")) && endDate.isSame(today.endOf("day"));
    case "yesterday":
      return (
        startDate.isSame(today.subtract(1, "day").startOf("day")) &&
        endDate.isSame(today.subtract(1, "day").endOf("day"))
      );
    case "thisWeek":
      return startDate.isSame(today.startOf("week")) && endDate.isSame(today.endOf("week"));
    case "thisMonth":
      return startDate.isSame(today.startOf("month")) && endDate.isSame(today.endOf("month"));
    case "thisYear":
      return startDate.isSame(today.startOf("year")) && endDate.isSame(today.endOf("year"));
    case "last12h": {
      const s = today.subtract(12, "hour");
      const e = today;
      return Math.abs(startDate.diff(s)) < graceMs && Math.abs(endDate.diff(e)) < graceMs;
    }
    case "last24h": {
      const s = today.subtract(24, "hour");
      const e = today;
      return Math.abs(startDate.diff(s)) < graceMs && Math.abs(endDate.diff(e)) < graceMs;
    }
    case "last7d": {
      const s = today.subtract(7, "day");
      const e = today;
      return Math.abs(startDate.diff(s)) < graceMs && Math.abs(endDate.diff(e)) < graceMs;
    }
    case "last30d": {
      const s = today.subtract(30, "day");
      const e = today;
      return Math.abs(startDate.diff(s)) < graceMs && Math.abs(endDate.diff(e)) < graceMs;
    }
    default:
      return false;
  }
}

function setSelectedRange(type: QuickRangeType, setStartDate: (d: Dayjs) => void, setEndDate: (d: Dayjs) => void) {
  const now = dayjs();
  const ranges: Record<QuickRangeType, [Dayjs, Dayjs]> = {
    today: [now.startOf("day"), now.endOf("day")],
    yesterday: [now.subtract(1, "day").startOf("day"), now.subtract(1, "day").endOf("day")],
    thisWeek: [now.startOf("week"), now.endOf("week")],
    thisMonth: [now.startOf("month"), now.endOf("month")],
    thisYear: [now.startOf("year"), now.endOf("year")],
    last24h: [now.subtract(24, "hour").startOf("hour"), now.endOf("hour")],
    last12h: [now.subtract(12, "hour").startOf("hour"), now.endOf("hour")],
    last7d: [now.subtract(7, "day").startOf("day"), now.endOf("day")],
    last30d: [now.subtract(30, "day").startOf("day"), now.endOf("day")],
  };
  const [start, end] = ranges[type];
  setStartDate(start);
  setEndDate(end);
}

export default function DateRangeControls({ startDate, endDate, setStartDate, setEndDate }: Props) {
  const { t } = useTranslation();

  // Compact text field styles to match ButtonGroup height
  const textFieldSx = {
    minWidth: TF_MIN_W,
    "& .MuiOutlinedInput-root": { height: CONTROL_H },
    "& .MuiInputBase-input": { paddingTop: 0, paddingBottom: 0, fontSize: BTN_FONT_SIZE },
    "& .MuiInputAdornment-root": {
      "& .MuiIconButton-root": { padding: 0.25 }, // shrink picker icon button
    },
    // keep label from overlapping when compact
    "& .MuiInputLabel-root": { fontSize: BTN_FONT_SIZE },
  };

  return (
    <Box display="flex" flexWrap="wrap" alignItems="center" justifyContent="space-between" gap={1}>
      <ButtonGroup
        variant="outlined"
        size="small"
        sx={{
          flexWrap: "wrap",
          // Make all buttons the same height + font size
          "& .MuiButtonBase-root": { height: CONTROL_H, fontSize: BTN_FONT_SIZE, paddingInline: 1 },
        }}
      >
        {(
          [
            "last12h",
            "last24h",
            "last7d",
            "last30d",
            "today",
            "yesterday",
            "thisWeek",
            "thisMonth",
            "thisYear",
          ] as QuickRangeType[]
        ).map((type) => (
          <QuickRangeButton
            key={type}
            isSel={isRangeSelected(type, startDate, endDate)}
            onClick={() => setSelectedRange(type, setStartDate, setEndDate)}
            label={t(`metrics.range.${type}`)}
          />
        ))}
      </ButtonGroup>

      <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="fr">
        <Box display="flex" gap={1} alignItems="center">
          <DateTimePicker
            label={t("metrics.from")}
            value={startDate}
            onChange={(v) => v && setStartDate(v)}
            format="YYYY-MM-DD HH:mm" // shorter to keep width tight
            slotProps={{
              textField: { size: "small", margin: "dense", sx: textFieldSx },
              openPickerButton: { size: "small" },
            }}
            maxDateTime={endDate}
          />
          <DateTimePicker
            label={t("metrics.to")}
            value={endDate}
            onChange={(v) => v && setEndDate(v)}
            format="YYYY-MM-DD HH:mm"
            slotProps={{
              textField: { size: "small", margin: "dense", sx: textFieldSx },
              openPickerButton: { size: "small" },
            }}
            minDateTime={startDate}
          />
        </Box>
      </LocalizationProvider>
    </Box>
  );
}
