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

import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import styles from "./UserProfile.module.scss";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";

/**
 * Bottom-of-rail user entry. Clicking the row opens a popover above it grouping
 * everything user-scoped: Profile (the existing settings page), the platform
 * admin console (only for platform admins — migrated here from the rail), and
 * Logout. Team admin stays on the team banner gear; this menu is global only.
 */
export default function UserProfile() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { canAdmin } = useUserCapabilities();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const userFullName = KeyCloakService.GetUserFullName();
  const username = KeyCloakService.GetUserName();
  const userEmail = KeyCloakService.GetUserMail();

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const goTo = (path: string) => {
    setOpen(false);
    navigate(path);
  };

  return (
    <div className={styles.container} ref={containerRef}>
      {open && (
        <div className={styles.popover} role="menu">
          <div className={styles.header}>
            <span className={styles.headerName}>{userFullName}</span>
            <span className={styles.headerEmail}>{userEmail}</span>
          </div>

          <div className={styles.separator} />
          <button type="button" className={styles.item} role="menuitem" onClick={() => goTo("/settings")}>
            <span className={styles.itemIcon} aria-hidden>
              <Icon category="outlined" type="person" />
            </span>
            <span className={styles.itemLabel}>{t("rework.profileMenu.profile")}</span>
          </button>

          {canAdmin && (
            <>
              <div className={styles.separator} />
              <button type="button" className={styles.item} role="menuitem" onClick={() => goTo("/admin")}>
                <span className={styles.itemIcon} aria-hidden>
                  <Icon category="outlined" type="admin_panel_settings" />
                </span>
                <span className={styles.itemLabel}>{t("rework.profileMenu.adminConsole")}</span>
                <span className={styles.badge}>{t("rework.profileMenu.adminBadge")}</span>
              </button>
            </>
          )}

          <div className={styles.separator} />
          <button
            type="button"
            className={`${styles.item} ${styles.danger}`}
            role="menuitem"
            onClick={KeyCloakService.CallLogout}
          >
            <span className={styles.itemIcon} aria-hidden>
              <Icon category="outlined" type="logout" />
            </span>
            <span className={styles.itemLabel}>{t("rework.userSettings.disconnect")}</span>
          </button>
        </div>
      )}

      <button
        type="button"
        className={styles.trigger}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <UserAvatar name={userFullName} size="medium" />
        <span className={styles.identity}>
          <span className={styles.identityName}>{userFullName}</span>
          <span className={styles.identityId}>{username}</span>
        </span>
        <span className={styles.chevron} aria-hidden>
          <Icon category="outlined" type={open ? "expand_more" : "expand_less"} />
        </span>
      </button>
    </div>
  );
}
