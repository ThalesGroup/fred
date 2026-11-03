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
import { useMemo } from "react";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { personalTeamId } from "../../../components/shared/utils/teamId";
import type { AuthorizationDeps } from "../scenarios/authorizationScenario";
import { authedFetch, authzProbeDeps } from "../useAuthzProbeRun";

/** Explicit tokens, never the app session: the sweeps need missing and forged credentials. */
export function useAuthorizationDeps(): AuthorizationDeps {
  const uid = KeyCloakService.GetUserId() ?? "";
  return useMemo(
    () => ({
      probe: authzProbeDeps,
      request: (path, token) => authedFetch(path, token),
      token: async () => ((await KeyCloakService.ensureFreshToken(30)) ? KeyCloakService.GetToken() : null),
      personalTeamId: personalTeamId(uid),
    }),
    [uid],
  );
}
