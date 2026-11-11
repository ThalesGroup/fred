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

import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties";

/** Apply deployment labels to analytics copy, including chart hints and empty states. */
export function useAnalyticsTranslation() {
  const translation = useTranslation();
  const { agentsNicknamePlural, agentsNicknameSingular } = useFrontendProperties();
  const labels = {
    agentsNicknamePlural,
    agentsNicknameSingular,
    agentsNicknamePluralLowercase: agentsNicknamePlural.toLowerCase(),
    agentsNicknameSingularLowercase: agentsNicknameSingular.toLowerCase(),
  };
  const t = ((key: string, options?: Record<string, unknown>) =>
    translation.t(key, { ...labels, ...options })) as typeof translation.t;
  return { ...translation, t };
}
