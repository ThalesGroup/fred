// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import TroubleshootOutlinedIcon from "@mui/icons-material/TroubleshootOutlined";
import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import ChatWidgetShell from "./ChatWidgetShell.tsx";

export type ChatLogGeniusWidgetProps = {
  open: boolean;
  closeOnClickAway?: boolean;
  disabled?: boolean;
  onRun?: () => void;
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
      tooltipLabel={t("chatbot.logGenius.label", "Log Genius")}
      tooltipDescription={t(
        "chatbot.logGenius.tooltipDescription",
        "Analyze recent logs and summarize likely issues with next steps.",
      )}
      actionLabel={t("chatbot.logGenius.action", "Analyze logs")}
      actionDisabled={disabled}
      onAction={() => onRun?.()}
    >
      <Box sx={{ px: 0.5 }}>
        <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-line" }}>
          {t(
            "chatbot.logGenius.description",
            "Runs a short investigation over the last few minutes of logs and returns a ready-to-use diagnosis.",
          )}
        </Typography>
      </Box>
    </ChatWidgetShell>
  );
};

export default ChatLogGeniusWidget;
