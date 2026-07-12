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

import type { KeycloakRealmConfig } from "../../../security/KeycloakService";

/**
 * Short-lived Keycloak password-grant login, used only by the admin
 * self-test's "test another profile" diagnostic (`authzProbeScenario.ts`).
 * Never touches the app's own session — the token this returns is held only
 * for the duration of that one probe run and then discarded.
 *
 * Requires the target realm/client to have `directAccessGrantsEnabled`,
 * documented as test/dev-only (`fred-deployment-factory/validation/README.md`).
 * On a realm where it's off, Keycloak rejects the grant and this throws a
 * message that says so, rather than "wrong password".
 */
export async function loginWithPassword(
  config: KeycloakRealmConfig,
  username: string,
  password: string,
): Promise<string> {
  const tokenUrl = `${config.url}realms/${config.realm}/protocol/openid-connect/token`;
  const body = new URLSearchParams({
    grant_type: "password",
    client_id: config.clientId,
    username,
    password,
  });

  let response: Response;
  try {
    response = await fetch(tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch (err) {
    throw new Error(`could not reach Keycloak at ${tokenUrl}: ${(err as Error).message}`);
  }

  if (!response.ok) {
    let errorCode: string | undefined;
    try {
      errorCode = (await response.json())?.error;
    } catch {
      // body wasn't JSON — fall through with no error code
    }
    if (response.status === 401 || errorCode === "invalid_grant") {
      throw new Error(`invalid username or password for '${username}'`);
    }
    if (errorCode === "unauthorized_client" || errorCode === "invalid_client") {
      throw new Error(
        "this realm/client does not allow direct-grant (password) login — that's a test/dev-only Keycloak " +
          "setting, so this diagnostic isn't available on this deployment",
      );
    }
    throw new Error(`Keycloak token request failed: HTTP ${response.status}${errorCode ? ` (${errorCode})` : ""}`);
  }

  const payload = (await response.json()) as { access_token?: string };
  if (!payload.access_token) throw new Error("Keycloak token response had no access_token");
  return payload.access_token;
}
