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
import type { IconType } from "@shared/utils/Type.ts";

// Medium button footprint (40px) but with the `small` tier's 1.25rem glyph.
// `--icon-size` is set on `.btn-medium`, so an inline override (higher
// precedence than the class) is what shrinks just the icon, not the hit area.
const ICON_STYLE = { "--icon-size": "1.25rem" } as CSSProperties;
import { useTranslation } from "react-i18next";
import { useHref, useLocation, useNavigate } from "react-router-dom";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";

interface MainNavEntry {
  key: string;
  icon: IconType;
  label: string;
  active: boolean;
  onClick: () => void;
}

/**
 * The application's primary navigation: a top-aligned column of icon buttons on
 * the far-left rail. Each entry swaps both the main nav panel (mainNavPanel) and
 * the page — this replaces the former team-switcher rail (the team list now
 * lives in the Home panel). Always mounted, so it also keeps the frontend
 * bootstrap query subscribed across routes (via `useUserCapabilities`), the way
 * the old rail did.
 */
export default function MainNavBar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { canAdmin, canObservePlatform } = useUserCapabilities();
  // Basename-aware href — the Help Center opens in its own tab (HELP-01).
  const helpCenterHref = useHref("/help");

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
    {
      key: "marketplace",
      icon: "storefront",
      label: t("rework.mainNav.marketplace"),
      active: pathname.startsWith("/marketplace"),
      onClick: () => navigate("/marketplace/teams"),
    },
    {
      key: "help",
      icon: "help_center",
      label: t("rework.mainNav.helpCenter"),
      active: false,
      onClick: () => window.open(helpCenterHref, "_blank", "noopener,noreferrer"),
    },
  ];

  if (canAdmin || canObservePlatform) {
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
        <IconButton
          key={entry.key}
          variant="icon"
          size="medium"
          style={ICON_STYLE}
          color={entry.active ? "on-surface" : "on-surface-retreat"}
          icon={{ category: "outlined", type: entry.icon, filled: entry.active }}
          title={entry.label}
          aria-label={entry.label}
          aria-current={entry.active || undefined}
          onClick={entry.onClick}
        />
      ))}
    </nav>
  );
}
