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

import SellOutlinedIcon from "@mui/icons-material/SellOutlined";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Tooltip,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

export function KeywordsPreview({
  keywords,
  docTitle,
  maxPeek = 8,
  onChipClick,
  sx,
}: {
  keywords?: string[] | null;
  docTitle?: string;
  maxPeek?: number;
  onChipClick?: (kw: string) => void;
  sx?: any;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  // Deduplicate, trim, preserve order
  const list = useMemo(() => {
    const src = (keywords ?? []).map((k) => (k ?? "").trim()).filter((k) => k.length > 0);
    const seen = new Set<string>();
    const out: string[] = [];
    for (const k of src) if (!seen.has(k)) seen.add(k), out.push(k);
    return out;
  }, [keywords]);

  if (list.length === 0) return null;

  const peek = list.slice(0, maxPeek);
  const tooltipText = peek.join(" · ") + (list.length > maxPeek ? " · …" : "");

  // Group by first letter; non A–Z -> '#'
  const groups = useMemo(() => {
    const normalize = (s: string) =>
      s
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toUpperCase();
    const out: Record<string, string[]> = {};
    for (const kw of list) {
      const letter = /^[A-Z]/.test(normalize(kw)) ? normalize(kw)[0] : "#";
      (out[letter] ||= []).push(kw);
    }
    for (const k of Object.keys(out)) out[k].sort((a, b) => a.localeCompare(b));
    return Object.fromEntries(Object.entries(out).sort(([a], [b]) => a.localeCompare(b)));
  }, [list]);

  return (
    <>
      {/* Icon-only trigger with SURFACE tooltip */}
      <Tooltip
        arrow
        placement="top"
        slotProps={{
          tooltip: {
            sx: (_) => ({
              maxWidth: 520,
            }),
          },
        }}
        title={<Typography variant="caption">{tooltipText || t("documentLibrary.keywords", "Keywords")}</Typography>}
      >
        <span>
          <IconButton
            size="small"
            onClick={() => setOpen(true)}
            aria-label={t("documentLibrary.keywords", "Keywords")}
            sx={{ width: 28, height: 28, ...sx }}
          >
            <SellOutlinedIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>

      {/* Dialog on SURFACE */}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle sx={{ pb: 1 }}>
          {t("documentLibrary.keywords", "Keywords")} • {list.length}
          {docTitle ? (
            <Typography variant="subtitle2" sx={{ mt: 0.5, opacity: 0.8 }}>
              {docTitle}
            </Typography>
          ) : null}
        </DialogTitle>

        <DialogContent dividers>
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "1fr 1fr 1fr" },
              gap: 1.5,
            }}
          >
            {Object.entries(groups).map(([letter, items]) => (
              <Box key={letter} sx={{ minWidth: 0 }}>
                <Typography variant="overline" color="text.secondary">
                  {letter}
                </Typography>
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mt: 0.5, maxWidth: "100%" }}>
                  {items.map((kw) => (
                    <Chip
                      key={`${letter}-${kw}`}
                      size="small"
                      label={kw}
                      onClick={
                        onChipClick
                          ? () => {
                              onChipClick(kw);
                              setOpen(false);
                            }
                          : undefined
                      }
                      sx={{ cursor: onChipClick ? "pointer" : "default" }}
                    />
                  ))}
                </Box>
              </Box>
            ))}
          </Box>
        </DialogContent>

        <DialogActions>
          <Button onClick={() => setOpen(false)} autoFocus>
            {t("common.close", "Close")}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

export default KeywordsPreview;
