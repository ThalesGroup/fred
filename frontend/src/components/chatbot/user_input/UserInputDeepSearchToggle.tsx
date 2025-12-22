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

import TravelExploreOutlinedIcon from "@mui/icons-material/TravelExploreOutlined";
import { Stack, ToggleButton, Tooltip, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";

type Props = {
  value: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
};

export function UserInputDeepSearchToggle({ value, onChange, disabled }: Props) {
  const { t } = useTranslation();

  return (
    <Tooltip title={t("chatbot.deepSearch.tooltip", "Delegate RAG search to Rico Senior")}>
      <ToggleButton
        value="deep-search"
        selected={value}
        disabled={disabled}
        onChange={() => onChange(!value)}
        aria-label={t("chatbot.deepSearch.label", "Deep Search")}
        sx={{
          borderRadius: 2,
          px: 1.1,
          py: 0.4,
          textTransform: "none",
          borderColor: "divider",
          backgroundColor: "background.paper",
          "&.Mui-selected": {
            color: "primary.main",
            backgroundColor: "primary.main",
            "& svg": { color: "common.white" },
            "&:hover": { backgroundColor: "primary.dark" },
          },
        }}
      >
        <Stack direction="row" alignItems="center" spacing={0.5}>
          <TravelExploreOutlinedIcon fontSize="small" />
          <Typography variant="caption" color="inherit">
            {t("chatbot.deepSearch.label", "Deep Search")}
          </Typography>
        </Stack>
      </ToggleButton>
    </Tooltip>
  );
}
