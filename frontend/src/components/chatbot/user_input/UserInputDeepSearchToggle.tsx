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
        sx={(theme) => {
          const rimA = theme.palette.primary.main;
          const rimB = theme.palette.secondary.main;
          const rimC = theme.palette.info.main;
          const rimD = theme.palette.success.main;
          const rimE = theme.palette.warning.main;

          return {
            borderRadius: 2,
            px: 0.85,
            py: 0.35,
            textTransform: "none",
            border: "none",
            background: `conic-gradient(${rimA}, ${rimB}, ${rimC}, ${rimD}, ${rimE}, ${rimA})`,
            padding: "2px",
            "& .MuiTouchRipple-root": {
              borderRadius: 8,
            },
            "&.Mui-selected": {
              "& > .deep-search-inner": {
                color: theme.palette.primary.contrastText,
                backgroundColor: theme.palette.primary.main,
              },
            },
            "&.Mui-selected:hover > .deep-search-inner": {
              color: theme.palette.primary.contrastText,
              backgroundColor: theme.palette.primary.dark,
            },
            "&:hover > .deep-search-inner": {
              backgroundColor:
                theme.palette.mode === "light"
                  ? theme.palette.grey[50]
                  : theme.palette.grey[900],
            },
          };
        }}
      >
        <Stack
          className="deep-search-inner"
          direction="row"
          alignItems="center"
          spacing={0.5}
          sx={(theme) => ({
            borderRadius: 1.5,
            px: 0.9,
            py: 0.35,
            color: theme.palette.text.secondary,
            backgroundColor: theme.palette.background.paper,
          })}
        >
          <TravelExploreOutlinedIcon fontSize="small" />
          <Typography variant="caption" color="inherit">
            {t("chatbot.deepSearch.label", "Deep Search")}
          </Typography>
        </Stack>
      </ToggleButton>
    </Tooltip>
  );
}
