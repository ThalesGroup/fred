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

// Publishes the local theme clock and initial appearance before the first paint.
// Same rules as src/app/uiThemes.ts and computeDarkMode. A static file so a
// `script-src 'self'` CSP allows it; never transpiled, so ES5 syntax and APIs only.
(function () {
  var THEMES = ["pebble", "cobalt", "cloud"];
  var root = document.documentElement;
  var subscribers = [];
  var timer;
  var preview = null;
  var snapshot;
  var activeSchedule;
  var minuteMs = 60000;
  var dayMs = 86400000;

  function pad(value) {
    return ("0" + value).slice(-2);
  }

  function localClock(now) {
    return {
      date: ("0000" + now.getFullYear()).slice(-4) + "-" + pad(now.getMonth() + 1) + "-" + pad(now.getDate()),
      secondsSinceMidnight: now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds(),
    };
  }

  function publish(sample) {
    if (snapshot && sample.date === snapshot.date && sample.secondsSinceMidnight === snapshot.secondsSinceMidnight)
      return;
    snapshot = sample;
    // Use UTC date arithmetic to count civil days, including across daylight saving changes.
    var januaryFirst = sample.date.slice(0, 4) + "-01-01";
    var dayOfYear = (Date.parse(sample.date) - Date.parse(januaryFirst)) / dayMs + 1;
    root.setAttribute("data-calendar-date", sample.date);
    root.setAttribute("data-calendar-day-of-year", String(dayOfYear));
    root.style.setProperty("--fred-seconds-since-midnight", String(sample.secondsSinceMidnight));
    if (activeSchedule) root.setAttribute("data-theme", isScheduledDark(activeSchedule) ? "dark" : "light");
    subscribers.slice().forEach(function (notify) {
      notify();
    });
  }

  function refresh() {
    window.clearTimeout(timer);
    if (preview) {
      publish(preview);
      return;
    }
    var now = new Date();
    publish(localClock(now));
    if (!document.hidden) timer = window.setTimeout(refresh, minuteMs - (now.getTime() % minuteMs));
  }

  function subscribe(notify) {
    subscribers.push(notify);
    return function () {
      subscribers = subscribers.filter(function (listener) {
        return listener !== notify;
      });
    };
  }

  function validSchedule(schedule) {
    var clockTime = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;
    return (
      !!schedule &&
      typeof schedule === "object" &&
      Object.keys(schedule).length === 2 &&
      typeof schedule.sunrise === "string" &&
      clockTime.test(schedule.sunrise) &&
      typeof schedule.sunset === "string" &&
      clockTime.test(schedule.sunset) &&
      schedule.sunrise < schedule.sunset
    );
  }

  function timeInSeconds(time) {
    return Number(time.slice(0, 2)) * 3600 + Number(time.slice(3)) * 60;
  }

  function isScheduledDark(schedule) {
    var seconds = snapshot.secondsSinceMidnight;
    return seconds < timeInSeconds(schedule.sunrise) || seconds >= timeInSeconds(schedule.sunset);
  }

  refresh();
  document.addEventListener("visibilitychange", refresh);
  window.addEventListener("pageshow", refresh);
  window.fredThemeClock = {
    getSnapshot: function () {
      return snapshot;
    },
    subscribe: subscribe,
    setPreview: function (sample) {
      preview = sample;
      refresh();
    },
    validSchedule: validSchedule,
    isScheduledDark: isScheduledDark,
    setActiveSchedule: function (schedule) {
      activeSchedule = schedule;
    },
  };

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

  // Before login, only public platform settings and OS mode are available.
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
  var schedule = selected && selected.localDaylight;
  if (validSchedule(schedule)) activeSchedule = schedule;
  var dark = activeSchedule ? isScheduledDark(activeSchedule) : prefersDark;

  root.setAttribute("data-ui-theme", theme);
  root.setAttribute("data-ui-base-theme", selected ? selected.base : theme);
  root.setAttribute("data-theme-mode", "system");
  root.setAttribute("data-theme", dark ? "dark" : "light");

  // Same rule as userPreferences.ts before the signed-in choice loads: a static
  // lang="en" on a French page makes the browser offer to translate it.
  var browserLanguage = (window.navigator && window.navigator.language) || "";
  root.lang = browserLanguage.toLowerCase().indexOf("fr") === 0 ? "fr" : "en";
})();
