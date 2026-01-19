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

import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import PublicOutlinedIcon from "@mui/icons-material/PublicOutlined";
import SyncAltOutlinedIcon from "@mui/icons-material/SyncAltOutlined";
import { Box, Divider, ToggleButton, ToggleButtonGroup, Tooltip, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

import type { RuntimeContext } from "../../../slices/agentic/agenticOpenApi.ts";

type SearchRagScope = NonNullable<RuntimeContext["search_rag_scope"]>;

type Props = {
  value: SearchRagScope;
  onChange: (next: SearchRagScope) => void;
  disabled?: boolean;
};

/**
 * Compact tri-state selector for corpus usage:
 * - corpus_only
 * - hybrid
 * - general_only
 */
export function UserInputRagScope({ value, onChange, disabled }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();

  const labels: Record<SearchRagScope, string> = {
    corpus_only: "Corpus",
    hybrid: "Hybrid",
    general_only: "General",
  };

  const tooltipByValue: Record<SearchRagScope, string> = {
    corpus_only: t("chatbot.ragScope.tooltipCorpus"),
    hybrid: t("chatbot.ragScope.tooltipHybrid"),
    general_only: t("chatbot.ragScope.tooltipGeneral"),
  };

  const renderTooltipContent = (scope: SearchRagScope) => (
    <Box sx={{ maxWidth: 360 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 0.75 }}>
        {labels[scope]}
      </Typography>
      <Divider sx={{ opacity: 0.5, mb: 0.75 }} />
      <Box sx={{ pl: 1.25, borderLeft: `2px solid ${theme.palette.divider}` }}>
        <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
          {tooltipByValue[scope]}
        </Typography>
      </Box>
    </Box>
  );

  const renderButton = (scope: SearchRagScope, icon: JSX.Element) => (
    <Tooltip
      key={scope}
      title={renderTooltipContent(scope)}
      placement="right"
      arrow
      componentsProps={{
        tooltip: { sx: { boxShadow: "none" } },
        arrow: { sx: { color: "background.paper" } },
      }}
    >
      <ToggleButton value={scope} aria-label={labels[scope]}>
        {icon}
      </ToggleButton>
    </Tooltip>
  );

  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={value}
      disabled={disabled}
      onChange={(_, next) => {
        if (next) onChange(next as SearchRagScope);
      }}
      aria-label="rag-knowledge-scope"
      sx={{
        borderRadius: 999,
        overflow: "hidden",
        "& .MuiToggleButton-root": {
          px: 1,
          py: 0.35,
          fontSize: "0.78rem",
          textTransform: "none",
          gap: 0.5,
          color: "text.secondary",
          borderColor: "divider",
          "&.Mui-selected": {
            color: "primary.main",
            backgroundColor: "primary.main",
            "& svg": { color: "common.white" },
            "&:hover": { backgroundColor: "primary.dark" },
          },
        },
      }}
    >
      {renderButton("corpus_only", <MenuBookOutlinedIcon fontSize="small" />)}
      {renderButton("hybrid", <SyncAltOutlinedIcon fontSize="small" />)}
      {renderButton("general_only", <PublicOutlinedIcon fontSize="small" />)}
    </ToggleButtonGroup>
  );
}
