// Copyright Thales 2026
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

import { Navigate } from "react-router-dom";
import { useUserCapabilities } from "@hooks/useUserCapabilities.ts";

/**
 * `"admin"` — only `canAdmin` (org-level `platform_admin`).
 * `"observer"` — `canAdmin` or `canObservePlatform`, so an admin never loses
 * an observer-gated page (mirrors the OpenFGA schema, where `platform_admin`
 * always satisfies `platform_observer` too).
 *
 * There is no team-scoped variant here: no route in this app is guarded at
 * the router level by a team capability today — team-scoped gating happens
 * inside the page (see `useTeamCapabilities`), not on the route. Add one only
 * when a route genuinely needs it.
 */
export type ProtectedRequirement = "admin" | "observer";

/** Pure decision, isolated from React/routing so it's trivially unit-testable. */
export function isProtectedAllowed(
  requires: ProtectedRequirement,
  capabilities: { canAdmin: boolean; canObservePlatform: boolean },
): boolean {
  if (requires === "admin") return capabilities.canAdmin;
  return capabilities.canAdmin || capabilities.canObservePlatform;
}

interface ProtectedProps {
  requires: ProtectedRequirement;
  children: React.ReactNode;
}

/**
 * Single route guard for the org-level capability tier — replaces
 * `AdminProtectedRoute`, `KpiObserverProtectedRoute`, and the old
 * `resource`/`action` `ProtectedRoute` (Keycloak-role-derived, dead since
 * AUTHZ-05 removed app roles — see `docs/swift/platform/FRONTEND-AUTHZ-PATTERN.md`).
 */
export const Protected = ({ children, requires }: ProtectedProps) => {
  const { canAdmin, canObservePlatform, isLoading } = useUserCapabilities();
  // On a hard refresh, `/frontend/bootstrap` hasn't resolved yet and
  // canAdmin/canObservePlatform default to `false` — deciding here would
  // redirect every admin to `/unauthorized` on every reload, with no way
  // back (the redirect replaces history; a later capability flip doesn't
  // un-redirect it). Render nothing until the real answer is known.
  if (isLoading) return null;
  if (!isProtectedAllowed(requires, { canAdmin, canObservePlatform })) {
    return <Navigate to="/unauthorized" replace />;
  }
  return <>{children}</>;
};
