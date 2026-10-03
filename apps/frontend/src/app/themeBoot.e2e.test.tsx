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

// The boot script must read exactly what the profile page writes: drive the
// real provider, then replay theme-boot.js against the same localStorage.
import { readFileSync } from "node:fs";
import path from "node:path";
import { runInNewContext } from "node:vm";
import { act, useContext, useEffect } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { ApplicationContext, ApplicationContextProvider } from "./ApplicationContextProvider";

const BOOT_SCRIPT = readFileSync(path.resolve(__dirname, "../../public/theme-boot.js"), "utf8");

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

function ChooseTheme() {
  const { setUiTheme, setThemeMode } = useContext(ApplicationContext);
  useEffect(() => {
    setUiTheme("cloud");
    setThemeMode("dark");
  }, [setUiTheme, setThemeMode]);
  return null;
}

afterEach(() => window.localStorage.clear());

describe("theme-boot.js after a choice made in the app", () => {
  it("applies the theme and mode the provider stored", async () => {
    const container = document.createElement("div");
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ApplicationContextProvider>
          <ChooseTheme />
        </ApplicationContextProvider>,
      );
    });
    await act(async () => root.unmount());

    const attributes: Record<string, string> = {};
    runInNewContext(BOOT_SCRIPT, {
      window: { localStorage: window.localStorage, matchMedia: () => ({ matches: false }) },
      document: { documentElement: { setAttribute: (name: string, value: string) => (attributes[name] = value) } },
    });
    expect(attributes).toEqual({ "data-ui-theme": "cloud", "data-theme": "dark" });
  });
});
