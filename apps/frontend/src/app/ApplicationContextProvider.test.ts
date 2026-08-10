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

// Regression coverage for the light/dark/system resolution at startup,
// flagged as untested in the MUI-purge PR review. `AppWithTheme` sets
// `document.documentElement`'s `[data-theme]` straight from this value on
// first render (App.tsx), so a wrong result here means the wrong palette
// paints before anyone can toggle anything.

import { describe, expect, it } from "vitest";
import { computeDarkMode } from "./ApplicationContextProvider";

describe("computeDarkMode", () => {
  it("resolves 'light' to light regardless of system preference", () => {
    expect(computeDarkMode("light", true)).toBe(false);
    expect(computeDarkMode("light", false)).toBe(false);
  });

  it("resolves 'dark' to dark regardless of system preference", () => {
    expect(computeDarkMode("dark", true)).toBe(true);
    expect(computeDarkMode("dark", false)).toBe(true);
  });

  it("resolves 'system' by following the OS preference", () => {
    expect(computeDarkMode("system", true)).toBe(true);
    expect(computeDarkMode("system", false)).toBe(false);
  });
});
