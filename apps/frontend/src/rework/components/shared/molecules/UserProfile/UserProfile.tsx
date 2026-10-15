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
import { useTranslation } from "react-i18next";
import styles from "./UserProfile.module.scss";
import { KeyCloakService } from "../../../../../security/KeycloakService.ts";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";

/** The account menu remains available before admission and never queries business data. */
export default function UserProfile() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const logoutRef = useRef<HTMLButtonElement>(null);

  const userFullName =
    KeyCloakService.GetUserFullName() || KeyCloakService.GetUserName() || KeyCloakService.GetUserId();
  const userEmail = KeyCloakService.GetUserMail();

  useEffect(() => {
    if (!open) return;
    logoutRef.current?.focus();
    const onPointer = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

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
                  key="logout"
                  ref={logoutRef}
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

      <Tooltip text={t("rework.profileMenu.trigger", { name: userFullName })} placement="right">
        <button
          type="button"
          ref={triggerRef}
          className={styles.trigger}
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-haspopup="menu"
          aria-label={t("rework.profileMenu.trigger", { name: userFullName })}
        >
          <UserAvatar name={userFullName} size="small" />
        </button>
      </Tooltip>
    </div>
  );
}
