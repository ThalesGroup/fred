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
 * Single source of truth for "am I platform_admin" / "am I platform_observer"
 * on the frontend.
 *
 * `canAdmin` is derived from `PermissionSummary.is_platform_admin`, and
 * `canObservePlatform` from `PermissionSummary.is_platform_observer`
 * (control-plane `/frontend/bootstrap`), both OpenFGA-derived (AUTHZ-05
 * review item 4) — never from Keycloak roles directly. `platform_admin`
 * always satisfies `canObservePlatform` too (the backend's `platform_observer`
 * relation unions in `platform_admin`, and `is_platform_observer` reflects
 * that), so admins never lose the KPI dashboard by this flag alone.
 * `canDebug` stays Keycloak-role-based: it gates a developer affordance, not
 * an admin surface.
 */
export function useUserCapabilities(): UserCapabilities {
  const { bootstrap } = useFrontendBootstrap();
  const canDebug = KeyCloakService.GetUserRoles().includes("admin");
  return {
    canDebug,
    canAdmin: bootstrap?.permissions?.is_platform_admin ?? false,
    canObservePlatform: bootstrap?.permissions?.is_platform_observer ?? false,
    canEditSessions: true,
    canDeleteSessions: true,
  };
}
