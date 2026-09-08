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

import { useFrontendBootstrap } from "../../../hooks/useFrontendBootstrap.ts";
import type { FrontendFeatureFlags } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";

/** Only control-plane-declared frontend flags can be requested by UI code. */
export type FrontendFeatureFlagName = keyof FrontendFeatureFlags;

export interface FrontendFeatureFlagState {
  enabled: boolean;
  isLoading: boolean;
}

/** Pure fail-closed resolver shared by the hook and its focused tests. */
export function resolveFrontendFeatureFlag(
  flags: FrontendFeatureFlags | undefined,
  name: FrontendFeatureFlagName,
): boolean {
  return flags?.[name] === true;
}

/** Read one typed flag from the authenticated control-plane bootstrap. */
export function useFrontendFeatureFlag(name: FrontendFeatureFlagName): FrontendFeatureFlagState {
  const { bootstrap, isLoading } = useFrontendBootstrap();
  return {
    enabled: resolveFrontendFeatureFlag(bootstrap?.feature_flags, name),
    isLoading,
  };
}
