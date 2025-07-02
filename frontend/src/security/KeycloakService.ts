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

import Keycloak from "keycloak-js";

const USE_AUTH = (import.meta.env.VITE_USE_AUTH || "false") === "true";
const keycloakInstance = USE_AUTH ? new Keycloak() : null;

/**
 * Initializes Keycloak instance and calls the provided callback function if successfully authenticated.
 *
 * @param onAuthenticatedCallback
 */
const Login = (onAuthenticatedCallback: Function) => {
  console.log("Login called", USE_AUTH);

  if (USE_AUTH) {
    keycloakInstance
      .init({
        onLoad: "login-required",
        pkceMethod: "S256",
        checkLoginIframe: false,
      })
      .then(function (authenticated) {
        if (authenticated) {
          // Store the token in localStorage (or sessionStorage)
          localStorage.setItem("keycloak_token", keycloakInstance.token);
          onAuthenticatedCallback();
        } else {
          alert("User not authenticated");
        }
      })
      .catch((e) => {
        console.dir(e);
        console.log(`keycloak init exception: ${e}`);
      });
  } else {
    onAuthenticatedCallback();
  }
};

const Logout = () => {
  if (USE_AUTH) {
    sessionStorage.clear();
    keycloakInstance.logout({
      redirectUri: window.location.origin + "/", // Ensure this matches Keycloak's allowed URIs
    });
  }
};

const refreshToken = () => {
  if (USE_AUTH) {
    if (keycloakInstance.isTokenExpired()) {
      console.log("Token expired, refreshing...");
      keycloakInstance
        .updateToken(30)
        .then((refreshed) => {
          if (refreshed) {
            console.log("Token refreshed:", keycloakInstance.token);
            localStorage.setItem("keycloak_token", keycloakInstance.token);
          }
        })
        .catch(() => {
          console.log("Failed to refresh token, forcing re-authentication");
          keycloakInstance.login();
        });
    }
  } else {
    console.log("No token to refresh, using default authentication");
  }
};

// Schedule token refresh
setInterval(refreshToken, 300000); // Every 30s

const GetRealmRoles = (): string[] => {
  if (USE_AUTH) {
    const resourceAccess = keycloakInstance.tokenParsed?.realm_access;
    return resourceAccess?.roles || [];
  }
  return ["admin"];
};
const GetUserRoles = (): string[] => {
  if (!USE_AUTH) {
    return ["admin"];
  }
  const clientRoles = keycloakInstance.tokenParsed?.resource_access?.[keycloakInstance.clientId]?.roles || [];
  return [...clientRoles]; // Merge both
};

const GetUserName = (): string => {
  if (USE_AUTH) {
    return keycloakInstance.tokenParsed.preferred_username;
  }
  return "admin"; // Default to "admin" if no authentication is used
};

const GetUserFullName = (): string => {
  if (USE_AUTH) {
    return keycloakInstance.tokenParsed.name;
  }
  return "Admin Istrator"; // Default to "Admin Istrator" if no authentication is used
};

const GetUserMail = (): string => {
  if (USE_AUTH && keycloakInstance?.tokenParsed) {
    // Au choix, "name", "preferred_username", "email", ...
    return keycloakInstance.tokenParsed.email || "user@mail.com";
  }
  return "admin@mail.com";
};

const GetUserId = (): string => {
  if (USE_AUTH && keycloakInstance?.tokenParsed) {
    return keycloakInstance.tokenParsed.sub || "admin";
  }
  return "admin";
};
/**
 * Renvoie le token brut pour l'ajouter dans Authorization: Bearer <token>.
 */
const GetToken = (): string | null => {
  if (USE_AUTH && keycloakInstance?.token) {
    return keycloakInstance.token;
  }
  return null;
};

/**
 * Renvoie tout le token décodé (claims) si dispo, sinon null.
 */
const GetTokenParsed = (): any => {
  if (USE_AUTH && keycloakInstance?.tokenParsed) {
    return keycloakInstance.tokenParsed;
  }
  return null;
};

export const KeyCloakService = {
  CallLogin: Login,
  CallLogout: Logout,
  GetUserName: GetUserName,
  GetUserId: GetUserId,
  GetUserFullName: GetUserFullName,
  GetUserMail: GetUserMail,
  GetToken: GetToken,
  GetRealmRoles: GetRealmRoles,
  GetUserRoles: GetUserRoles,
  GetTokenParsed,
};
