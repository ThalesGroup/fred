// Copyright Thales 2025
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

import AdminTeamsPage from "@components/pages/admin/AdminTeamsPage/AdminTeamsPage.tsx";
import AnalyticsPage from "@components/pages/admin/AnalyticsPage/AnalyticsPage.tsx";
import CapabilitiesPage from "@components/pages/admin/CapabilitiesPage/CapabilitiesPage.tsx";
import CorpusAuditPage from "@components/pages/admin/CorpusAuditPage/CorpusAuditPage.tsx";
// KEA CUTOVER 2026 — temporary, delete this import and its route below a few
// weeks after the S3NS cutover completes (see kea_reconciliation.py, backend).
import KeaMigrationPage from "@components/pages/admin/KeaMigrationPage/KeaMigrationPage.tsx";
import MigrationPage from "@components/pages/admin/MigrationPage/MigrationPage.tsx";
import PlatformRolesPage from "@components/pages/admin/PlatformRolesPage/PlatformRolesPage.tsx";
import SelfTestPage from "@components/pages/admin/SelfTestPage/SelfTestPage.tsx";
import TasksPage from "@components/pages/admin/TasksPage/TasksPage.tsx";
import BootstrapPage from "@components/pages/BootstrapPage/BootstrapPage.tsx";
import DocumentViewerPage from "@components/pages/DocumentViewerPage/DocumentViewerPage.tsx";
import GcuPage from "@components/pages/GcuPage/GcuPage.tsx";
import GdprPage from "@components/pages/GdprPage/GdprPage.tsx";
import HomePage from "@components/pages/HomePage/HomePage.tsx";
import ManagedChatPage from "@components/pages/ManagedChatPage/ManagedChatPage.tsx";
import MarketplaceTeams from "@components/pages/marketplace/MarketplaceTeams/MarketplaceTeams.tsx";
import MarketplacePrompts from "@components/pages/marketplace/MarketplacePrompts/MarketplacePrompts.tsx";
import PptFillerHelpPage from "@components/pages/PptFillerHelpPage/PptFillerHelpPage.tsx";
import PromptsPage from "@components/pages/PromptsPage/PromptsPage.tsx";
import TeamResourcesPage from "@components/pages/TeamResourcesPage/TeamResourcesPage.tsx";
import TeamSettingsPage from "@components/pages/TeamSettingsPage/TeamSettingsPage.tsx";
import TeamUsagePage from "@components/pages/TeamUsagePage/TeamUsagePage.tsx";
import ReleaseNotesPage from "@components/pages/ReleaseNotesPage/ReleaseNotesPage.tsx";
import TeamAgentsPage from "@components/pages/TeamAgentsPage/TeamAgentsPage.tsx";
import UserSettingsPage from "@components/pages/UserSettingsPage/UserSettingsPage.tsx";
import MainLayout from "@shared/layouts/MainLayout/MainLayout.tsx";
import React, { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";
import { createBrowserRouter, Navigate, RouteObject, useParams } from "react-router-dom";
import LoadingWithProgress from "../components/LoadingWithProgress";
import { Protected } from "@core/guards/Protected";
import { useFrontendBootstrap } from "../hooks/useFrontendBootstrap.ts";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { ComingSoon } from "../pages/ComingSoon.tsx";
import { PageError } from "@components/pages/PageError/PageError.tsx";
import Unauthorized from "@components/pages/PageUnauthorized/PageUnauthorized.tsx";
import { getConfig } from "./config";

const basename = getConfig().frontend_basename;

// Remounts cleanly on every agent change — prevents stale hook state leaking across agents.
const ManagedChatPageRoute = () => {
  const { agentInstanceId } = useParams<{ agentInstanceId: string }>();
  return <ManagedChatPage key={agentInstanceId} />;
};

// Bare `/` should land on the canonical personal-space URL (`personal-<uid>`,
// not the bare `"personal"` alias) so the address bar and the team selection
// check agree from the first paint. A static `<Navigate>` here never
// resolves the real id: CTRLP-10 residual, see
// docs/swift/rfc/PERSONAL-TEAM-ISOLATION-RFC.md §4.3.
const HomeIndexRoute = () => {
  const { activeTeam, isLoading } = useFrontendBootstrap();
  if (isLoading) return null;
  return <Navigate to={`/team/${activeTeam?.id ?? "personal"}/agents`} replace />;
};

// Bare `/admin` has no page of its own — land on the first page the caller
// can actually see: `/admin/teams` for a platform_admin, or `/admin/analytics`
// (`can_observe_platform`, item 16 — the one `/admin` page an observer may
// see) otherwise. `Protected requires="admin"` on a hardcoded `/admin/teams`
// redirect would bounce every observer to `/unauthorized` before they ever
// reach analytics.
const AdminIndexRoute = () => {
  const { canAdmin, canObservePlatform, isLoading } = useUserCapabilities();
  if (isLoading) return null;
  if (canAdmin) return <Navigate to="/admin/teams" replace />;
  if (canObservePlatform) return <Navigate to="/admin/analytics" replace />;
  return <Navigate to="/unauthorized" replace />;
};

const TaskPlayground = lazy(() => import("../pages/TaskPlayground"));
const LibraryTreePlayground = lazy(() => import("@components/pages/LibraryTreePlayground/LibraryTreePlayground.tsx"));
// Lazy: the Help Center chunk carries its whole markdown corpus (HELP-01).
const HelpCenterPage = lazy(() => import("@components/pages/HelpCenterPage/HelpCenterPage.tsx"));

// Bare `/help` picks the content language from the app language, then the
// page itself redirects to the first section.
const HelpIndexRoute = () => {
  const { i18n } = useTranslation();
  const lang = i18n.language?.toLowerCase().startsWith("en") ? "en" : "fr";
  return <Navigate to={`/help/${lang}`} replace />;
};

const SuspenseWrapper = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<LoadingWithProgress />}>{children}</Suspense>
);

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <MainLayout />,
    children: [
      {
        index: true,
        element: <HomeIndexRoute />,
      },
      {
        // Landing behind the mainNavBar Home entry (#2298). The team switcher
        // renders in the Home nav panel (Sidebar HOME mode); this is the
        // content-area placeholder.
        path: "home",
        element: <HomePage />,
      },
      {
        path: "team/:teamId/agents",
        element: <TeamAgentsPage />,
      },
      {
        path: "team/:teamId/managed-chat/:agentInstanceId",
        element: <ManagedChatPageRoute />,
      },
      {
        path: "team/:teamId/prompts",
        element: <PromptsPage />,
      },
      {
        path: "team/:teamId/resources",
        element: <TeamResourcesPage />,
      },
      {
        path: "team/:teamId/usage",
        element: <TeamUsagePage />,
      },
      {
        // Team settings render in the main content area while the sidebar shell
        // (coloured team banner + dimmed team rail) stays mounted. Bare
        // `/settings` lands on the members section.
        path: "team/:teamId/settings",
        element: <Navigate to="members" replace />,
      },
      {
        path: "team/:teamId/settings/:section",
        element: <TeamSettingsPage />,
      },
      {
        // Bare /team/:teamId lands on the agents page; the legacy KnowledgePage
        // (old team document library) was superseded by the Resources/Files page.
        path: "team/:teamId",
        element: <Navigate to="agents" replace />,
      },
      {
        path: "marketplace/teams",
        element: <MarketplaceTeams />,
      },
      {
        path: "marketplace/prompts",
        element: <MarketplacePrompts />,
      },
      {
        path: "admin",
        element: <AdminIndexRoute />,
      },
      {
        path: "admin/teams",
        element: (
          <Protected requires="admin">
            <AdminTeamsPage />
          </Protected>
        ),
      },
      {
        // Platform roles (PLATFORM-ADMIN-DELEGATION-RFC.md §3.7, #2405). Gated
        // on the admin role like the backend's `can_administer_users`; the
        // stricter bootstrap-root-only rules on the platform_admin relation
        // are enforced server-side and only mirrored in the page's UI.
        path: "admin/platform-roles",
        element: (
          <Protected requires="admin">
            <PlatformRolesPage />
          </Protected>
        ),
      },
      {
        path: "admin/tasks",
        element: (
          <Protected requires="admin">
            <TasksPage />
          </Protected>
        ),
      },
      {
        path: "admin/analytics",
        element: (
          <Protected requires="observer">
            <AnalyticsPage />
          </Protected>
        ),
      },
      {
        // Admin Capabilities dashboard (CAPAB-01 / #1981, RFC §8.5). Gated on the
        // admin role — the equivalent of `capability#can_manage` (org-admin), the
        // same relation the backend list endpoint enforces.
        path: "admin/capabilities",
        element: (
          <Protected requires="admin">
            <CapabilitiesPage />
          </Protected>
        ),
      },
      {
        path: "admin/self-test",
        element: (
          <Protected requires="admin">
            <SelfTestPage />
          </Protected>
        ),
      },
      {
        // Corpus audit (#2112): platform-admin-only surface over the document
        // store audit/fix endpoints (`CAN_MANAGE_PLATFORM`) — same gate as the
        // other admin-only pages above.
        path: "admin/corpus-audit",
        element: (
          <Protected requires="admin">
            <CorpusAuditPage />
          </Protected>
        ),
      },
      {
        path: "admin/migration",
        element: (
          <Protected requires="admin">
            <MigrationPage />
          </Protected>
        ),
      },
      {
        // KEA CUTOVER 2026 — temporary, deliberately NOT linked from any nav
        // menu (reached by direct URL only, mirroring kea's own
        // /admin/kea-migration) so it never gets mistaken for the permanent
        // export/import tool above. Delete with KeaMigrationPage/.
        path: "admin/kea-migration",
        element: (
          <Protected requires="admin">
            <KeaMigrationPage />
          </Protected>
        ),
      },
      {
        path: "dev/tasks",
        element: import.meta.env.DEV ? (
          <SuspenseWrapper>
            <TaskPlayground />
          </SuspenseWrapper>
        ) : (
          <PageError />
        ),
      },
      {
        path: "dev/library",
        element: import.meta.env.DEV ? (
          <SuspenseWrapper>
            <LibraryTreePlayground />
          </SuspenseWrapper>
        ) : (
          <PageError />
        ),
      },
      {
        path: "*",
        element: <PageError />,
      },
    ].filter(Boolean),
  },
  {
    path: "/bootstrap",
    element: <BootstrapPage />,
  },
  {
    path: "/documents/:uid",
    element: <DocumentViewerPage />,
  },
  {
    path: "/gcu",
    element: <GcuPage />,
  },
  {
    path: "/gdpr",
    element: <GdprPage />,
  },
  {
    path: "/release-notes",
    element: <ReleaseNotesPage />,
  },
  {
    // Help Center (HELP-01) — own tab, no app chrome, shareable URLs.
    path: "/help",
    element: <HelpIndexRoute />,
  },
  {
    path: "/help/:lang/:sectionId?/:pageId?",
    element: (
      <SuspenseWrapper>
        <HelpCenterPage />
      </SuspenseWrapper>
    ),
  },
  {
    // PPT Filler capability documentation — opened in a new tab from the
    // agent-creation form, so it renders without the app chrome.
    path: "/ppt-filler-help",
    element: <PptFillerHelpPage />,
  },
  {
    path: "/settings",
    element: <UserSettingsPage />,
  },
  {
    path: "unauthorized",
    element: <Unauthorized />,
  },
  {
    // Whitelist-rejection landing page (HTTP 403 "user_not_whitelisted",
    // see docs/swift/platform/KEYCLOAK.md §"Behavior"). Standalone, no
    // MainLayout chrome — must render even when auth/bootstrap has failed.
    path: "coming-soon",
    element: <ComingSoon />,
  },
];

export const router = createBrowserRouter(routes, { basename });
