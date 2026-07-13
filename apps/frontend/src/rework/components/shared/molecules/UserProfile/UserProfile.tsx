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
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties.ts";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";

/**
 * Bottom-of-rail user entry. Clicking the row opens a popover above it grouping
 * everything user-scoped: Profile (the existing settings page), the platform
 * admin/observability console (migrated here from the rail — visible to
 * platform_admin and platform_observer; `AdminIndexRoute` in router.tsx sends
 * each to the first `/admin` page they can actually see, item 16), and
 * Logout. Team admin stays on the team banner gear; this menu is global only.
 */
export default function UserProfile() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { canAdmin, canObservePlatform } = useUserCapabilities();
  const { contactSupportLink } = useFrontendProperties();
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
        <div className={styles.popoverWrap}>
          <MenuPopover
            className={styles.popoverBox}
            headerTitle={userFullName}
            headerSubtitle={userEmail}
            groups={[
              [
                <MenuPopoverItem
                  key="profile"
                  icon={{ category: "outlined", type: "person" }}
                  label={t("rework.profileMenu.profile")}
                  onClick={() => goTo("/settings")}
                />,
              ],
              canAdmin || canObservePlatform
                ? [
                    <MenuPopoverItem
                      key="admin"
                      icon={{ category: "outlined", type: "admin_panel_settings" }}
                      label={t("rework.profileMenu.adminConsole")}
                      badge={t("rework.profileMenu.adminBadge")}
                      onClick={() => goTo("/admin")}
                    />,
                  ]
                : [],
              contactSupportLink
                ? [
                    <MenuPopoverItem
                      key="support"
                      icon={{ category: "outlined", type: "chat" }}
                      label={t("rework.profileMenu.contactSupport")}
                      onClick={() => {
                        setOpen(false);
                        window.open(contactSupportLink, "_blank", "noopener,noreferrer");
                      }}
                    />,
                  ]
                : [],
              [
                <MenuPopoverItem
                  key="logout"
                  icon={{ category: "outlined", type: "logout" }}
                  label={t("rework.userSettings.disconnect")}
                  danger
                  onClick={KeyCloakService.CallLogout}
                />,
              ],
            ]}
          />
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
