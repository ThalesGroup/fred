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
import { slugifyHeading } from "./HeadingWithAnchor";

describe("slugifyHeading", () => {
  it("lowercases and dashes plain text", () => {
    expect(slugifyHeading("Key concepts")).toBe("key-concepts");
  });

  it("strips French diacritics", () => {
    expect(slugifyHeading("Créer un agent")).toBe("creer-un-agent");
    expect(slugifyHeading("Équipe personnelle")).toBe("equipe-personnelle");
  });

  it("collapses punctuation runs and trims edge dashes", () => {
    expect(slugifyHeading("Guides & cas d'usage !")).toBe("guides-cas-d-usage");
  });
});
