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

import { useFrontendConfigQuery } from "../../../slices/controlPlane/controlPlaneApiEnhancements";

/** Platform switch (admin "Interface" page): does the tutorial start on its own at first sign-in? */
export function useTutorialEnabled(): boolean {
  const { data } = useFrontendConfigQuery();
  return data?.onboarding_tour_enabled ?? true;
}
