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

import type { ReactNode } from "react";
import { useFrontendFeatureFlag, type FrontendFeatureFlagName } from "@hooks/useFrontendFeatureFlag.ts";

interface FrontendFeatureGateProps {
  flag: FrontendFeatureFlagName;
  children: ReactNode;
  /** Hidden surfaces render nothing unless a route supplies a not-found view. */
  fallback?: ReactNode;
}

/** Generic fail-closed gate for UI surfaces controlled by frontend bootstrap. */
export function FrontendFeatureGate({ flag, children, fallback = null }: FrontendFeatureGateProps) {
  const { enabled, isLoading } = useFrontendFeatureFlag(flag);
  if (isLoading) return null;
  return enabled ? <>{children}</> : <>{fallback}</>;
}
