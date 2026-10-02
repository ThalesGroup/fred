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

// Applies the UI theme and light/dark mode to <html> before the first paint.
// Same rules as src/app/uiThemes.ts and computeDarkMode. A static file so a
// `script-src 'self'` CSP allows it; never transpiled, so ES5 syntax and APIs only.
(function () {
  var THEMES = ["pebble", "cobalt", "cloud"];
  var DEFAULT_THEME = "pebble";

  function read(key) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw === null ? null : JSON.parse(raw);
    } catch (error) {
      return null;
    }
  }

  var theme = read("localHook:ApplicationContextProvider.uiTheme");
  if (THEMES.indexOf(theme) < 0) theme = DEFAULT_THEME;

  var mode = read("localHook:ApplicationContextProvider.themeMode");
  if (mode !== "light" && mode !== "dark") {
    var prefersDark = !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    mode = prefersDark ? "dark" : "light";
  }

  document.documentElement.setAttribute("data-ui-theme", theme);
  document.documentElement.setAttribute("data-theme", mode);
})();
