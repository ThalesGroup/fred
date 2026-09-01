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

import { KeyCloakService } from "../../../security/KeycloakService.ts";
import type { FredApplicationRequest } from "./applicationHost.ts";
import { applicationServiceUrl } from "./applicationPath.ts";

const PROTECTED_HEADERS = new Set([
  "authorization",
  "cookie",
  "host",
  "proxy-authorization",
  "x-fred-application-id",
  "x-fred-team-id",
]);

interface ApplicationRequestDependencies {
  fetch: typeof fetch;
  ensureFreshToken: (minValidity?: number) => Promise<boolean>;
  getToken: () => string | null;
  logout: () => void;
}

const browserDependencies: ApplicationRequestDependencies = {
  fetch: (input, init) => fetch(input, init),
  ensureFreshToken: KeyCloakService.ensureFreshToken,
  getToken: KeyCloakService.GetToken,
  logout: KeyCloakService.CallLogout,
};

function applicationHeaders(headersInit: HeadersInit | undefined, token: string | null): Headers {
  const headers = new Headers(headersInit);
  for (const header of PROTECTED_HEADERS) {
    if (headers.has(header)) {
      throw new TypeError(`Application requests cannot set the ${header} header`);
    }
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

/** Internal factory used by the host; applications receive only its result. */
export function createApplicationRequest(
  applicationId: string,
  teamId: string,
  dependencies: ApplicationRequestDependencies = browserDependencies,
): FredApplicationRequest {
  return async (relativePath, init = {}) => {
    const url = applicationServiceUrl(applicationId, teamId, relativePath);
    const request = async (): Promise<Response> =>
      dependencies.fetch(url, {
        method: init.method,
        headers: applicationHeaders(init.headers, dependencies.getToken()),
        body: init.body,
        signal: init.signal,
        cache: "no-store",
        credentials: "omit",
      });

    await dependencies.ensureFreshToken(30);
    let response = await request();
    if (response.status !== 401) return response;

    if (await dependencies.ensureFreshToken(0)) {
      response = await request();
    }
    if (response.status === 401) dependencies.logout();
    return response;
  };
}
