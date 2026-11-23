// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useChatNavPanel } from "@core/hooks/useChatNavPanel";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useTranslation } from "react-i18next";

/** Its own component so that toggling never re-renders the whole conversation page. */
export function ChatNavPanelToggle() {
  const { t } = useTranslation();
  const { collapsed, toggle } = useChatNavPanel();
  const label = t(collapsed ? "chatbot.showNavPanel" : "chatbot.hideNavPanel");
  return (
    <Tooltip text={label}>
      <IconButton
        variant="icon"
        size="medium"
        color="on-surface-retreat"
        icon={{ category: "outlined", type: collapsed ? "left_panel_open" : "left_panel_close" }}
        aria-label={label}
        aria-expanded={!collapsed}
        onClick={toggle}
      />
    </Tooltip>
  );
}
