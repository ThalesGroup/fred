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
 * Obtain a short-lived test account token independently of the operator's session.
 * Password grants must be enabled on the test client.
 */
export async function loginWithPassword(
  config: KeycloakRealmConfig,
  username: string,
  password: string,
  signal?: AbortSignal,
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
    const timeout = AbortSignal.timeout(15_000);
    response = await fetch(tokenUrl, {
      method: "POST",
      credentials: "omit",
      redirect: "error",
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
  } catch {
    throw new Error("Could not reach the test account sign-in endpoint");
  }

  const payload = (await response.json().catch(() => null)) as {
    error?: string;
    access_token?: string;
  } | null;
  if (!response.ok) {
    const errorCode = payload?.error;
    if (errorCode === "unauthorized_client" || errorCode === "invalid_client") {
      throw new Error("This Keycloak client does not allow direct-grant login for test accounts");
    }
    if (response.status === 401 || errorCode === "invalid_grant") {
      throw new Error("Invalid test account username or password");
    }
    throw new Error(`Test account sign-in failed: HTTP ${response.status}`);
  }

  if (typeof payload?.access_token !== "string" || !payload.access_token.trim()) {
    throw new Error("Test account sign-in returned no usable access token");
  }
  return payload.access_token;
}
