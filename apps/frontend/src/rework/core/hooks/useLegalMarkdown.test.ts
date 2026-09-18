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

import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../common/config.tsx", () => ({ getProperty: () => undefined }));

import { legalMarkdownCandidates, loadLegalMarkdown } from "./useLegalMarkdown.ts";

describe("legal markdown loading", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("tries the language variant before the default file", () => {
    expect(legalMarkdownCandidates("team-admin-charter", "fr-FR", undefined)).toEqual([
      "/team-admin-charter.fr.md",
      "/team-admin-charter.md",
    ]);
  });

  it("puts the normalized release brand folder first", () => {
    expect(legalMarkdownCandidates("gcu", "en", " Acme Corp ")).toEqual([
      "/contrib/acme-corp/gcu.en.md",
      "/contrib/acme-corp/gcu.md",
      "/gcu.en.md",
      "/gcu.md",
    ]);
  });

  it("falls back to English when the language is unknown", () => {
    expect(legalMarkdownCandidates("gdpr", undefined, "")).toEqual(["/gdpr.en.md", "/gdpr.md"]);
  });

  it("returns the first markdown answer and skips the SPA fallback", async () => {
    const bodies: Record<string, string> = {
      "/base/gcu.fr.md": "<!DOCTYPE html><html></html>",
      "/base/gcu.md": "# Terms",
    };
    const fetchMock = vi.fn(async (url: string) => ({
      ok: url in bodies,
      text: async () => bodies[url] ?? "",
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadLegalMarkdown(["/gcu.fr.md", "/gcu.md"], "/base")).resolves.toBe("# Terms");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("returns null when no candidate answers", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );

    await expect(loadLegalMarkdown(["/gcu.md"], "")).resolves.toBeNull();
  });
});
