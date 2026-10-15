// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { createBrowserRouter, Navigate, type RouteObject } from "react-router-dom";
import GcuGuard from "@core/guards/GcuGuard";
import BootstrapGuard from "@core/guards/BootstrapGuard";
import MainLayout from "@shared/layouts/MainLayout/MainLayout";
import HomePage from "@components/pages/HomePage/HomePage";
import ProvisioningPage from "@components/pages/admin/ProvisioningPage/ProvisioningPage";
import { getConfig } from "./config";

// Only implemented destinations mount; hidden links alone would leave legacy calls reachable.
export const routes: RouteObject[] = [
  {
    path: "/",
    element: (
      <GcuGuard>
        <BootstrapGuard>
          <MainLayout />
        </BootstrapGuard>
      </GcuGuard>
    ),
    children: [
      { index: true, element: <Navigate to="/home" replace /> },
      { path: "home", element: <HomePage /> },
      { path: "admin", element: <Navigate to="/admin/provisioning" replace /> },
      { path: "admin/provisioning", element: <ProvisioningPage /> },
      { path: "*", element: <Navigate to="/home" replace /> },
    ],
  },
];

export const router = createBrowserRouter(routes, { basename: getConfig().frontend_basename });
