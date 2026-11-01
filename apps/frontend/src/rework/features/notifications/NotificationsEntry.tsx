// Copyright Thales 2026
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

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { useClickOutside } from "@shared/hooks/UseClickOutside";
import RailPopoverLayer from "@shared/molecules/RailPopoverLayer/RailPopoverLayer.tsx";
import { ICON_STYLE } from "@shared/layouts/Sidebar/MainNavBar/MainNavBar.tsx";
import NotificationsPopover from "./NotificationsPopover";
import { useNotificationSummary } from "./useNotificationSummary";
import styles from "./NotificationsEntry.module.scss";

// The bell is the container's first button (IconButton takes no ref).
const focusBell = (container: HTMLElement | null) => container?.querySelector("button")?.focus();

/** The rail's bell: unseen count as a badge, the notifications popover on click. */
export default function NotificationsEntry() {
  const { t } = useTranslation();
  const unseen = useNotificationSummary();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const layerRef = useRef<HTMLDivElement>(null);
  const popoverId = useId();

  const closeOnOutsideClick = useCallback(() => setOpen(false), []);
  useClickOutside(containerRef, closeOnOutsideClick, layerRef);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      focusBell(containerRef.current);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) focusBell(containerRef.current);
  };

  const label =
    unseen > 0 ? t("rework.mainNav.notificationsUnseen", { count: unseen }) : t("rework.mainNav.notifications");

  return (
    <div className={styles.container} ref={containerRef}>
      <Tooltip text={t("rework.mainNav.notifications")} placement="right" disabled={open}>
        <IconButton
          variant="icon"
          size="medium"
          style={ICON_STYLE}
          color={open ? "primary" : "on-surface-retreat"}
          icon={{ category: "outlined", type: "notifications", filled: open }}
          badgeCount={unseen}
          badgeMax={99}
          aria-label={label}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? popoverId : undefined}
          onClick={() => setOpen((value) => !value)}
        />
      </Tooltip>
      {open && (
        <RailPopoverLayer anchor={containerRef} ref={layerRef}>
          <NotificationsPopover id={popoverId} onClose={close} />
        </RailPopoverLayer>
      )}
    </div>
  );
}
