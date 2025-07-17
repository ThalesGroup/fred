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
import { Chat } from "../pages/Chat";
import { Profile } from "../pages/Profile";
import { ExplainWorkload } from "../frugalit/pages/ExplainWorkload";
import { PageError } from "../pages/PageError";
import { Scores } from "../pages/Scores";
import { ExplainNamespace } from "../frugalit/pages/ExplainNamespace";
import { ExplainCluster } from "../frugalit/pages/ExplainCluster";
import { FactsWorkload } from "../frugalit/pages/FactsWorkload";
import { FactsCluster } from "../frugalit/pages/FactsCluster";
import { FactsNamespace } from "../frugalit/pages/FactsNamespace";
import { DocumentLibrary } from "../pages/DocumentLibrary";
import { AgentHub } from "../pages/AgentHub";
import { Optimize } from "../frugalit/pages/Optimize";
import { Geomap } from "../warfare/pages/TheaterOfOperations";
import { ProtectedRoute } from "../components/ProtectedRoute";
import { FootprintContextProvider } from "./FootprintContextProvider";
import { ExplainContextProvider } from "./ExplainContextProvider";
import { FeatureFlagKey, isFeatureEnabled } from "../common/config";
import { LayoutWithSidebar } from "./LayoutWithSidebar";
import { Explain } from "../frugalit/pages/Explain";
import { Facts } from "../frugalit/pages/Facts";
import { Audit } from "../pages/Audit";
import { FrugalIt } from "../pages/FrugalIt";
import Inspect from "../frugalit/pages/Inspect";
import { Monitoring } from "../pages/Monitoring";
import { Workspaces } from "../pages/Workspaces";
import { K8ApplicationContextProvider } from "./K8ApplicationContextProvider";

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
        element: isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) ? (
          <K8ApplicationContextProvider>
            <FootprintContextProvider>
              <FrugalIt />
            </FootprintContextProvider>
          </K8ApplicationContextProvider>
        ) : (
          <Chat />
        ),
      },

      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "score/:cluster/:namespace/:application",
        element:  <K8ApplicationContextProvider><Scores /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "audit",
        element: <K8ApplicationContextProvider><Audit /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "facts",
        element: <K8ApplicationContextProvider><Facts /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "facts-workload",
        element: <K8ApplicationContextProvider><FactsWorkload /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "facts-cluster",
        element: <K8ApplicationContextProvider><FactsCluster /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "facts-namespace",
        element: <K8ApplicationContextProvider><FactsNamespace /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "explain",
        element: <K8ApplicationContextProvider><Explain /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "explain-cluster",
        element: <K8ApplicationContextProvider><ExplainCluster /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "explain-namespace",
        element: <K8ApplicationContextProvider><ExplainNamespace /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "explain-workload",
        element: (
          <K8ApplicationContextProvider>
          <ExplainContextProvider>
            <ExplainWorkload />
          </ExplainContextProvider>
          </K8ApplicationContextProvider>
        ),
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "optimize",
        element:  <K8ApplicationContextProvider><Optimize /></K8ApplicationContextProvider>,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "inspect",
        element: (
           <K8ApplicationContextProvider>
          <FootprintContextProvider>
            <Inspect />
          </FootprintContextProvider>
          </K8ApplicationContextProvider>
        ),
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "geomap",
        element: <Geomap />,
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
        path: "documentLibrary",
        element: <DocumentLibrary />,
      },
      {
        path: "agentHub",
        element: <AgentHub />,
      },
      {
        path: "workspaces",
        element: <Workspaces />,
      },
    ].filter(Boolean),
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
