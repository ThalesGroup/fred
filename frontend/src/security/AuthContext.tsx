// src/security/AuthContext.tsx
import React from "react";
import { KeyCloakService } from "./KeycloakService";

type Role = "admin" | "contributor" | "viewer";

type AuthState = {
  userId: string | null;
  roles: Role[];
  isAuthenticated: boolean;
};

const AuthContext = React.createContext<AuthState | null>(null);

export const AuthProvider: React.FC<React.PropsWithChildren> = ({ children }) => {
  // Pull once from Keycloak (or subscribe if your SDK supports updates)
  const kcRoles = KeyCloakService.GetUserRoles() as Role[]; // ensure this returns strings you map to Role
  const state: AuthState = {
    userId: KeyCloakService.GetUserId?.() ?? null,
    roles: kcRoles ?? [],
    isAuthenticated: !!kcRoles,
  };

  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
};

export function useAuth() {
  const ctx = React.useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}
