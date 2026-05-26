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

import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Typography } from "@mui/material";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { SimpleTooltip } from "../../../shared/ui/tooltips/Tooltips";
import type { DocSummary } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export default function SummaryPreview({
  summary,
  docTitle,
  previewChars = 420,
  sx,
}: {
  summary?: DocSummary | null;
  docTitle?: string;
  previewChars?: number;
  sx?: any;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const abstract = summary?.abstract ?? "";
  const hasSummary = !!summary && (Boolean(abstract) || (summary.keywords?.length ?? 0) > 0);
  const abstractPreview = useMemo(
    () => (abstract.length > previewChars ? abstract.slice(0, previewChars) + "…" : abstract),
    [abstract, previewChars],
  );
  if (!hasSummary) return null;

  return (
    <>
      {/* Minimal trigger with SURFACE tooltip */}
      <SimpleTooltip
        placement="top"
        // ATTENTION slotProps={{
        //   tooltip: {
        //     sx: {
        //       maxWidth: 520,
        //     },
        //   },
        // }}
        title={
          abstractPreview ? (
            <Box sx={{ maxWidth: 520 }}>
              <Typography variant="body2" sx={{ whiteSpace: "pre-line" }}>
                {abstractPreview}
              </Typography>
            </Box>
          ) : (
            t("documentLibrary.summary", "Summary")
          )
        }
      >
        <span>
          <IconButton
            size="small"
            onClick={() => setOpen(true)}
            aria-label={t("documentLibrary.summary", "Summary")}
            sx={{ width: 28, height: 28, ...sx }}
          >
            <InfoOutlinedIcon fontSize="small" />
          </IconButton>
        </span>
      </SimpleTooltip>

      {/* Full summary dialog on SURFACE */}
      <Dialog open={open} onClose={() => setOpen(false)} fullWidth maxWidth="md">
        <DialogTitle sx={{ pb: 1 }}>
          {t("documentLibrary.summary", "Summary")}
          {docTitle ? (
            <Typography variant="subtitle2" sx={{ mt: 0.5, opacity: 0.8 }}>
              {docTitle}
            </Typography>
          ) : null}
        </DialogTitle>

        <DialogContent dividers>
          {abstract ? (
            <Typography variant="body2" sx={{ whiteSpace: "pre-line" }}>
              {abstract}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {t("documentLibrary.noSummary", "No summary available.")}
            </Typography>
          )}
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
