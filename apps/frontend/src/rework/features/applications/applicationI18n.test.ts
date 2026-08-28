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
import { mergeApplicationLocaleResources } from "./applicationI18n.ts";

describe("mergeApplicationLocaleResources", () => {
  it("registers generated locales beyond the host's built-in locales", () => {
    const resources = mergeApplicationLocaleResources(
      { en: { shell: { title: "Fred" } }, fr: { shell: { title: "Fred" } } },
      {
        en: { applications: { example: { name: "Example" } } },
        de: { applications: { example: { name: "Beispiel" } } },
      },
    );

    expect(Object.keys(resources)).toEqual(["de", "en", "fr"]);
    expect(resources.de.translation).toEqual({ applications: { example: { name: "Beispiel" } } });
    expect(resources.en.translation).toEqual({
      shell: { title: "Fred" },
      applications: { example: { name: "Example" } },
    });
    expect(resources.fr.translation).toEqual({ shell: { title: "Fred" } });
  });
});
