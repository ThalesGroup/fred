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

import ClearIcon from "@mui/icons-material/Clear";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Box,
  Chip,
  IconButton,
  InputAdornment,
  MenuItem,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
} from "@mui/material";
import { t } from "i18next";
import { SimpleTooltip } from "../../../shared/ui/tooltips/Tooltips";
import { Level, LEVELS, SERVICE_OPTIONS, ServiceId } from "./logType";

const H = 24;
const FS = "0.7rem";

const levelColor: Record<Level, "default" | "success" | "info" | "warning" | "error"> = {
  DEBUG: "default",
  INFO: "info",
  WARNING: "warning",
  ERROR: "error",
  CRITICAL: "error",
};

function LvlChip({ lvl }: { lvl: Level }) {
  return (
    <Chip
      size="small"
      variant="outlined"
      color={levelColor[lvl]}
      label={lvl}
      sx={{
        height: 16,
        "& .MuiChip-label": { px: 0.5, py: 0, fontSize: FS, fontWeight: 600, lineHeight: 1 },
      }}
    />
  );
}

const fieldSx = {
  "& .MuiOutlinedInput-root": { height: H, fontSize: FS },
  "& .MuiInputBase-input": { py: "0 !important", px: "8px !important", fontSize: FS },
  "& .MuiOutlinedInput-notchedOutline legend": { display: "none" },
  "& .MuiOutlinedInput-notchedOutline": { top: 0 },
};

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
    <Stack direction="row" gap={0.75} alignItems="center" flexWrap="wrap">
      {/* Min level */}
      <Select
        size="small"
        value={minLevel}
        onChange={(e) => setMinLevel(e.target.value as Level)}
        displayEmpty
        renderValue={(val) => (
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <LvlChip lvl={val as Level} />
            <Box component="span" sx={{ fontSize: FS }}>{val as string}</Box>
          </Box>
        )}
        sx={{ height: H, minWidth: 120, fontSize: FS, ...fieldSx }}
        MenuProps={{
          PaperProps: {
            sx: { "& .MuiMenuItem-root": { minHeight: H, py: 0, fontSize: FS } },
          },
        }}
      >
        {LEVELS.map((l) => (
          <MenuItem key={l} value={l} sx={{ gap: 0.75, fontSize: FS }}>
            <LvlChip lvl={l} />
            <Box component="span" sx={{ fontSize: FS }}>{l}</Box>
          </MenuItem>
        ))}
      </Select>

      {/* Service toggle */}
      <ToggleButtonGroup
        size="small"
        color="primary"
        exclusive
        value={service}
        onChange={(_, v) => v && setService(v as ServiceId)}
        sx={{
          "& .MuiToggleButton-root": {
            height: H,
            px: 1,
            py: 0,
            fontSize: FS,
            textTransform: "none",
            lineHeight: 1,
          },
        }}
      >
        {SERVICE_OPTIONS.map((opt) => (
          <ToggleButton key={opt.id} value={opt.id}>
            {opt.label}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      {/* Logger filter */}
      <TextField
        size="small"
        variant="outlined"
        placeholder={t("logs.file")}
        value={loggerLike}
        onChange={(e) => setLoggerLike(e.target.value)}
        sx={{ minWidth: 150, ...fieldSx }}
        slotProps={{
          input: {
            endAdornment: loggerLike ? (
              <InputAdornment position="end">
                <IconButton size="small" onClick={() => setLoggerLike("")} sx={{ p: 0.25 }}>
                  <ClearIcon sx={{ fontSize: 14 }} />
                </IconButton>
              </InputAdornment>
            ) : null,
          },
        }}
      />

      {/* Message filter */}
      <TextField
        size="small"
        variant="outlined"
        placeholder={t("logs.content")}
        value={textLike}
        onChange={(e) => setTextLike(e.target.value)}
        sx={{ minWidth: 200, ...fieldSx }}
        slotProps={{
          input: {
            endAdornment: textLike ? (
              <InputAdornment position="end">
                <IconButton size="small" onClick={() => setTextLike("")} sx={{ p: 0.25 }}>
                  <ClearIcon sx={{ fontSize: 14 }} />
                </IconButton>
              </InputAdornment>
            ) : null,
          },
        }}
      />

      {/* Refresh */}
      <SimpleTooltip title="Refresh now">
        <IconButton
          size="small"
          onClick={onRefresh}
          sx={{
            p: 0,
            height: H,
            width: H,
            border: (t) => `1px solid ${t.palette.divider}`,
            borderRadius: (t) => `${t.shape.borderRadius}px`,
          }}
        >
          <RefreshIcon sx={{ fontSize: 14 }} />
        </IconButton>
      </SimpleTooltip>
    </Stack>
  );
}
