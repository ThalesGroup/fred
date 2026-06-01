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

import DocumentViewerPage from "@components/pages/DocumentViewerPage/DocumentViewerPage.tsx";
import GcuPage from "@components/pages/GcuPage/GcuPage.tsx";
import GdprPage from "@components/pages/GdprPage/GdprPage.tsx";
import ManagedChatPage from "@components/pages/ManagedChatPage/ManagedChatPage.tsx";
import MarketplaceTeams from "@components/pages/marketplace/MarketplaceTeams/MarketplaceTeams.tsx";
import TeamAgentsPage from "@components/pages/TeamAgentsPage/TeamAgentsPage.tsx";
import PromptsPage from "@components/pages/PromptsPage/PromptsPage.tsx";
import MainLayout from "@shared/layouts/MainLayout/MainLayout.tsx";
import React, { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, RouteObject, useParams } from "react-router-dom";
import LoadingWithProgress from "../components/LoadingWithProgress";
import RendererPlayground from "../components/markdown/RenderedPlayground";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { ComingSoon } from "../pages/ComingSoon.tsx";
import KnowledgeHubPage from "@components/pages/KnowledgeHubPage/KnowledgeHubPage.tsx";
import { KnowledgePage } from "../pages/KnowledgePage.tsx";
import { McpHub } from "../pages/McpHub";
import { PageError } from "../pages/PageError";
import Unauthorized from "../pages/PageUnauthorized";
import ReleaseNotesPage from "@components/pages/ReleaseNotesPage/ReleaseNotesPage.tsx";
import UserSettingsPage from "@components/pages/UserSettingsPage/UserSettingsPage.tsx";
import AdminTeamsPage from "@components/pages/admin/AdminTeamsPage/AdminTeamsPage.tsx";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";
import { getConfig } from "./config";

const basename = getConfig().frontend_basename;

// Remounts cleanly on every agent change — prevents stale hook state leaking across agents.
const ManagedChatPageRoute = () => {
  const { agentInstanceId } = useParams<{ agentInstanceId: string }>();
  return <ManagedChatPage key={agentInstanceId} />;
};

// Lazy loaded monitoring pages
const Kpis = lazy(() => import("../pages/Kpis").then((module) => ({ default: module.Kpis })));
const Runtime = lazy(() => import("../pages/Runtime"));
const DataHub = lazy(() => import("../pages/DataHub"));
const Logs = lazy(() => import("../pages/Logs"));
const RebacBackfill = lazy(() => import("../pages/RebacBackfill"));
const ProcessorBench = lazy(() => import("../pages/ProcessorBench"));
const ProcessorRunDetail = lazy(() => import("../pages/ProcessorRunDetail"));

const SuspenseWrapper = ({ children }: { children: React.ReactNode }) => (
  <Suspense fallback={<LoadingWithProgress />}>{children}</Suspense>
);

const AdminProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { canAdmin } = useUserCapabilities();
  if (!canAdmin) {
    return <Navigate to="/unauthorized" replace />;
  }
  return <>{children}</>;
};

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <MainLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/team/personal/agents" replace />,
      },
      {
        path: "knowledge",
        element: <KnowledgeHubPage />,
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
        path: "team/:teamId/*",
        element: <KnowledgePage />,
      },
      {
        path: "marketplace/teams",
        element: <MarketplaceTeams />,
      },
      {
        path: "admin",
        element: (
          <AdminProtectedRoute>
            <Navigate to="/admin/teams" replace />
          </AdminProtectedRoute>
        ),
      },
      {
        path: "admin/teams",
        element: (
          <AdminProtectedRoute>
            <AdminTeamsPage />
          </AdminProtectedRoute>
        ),
      },
      {
        path: "monitoring/kpis",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <SuspenseWrapper>
              <Kpis />
            </SuspenseWrapper>
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/runtime",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <SuspenseWrapper>
              <Runtime />
            </SuspenseWrapper>
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/data",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <SuspenseWrapper>
              <DataHub />
            </SuspenseWrapper>
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/logs",
        element: (
          <ProtectedRoute
            resource={["opensearch", "logs"]}
            action="create"
            anyResource // means that any of the permissions is enough so the user can have opensearch:create || logs:create and it would let the user pass.
          >
            <SuspenseWrapper>
              <Logs />
            </SuspenseWrapper>
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/rebac-backfill",
        element: (
          <ProtectedRoute resource="tag" action="update">
            <SuspenseWrapper>
              <RebacBackfill />
            </SuspenseWrapper>
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/processors",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <SuspenseWrapper>
              <ProcessorBench />
            </SuspenseWrapper>
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/processors/runs/:runId",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <SuspenseWrapper>
              <ProcessorRunDetail />
            </SuspenseWrapper>
          </ProtectedRoute>
        ),
      },
      {
        path: "test-renderer",
        element: <RendererPlayground />,
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
