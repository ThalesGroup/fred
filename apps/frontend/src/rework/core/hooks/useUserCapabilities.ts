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

import { useMemo } from "react";
import { KeyCloakService } from "../../../security/KeycloakService";
import type { UserCapabilities } from "../../types/conversation.ts";

export function useUserCapabilities(): UserCapabilities {
  return useMemo(() => {
    const roles = KeyCloakService.GetUserRoles();
    const isAdmin = roles.includes("admin");
    return {
      canDebug: isAdmin,
      canAdmin: isAdmin,
      canEditSessions: true,
      canDeleteSessions: true,
    };
  }, []);
}
