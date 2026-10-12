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

import { useContext, useEffect } from "react";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import { ApplicationContext } from "./ApplicationContextProvider";
import { uiThemeTabBranding } from "./uiThemes";

export function useThemeBrowserTab(): void {
  const { uiTheme, darkMode } = useContext(ApplicationContext);
  const properties = useFrontendProperties();
  const theme = uiThemeTabBranding(uiTheme);
  const title = theme?.tabTitle ?? properties.siteDisplayName;
  const lightIcon = theme?.faviconName ?? properties.faviconName;
  const darkIcon = theme?.faviconNameDark ?? theme?.faviconName ?? properties.faviconNameDark;
  const icon = darkMode ? darkIcon : lightIcon;
  const baseUrl = import.meta.env.BASE_URL ?? "/";

  useEffect(() => {
    document.title = title;
    const favicon = document.getElementById("favicon") as HTMLLinkElement | null;
    if (favicon) favicon.href = `${baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`}images/${icon}.svg`;
  }, [baseUrl, title, icon]);
}
