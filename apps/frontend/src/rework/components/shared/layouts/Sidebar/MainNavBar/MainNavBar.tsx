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

import type { CSSProperties } from "react";
import styles from "./MainNavBar.module.scss";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import type { IconType } from "@shared/utils/Type.ts";

// Medium button footprint (40px) but with the `small` tier's 1.25rem glyph.
// `--icon-size` is set on `.btn-medium`, so an inline override (higher
// precedence than the class) is what shrinks just the icon, not the hit area.
const ICON_STYLE = { "--icon-size": "1.25rem" } as CSSProperties;
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";

interface MainNavEntry {
  key: string;
  icon: IconType;
  label: string;
  active: boolean;
  onClick: () => void;
}

export default function MainNavBar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const manager = useManagerPlatformAdmin();
  const entries: MainNavEntry[] = [
    {
      key: "home",
      icon: "home",
      label: t("rework.mainNav.home"),
      // Home is highlighted only on its own view — once the user is inside a
      // team (`/team/...`), no primary entry is marked active (#2298 decision).
      active: pathname.startsWith("/home"),
      onClick: () => navigate("/home"),
    },
  ];

  if (manager.isAdmin) {
    entries.push({
      key: "admin",
      icon: "admin_panel_settings",
      label: t("rework.mainNav.adminConsole"),
      active: pathname.startsWith("/admin"),
      onClick: () => navigate("/admin"),
    });
  }

  return (
    <nav className={styles.bar} aria-label={t("rework.mainNav.ariaLabel")}>
      {entries.map((entry) => (
        <Tooltip key={entry.key} text={entry.label} placement="right">
          <IconButton
            variant="icon"
            size="medium"
            style={ICON_STYLE}
            color={entry.active ? "primary" : "on-surface-retreat"}
            icon={{ category: "outlined", type: entry.icon, filled: entry.active }}
            aria-label={entry.label}
            aria-current={entry.active || undefined}
            onClick={entry.onClick}
          />
        </Tooltip>
      ))}
    </nav>
  );
}
