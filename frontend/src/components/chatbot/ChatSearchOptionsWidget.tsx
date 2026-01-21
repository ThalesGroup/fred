// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import CloseIcon from "@mui/icons-material/Close";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import { Box, ClickAwayListener, IconButton, Paper, Stack, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";

import { FeatureTooltip } from "../../shared/tooltips/DetailedTooltip.tsx";
import { ResetButton } from "../../shared/ui/buttons/ResetButton.tsx";
import { ToggleIconButton } from "../../shared/ui/buttons/ToggleIconButton.tsx";
import type { RuntimeContext } from "../../slices/agentic/agenticOpenApi.ts";
import { SearchPolicyName } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";
import { UserInputRagScope } from "./user_input/UserInputRagScope.tsx";
import { UserInputSearchPolicy } from "./user_input/UserInputSearchPolicy.tsx";

type SearchRagScope = NonNullable<RuntimeContext["search_rag_scope"]>;

export type ChatSearchOptionsWidgetProps = {
  searchPolicy: SearchPolicyName;
  onSearchPolicyChange: (next: SearchPolicyName) => void;
  defaultSearchPolicy: SearchPolicyName;
  searchRagScope: SearchRagScope;
  onSearchRagScopeChange: (next: SearchRagScope) => void;
  defaultRagScope: SearchRagScope;
  ragScopeDisabled?: boolean;
  searchPolicyDisabled?: boolean;
  open: boolean;
  closeOnClickAway?: boolean;
  disabled?: boolean;
  onOpen: () => void;
  onClose: () => void;
  onResetToDefaults?: () => void;
};

const ChatSearchOptionsWidget = ({
  searchPolicy,
  onSearchPolicyChange,
  defaultSearchPolicy,
  searchRagScope,
  onSearchRagScopeChange,
  defaultRagScope,
  ragScopeDisabled = false,
  searchPolicyDisabled = false,
  open,
  closeOnClickAway = true,
  disabled = false,
  onOpen,
  onClose,
  onResetToDefaults,
}: ChatSearchOptionsWidgetProps) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const isVisible = open;
  const hasOverrides =
    (!ragScopeDisabled && searchRagScope !== defaultRagScope) ||
    (!searchPolicyDisabled && searchPolicy !== defaultSearchPolicy);
  const canReset = Boolean(onResetToDefaults) && hasOverrides && !disabled;
  const showOverrideIndicator = hasOverrides && !disabled;

  const widgetBody = (
    <Paper
      elevation={2}
      sx={{
        width: "100%",
        minWidth: "100%",
        maxWidth: "100%",
        maxHeight: "70vh",
        borderRadius: 3,
        border: `1px solid ${theme.palette.divider}`,
        p: 1.5,
        bgcolor: theme.palette.background.paper,
      }}
    >
      <Stack spacing={1} sx={{ pb: 0.5 }}>
        <Box display="flex" alignItems="center" gap={1} sx={{ width: "100%" }}>
          <Box sx={{ flex: 1, minWidth: 0, minHeight: 28, display: "flex", alignItems: "center" }}>
            <Typography variant="subtitle2" noWrap>
              {t("chatbot.searchOptions", "Search options")}
            </Typography>
          </Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
            <ResetButton
              size="small"
              onClick={onResetToDefaults}
              disabled={!canReset}
              aria-label={t("chatbot.searchOptionsReset", "Back to default")}
              tooltip={t("chatbot.searchOptionsResetTooltip", "Reset to default values")}
              sx={{ p: 0.5 }}
            />
            <IconButton size="small" onClick={onClose}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>
        </Box>

        <Stack spacing={0.75}>
          <Box display="flex" alignItems="center" justifyContent="space-between" gap={1}>
            <Typography variant="caption" color="text.secondary" sx={{ minWidth: 0 }}>
              {t("chatbot.ragScope.label", "RAG scope")}
            </Typography>
            <Box sx={{ flexShrink: 0 }}>
              <UserInputRagScope value={searchRagScope} onChange={onSearchRagScopeChange} disabled={ragScopeDisabled} />
            </Box>
          </Box>
          <Box display="flex" alignItems="center" justifyContent="space-between" gap={1}>
            <Typography variant="caption" color="text.secondary" sx={{ minWidth: 0 }}>
              {t("chatbot.searchPolicy.label", "Search policy")}
            </Typography>
            <Box sx={{ flexShrink: 0 }}>
              <UserInputSearchPolicy
                value={searchPolicy}
                onChange={onSearchPolicyChange}
                disabled={searchPolicyDisabled}
              />
            </Box>
          </Box>
        </Stack>
      </Stack>
    </Paper>
  );

  return (
    <Box sx={{ position: "relative", width: isVisible ? "100%" : "auto" }}>
      {!isVisible && (
        <FeatureTooltip
          label={t("chatbot.searchOptions", "Search options")}
          description={t(
            "chatbot.searchOptionsTooltip.description",
            "Adjust how the agent retrieves knowledge (RAG scope and search policy).",
          )}
          disabledReason={
            disabled
              ? t("chatbot.searchOptionsTooltip.disabled", "This agent does not support search options.")
              : undefined
          }
        >
          <ToggleIconButton
            size="small"
            onClick={onOpen}
            aria-label={t("chatbot.searchOptions", "Search options")}
            disabled={disabled}
            sx={{ color: disabled ? "text.disabled" : "inherit" }}
            active={showOverrideIndicator}
            icon={<TuneOutlinedIcon fontSize="small" />}
          />
        </FeatureTooltip>
      )}

      {isVisible && closeOnClickAway && (
        <ClickAwayListener onClickAway={onClose}>
          <Box sx={{ width: "100%" }}>{widgetBody}</Box>
        </ClickAwayListener>
      )}
      {isVisible && !closeOnClickAway && <Box sx={{ width: "100%" }}>{widgetBody}</Box>}
    </Box>
  );
};

export default ChatSearchOptionsWidget;
