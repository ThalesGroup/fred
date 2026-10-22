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

import { useEffect, useId, useRef, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import NotificationsPopover from "./NotificationsPopover";
import { useNotificationSummary } from "./useNotificationSummary";
import styles from "./NotificationsEntry.module.scss";

// The bell is the container's first button (IconButton takes no ref).
const focusBell = (container: HTMLElement | null) => container?.querySelector("button")?.focus();

interface NotificationsEntryProps {
  /** The rail's shared glyph override, so the bell matches its neighbours. */
  iconStyle: CSSProperties;
}

/** The rail's bell: unseen count as a badge, the notifications popover on click. */
export default function NotificationsEntry({ iconStyle }: NotificationsEntryProps) {
  const { t } = useTranslation();
  const unseen = useNotificationSummary();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const popoverId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      focusBell(containerRef.current);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const close = (refocus: boolean) => {
    setOpen(false);
    if (refocus) focusBell(containerRef.current);
  };

  const label =
    unseen > 0 ? t("rework.mainNav.notificationsUnseen", { count: unseen }) : t("rework.mainNav.notifications");

  return (
    <div className={styles.container} ref={containerRef}>
      <Tooltip text={t("rework.mainNav.notifications")} placement="right">
        <IconButton
          variant="icon"
          size="medium"
          style={iconStyle}
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
      {open && <NotificationsPopover id={popoverId} onClose={close} />}
    </div>
  );
}
