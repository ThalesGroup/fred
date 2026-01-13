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

import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import SettingsBrightnessIcon from "@mui/icons-material/SettingsBrightness";
import { Button, ButtonGroup } from "@mui/material";
import { useContext } from "react";
import { useTranslation } from "react-i18next";
import { ApplicationContext } from "../app/ApplicationContextProvider";

export function ThemeModeSelector() {
  const { themeMode, setThemeMode } = useContext(ApplicationContext);
  const { t } = useTranslation();

  return (
    <ButtonGroup variant="outlined" size="small" fullWidth>
      <Button
        onClick={() => setThemeMode("light")}
        variant={themeMode === "light" ? "contained" : "outlined"}
        startIcon={<LightModeIcon fontSize="small" />}
      >
        {t("profile.theme.light")}
      </Button>
      <Button
        onClick={() => setThemeMode("system")}
        variant={themeMode === "system" ? "contained" : "outlined"}
        startIcon={<SettingsBrightnessIcon fontSize="small" />}
      >
        {t("profile.theme.system")}
      </Button>
      <Button
        onClick={() => setThemeMode("dark")}
        variant={themeMode === "dark" ? "contained" : "outlined"}
        startIcon={<DarkModeIcon fontSize="small" />}
      >
        {t("profile.theme.dark")}
      </Button>
    </ButtonGroup>
  );
}
