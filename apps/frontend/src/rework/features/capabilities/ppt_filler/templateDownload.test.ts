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

// Pins the stored-asset path. It mirrors a server-side convention the frontend
// cannot see, so a silent drift would surface as a 404 in the browser and
// nowhere else. The SAME literal is pinned on the Python side over
// `AgentConfigAssetsAdapter._config_path` (see its own test), so changing either
// side alone fails a suite.

import { describe, expect, it, vi } from "vitest";

const downloadAuthed = vi.hoisted(() => vi.fn());
vi.mock("../../../../utils/downloadUtils", () => ({
  downloadAuthed: (url: string, filename: string) => downloadAuthed(url, filename),
}));

const uid = vi.hoisted(() => ({ value: "user-9" }));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserId: () => uid.value },
}));

const { PPT_FILLER_TEMPLATE_KEY, downloadStoredTemplate, storedTemplateUrl, templateFileName } = await import(
  "./templateDownload"
);

describe("storedTemplateUrl", () => {
  it("addresses the instance's config area under the fixed template key", () => {
    expect(storedTemplateUrl("team-a", "inst-1")).toBe(
      "/knowledge-flow/v1/fs/download/teams/team-a/agents/inst-1/config/ppt_filler_template.pptx",
    );
  });

  // The route alias is NOT the resource id: KF checks ReBAC against
  // `personal-<uid>`, so a download from the personal space would 404 on the
  // bare alias. The repo says so on `personalTeamId` itself.
  it("resolves the bare personal route alias to the canonical team id", () => {
    expect(storedTemplateUrl("personal", "inst-1")).toBe(
      "/knowledge-flow/v1/fs/download/teams/personal-user-9/agents/inst-1/config/ppt_filler_template.pptx",
    );
  });

  it("leaves an already-canonical personal id alone", () => {
    expect(storedTemplateUrl("personal-user-9", "inst-1")).toContain("/teams/personal-user-9/agents/inst-1/");
  });

  // `encodeURI` leaves these raw; `?` would turn the rest of the path into a
  // query string on a route that really does take a `token` query param.
  it("escapes every reserved character, separators excepted", () => {
    expect(storedTemplateUrl("r&d?x#y", "inst 1")).toBe(
      "/knowledge-flow/v1/fs/download/teams/r%26d%3Fx%23y/agents/inst%201/config/ppt_filler_template.pptx",
    );
  });
});

describe("templateFileName", () => {
  it("names the file after the agent", () => {
    expect(templateFileName("Revue mensuelle")).toBe("Revue mensuelle.pptx");
  });

  it("drops characters a filesystem would refuse, without leaving double spaces", () => {
    expect(templateFileName("Revue / Q3: v2")).toBe("Revue Q3 v2.pptx");
  });

  it("does not double the extension when the agent is itself named like a file", () => {
    expect(templateFileName("modele.pptx")).toBe("modele.pptx");
  });

  it("falls back to the stored key when the agent has no usable name", () => {
    expect(templateFileName("")).toBe(PPT_FILLER_TEMPLATE_KEY);
    expect(templateFileName(undefined)).toBe(PPT_FILLER_TEMPLATE_KEY);
    expect(templateFileName("///")).toBe(PPT_FILLER_TEMPLATE_KEY);
  });
});

describe("downloadStoredTemplate", () => {
  it("downloads the stored template with the live bearer, under the agent's name", async () => {
    downloadAuthed.mockClear();
    downloadAuthed.mockResolvedValue(undefined);

    await downloadStoredTemplate("team-a", "inst-1", "Revue mensuelle");

    expect(downloadAuthed).toHaveBeenCalledWith(
      "/knowledge-flow/v1/fs/download/teams/team-a/agents/inst-1/config/ppt_filler_template.pptx",
      "Revue mensuelle.pptx",
    );
  });

  it("propagates a failed download so the caller can report it", async () => {
    downloadAuthed.mockClear();
    downloadAuthed.mockRejectedValue(new Error("Download failed (404)"));

    await expect(downloadStoredTemplate("team-a", "inst-1")).rejects.toThrow("Download failed (404)");
  });
});
