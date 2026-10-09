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

  function read(key) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw === null ? null : JSON.parse(raw);
    } catch (error) {
      return null;
    }
  }

  var custom = read("localHook:ApplicationContextProvider.customUiThemes");
  var bases = {};
  if (custom instanceof Array) {
    for (var c = 0; c < custom.length; c++) {
      var entry = custom[c];
      if (entry && typeof entry.id === "string" && /^[a-z][a-z0-9-]{0,31}$/.test(entry.id) &&
          THEMES.indexOf(entry.id) < 0 && THEMES.indexOf(entry.base) >= 0) {
        THEMES.push(entry.id);
        bases[entry.id] = entry.base;
      }
    }
  }

  // Same rules as resolveUiTheme: user's choice if offered, else the platform
  // default if offered, else the first offered theme (platform settings cached
  // from the last /frontend/config; index.tsx re-applies the fresh ones).
  var platform = read("localHook:ApplicationContextProvider.platformUiThemes") || {};
  var hidden = platform.hidden_themes instanceof Array ? platform.hidden_themes : [];
  var offered = [];
  for (var i = 0; i < THEMES.length; i++) {
    if (hidden.indexOf(THEMES[i]) < 0) offered.push(THEMES[i]);
  }
  if (offered.length === 0) offered = THEMES;

  var theme = read("localHook:ApplicationContextProvider.uiTheme");
  if (offered.indexOf(theme) < 0) {
    theme = offered.indexOf(platform.default_theme) >= 0 ? platform.default_theme : offered[0];
  }

  var mode = read("localHook:ApplicationContextProvider.themeMode");
  if (mode !== "light" && mode !== "dark") {
    var prefersDark = !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
    mode = prefersDark ? "dark" : "light";
  }

  document.documentElement.setAttribute("data-ui-theme", theme);
  document.documentElement.setAttribute("data-ui-base-theme", bases[theme] || theme);
  document.documentElement.setAttribute("data-theme", mode);
})();
