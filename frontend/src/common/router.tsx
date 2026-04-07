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

import { createBrowserRouter, Navigate, RouteObject } from "react-router-dom";
import RendererPlayground from "../components/markdown/RenderedPlayground";
import { ProtectedRoute } from "../components/ProtectedRoute";
import Chat from "../pages/Chat";
import { ComingSoon } from "../pages/ComingSoon.tsx";
import { KnowledgeHub } from "../pages/KnowledgeHub";
import { McpHub } from "../pages/McpHub";
import { PageError } from "../pages/PageError";
import Unauthorized from "../pages/PageUnauthorized";
import { Profile } from "../pages/Profile";
import { KnowledgePage } from "../pages/KnowledgePage.tsx";
import { getConfig } from "./config";
import DesignSystemPage from "../pages/DesignSystemPage/DesignSystemPage.tsx";
import MainLayout from "@shared/layouts/MainLayout/MainLayout.tsx";
import React, { lazy, Suspense } from "react";
import LoadingWithProgress from "../components/LoadingWithProgress";
import TeamAgentsPage from "@components/pages/TeamAgentsPage/TeamAgentsPage.tsx";
import MarketplaceTeams from "@components/pages/marketplace/MarketplaceTeams/MarketplaceTeams.tsx";

const basename = getConfig().frontend_basename;

// Lazy loaded monitoring pages
const Kpis = lazy(() => import("../pages/Kpis").then((module) => ({ default: module.Kpis })));
const Runtime = lazy(() => import("../pages/Runtime"));
const DataHub = lazy(() => import("../pages/DataHub"));
const GraphHub = lazy(() => import("../pages/GraphHub"));
const Logs = lazy(() => import("../pages/Logs"));
const RebacBackfill = lazy(() => import("../pages/RebacBackfill"));
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
        element: <Navigate to="/team/personal/agents" replace />,
      },
      {
        path: "/design-system",
        element: <DesignSystemPage />,
      },
      {
        path: "team/:teamId/new-chat/:agent-id",
        element: <Chat />,
      },
      {
        path: "team/:teamId/chat/:sessionId",
        element: <Chat />,
      },
      {
        path: "knowledge",
        element: <KnowledgeHub />,
      },
      {
        path: "team/:teamId/agents",
        element: <TeamAgentsPage />,
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
        path: "monitoring/graph",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <SuspenseWrapper>
              <GraphHub />
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
        path: "settings",
        element: <Profile />,
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
    path: "unauthorized",
    element: <Unauthorized />,
  },
  {
    path: "coming-soon",
    element: <ComingSoon />,
  },
];

export const router = createBrowserRouter(routes, { basename });
