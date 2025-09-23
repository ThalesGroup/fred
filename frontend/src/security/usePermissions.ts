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

import { KeyCloakService } from "./KeycloakService";

type Role = "admin" | "contributor" | "viewer";
type Permission =
  | "document:create"
  | "document:delete"
  | "document:toggleRetrievable"
  | "document:view"
  | "library:create"
  | "library:delete"
  | "prompt:create"
  | "prompt:delete"
  | "agent:run";

const rolePermissions: Record<Role, Permission[]> = {
  admin: [
    "document:create",
    "document:delete",
    "document:toggleRetrievable",
    "document:view",
    "library:create",
    "library:delete",
    "prompt:create",
    "prompt:delete",
    "agent:run",
  ],
  contributor: ["document:create", "document:toggleRetrievable", "document:view", "prompt:create", "agent:run"],
  viewer: ["document:view", "agent:run"],
};

function getCurrentRole(): Role {
  const roles = KeyCloakService.GetUserRoles() || [];
  if (roles.includes("admin")) return "admin";
  if (roles.includes("editor") || roles.includes("contributor")) return "contributor";
  return "viewer";
}

export function usePermissions() {
  const role = getCurrentRole();
  const can = (perm: Permission) => rolePermissions[role]?.includes(perm) ?? false;
  return { role, can };
}
