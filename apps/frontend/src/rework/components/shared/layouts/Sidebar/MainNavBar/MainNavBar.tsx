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

import { isAgentManagementRoute } from "@core/utils/agentManagementRoute";
import type { CSSProperties } from "react";
import styles from "./MainNavBar.module.scss";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import type { IconType } from "@shared/utils/Type.ts";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { useMediaQuery } from "@core/hooks/useMediaQuery";

// Medium button footprint (40px) but with the `small` tier's 1.25rem glyph.
// `--icon-size` is set on `.btn-medium`, so an inline override (higher
// precedence than the class) is what shrinks just the icon, not the hit area.
const ICON_STYLE = { "--icon-size": "1.25rem" } as CSSProperties;
import { useTranslation } from "react-i18next";
import { useHref, useLocation, useNavigate } from "react-router-dom";
import { useManagerPlatformAdmin } from "@core/hooks/useManagerPlatformAdmin";
import { useOrganizationSupervisionAccess } from "@core/hooks/useOrganizationSupervisionAccess";
import { useOrganizationAdmin } from "@core/hooks/useOrganizationAdmin";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { canEnterAdminSection } from "@core/guards/Protected";

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
function BusinessMainNavBar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const capabilities = useUserCapabilities(
    isAgentManagementRoute(pathname) || ["/admin/features", "/admin/supervision"].includes(pathname.replace(/\/$/, "")),
  );
  const organization = useOrganizationAdmin(pathname.replace(/\/$/, "") !== "/admin/supervision");
  const supervision = useOrganizationSupervisionAccess();
  const manager = useManagerPlatformAdmin();
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
      icon: "help",
      label: t("rework.mainNav.helpCenter"),
      active: false,
      // Same-origin page: no noopener, so the browser copies this tab's OIDC session.
      onClick: () => window.open(helpCenterHref, "_blank"),
    },
  ];

  // Any admin-tier role opens the console — gating the shell on canAdmin
  // alone would leave a delegated role holder with no way to reach the one
  // page they own.
  if (
    supervision.allowed ||
    manager.isAdmin ||
    canEnterAdminSection({ ...capabilities, canManageFeatures: organization.isAdmin })
  ) {
    entries.push({
      key: "admin",
      icon: "admin_panel_settings",
      label: t("rework.mainNav.adminConsole"),
      active: pathname.startsWith("/admin"),
      onClick: () => navigate("/admin"),
    });
  }

  return <NavRail entries={entries} />;
}

export default function MainNavBar({ platformArea = false }: { platformArea?: boolean }) {
  return platformArea ? <PlatformMainNavBar /> : <BusinessMainNavBar />;
}

function PlatformMainNavBar() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  return (
    <NavRail
      entries={[
        {
          key: "admin",
          icon: "admin_panel_settings",
          label: t("rework.mainNav.adminConsole"),
          active: true,
          onClick: () => navigate("/admin/organizations"),
        },
      ]}
    />
  );
}

function NavRail({ entries }: { entries: MainNavEntry[] }) {
  const { t } = useTranslation();
  // Touch devices get the labelled M3 rail item; a mouse keeps the compact icon rail.
  const coarse = useMediaQuery("(pointer: coarse)");
  return (
    <nav className={styles.bar} data-touch={coarse || undefined} aria-label={t("rework.mainNav.ariaLabel")}>
      {entries.map((entry) =>
        coarse ? (
          <button
            key={entry.key}
            type="button"
            className={styles.item}
            data-active={entry.active || undefined}
            aria-current={entry.active || undefined}
            onClick={entry.onClick}
          >
            <span className={styles.indicator}>
              <Icon category="outlined" type={entry.icon} filled={entry.active} />
            </span>
            <span className={styles.label}>{entry.label}</span>
          </button>
        ) : (
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
        ),
      )}
    </nav>
  );
}
