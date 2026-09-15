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

import { useFrontendBootstrap } from "../../../hooks/useFrontendBootstrap";
import { KeyCloakService } from "../../../security/KeycloakService";
import type { UserCapabilities } from "../../types/conversation.ts";

/**
 * Single source of truth for "which platform roles do I hold" on the frontend.
 *
 * Every flag below reads `PermissionSummary.platform_roles` (control-plane
 * `/frontend/bootstrap`), which is OpenFGA-derived (AUTHZ-05 review item 4) —
 * never Keycloak roles. The list is union-resolved server-side and every role
 * relation unions in `platform_admin`, so a `platform_admin` holds all of them
 * and never loses a surface to a narrower flag. `canDebug` stays
 * Keycloak-role-based: it gates a developer affordance, not an admin surface.
 */
export function useUserCapabilities(): UserCapabilities {
  const { bootstrap, isLoading } = useFrontendBootstrap();
  const canDebug = KeyCloakService.GetUserRoles().includes("admin");
  const roles = bootstrap?.permissions?.platform_roles ?? [];
  return {
    canDebug,
    canAdmin: roles.includes("platform_admin"),
    canObservePlatform: roles.includes("platform_observer"),
    canManageTeams: roles.includes("team_manager"),
    canManageFeatures: roles.includes("feature_manager"),
    canEditPlatformPrompt: roles.includes("prompt_editor"),
    canEditSessions: true,
    canDeleteSessions: true,
    isLoading,
  };
}
