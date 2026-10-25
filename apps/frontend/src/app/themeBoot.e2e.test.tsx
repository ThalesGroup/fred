// @vitest-environment happy-dom
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

// Before login, the boot script uses public settings and ignores personal keys.
import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";
import { expect, it } from "vitest";

const BOOT_SCRIPT = readFileSync(path.resolve(__dirname, "../../public/theme-boot.js"), "utf8");

it("ignores retained personal theme and mode keys before authentication", () => {
  const storage: Record<string, string> = {
    "localHook:ApplicationContextProvider.uiTheme": '"cloud"',
    "localHook:ApplicationContextProvider.themeMode": '"dark"',
    "localHook:ApplicationContextProvider.platformUiThemes": JSON.stringify({ default_theme: "cobalt" }),
  };
  const attributes: Record<string, string> = {};
  runInNewContext(BOOT_SCRIPT, {
    window: {
      localStorage: { getItem: (key: string) => storage[key] ?? null },
      matchMedia: () => ({ matches: false }),
    },
    document: { documentElement: { setAttribute: (name: string, value: string) => (attributes[name] = value) } },
  });
  expect(attributes).toEqual({
    "data-ui-theme": "cobalt",
    "data-ui-base-theme": "cobalt",
    "data-theme": "light",
  });
});
