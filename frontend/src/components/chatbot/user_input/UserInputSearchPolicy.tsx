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

import { ListItemText, MenuItem, Select } from "@mui/material";
import { useTranslation } from "react-i18next";

import { SearchPolicyName } from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

type Props = {
  value: SearchPolicyName;
  onChange: (next: SearchPolicyName) => void;
  disabled?: boolean;
};

export function UserInputSearchPolicy({ value, onChange, disabled }: Props) {
  const { t } = useTranslation();

  const labels: Record<SearchPolicyName, string> = {
    hybrid: t("search.hybrid", "Hybrid"),
    semantic: t("search.semantic", "Semantic"),
    strict: t("search.strict", "Strict"),
  };

  const tooltipByValue: Record<SearchPolicyName, string> = {
    hybrid: t("search.hybridDescription"),
    semantic: t("search.semanticDescription"),
    strict: t("search.strictDescription"),
  };

  const options = [
    {
      value: "strict" as const,
      label: labels.strict,
      description: tooltipByValue.strict,
    },
    {
      value: "hybrid" as const,
      label: labels.hybrid,
      description: tooltipByValue.hybrid,
    },
    {
      value: "semantic" as const,
      label: labels.semantic,
      description: tooltipByValue.semantic,
    },
  ];

  return (
    <Select
      value={value}
      disabled={disabled}
      size="small"
      onChange={(event) => onChange(event.target.value as SearchPolicyName)}
      renderValue={(selected) => labels[selected as SearchPolicyName]}
      sx={{
        borderRadius: 999,
        minWidth: 150,
        fontSize: "0.78rem",
        "& .MuiSelect-select": {
          py: 0.35,
          pl: 1.25,
          pr: 3.25,
          display: "flex",
          alignItems: "center",
        },
        "& .MuiOutlinedInput-notchedOutline": { borderColor: "divider" },
      }}
      MenuProps={{
        PaperProps: {
          sx: { mt: 0.75, maxWidth: 360 },
        },
        MenuListProps: { dense: true },
      }}
      inputProps={{ "aria-label": "search-policy" }}
    >
      {options.map((option) => (
        <MenuItem
          key={option.value}
          value={option.value}
          dense
          sx={{ alignItems: "flex-start", whiteSpace: "normal", py: 0.75 }}
        >
          <ListItemText
            primary={option.label}
            secondary={option.description}
            slotProps={{
              primary: { sx: { fontSize: "0.78rem", fontWeight: 600 } },
              secondary: { sx: { fontSize: "0.72rem", color: "text.secondary" } },
            }}
          />
        </MenuItem>
      ))}
    </Select>
  );
}
