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
import { applicationLocaleText } from "./applicationI18n.ts";

const labels = { en: "Reports", fr: "Rapports" };

describe("applicationLocaleText", () => {
  it("prefers the exact locale, then its base language, then English", () => {
    expect(applicationLocaleText(labels, "fr")).toBe("Rapports");
    expect(applicationLocaleText(labels, "fr-CA")).toBe("Rapports");
    expect(applicationLocaleText(labels, "de")).toBe("Reports");
  });

  // The last-resort scan returns whatever the map happens to enumerate first,
  // so English has to win before it — an application is free to declare its
  // locales in any order, and the fallback must not depend on that order.
  it("prefers English over an earlier-declared locale", () => {
    expect(applicationLocaleText({ de: "Berichte", en: "Reports" }, "fr")).toBe("Reports");
  });

  it("falls back to any translated value when English is absent", () => {
    expect(applicationLocaleText({ de: "Berichte" }, "fr")).toBe("Berichte");
  });

  it("never resolves an inherited property to a label", () => {
    expect(applicationLocaleText({}, "constructor")).toBe("");
    expect(applicationLocaleText({}, "toString")).toBe("");
  });

  it("returns an empty string for an empty label map", () => {
    expect(applicationLocaleText({}, "en")).toBe("");
  });
});
