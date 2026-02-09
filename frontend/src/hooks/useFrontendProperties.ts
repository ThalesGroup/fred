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

import { useMemo } from "react";
import { useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery } from "../slices/agentic/agenticOpenApi";
import type { Properties } from "../slices/agentic/agenticOpenApi";

/**
 * Custom hook to access frontend properties from the configuration.
 *
 * This hook wraps the frontend config query and exposes only the properties object.
 * The query is configured with aggressive caching since frontend config rarely changes
 * (only on helm chart redeployment).
 *
 * @returns The frontend properties object containing configuration like agentsNickname, etc.
 */
export function useFrontendProperties(): Properties {
  const { data: frontendConfig } = useGetFrontendConfigAgenticV1ConfigFrontendSettingsGetQuery(
    undefined,
    {
      // Cache for 1 hour (3600 seconds) since config rarely changes
      pollingInterval: 0,
      // Keep unused data in cache for 1 hour
      refetchOnMountOrArgChange: 3600,
      // Keep data fresh in cache even when component unmounts
      refetchOnFocus: false,
      refetchOnReconnect: false,
    }
  );

  return useMemo(() => {
    return frontendConfig?.frontend_settings?.properties || ({} as Properties);
  }, [frontendConfig]);
}
