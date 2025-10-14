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

/**
 * Custom hook to retrieve the raw JWT/access token from Keycloak.
 * * * This utilizes KeyCloakService.GetToken(), which handles both production (real KC token) 
 * and development (local dev admin token) modes correctly.
 * * @returns The raw access token string, or undefined if not authenticated.
 */
export function useAuthToken(): string | undefined {
  // Retrieve the token using the service's defined getter
  const token = KeyCloakService.GetToken();
  
  // GetToken returns string | null, so we cast null to undefined for TypeScript
  return token || undefined;
}