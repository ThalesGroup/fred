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

import { useEffect, useState } from "react";
import { getConfig, loadPermissions } from "../common/config";
import { KeyCloakService } from "./KeycloakService";

// Get the current user’s role based on Keycloak roles
function getCurrentRole(): string {
  const roles = KeyCloakService.GetUserRoles() || [];
  if (roles.includes("admin")) return "admin";
  if (roles.includes("editor")) return "editor";
  if (roles.includes("service_agent")) return "service_agent";
  return "viewer";
}

// Hook to check permissions
export const usePermissions = () => {
  const [permissions, setPermissions] = useState<string[]>(getConfig().permissions);

  // Loads permissions at mount time
  useEffect(() => {
    const fetchPermissions = async () => {
      const perms = await loadPermissions();
      setPermissions(perms);
    };
    fetchPermissions();
  }, []);

  const can = (resource: string, action: string) =>
    permissions.some(p => p.toLowerCase() === `${resource}:${action}`.toLowerCase());

  const refreshPermissions = async () => {
    const perms = await loadPermissions();
    setPermissions(perms);
  };

  return { permissions, can, refreshPermissions, role: getCurrentRole() };
};
