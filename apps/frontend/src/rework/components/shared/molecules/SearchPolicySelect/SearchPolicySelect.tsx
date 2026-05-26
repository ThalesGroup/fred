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
import type { SearchPolicyName } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { OptionModel } from "@models/Option.model";
import Select from "@shared/molecules/Select/Select.tsx";

type Props = {
  value: SearchPolicyName;
  onChange: (next: SearchPolicyName) => void;
  disabled?: boolean;
};

export function SearchPolicySelect({ value, onChange, disabled }: Props) {
  const { t } = useTranslation();

  const options: OptionModel<SearchPolicyName>[] = [
    { key: "strict", value: "strict", label: t("search.strict"), description: t("search.strictDescription") },
    { key: "hybrid", value: "hybrid", label: t("search.hybrid"), description: t("search.hybridDescription") },
    { key: "semantic", value: "semantic", label: t("search.semantic"), description: t("search.semanticDescription") },
  ];

  return <Select options={options} value={value} onChange={onChange} size="small" disabled={disabled} />;
}
