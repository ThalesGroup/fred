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

// Stock chat-turn control for the MCP capability's `search_policy` widget
// (CAPAB-01 #1976, RFC §3.3). Extracted from the former bespoke `SearchConfig`
// molecule's policy row. `params.default` only seeds `useComposerSettings`'s
// initial value (RFC §3.7) — the row itself reads/writes the live
// `composer.searchPolicy` state, which still travels to the pod on
// `RuntimeContext.search_policy` exactly as before extraction.

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { SearchPolicyName } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { EnumSelectRow, type EnumSelectOption } from "@shared/molecules/EnumSelectRow/EnumSelectRow";
import type { CapabilityChatTurnControlProps } from "../types";

export interface SearchPolicyControlParams {
  default?: SearchPolicyName;
}

export function SearchPolicyControl({ composer, open, onToggleOpen }: CapabilityChatTurnControlProps) {
  const { t } = useTranslation();

  const options = useMemo<EnumSelectOption<SearchPolicyName>[]>(
    () => [
      { value: "strict", label: t("search.strict") },
      { value: "hybrid", label: t("search.hybrid") },
      { value: "semantic", label: t("search.semantic") },
    ],
    [t],
  );

  return (
    <EnumSelectRow
      icon={{ category: "outlined", type: "search" }}
      label={t("chatbot.composerSettings.searchPolicyRowLabel")}
      title={t("chatbot.composerSettings.searchPolicyTitle")}
      value={composer.searchPolicy}
      options={options}
      open={open}
      onToggle={onToggleOpen}
      onChange={(value) => {
        composer.onSearchPolicyChange(value);
        // Selecting a value closes this row's submenu, mirroring the former
        // SearchConfig's `setOpenMenu(null)` on choice. The row is open when a
        // choice is made, so toggling collapses it (never re-opens another row).
        onToggleOpen();
      }}
    />
  );
}
