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

import { describe, expect, it } from "vitest";

import i18n from "./i18n";

describe("<html lang> follows the displayed language", () => {
  it("names the language Fred switched to", async () => {
    await i18n.changeLanguage("fr");
    expect(document.documentElement.lang).toBe("fr");

    await i18n.changeLanguage("en");
    expect(document.documentElement.lang).toBe("en");
  });

  it("names the fallback for a language Fred does not ship", async () => {
    await i18n.changeLanguage("de-DE");
    expect(document.documentElement.lang).toBe("en");
  });
});
