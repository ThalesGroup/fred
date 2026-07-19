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
import MigrationPage from "@components/pages/admin/MigrationPage/MigrationPage.tsx";
import SelfTestPage from "@components/pages/admin/SelfTestPage/SelfTestPage.tsx";
import TasksPage from "@components/pages/admin/TasksPage/TasksPage.tsx";
import BootstrapPage from "@components/pages/BootstrapPage/BootstrapPage.tsx";
import DocumentViewerPage from "@components/pages/DocumentViewerPage/DocumentViewerPage.tsx";
import GcuPage from "@components/pages/GcuPage/GcuPage.tsx";
import GdprPage from "@components/pages/GdprPage/GdprPage.tsx";
import ManagedChatPage from "@components/pages/ManagedChatPage/ManagedChatPage.tsx";
import MarketplaceTeams from "@components/pages/marketplace/MarketplaceTeams/MarketplaceTeams.tsx";
import PromptsPage from "@components/pages/PromptsPage/PromptsPage.tsx";
import TeamResourcesPage from "@components/pages/TeamResourcesPage/TeamResourcesPage.tsx";
import TeamSettingsPage from "@components/pages/TeamSettingsPage/TeamSettingsPage.tsx";
import TeamUsagePage from "@components/pages/TeamUsagePage/TeamUsagePage.tsx";
import ReleaseNotesPage from "@components/pages/ReleaseNotesPage/ReleaseNotesPage.tsx";
import TeamAgentsPage from "@components/pages/TeamAgentsPage/TeamAgentsPage.tsx";
import UserSettingsPage from "@components/pages/UserSettingsPage/UserSettingsPage.tsx";
import MainLayout from "@shared/layouts/MainLayout/MainLayout.tsx";
import React, { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, RouteObject, useParams } from "react-router-dom";
import LoadingWithProgress from "../components/LoadingWithProgress";
import RendererPlayground from "../components/markdown/RenderedPlayground";
import { Protected } from "@core/guards/Protected";
import { useFrontendBootstrap } from "../hooks/useFrontendBootstrap.ts";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { ComingSoon } from "../pages/ComingSoon.tsx";
import { McpHub } from "../pages/McpHub";
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
// not the bare `"personal"` alias) so the address bar and TeamSelectionNavbar's
// selection check agree from the first paint. A static `<Navigate>` here never
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

// Lazy loaded monitoring pages
const Kpis = lazy(() => import("../pages/Kpis").then((module) => ({ default: module.Kpis })));
const Runtime = lazy(() => import("../pages/Runtime"));
const DataHub = lazy(() => import("../pages/DataHub"));
const RebacBackfill = lazy(() => import("../pages/RebacBackfill"));
const TaskPlayground = lazy(() => import("../pages/TaskPlayground"));
const LibraryTreePlayground = lazy(() => import("@components/pages/LibraryTreePlayground/LibraryTreePlayground.tsx"));
const ProcessorBench = lazy(() => import("../pages/ProcessorBench"));
const ProcessorRunDetail = lazy(() => import("../pages/ProcessorRunDetail"));

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
        path: "admin/migration",
        element: (
          <Protected requires="admin">
            <MigrationPage />
          </Protected>
        ),
      },
      {
        path: "monitoring/kpis",
        element: (
          <Protected requires="observer">
            <SuspenseWrapper>
              <Kpis />
            </SuspenseWrapper>
          </Protected>
        ),
      },
      {
        path: "monitoring/runtime",
        element: (
          <Protected requires="admin">
            <SuspenseWrapper>
              <Runtime />
            </SuspenseWrapper>
          </Protected>
        ),
      },
      {
        path: "monitoring/data",
        element: (
          <Protected requires="admin">
            <SuspenseWrapper>
              <DataHub />
            </SuspenseWrapper>
          </Protected>
        ),
      },
      {
        path: "monitoring/rebac-backfill",
        element: (
          <Protected requires="admin">
            <SuspenseWrapper>
              <RebacBackfill />
            </SuspenseWrapper>
          </Protected>
        ),
      },
      {
        path: "monitoring/processors",
        element: (
          <Protected requires="admin">
            <SuspenseWrapper>
              <ProcessorBench />
            </SuspenseWrapper>
          </Protected>
        ),
      },
      {
        path: "monitoring/processors/runs/:runId",
        element: (
          <Protected requires="admin">
            <SuspenseWrapper>
              <ProcessorRunDetail />
            </SuspenseWrapper>
          </Protected>
        ),
      },
      {
        path: "test-renderer",
        element: <RendererPlayground />,
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
        path: "tools",
        element: <McpHub />,
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
    path: "/settings",
    element: <UserSettingsPage />,
  },
  {
    path: "unauthorized",
    element: <Unauthorized />,
  },
  {
    path: "coming-soon",
    element: <ComingSoon />,
  },
];

export const router = createBrowserRouter(routes, { basename });
