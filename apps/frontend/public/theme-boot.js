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

// Applies the UI theme, light/dark mode and page language to <html> before the first paint.
// Same rules as src/app/uiThemes.ts and computeDarkMode. A static file so a
// `script-src 'self'` CSP allows it; never transpiled, so ES5 syntax and APIs only.
(function () {
  var THEMES = ["pebble", "cobalt", "cloud"];

  // Shared with React so a cached schedule paints the same sky throughout startup.
  function validSchedule(schedule) {
    var time = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;
    return (
      !!schedule &&
      typeof schedule === "object" &&
      Object.keys(schedule).length === 2 &&
      typeof schedule.sunrise === "string" &&
      time.test(schedule.sunrise) &&
      typeof schedule.sunset === "string" &&
      time.test(schedule.sunset) &&
      schedule.sunrise < schedule.sunset
    );
  }

  function minutes(time) {
    return Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
  }

  function smooth(value) {
    var t = Math.max(0, Math.min(1, value));
    return t * t * (3 - 2 * t);
  }

  function sample(schedule, date) {
    var rise = minutes(schedule.sunrise);
    var set = minutes(schedule.sunset);
    var now = date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60;
    var dayLength = set - rise;
    var nightLength = 1440 - dayLength;
    var day = now >= rise && now < set;
    var phaseLength = day ? dayLength : nightLength;
    var elapsed = day ? now - rise : (now - set + 1440) % 1440;
    var arc = elapsed / phaseLength;
    var distance = Math.min(elapsed, phaseLength - elapsed) * (day ? 1 : -1);
    var halfTwilight = Math.min(60, dayLength / 2, nightLength / 2);
    var daylight = smooth(0.5 + distance / (2 * halfTwilight));
    var sun = smooth(0.5 + distance / (2 * Math.min(12, halfTwilight)));
    return {
      dark: !day,
      values: {
        "--ui-daylight": daylight,
        "--ui-twilight": 4 * daylight * (1 - daylight),
        "--ui-sun-progress": day ? arc : arc < 0.5 ? 1 : 0,
        "--ui-moon-progress": day ? (arc < 0.5 ? 1 : 0) : arc,
        "--ui-sun-opacity": sun,
        "--ui-moon-opacity": 1 - sun,
      },
    };
  }

  var previousLight = null;
  function paint(light) {
    var element = document.documentElement;
    if (light) {
      element.setAttribute("data-ui-lighting", "clock");
      Object.keys(light.values).forEach(function (key) {
        element.style.setProperty(key, String(light.values[key]));
      });
    } else if (previousLight) {
      element.removeAttribute("data-ui-lighting");
      Object.keys(previousLight.values).forEach(function (key) {
        element.style.removeProperty(key);
      });
    }
    previousLight = light;
  }

  window.fredLocalDaylight = { validSchedule: validSchedule, sample: sample, paint: paint };

  function read(key) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw === null ? null : JSON.parse(raw);
    } catch (error) {
      return null;
    }
  }

  var custom = read("localHook:ApplicationContextProvider.customUiThemes");
  var catalog = Object.create(null);
  if (custom instanceof Array) {
    for (var c = 0; c < custom.length; c++) {
      var entry = custom[c];
      if (
        entry &&
        typeof entry.id === "string" &&
        /^[a-z][a-z0-9-]{0,31}$/.test(entry.id) &&
        THEMES.indexOf(entry.id) < 0 &&
        THEMES.indexOf(entry.base) >= 0
      ) {
        THEMES.push(entry.id);
        catalog[entry.id] = entry;
      }
    }
  }

  // Before login, only public platform settings and system appearance are available.
  // Signed-in choices come from the database before application content mounts.
  var platform = read("localHook:ApplicationContextProvider.platformUiThemes") || {};
  var hidden = platform.hidden_themes instanceof Array ? platform.hidden_themes : [];
  var offered = [];
  for (var i = 0; i < THEMES.length; i++) {
    if (hidden.indexOf(THEMES[i]) < 0) offered.push(THEMES[i]);
  }
  if (offered.length === 0) offered = THEMES;

  var theme = offered.indexOf(platform.default_theme) >= 0 ? platform.default_theme : offered[0];

  var prefersDark = !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var selected = catalog[theme];
  var light = selected && validSchedule(selected.localDaylight) ? sample(selected.localDaylight, new Date()) : null;
  paint(light);
  var mode = (light ? light.dark : prefersDark) ? "dark" : "light";

  document.documentElement.setAttribute("data-ui-theme", theme);
  document.documentElement.setAttribute("data-ui-base-theme", selected ? selected.base : theme);
  document.documentElement.setAttribute("data-theme", mode);

  // Same rule as userPreferences.ts before the signed-in choice loads: a static
  // lang="en" on a French page makes the browser offer to translate it.
  var browserLanguage = (window.navigator && window.navigator.language) || "";
  document.documentElement.lang = browserLanguage.toLowerCase().indexOf("fr") === 0 ? "fr" : "en";
})();
