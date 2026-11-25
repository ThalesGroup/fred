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

/** Legacy platform flags come from bootstrap; conversation capture is disabled in Weaver.
 * `canDebug` only gates the developer's raw-message view.
 */
export function useUserCapabilities(skip = false): UserCapabilities {
  const { bootstrap, isLoading } = useFrontendBootstrap(skip);
  const canDebug = KeyCloakService.GetUserRoles().includes("admin");
  const roles = bootstrap?.permissions?.platform_roles ?? [];
  return {
    canDebug,
    canAdmin: roles.includes("platform_admin"),
    canObservePlatform: roles.includes("platform_observer"),
    canManageTeams: roles.includes("team_manager"),
    canManagePlatformAccess: roles.includes("platform_access_manager"),
    canManageFeatures: roles.includes("feature_manager"),
    canEditPlatformPrompt: roles.includes("prompt_editor"),
    canManageConversationTraces: false,
    canConfigureConversationTraces: false,
    canEditSessions: true,
    canDeleteSessions: true,
    isLoading,
  };
}
