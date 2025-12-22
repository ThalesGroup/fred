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

// Purpose (Fred): One compact date-range header; behavior is driven by `quickRanges` config.
// Why: avoid two near-identical components (short vs. full); keep UI consistent.

import { Box, ButtonGroup } from "@mui/material";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { DateTimePicker } from "@mui/x-date-pickers/DateTimePicker";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import dayjs, { Dayjs } from "dayjs";
import { useTranslation } from "react-i18next";
import QuickRangeButton from "./QuickRangeButton";

export type QuickRangeId = string;

export type QuickRangeItem = {
  id: QuickRangeId;
  /** i18n key or literal; we’ll try i18n first then fallback to provided text */
  labelKey?: string;
  labelFallback: string;
  /** Compute [start,end] based on "now" */
  compute: (now: Dayjs) => [Dayjs, Dayjs];
};

type Props = {
  startDate: Dayjs;
  endDate: Dayjs;
  setStartDate: (d: Dayjs) => void;
  setEndDate: (d: Dayjs) => void;
  /** Rendered quick-range buttons; pass different arrays for short/full presets */
  quickRanges: QuickRangeItem[];
  /** Selected detection tolerance for “live-ish” windows (default 5min) */
  toleranceMs?: number;
  /** Optional: tell parent a quick range was picked (e.g., set Live=true) */
  onQuickRangePick?: () => void;
  /** Optional: minify date format per page constraints */
  dateFormat?: string; // default "YYYY-MM-DD HH:mm"
};

const CONTROL_H = 32;
const BTN_FONT_SIZE = 13;
const TF_MIN_W = 160;

export default function DateRangeControl({
  startDate,
  endDate,
  setStartDate,
  setEndDate,
  quickRanges,
  toleranceMs = 5 * 60 * 1000,
  onQuickRangePick,
  dateFormat = "YYYY-MM-DD HH:mm",
}: Props) {
  const { t, i18n } = useTranslation();
  const isSelected = (item: QuickRangeItem) => {
    const now = dayjs();
    const [s, e] = item.compute(now);
    return Math.abs(startDate.diff(s)) < toleranceMs && Math.abs(endDate.diff(e)) < toleranceMs;
  };

  const applyRange = (item: QuickRangeItem) => {
    const now = dayjs();
    const [s, e] = item.compute(now);
    setStartDate(s);
    setEndDate(e);
    onQuickRangePick?.();
  };

  const textFieldSx = {
    minWidth: TF_MIN_W,
    "& .MuiOutlinedInput-root": { height: CONTROL_H },
    "& .MuiInputBase-input": { paddingTop: 0, paddingBottom: 0, fontSize: BTN_FONT_SIZE },
    "& .MuiInputAdornment-root .MuiIconButton-root": { padding: 0.25 },
    "& .MuiInputLabel-root": { fontSize: BTN_FONT_SIZE },
  };

  return (
    <Box display="flex" flexWrap="wrap" alignItems="center" justifyContent="space-between" gap={1}>
      <ButtonGroup
        variant="outlined"
        size="small"
        sx={{
          flexWrap: "wrap",
          "& .MuiButtonBase-root": { height: CONTROL_H, fontSize: BTN_FONT_SIZE, paddingInline: 2 },
        }}
      >
        {quickRanges.map((qr) => (
          <QuickRangeButton
            key={qr.id}
            isSel={isSelected(qr)}
            onClick={() => applyRange(qr)}
            label={t(qr.labelKey ?? "", { defaultValue: qr.labelFallback }) as string}
          />
        ))}
      </ButtonGroup>

      <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale={i18n.language}>
        <Box display="flex" gap={1} alignItems="center">
          <DateTimePicker
            label={t("metrics.from")}
            value={startDate}
            onChange={(v) => v && setStartDate(v)}
            format={dateFormat}
            slotProps={{
              // MODIFICATION: Removed margin: "dense"
              textField: { size: "small", sx: textFieldSx },
              openPickerButton: { size: "small" },
            }}
            maxDateTime={endDate}
          />
          <DateTimePicker
            label={t("metrics.to")}
            value={endDate}
            onChange={(v) => v && setEndDate(v)}
            format={dateFormat}
            slotProps={{
              // MODIFICATION: Removed margin: "dense"
              textField: { size: "small", sx: textFieldSx },
              openPickerButton: { size: "small" },
            }}
            minDateTime={startDate}
          />
        </Box>
      </LocalizationProvider>
    </Box>
  );
}
