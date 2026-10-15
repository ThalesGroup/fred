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

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

let givenName: string | null = null;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { name?: string }) => (opts?.name ? `${key}:${opts.name}` : key),
  }),
}));
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { GetUserGivenName: () => givenName },
}));
const state = vi.hoisted(() => ({ spaces: [] as unknown[], selected: "", failed: false, loading: false }));
vi.mock("react-router-dom", () => ({
  useSearchParams: () => [new URLSearchParams(state.selected ? { space: state.selected } : {})],
}));
vi.mock("../../../../slices/fredManager/fredManagerApiEnhancements", () => ({
  useMySpacesQuery: () => ({ data: state.spaces, isError: state.failed, isLoading: state.loading, refetch: vi.fn() }),
}));

import HomePage from "./HomePage";

describe("HomePage greeting", () => {
  beforeEach(() => {
    givenName = null;
  });

  it("greets with the token given name, like the chat welcome does", () => {
    givenName = "Ada";
    expect(renderToStaticMarkup(<HomePage />)).toContain("rework.home.greetingNamed:Ada");
  });

  it("falls back to the unnamed greeting rather than showing an identifier", () => {
    const html = renderToStaticMarkup(<HomePage />);
    expect(html).toContain("rework.home.greeting<");
    expect(html).not.toContain("greetingNamed");
  });
});

const org = { id: "org", kind: "organization", name: "Org", path: ["org"], roles: ["member"] };
const team = { id: "team", kind: "team", name: "Team", path: ["org", "team"], roles: ["admin"] };
const project = {
  id: "project",
  kind: "project",
  name: "Project",
  path: ["org", "team", "project"],
  roles: ["analyst", "editor"],
};
beforeEach(() => {
  state.spaces = [];
  state.selected = "";
  state.failed = false;
  state.loading = false;
});
it("shows the platform root's empty state without inventing a personal space", () => {
  expect(renderToStaticMarkup(<HomePage />)).toContain("rework.manager.empty");
});
it("shows declared hierarchy and every direct role without implied member grants", () => {
  state.spaces = [org, team, project];
  state.selected = "project";
  const html = renderToStaticMarkup(<HomePage />);
  expect(html).toContain("Org / Team / Project");
  expect(html).toContain("rework.manager.roles.analyst, rework.manager.roles.editor");
  expect(html).not.toContain("rework.manager.roles.member");
  expect(html).not.toContain('aria-label="Team"');
});
it("does not substitute another membership for an unknown selection", () => {
  state.spaces = [org, team];
  state.selected = "other";
  const html = renderToStaticMarkup(<HomePage />);
  expect(html).toContain("rework.manager.missingSpace");
  expect(html).not.toContain('aria-label="Team"');
});
it("hides cached memberships on query failure and offers retry", () => {
  state.spaces = [org];
  state.failed = true;
  const html = renderToStaticMarkup(<HomePage />);
  expect(html).toContain("rework.provisioning.retryAuthority");
  expect(html).not.toContain('aria-label="Org"');
});
it("shows loading without an empty-membership claim", () => {
  state.loading = true;
  const html = renderToStaticMarkup(<HomePage />);
  expect(html).toContain('role="status"');
  expect(html).not.toContain("rework.manager.empty");
});
