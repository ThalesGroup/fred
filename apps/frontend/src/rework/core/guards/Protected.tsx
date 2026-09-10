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
import type { UserCapabilities } from "../../types/conversation.ts";

/**
 * One requirement per org-level role: `"admin"` is the full `platform_admin`
 * tier, the others are the delegated roles that own a single admin surface.
 *
 * There is no team-scoped variant here: no route in this app is guarded at
 * the router level by a team capability today — team-scoped gating happens
 * inside the page (see `useTeamCapabilities`), not on the route. Add one only
 * when a route genuinely needs it.
 */
export type ProtectedRequirement = "admin" | "observer" | "teams" | "features" | "platformPrompt";

export type ProtectedCapabilities = Pick<
  UserCapabilities,
  "canAdmin" | "canObservePlatform" | "canManageTeams" | "canManageFeatures" | "canEditPlatformPrompt"
>;

/** The capability flag that satisfies each requirement. Adding a delegated
 * role is one entry here plus one flag on `useUserCapabilities`. */
const REQUIREMENT_CAPABILITY: Record<ProtectedRequirement, keyof ProtectedCapabilities> = {
  admin: "canAdmin",
  observer: "canObservePlatform",
  teams: "canManageTeams",
  features: "canManageFeatures",
  platformPrompt: "canEditPlatformPrompt",
};

/** Pure decision, isolated from React/routing so it's trivially unit-testable.
 * `canAdmin` satisfies every requirement, mirroring the OpenFGA schema where
 * each role relation unions in `platform_admin`. */
export function isProtectedAllowed(requires: ProtectedRequirement, capabilities: ProtectedCapabilities): boolean {
  return capabilities.canAdmin || capabilities[REQUIREMENT_CAPABILITY[requires]];
}

/** Does this user reach the admin section at all? Any single delegated role
 * is enough — gating the shell on `canAdmin` would leave every new role with
 * pages it can pass `Protected` for but never navigate to. */
export function canEnterAdminSection(capabilities: ProtectedCapabilities): boolean {
  return (Object.keys(REQUIREMENT_CAPABILITY) as ProtectedRequirement[]).some((requirement) =>
    isProtectedAllowed(requirement, capabilities),
  );
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
  const { isLoading, ...capabilities } = useUserCapabilities();
  // On a hard refresh, `/frontend/bootstrap` hasn't resolved yet and every
  // role flag defaults to `false` — deciding here would redirect every admin
  // to `/unauthorized` on every reload, with no way back (the redirect
  // replaces history; a later capability flip doesn't un-redirect it).
  // Render nothing until the real answer is known.
  if (isLoading) return null;
  if (!isProtectedAllowed(requires, capabilities)) {
    return <Navigate to="/unauthorized" replace />;
  }
  return <>{children}</>;
};
