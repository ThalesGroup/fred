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
import { Profile } from "../pages/Profile";
import { PageError } from "../pages/PageError";
import { KnowledgeHub } from "../pages/KnowledgeHub";
import { AgentHub } from "../pages/AgentHub";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { LayoutWithSidebar } from "../app/LayoutWithSidebar";
import { Monitoring } from "../pages/Monitoring";
import Chat from "../pages/Chat";

const RootLayout = ({ children }: React.PropsWithChildren<{}>) => (
  <ProtectedRoute permission="viewer">
    <LayoutWithSidebar>{children}</LayoutWithSidebar>
  </ProtectedRoute>
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
        path: "monitoring",
        element: <Monitoring />,
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
        path: "agentHub",
        element: <AgentHub />,
      },
    ].filter(Boolean),
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
