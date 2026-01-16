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

import AutoFixHighOutlinedIcon from "@mui/icons-material/AutoFixHighOutlined";
import RuleOutlinedIcon from "@mui/icons-material/RuleOutlined";
import SyncAltOutlinedIcon from "@mui/icons-material/SyncAltOutlined";
import { ToggleButton, ToggleButtonGroup, Tooltip } from "@mui/material";
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

  const renderButton = (policy: SearchPolicyName, icon: JSX.Element) => (
    <Tooltip key={policy} title={tooltipByValue[policy]}>
      <ToggleButton value={policy} aria-label={labels[policy]}>
        {icon}
      </ToggleButton>
    </Tooltip>
  );

  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={value}
      disabled={disabled}
      onChange={(_, next) => {
        if (next) onChange(next as SearchPolicyName);
      }}
      aria-label="search-policy"
      sx={{
        borderRadius: 999,
        overflow: "hidden",
        "& .MuiToggleButton-root": {
          px: 1,
          py: 0.35,
          fontSize: "0.78rem",
          textTransform: "none",
          gap: 0.5,
          color: "text.secondary",
          borderColor: "divider",
          "&.Mui-selected": {
            color: "primary.main",
            backgroundColor: "primary.main",
            "& svg": { color: "common.white" },
            "&:hover": { backgroundColor: "primary.dark" },
          },
        },
      }}
    >
      {renderButton("hybrid", <SyncAltOutlinedIcon fontSize="small" />)}
      {renderButton("semantic", <AutoFixHighOutlinedIcon fontSize="small" />)}
      {renderButton("strict", <RuleOutlinedIcon fontSize="small" />)}
    </ToggleButtonGroup>
  );
}

