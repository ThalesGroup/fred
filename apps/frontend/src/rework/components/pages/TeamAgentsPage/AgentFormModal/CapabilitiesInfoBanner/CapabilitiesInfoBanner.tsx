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

import { ExpandableInfoContainer } from "@shared/molecules/ExpandableInfoContainer/ExpandableInfoContainer.tsx";
import { useTranslation } from "react-i18next";

/**
 * Collapsible explainer shown above the capability list in the agent form's
 * Capacités/Capabilities tab (create and edit alike) — what capabilities are,
 * in plain language, for non-technical users. Thin content wrapper around
 * the generic {@link ExpandableInfoContainer}.
 */
export function CapabilitiesInfoBanner() {
  const { t } = useTranslation();

  return (
    <ExpandableInfoContainer color="info" icon="info" title={t("rework.teams.formAgent.capabilitiesInfo.title")}>
      {t("rework.teams.formAgent.capabilitiesInfo.body")}
    </ExpandableInfoContainer>
  );
}
