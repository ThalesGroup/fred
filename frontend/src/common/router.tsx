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
import { LayoutWithSidebar } from "../app/LayoutWithSidebar";
import RendererPlayground from "../components/markdown/RenderedPlayground";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { AgentHub } from "../pages/AgentHub";
import Chat from "../pages/Chat";
import { ComingSoon } from "../pages/ComingSoon.tsx";
import DataHub from "../pages/DataHub";
import GraphHub from "../pages/GraphHub.tsx";
import { KnowledgeHub } from "../pages/KnowledgeHub";
import { Kpis } from "../pages/Kpis";
import Logs from "../pages/Logs";
import { McpHub } from "../pages/McpHub";
import { NewChatAgentSelection } from "../pages/NewChatAgentSelection.tsx";
import { PageError } from "../pages/PageError";
import Unauthorized from "../pages/PageUnauthorized";
import ProcessorBench from "../pages/ProcessorBench";
import ProcessorRunDetail from "../pages/ProcessorRunDetail";
import { Profile } from "../pages/Profile";
import RebacBackfill from "../pages/RebacBackfill";
import Runtime from "../pages/Runtime";
import { getConfig } from "./config";

const basename = getConfig().frontend_basename;

const RootLayout = ({ children }: React.PropsWithChildren<{}>) => <LayoutWithSidebar>{children}</LayoutWithSidebar>;

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <RootLayout />,
    children: [
      {
        index: true,
        element: <Navigate to="/new-chat" replace />,
      },
      {
        path: "/new-chat",
        element: <NewChatAgentSelection />,
      },
      {
        path: "/new-chat/:agent-id",
        element: <Chat />,
      },
      {
        path: "chat/:sessionId",
        element: <Chat />,
      },
      {
        path: "monitoring/kpis",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <Kpis />
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/runtime",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <Runtime />
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/data",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <DataHub />
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/graph",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <GraphHub />
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
            <Logs />
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/rebac-backfill",
        element: (
          <ProtectedRoute resource="tag" action="update">
            <RebacBackfill />
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/processors",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <ProcessorBench />
          </ProtectedRoute>
        ),
      },
      {
        path: "monitoring/processors/runs/:runId",
        element: (
          <ProtectedRoute resource="kpi" action="create">
            <ProcessorRunDetail />
          </ProtectedRoute>
        ),
      },
      {
        path: "settings",
        element: <Profile />,
      },
      {
        path: "knowledge",
        element: <KnowledgeHub />,
      },
      {
        path: "test-renderer",
        element: <RendererPlayground />,
      },
      {
        path: "agents",
        element: <AgentHub />,
      },
      {
        path: "tools",
        element: <McpHub />,
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
  {
    path: "*",
    element: (
      <RootLayout>
        <PageError />
      </RootLayout>
    ),
  },
];

export const router = createBrowserRouter(routes, { basename });
