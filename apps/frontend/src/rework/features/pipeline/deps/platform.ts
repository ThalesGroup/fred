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
import { controlPlaneApi } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { knowledgeFlowApi } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { KeyCloakService } from "../../../../security/KeycloakService";
import { personalTeamId } from "../../../components/shared/utils/teamId";
import type { PlatformDeps } from "../scenarios/platformScenario";
import { FRESH, useApiDispatch } from "./api";

export function usePlatformDeps(): PlatformDeps {
  const dispatch = useApiDispatch();
  const teamId = personalTeamId(KeyCloakService.GetUserId() ?? "");
  return useMemo(() => {
    const cp = controlPlaneApi.endpoints;
    const kf = knowledgeFlowApi.endpoints;
    return {
      controlPlaneHealth: async () => {
        await dispatch(cp.healthzControlPlaneV1HealthzGet.initiate(undefined, FRESH)).unwrap();
        await dispatch(cp.readyControlPlaneV1ReadyGet.initiate(undefined, FRESH)).unwrap();
      },
      knowledgeFlowHealth: async () => {
        await dispatch(kf.healthzKnowledgeFlowV1HealthzGet.initiate(undefined, FRESH)).unwrap();
        await dispatch(kf.readyKnowledgeFlowV1ReadyGet.initiate(undefined, FRESH)).unwrap();
      },
      platformRoles: async () => {
        const bootstrap = await dispatch(
          cp.getFrontendBootstrapControlPlaneV1FrontendBootstrapGet.initiate(undefined, FRESH),
        ).unwrap();
        return bootstrap.permissions?.platform_roles ?? [];
      },
      frontendConfig: () =>
        dispatch(cp.getFrontendConfigControlPlaneV1FrontendConfigGet.initiate(undefined, FRESH)).unwrap(),
      tokenClaims: () => KeyCloakService.GetTokenParsed() ?? null,
      // A response header is beyond what the generated client exposes; the route is public.
      serverDate: async () => {
        const response = await fetch("/control-plane/v1/healthz", { credentials: "omit", cache: "no-store" });
        const header = response.headers.get("Date");
        return header ? new Date(header) : null;
      },
      templates: () =>
        dispatch(
          cp.getTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGet.initiate(
            { teamId, includeNonPublic: true },
            FRESH,
          ),
        ).unwrap(),
      modelProfiles: () =>
        dispatch(
          cp.getAvailableModelProfilesControlPlaneV1TeamsTeamIdRoutingPolicyAvailableModelsGet.initiate(
            { teamId },
            FRESH,
          ),
        ).unwrap(),
      capabilities: async () =>
        (await dispatch(cp.getAdminCapabilitiesControlPlaneV1AdminCapabilitiesGet.initiate(undefined, FRESH)).unwrap())
          .items ?? [],
      reads: [
        {
          id: "model-binding",
          title: "The platform model binding can be read",
          read: async () => {
            const binding = await dispatch(
              cp.getPlatformModelBindingControlPlaneV1AdminPlatformModelBindingsGet.initiate(undefined, FRESH),
            ).unwrap();
            return binding.binding ? "a platform binding fixes the chat model" : "no platform binding";
          },
        },
        {
          id: "knowledge-bases",
          title: "Knowledge base definitions can be read",
          read: async () => {
            const list = await dispatch(
              cp.listKnowledgeBaseDefinitionsControlPlaneV1KnowledgeBasesDefinitionsGet.initiate({ teamId }, FRESH),
            ).unwrap();
            return `${list.length} definition(s)`;
          },
        },
        {
          id: "ui-settings",
          title: "Interface settings can be read",
          read: async () => {
            await dispatch(
              cp.getPlatformUiSettingsControlPlaneV1AdminPlatformUiSettingsGet.initiate(undefined, FRESH),
            ).unwrap();
            return "read";
          },
        },
        {
          id: "announcements",
          title: "Announcements can be read",
          read: async () => {
            const list = await dispatch(
              cp.listAnnouncementsControlPlaneV1AdminPlatformAnnouncementsGet.initiate(undefined, FRESH),
            ).unwrap();
            return `${list.length} announcement(s)`;
          },
        },
        {
          id: "purge-policy",
          title: "The data retention policy can be read",
          read: async () => {
            await dispatch(cp.getPurgePolicySummaryControlPlaneV1PoliciesPurgeGet.initiate(undefined, FRESH)).unwrap();
            return "read";
          },
        },
      ],
      now: () => Date.now(),
    };
  }, [dispatch, teamId]);
}
