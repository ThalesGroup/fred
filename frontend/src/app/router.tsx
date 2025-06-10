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
import { ChatProfiles } from "../pages/ChatProfiles";

const RootLayout = () => (
  <ProtectedRoute permission="viewer">
    <LayoutWithSidebar />
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
          <FootprintContextProvider>
            <FrugalIt />
          </FootprintContextProvider>
        ) : (
          <FootprintContextProvider>
            <Chat />
          </FootprintContextProvider>
        ),
      },

      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "score/:cluster/:namespace/:application",
        element: <Scores />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "audit",
        element: <Audit />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "facts",
        element: <Facts />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "facts-workload",
        element: <FactsWorkload />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "facts-cluster",
        element: <FactsCluster />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "facts-namespace",
        element: <FactsNamespace />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "explain",
        element: <Explain />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "explain-cluster",
        element: <ExplainCluster />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "explain-namespace",
        element: <ExplainNamespace />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "explain-workload",
        element: (
          <ExplainContextProvider>
            <ExplainWorkload />
          </ExplainContextProvider>
        ),
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "optimize",
        element: <Optimize />,
      },
      isFeatureEnabled(FeatureFlagKey.ENABLE_K8_FEATURES) && {
        path: "inspect",
        element: ( 
         <FootprintContextProvider>

        
        <Inspect />
         </FootprintContextProvider>),
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
        path: "chatProfiles",
        element: <ChatProfiles />,
      },
    ].filter(Boolean),
  },
  {
    path: "*",
    element: <PageError />,
  },
];

export const router = createBrowserRouter(routes);
