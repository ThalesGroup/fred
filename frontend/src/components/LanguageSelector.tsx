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

import { Box, IconButton } from "@mui/material";
import { useTranslation } from "react-i18next";
import { SimpleTooltip } from "../shared/ui/tooltips/Tooltips";

export const LanguageSelector = () => {
  const { i18n } = useTranslation();
  const currentLang = i18n.language;

  const changeLanguage = (lang: string) => {
    i18n.changeLanguage(lang);
  };

  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <SimpleTooltip title="Français">
        <IconButton
          onClick={() => changeLanguage("fr")}
          size="small"
          sx={{
            fontSize: "0.75rem",
            //fontWeight: "bold",
            opacity: currentLang === "fr" ? 1 : 0.4,
            borderRadius: 1,
            border: currentLang === "fr" ? "1px solid" : "none",
            borderColor: "primary.main",
            color: "text.primary",
            px: 1,
          }}
        >
          FR
        </IconButton>
      </SimpleTooltip>
      <SimpleTooltip title="English">
        <IconButton
          onClick={() => changeLanguage("en")}
          size="small"
          sx={{
            fontSize: "0.75rem",
            //fontWeight: "bold",
            opacity: currentLang === "en" ? 1 : 0.4,
            borderRadius: 1,
            border: currentLang === "en" ? "1px solid" : "none",
            borderColor: "primary.main",
            color: "text.primary",
            px: 1,
          }}
        >
          EN
        </IconButton>
      </SimpleTooltip>
    </Box>
  );
};
