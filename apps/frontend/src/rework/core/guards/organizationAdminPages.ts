// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { IconProps } from "@shared/atoms/Icon/Icon.tsx";
import { isProtectedAllowed, type ProtectedCapabilities, type ProtectedRequirement } from "./Protected";

export interface OrganizationAdminPage {
  to: string;
  labelKey: string;
  icon: IconProps;
  /** The route guard's requirement; "supervision" is the `own_organization` check. */
  requires: ProtectedRequirement | "supervision";
}

/** The organization admin menu, in order. Its first visible page is also where Admin lands. */
const PAGES: OrganizationAdminPage[] = [
  {
    to: "/admin/supervision",
    labelKey: "rework.supervision.title",
    icon: { category: "outlined", type: "analytics", filled: false },
    requires: "supervision",
  },
  {
    to: "/admin/teams",
    labelKey: "rework.sidebar.admin.menu.teams",
    icon: { category: "outlined", type: "groups", filled: true },
    requires: "teamRoster",
  },
  {
    to: "/admin/platform-roles",
    labelKey: "rework.sidebar.admin.menu.platformRoles",
    icon: { category: "outlined", type: "admin_panel_settings", filled: false },
    requires: "admin",
  },
  {
    to: "/admin/analytics",
    labelKey: "rework.sidebar.admin.menu.analytics",
    icon: { category: "outlined", type: "analytics", filled: false },
    requires: "observer",
  },
  {
    to: "/admin/platform-prompt",
    labelKey: "rework.sidebar.admin.menu.platformPrompt",
    icon: { category: "outlined", type: "auto_awesome", filled: false },
    requires: "platformPrompt",
  },
  {
    to: "/admin/annonces",
    labelKey: "rework.sidebar.admin.menu.announcements",
    icon: { category: "outlined", type: "campaign", filled: false },
    requires: "admin",
  },
  {
    to: "/admin/interface",
    labelKey: "rework.sidebar.admin.menu.uiSettings",
    icon: { category: "outlined", type: "dark_mode", filled: false },
    requires: "admin",
  },
  {
    to: "/admin/features",
    labelKey: "rework.sidebar.admin.menu.features",
    icon: { category: "outlined", type: "tune", filled: false },
    requires: "features",
  },
  {
    to: "/admin/marketplaces",
    labelKey: "rework.sidebar.admin.menu.marketplaces",
    icon: { category: "outlined", type: "storefront", filled: false },
    requires: "admin",
  },
  {
    to: "/admin/platform-access",
    labelKey: "rework.platformAccess.title",
    icon: { category: "outlined", type: "lock", filled: false },
    requires: "platformAccess",
  },
];

export interface OrganizationAdminAccess {
  /** `canManageFeatures` carries the organization admin role. */
  capabilities: ProtectedCapabilities;
  supervision: boolean;
  platformAccessEnabled: boolean;
}

/** The organization admin pages this person can open, in menu order. */
export function organizationAdminPages(access: OrganizationAdminAccess): OrganizationAdminPage[] {
  return PAGES.filter((page) => {
    if (page.requires === "supervision") return access.supervision;
    if (page.to === "/admin/platform-access" && !access.platformAccessEnabled) return false;
    return isProtectedAllowed(page.requires, access.capabilities);
  });
}

/** Admin opens the organization's first menu page; the platform space is one switch away. */
export function adminIndexPath(access: OrganizationAdminAccess & { platformOwner: boolean }): string {
  return organizationAdminPages(access)[0]?.to ?? (access.platformOwner ? "/admin/organizations" : "/unauthorized");
}
