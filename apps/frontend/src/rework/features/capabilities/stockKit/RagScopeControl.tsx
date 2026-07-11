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

// Stock chat-turn control for the MCP capability's `rag_scope` widget
// (CAPAB-01 #1976, RFC §3.3). Extracted from the former bespoke `SearchConfig`
// molecule's scope row. `params.default` only seeds `useComposerSettings`'s
// initial value (RFC §3.7) — the row itself reads/writes the live
// `composer.ragScope` state, which still travels to the pod on
// `RuntimeContext.search_rag_scope` exactly as before extraction.

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { EnumSelectRow, type EnumSelectOption } from "@shared/molecules/EnumSelectRow/EnumSelectRow";
import type { CapabilityChatTurnControlProps, RagScopeName } from "../types";

export interface RagScopeControlParams {
  default?: RagScopeName;
}

export function RagScopeControl({ composer, open, onToggleOpen }: CapabilityChatTurnControlProps) {
  const { t } = useTranslation();

  const options = useMemo<EnumSelectOption<RagScopeName>[]>(
    () => [
      { value: "corpus_only", label: t("chatbot.composerSettings.scopeCorpus") },
      { value: "hybrid", label: t("chatbot.composerSettings.scopeCorpusAndWeb") },
      { value: "general_only", label: t("chatbot.composerSettings.scopeGeneral") },
    ],
    [t],
  );

  return (
    <EnumSelectRow
      icon={{ category: "outlined", type: "hub" }}
      label={t("chatbot.composerSettings.scopeRowLabel")}
      title={t("chatbot.composerSettings.scopeTitle")}
      value={composer.ragScope}
      options={options}
      open={open}
      onToggle={onToggleOpen}
      onChange={(value) => {
        composer.onRagScopeChange(value);
        onToggleOpen();
      }}
    />
  );
}
