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

import { ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { type IconProps } from "@shared/atoms/Icon/Icon";
import styles from "./ComposerActionsMenu.module.css";

interface ComposerActionsMenuProps {
  disabled?: boolean;
  align?: "left" | "right";
  size?: "2xs" | "small";
  portal?: boolean;
  /** Trigger glyph — defaults to the "add" (+) icon. */
  icon?: IconProps;
  /** aria-label for the trigger button; defaults to the add-menu string. */
  openAriaLabel?: string;
  /** aria-label for the opened popover; defaults to the add-menu string. */
  dialogAriaLabel?: string;
  /** Small red dot over the trigger, signalling an active per-turn override
   * (e.g. a ponctual document scope, #2259). */
  badge?: boolean;
  children?: ReactNode | ((controls: { closeMenu: () => void }) => ReactNode);
}

export function ComposerActionsMenu({
  disabled = false,
  align = "left",
  size = "small",
  portal = false,
  icon = { category: "outlined", type: "add" },
  openAriaLabel,
  dialogAriaLabel,
  badge = false,
  children,
}: ComposerActionsMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{ top?: number; right: number; bottom?: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const closeMenu = () => {
    if (portal && menuRef.current?.contains(document.activeElement))
      containerRef.current?.querySelector("button")?.focus();
    setOpen(false);
  };

  useEffect(() => {
    if (disabled && open) {
      setOpen(false);
    }
  }, [disabled, open]);

  useEffect(() => {
    if (!open) return;
    const handleMouseDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node) && !menuRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        containerRef.current?.querySelector("button")?.focus();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleMouseDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleMouseDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  useEffect(() => {
    if (!open || !portal) return;
    menuRef.current?.querySelector<HTMLElement>("button, [href], [tabindex]:not([tabindex='-1'])")?.focus();
    window.addEventListener("resize", closeMenu);
    return () => {
      window.removeEventListener("resize", closeMenu);
    };
  }, [open, portal]);

  const menu = open && (
    <div
      ref={menuRef}
      className={styles.menu}
      data-align={align}
      data-portal={portal}
      style={portal ? (menuPosition ?? undefined) : undefined}
      role="dialog"
      aria-label={dialogAriaLabel ?? t("chatbot.composerActions.dialogAria")}
    >
      {children ? (
        <div className={styles.menuBody}>{typeof children === "function" ? children({ closeMenu }) : children}</div>
      ) : null}
    </div>
  );

  return (
    <div ref={containerRef} className={styles.container} data-open={open}>
      <IconButton
        variant="icon"
        size={size}
        icon={icon}
        aria-label={openAriaLabel ?? t("chatbot.composerActions.openAria")}
        aria-expanded={open}
        aria-haspopup="dialog"
        disabled={disabled}
        onClick={(event) => {
          if (portal) {
            const rect = event.currentTarget.getBoundingClientRect();
            setMenuPosition(
              rect.top < 100
                ? { top: rect.bottom + 4, right: window.innerWidth - rect.right }
                : { bottom: window.innerHeight - rect.top + 4, right: window.innerWidth - rect.right },
            );
          }
          setOpen((value) => !value);
        }}
      />
      {badge && <span className={styles.badge} aria-hidden />}
      {portal && menu ? createPortal(menu, document.body) : menu}
    </div>
  );
}
