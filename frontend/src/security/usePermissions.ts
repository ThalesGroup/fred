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

// Roles consistent with backend RBAC
type Role = "admin" | "editor" | "viewer" | "service_agent";

// Permissions mapped to backend Actions/Resources
type Permission =
  | "tags:create"
  | "tags:read"
  | "tags:update"
  | "tags:delete"
  | "documents:create"
  | "documents:read"
  | "documents:update"
  | "documents:delete"
  | "resources:create"
  | "resources:read"
  | "resources:update"
  | "resources:delete"
  | "feedback:create"
  | "prompt:create"
  | "metrics:read"
  | "agents:read"
  | "sessions:create"
  | "sessions:read"
  | "sessions:update"
  | "sessions:delete"
  | "message_attachments:create";

// Role permission mapping
const rolePermissions: Record<Role, Permission[]> = {
  admin: [
    // Admin can do everything
    "tags:create", "tags:read", "tags:update", "tags:delete",
    "documents:create", "documents:read", "documents:update", "documents:delete",
    "resources:create", "resources:read", "resources:update", "resources:delete",
    "feedback:create",
    "prompt:create",
    "metrics:read",
    "agents:read",
    "sessions:create", "sessions:read", "sessions:update", "sessions:delete",
    "message_attachments:create",
  ],

  editor: [
    // Editor can CRUD most things
    "tags:create", "tags:read", "tags:update", "tags:delete",
    "documents:create", "documents:read", "documents:update", "documents:delete",
    "resources:create", "resources:read", "resources:update", "resources:delete",
    "feedback:create",
    "prompt:create",
    "metrics:read",
    "agents:read",
    "sessions:create", "sessions:read", "sessions:update", "sessions:delete",
    "message_attachments:create",
  ],

  viewer: [
    // Viewer is mostly read-only, but can create feedback, sessions, and prompts
    "tags:read",
    "documents:read",
    "resources:read",
    "metrics:read",
    "agents:read",
    "feedback:create",
    "prompt:create",
    "sessions:create", "sessions:read", "sessions:update", "sessions:delete",
    "message_attachments:create",
  ],

  service_agent: [
    // Read-only for selected resources
    "tags:read",
    "documents:read",
    "resources:read",
  ],
};

// Get the current user’s role based on Keycloak roles
function getCurrentRole(): Role {
  const roles = KeyCloakService.GetUserRoles() || [];
  if (roles.includes("admin")) return "admin";
  if (roles.includes("editor")) return "editor";
  if (roles.includes("service_agent")) return "service_agent";
  return "viewer";
}

// Hook to check permissions
export function usePermissions() {
  const role = getCurrentRole();
  const can = (perm: Permission): boolean =>
    rolePermissions[role]?.includes(perm) ?? false;
  return { role, can };
}
