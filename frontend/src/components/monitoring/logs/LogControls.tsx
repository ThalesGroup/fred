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

import ClearIcon from "@mui/icons-material/Clear";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Box,
  Chip,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";
import InputAdornment from "@mui/material/InputAdornment";
import { t } from "i18next";
import { SimpleTooltip } from "../../../shared/ui/tooltips/Tooltips";
import { Level, LEVELS, SERVICE_OPTIONS, ServiceId } from "./logType";

const CONTROL_HEIGHT = 32; // one height to rule them all

const levelColor: Record<Level, "default" | "success" | "info" | "warning" | "error"> = {
  DEBUG: "default",
  INFO: "info",
  WARNING: "warning",
  ERROR: "error",
  CRITICAL: "error",
};

// Simplified and refined LvlChip for better vertical fit
function LvlChip({ lvl }: { lvl: Level }) {
  return (
    <Chip
      size="small"
      variant="outlined"
      color={levelColor[lvl]}
      label={lvl}
      sx={{
        height: 20,
        "& .MuiChip-label": {
          px: 0.5,
          py: 0,
          fontSize: (t) => t.typography.caption.fontSize,
          fontWeight: 600,
          lineHeight: 1.1,
        },
      }}
    />
  );
}

export type LogControlsProps = {
  minLevel: Level;
  setMinLevel: React.Dispatch<React.SetStateAction<Level>>;

  service: ServiceId;
  setService: React.Dispatch<React.SetStateAction<ServiceId>>;

  loggerLike: string;
  setLoggerLike: React.Dispatch<React.SetStateAction<string>>;

  textLike: string;
  setTextLike: React.Dispatch<React.SetStateAction<string>>;

  onRefresh: () => void;
};

// Helper for consistent height and alignment on fields
const FIELD_WRAPPER_SX = {
  // Target the root of the input (the outline box)
  "& .MuiOutlinedInput-root": {
    height: CONTROL_HEIGHT,
    // Add display flex and align-items: center to ensure contents (text, adornment) are centered
    display: "flex",
    alignItems: "center",
  },
  // Target the actual text input area inside the box
  "& .MuiInputBase-input": {
    paddingTop: "0 !important", // Force remove any default vertical padding
    paddingBottom: "0 !important",
  },
  // FIX: Vertical alignment for the placeholder label when the input is empty (not shrinked)
  "& .MuiInputLabel-root:not(.MuiInputLabel-shrink)": {
    // Calculates vertical center: CONTROL_HEIGHT / 2 - (Label_FontSize / 2) - small adjustment
    // (36 / 2) - 12px = 6px down
    transform: `translate(14px, ${CONTROL_HEIGHT / 2 - 12}px) scale(1)`,
    // ensure label color matches text color when acting as placeholder
    color: (t) => t.palette.text.secondary,
  },
  // FIX: Align the label when it is shrinked (on focus/with value)
  "& .MuiInputLabel-shrink": {
    top: 0,
    transform: "translate(14px, -9px) scale(0.75)", // Adjusted position for small controls
  },
};

export function LogControls({
  minLevel,
  setMinLevel,
  service,
  setService,
  loggerLike,
  setLoggerLike,
  textLike,
  setTextLike,
  onRefresh,
}: LogControlsProps) {
  return (
    <>
      <Stack
        direction="row"
        gap={1}
        alignItems="center"
        flexWrap="wrap"
        sx={
          {
            // Removed the global InputLabel adjustment: "& .MuiInputLabel-root": { top: -6 },
            // The label alignment is now handled specifically in FIELD_WRAPPER_SX
          }
        }
      >
        {/* Min level (Select) - Uses FIELD_WRAPPER_SX */}
        <FormControl size="small" variant="outlined" sx={{ minWidth: 160, ...FIELD_WRAPPER_SX }}>
          <InputLabel id="lvl-lbl">Min level</InputLabel>
          <Select
            labelId="lvl-lbl"
            label="Min level"
            value={minLevel}
            onChange={(e) => setMinLevel(e.target.value as Level)}
            renderValue={(val) => (
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <LvlChip lvl={val as Level} />
                <Box component="span" sx={{ fontSize: (t) => t.typography.caption.fontSize }}>
                  {val as string}
                </Box>
              </Box>
            )}
            MenuProps={{
              PaperProps: {
                sx: {
                  "& .MuiMenuItem-root": { minHeight: CONTROL_HEIGHT, py: 0, display: "flex", alignItems: "center" },
                },
              },
            }}
          >
            {LEVELS.map((l) => (
              <MenuItem key={l} value={l} sx={{ gap: 0.75 }}>
                <LvlChip lvl={l} />
                <Box component="span" sx={{ fontSize: (t) => t.typography.caption.fontSize }}>
                  {l}
                </Box>
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {/* Service toggle — forced to the same height */}
        <ToggleButtonGroup
          size="small"
          color="primary"
          exclusive
          value={service}
          onChange={(_, v) => v && setService(v as ServiceId)}
          sx={{
            "& .MuiToggleButton-root": {
              height: CONTROL_HEIGHT,
              display: "flex",
              alignItems: "center",
              px: 1.25,
              py: 0,
              fontSize: (t) => t.typography.caption.fontSize,
            },
          }}
        >
          {SERVICE_OPTIONS.map((opt) => (
            <ToggleButton key={opt.id} value={opt.id}>
              {opt.label}
            </ToggleButton>
          ))}
        </ToggleButtonGroup>

        {/* Logger contains (TextField) - FIX: Label alignment handled by FIELD_WRAPPER_SX */}
        <TextField
          size="small"
          variant="outlined"
          label={t("logs.file")}
          value={loggerLike}
          onChange={(e) => setLoggerLike(e.target.value)}
          // Use FIELD_WRAPPER_SX for alignment consistency
          sx={{ minWidth: 200, ...FIELD_WRAPPER_SX }}
          slotProps={{
            input: {
              endAdornment: loggerLike ? (
                <InputAdornment position="end">
                  <IconButton
                    size="small"
                    edge="end"
                    aria-label="clear logger filter"
                    onClick={() => setLoggerLike("")}
                    sx={{ p: 0.5 }}
                  >
                    <ClearIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ) : null,
            },
          }}
        />

        {/* Text contains (TextField) - FIX: Label alignment handled by FIELD_WRAPPER_SX */}
        <TextField
          size="small"
          variant="outlined"
          label={t("logs.content")}
          value={textLike}
          onChange={(e) => setTextLike(e.target.value)}
          // Use FIELD_WRAPPER_SX for alignment consistency
          sx={{ minWidth: 240, ...FIELD_WRAPPER_SX }}
          slotProps={{
            input: {
              endAdornment: loggerLike ? (
                <InputAdornment position="end">
                  <IconButton
                    size="small"
                    edge="end"
                    aria-label="clear logger filter"
                    onClick={() => setLoggerLike("")}
                    sx={{ p: 0.5 }}
                  >
                    <ClearIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ) : null,
            },
          }}
        />

        <SimpleTooltip title="Refresh now">
          <IconButton
            size="small"
            onClick={onRefresh}
            sx={{
              p: 0,
              height: CONTROL_HEIGHT,
              width: CONTROL_HEIGHT, // square
              border: (t) => `1px solid ${t.palette.divider}`,
              borderRadius: (t) => t.shape.borderRadius,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <RefreshIcon fontSize="small" />
          </IconButton>
        </SimpleTooltip>
      </Stack>

      <Divider />
    </>
  );
}
