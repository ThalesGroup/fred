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

import { createBrowserRouter, RouteObject } from "react-router-dom";
import { LayoutWithSidebar } from "../app/LayoutWithSidebar";
import RendererPlayground from "../components/markdown/RenderedPlayground";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { AgentHub } from "../pages/AgentHub";
import Chat from "../pages/Chat";
import { KnowledgeHub } from "../pages/KnowledgeHub";
import { Kpis } from "../pages/Kpis";
import Logs from "../pages/Logs";
import { PageError } from "../pages/PageError";
import Unauthorized from "../pages/PageUnauthorized";
import { Profile } from "../pages/Profile";

const RootLayout = ({ children }: React.PropsWithChildren<{}>) => (
  <LayoutWithSidebar>{children}</LayoutWithSidebar>
);

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <RootLayout />,
    children: [
      {
        index: true,
        element: <Chat />,
      },
      {
        path: "chat",
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
        path: "account",
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
        path: "agentHub",
        element: <AgentHub />,
      },
    ].filter(Boolean),
  },
  {
    path: "unauthorized",
    element: <Unauthorized />,
  },
  {
    path: "/knowledge",
    element: (
      <RootLayout>
        <KnowledgeHub />
      </RootLayout>
    ),
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

export const router = createBrowserRouter(routes);
