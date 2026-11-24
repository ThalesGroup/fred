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

// What these pin: the personal space's features are the union of its templates'
// granted capabilities, the wiki follows its own switch, and nothing counts as known
// until both answers are in.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

type Query<T> = { data?: T; isLoading: boolean; isUninitialized: boolean };
let templates: Query<{ available_capabilities?: { id: string }[] }[]>;
let wiki: Query<{ enabled: boolean }>;
const queriedTeams: string[] = [];

vi.mock("../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({ activeTeam: { id: "personal-1" } }),
}));
vi.mock("../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useGetTeamAgentTemplatesControlPlaneV1TeamsTeamIdAgentTemplatesGetQuery: ({ teamId }: { teamId: string }) => {
    queriedTeams.push(teamId);
    return templates;
  },
}));
vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useWikiAvailabilityQuery: () => wiki,
}));

import { usePersonalSpaceFeatures, type PersonalSpaceFeatures } from "./usePersonalSpaceFeatures";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function read(): PersonalSpaceFeatures {
  let result: PersonalSpaceFeatures | undefined;
  function Probe() {
    result = usePersonalSpaceFeatures();
    return null;
  }
  const root = createRoot(document.createElement("div"));
  act(() => root.render(<Probe />));
  act(() => root.unmount());
  return result!;
}

const done = { isLoading: false, isUninitialized: false };

afterEach(() => {
  queriedTeams.length = 0;
});

describe("usePersonalSpaceFeatures", () => {
  it("unions the templates' capabilities and adds the wiki when it is on", () => {
    templates = {
      ...done,
      data: [
        { available_capabilities: [{ id: "ppt_builder" }] },
        { available_capabilities: [{ id: "html_artifact" }] },
        {},
      ],
    };
    wiki = { ...done, data: { enabled: true } };

    const { features, loaded } = read();

    expect(loaded).toBe(true);
    expect([...features].sort()).toEqual(["html_artifact", "ppt_builder", "team_wiki"]);
    expect(queriedTeams).toContain("personal-1");
  });

  it("follows the wiki switch over what templates advertise", () => {
    templates = { ...done, data: [{ available_capabilities: [{ id: "team_wiki" }] }] };
    wiki = { ...done, data: { enabled: false } };

    expect(read().features.has("team_wiki")).toBe(false);
  });

  it("is not loaded while an answer is pending", () => {
    templates = { isLoading: true, isUninitialized: false };
    wiki = { ...done, data: { enabled: true } };

    expect(read().loaded).toBe(false);
  });
});
