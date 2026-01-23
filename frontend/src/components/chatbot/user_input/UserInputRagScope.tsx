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

import type { RuntimeContext } from "../../../slices/agentic/agenticOpenApi.ts";

type SearchRagScope = NonNullable<RuntimeContext["search_rag_scope"]>;

type Props = {
  value: SearchRagScope;
  onChange: (next: SearchRagScope) => void;
  disabled?: boolean;
};

/**
 * Compact tri-state selector for corpus usage:
 * - corpus_only
 * - hybrid
 * - general_only
 */
export function UserInputRagScope({ value, onChange, disabled }: Props) {
  const { t } = useTranslation();

  const labels: Record<SearchRagScope, string> = {
    corpus_only: "Corpus",
    hybrid: "Hybrid",
    general_only: "General",
  };

  const tooltipByValue: Record<SearchRagScope, string> = {
    corpus_only: t("chatbot.ragScope.tooltipCorpus"),
    hybrid: t("chatbot.ragScope.tooltipHybrid"),
    general_only: t("chatbot.ragScope.tooltipGeneral"),
  };

  const options = [
    {
      value: "corpus_only" as const,
      label: labels.corpus_only,
      description: tooltipByValue.corpus_only,
    },
    {
      value: "hybrid" as const,
      label: labels.hybrid,
      description: tooltipByValue.hybrid,
    },
    {
      value: "general_only" as const,
      label: labels.general_only,
      description: tooltipByValue.general_only,
    },
  ];

  return (
    <Select
      value={value}
      disabled={disabled}
      size="small"
      onChange={(event) => onChange(event.target.value as SearchRagScope)}
      renderValue={(selected) => labels[selected as SearchRagScope]}
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
      inputProps={{ "aria-label": "rag-knowledge-scope" }}
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
