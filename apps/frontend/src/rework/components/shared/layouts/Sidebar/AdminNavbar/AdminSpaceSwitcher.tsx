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

import { type FocusEvent, type KeyboardEvent as ReactKeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import MenuPopover from "@shared/molecules/MenuPopover/MenuPopover.tsx";
import MenuPopoverItem from "@shared/molecules/MenuPopover/MenuPopoverItem.tsx";
import SpaceHeader, { type SpaceHeaderProps } from "@shared/molecules/SpaceHeader/SpaceHeader.tsx";
import type { Role } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AdminSpaceSwitcher.module.css";

export type AdminSpace = "platform" | "organization";

const SHOWN_ROLES: Role[] = ["organization_owner", "admin", "analyst", "editor", "member"];
// "/admin" opens the organization's first page the person can manage.
const SPACE_HOME: Record<AdminSpace, string> = { platform: "/admin/organizations", organization: "/admin" };

/** The only way between admin spaces: each menu lists its own space's pages. */
export default function AdminSpaceSwitcher({
  current,
  identity,
  organization,
}: {
  current: AdminSpace;
  /** The current space as the read-only header shows it. */
  identity: SpaceHeaderProps;
  organization: { name: string; roles: Role[] };
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const groupId = useId();

  useEffect(() => {
    if (!open) return;
    // Focus lands on the current space; the browser shows a ring only after a keyboard open.
    if (!menuRef.current?.contains(document.activeElement))
      menuRef.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
    const onPointer = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      triggerRef.current?.focus();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const choose = (space: AdminSpace) => {
    setOpen(false);
    triggerRef.current?.focus();
    if (space !== current) navigate(SPACE_HOME[space]);
  };
  // Menu keys, kept local until the shared focus handoff reaches this base.
  const onMenuKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Tab") return setOpen(false);
    const items = [...(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? [])];
    const index = items.indexOf(document.activeElement as HTMLElement);
    const target = { ArrowDown: index + 1, ArrowUp: index - 1, Home: 0, End: items.length - 1 }[event.key];
    if (target === undefined || items.length === 0) return;
    event.preventDefault();
    items[(target + items.length) % items.length].focus();
  };
  // Focus moving out of the switcher closes the menu; outside clicks close it above.
  const onMenuBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (event.relatedTarget && !containerRef.current?.contains(event.relatedTarget)) setOpen(false);
  };
  const roles = SHOWN_ROLES.filter((role) => organization.roles.includes(role))
    .map((role) => t(`rework.supervision.roleNames.${role}`))
    .join(", ");

  return (
    <div ref={containerRef}>
      <SpaceHeader {...identity} menu={{ open, onToggle: () => setOpen((value) => !value), ref: triggerRef }}>
        {open && (
          <div className={styles.menuAnchor} onKeyDown={onMenuKeyDown} onBlur={onMenuBlur}>
            <MenuPopover
              ref={menuRef}
              aria-label={t("rework.sidebar.admin.spaces.switch")}
              groups={[
                [
                  <div key="platform" role="group" aria-labelledby={`${groupId}-platform`}>
                    <span id={`${groupId}-platform`} className={styles.groupLabel}>
                      {t("rework.sidebar.admin.platformTitle")}
                    </span>
                    <MenuPopoverItem
                      role="menuitemradio"
                      icon={{ category: "outlined", type: "admin_panel_settings" }}
                      label={t("rework.sidebar.admin.spaces.platform")}
                      selected={current === "platform"}
                      onClick={() => choose("platform")}
                    />
                  </div>,
                ],
                [
                  <div key="organization" role="group" aria-labelledby={`${groupId}-organization`}>
                    <span id={`${groupId}-organization`} className={styles.groupLabel}>
                      {t("rework.sidebar.admin.spaces.organizations")}
                    </span>
                    <MenuPopoverItem
                      role="menuitemradio"
                      icon={{ category: "outlined", type: "groups" }}
                      label={organization.name}
                      description={roles || undefined}
                      selected={current === "organization"}
                      onClick={() => choose("organization")}
                    />
                  </div>,
                ],
              ]}
            />
          </div>
        )}
      </SpaceHeader>
    </div>
  );
}
