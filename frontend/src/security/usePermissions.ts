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
  contributor: [
    "document:create",
    "document:toggleRetrievable",
    "document:view",
    "prompt:create",
    "agent:run",
  ],
  viewer: [
    "document:view",
    "agent:run",
  ],
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