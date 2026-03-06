// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import TroubleshootOutlinedIcon from "@mui/icons-material/TroubleshootOutlined";
import ReportProblemOutlinedIcon from "@mui/icons-material/ReportProblemOutlined";
import SpeedOutlinedIcon from "@mui/icons-material/SpeedOutlined";
import { Box, Button, Stack } from "@mui/material";
import { useTranslation } from "react-i18next";
import { DetailedTooltip } from "../../shared/ui/tooltips/Tooltips.tsx";
import ChatWidgetShell from "./ChatWidgetShell.tsx";

export type LogGeniusMode = "logs" | "performance";

export type ChatLogGeniusWidgetProps = {
  open: boolean;
  closeOnClickAway?: boolean;
  disabled?: boolean;
  onRun?: (mode: LogGeniusMode) => void;
  onOpen: () => void;
  onClose: () => void;
};

const ChatLogGeniusWidget = ({
  open,
  closeOnClickAway = true,
  disabled = false,
  onRun,
  onOpen,
  onClose,
}: ChatLogGeniusWidgetProps) => {
  const { t } = useTranslation();

  return (
    <ChatWidgetShell
      open={open}
      onOpen={onOpen}
      onClose={onClose}
      closeOnClickAway={closeOnClickAway}
      disabled={disabled}
      icon={<TroubleshootOutlinedIcon fontSize="small" />}
      ariaLabel={t("chatbot.logGenius.label", "Log Genius")}
      tooltip={t("chatbot.logGenius.tooltip", "Ouvrir les options de diagnostic")}
      headerTitle={t("chatbot.logGenius.panelTitle", "Diagnostics Assistant")}
    >
      <Box sx={{ px: 0.5, display: "flex", flexDirection: "column", gap: 1 }}>
        <Stack direction="column" spacing={1}>
          <DetailedTooltip
            label={t("chatbot.logGenius.incidentAction", "Incident diagnosis")}
            description={t(
              "chatbot.logGenius.incidentDescription",
              "Investigates recent errors and abnormal signals, then returns a concise diagnosis with concrete remediation steps.",
            )}
            placement="left-start"
          >
            <span style={{ display: "block" }}>
              <Button
                fullWidth
                variant="outlined"
                size="small"
                disabled={disabled}
                onClick={() => onRun?.("logs")}
                startIcon={<ReportProblemOutlinedIcon fontSize="small" />}
                sx={{ textTransform: "none", justifyContent: "flex-start" }}
              >
                {t("chatbot.logGenius.incidentAction", "Incident diagnosis")}
              </Button>
            </span>
          </DetailedTooltip>
          <DetailedTooltip
            label={t("chatbot.logGenius.performanceAction", "Performance diagnosis")}
            description={t(
              "chatbot.logGenius.performanceDescription",
              "Analyzes conversation traces to identify bottlenecks (model, tools, step latency) and prioritize optimization actions.",
            )}
            placement="left-start"
          >
            <span style={{ display: "block" }}>
              <Button
                fullWidth
                variant="outlined"
                size="small"
                disabled={disabled}
                onClick={() => onRun?.("performance")}
                startIcon={<SpeedOutlinedIcon fontSize="small" />}
                sx={{ textTransform: "none", justifyContent: "flex-start" }}
              >
                {t("chatbot.logGenius.performanceAction", "Performance diagnosis")}
              </Button>
            </span>
          </DetailedTooltip>
        </Stack>
      </Box>
    </ChatWidgetShell>
  );
};

export default ChatLogGeniusWidget;
