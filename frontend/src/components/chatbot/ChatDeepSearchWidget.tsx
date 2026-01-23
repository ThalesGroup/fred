// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// http://www.apache.org/licenses/LICENSE-2.0

import TravelExploreOutlinedIcon from "@mui/icons-material/TravelExploreOutlined";
import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import ChatWidgetShell from "./ChatWidgetShell.tsx";

export type ChatDeepSearchWidgetProps = {
  open: boolean;
  enabled: boolean;
  closeOnClickAway?: boolean;
  disabled?: boolean;
  onToggle?: (next: boolean) => void;
  onOpen: () => void;
  onClose: () => void;
};

const ChatDeepSearchWidget = ({
  open,
  enabled,
  closeOnClickAway = true,
  disabled = false,
  onToggle,
  onOpen,
  onClose,
}: ChatDeepSearchWidgetProps) => {
  const { t } = useTranslation();

  return (
    <ChatWidgetShell
      open={open}
      onOpen={onOpen}
      onClose={onClose}
      closeOnClickAway={closeOnClickAway}
      disabled={disabled}
      showBadgeDotWhenEmpty={enabled}
      badgeColor={enabled ? "primary" : "default"}
      icon={<TravelExploreOutlinedIcon fontSize="small" />}
      ariaLabel={t("chatbot.deepSearch.label", "Deep Search")}
      tooltipLabel={t("chatbot.deepSearch.label", "Deep Search")}
      tooltipDescription={t(
        "chatbot.deepSearch.tooltipDescription",
        "Delegates retrieval to a specialized agent for deeper search across your knowledge.",
      )}
      tooltipDisabledReason={
        disabled ? t("chatbot.deepSearch.tooltipDisabled", "This agent does not support deep search delegation.") : undefined
      }
      actionLabel={
        enabled
          ? t("chatbot.deepSearch.actionDisable", "Disable deep search")
          : t("chatbot.deepSearch.actionEnable", "Enable deep search")
      }
      actionDisabled={disabled}
      onAction={() => onToggle?.(!enabled)}
    >
      <Box sx={{ px: 0.5 }}>
        <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: "pre-line" }}>
          {t(
            "chatbot.deepSearch.description",
            "Runs a deeper retrieval pass with a specialized agent. Enables slower but more thorough answers.",
          )}
        </Typography>
      </Box>
    </ChatWidgetShell>
  );
};

export default ChatDeepSearchWidget;
