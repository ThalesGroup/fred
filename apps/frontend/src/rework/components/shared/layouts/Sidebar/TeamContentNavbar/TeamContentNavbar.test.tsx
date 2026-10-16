// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import TeamContentNavbar from "./TeamContentNavbar";
const h = vi.hoisted(() => ({ personal: false, denied: false }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../../security/KeycloakService", () => ({ KeyCloakService: { GetUserFullName: () => "Priya" } }));
vi.mock("../../../../../../slices/fredManager/fredManagerApiEnhancements", () => ({
  useMySpacesQuery: () => ({
    isError: h.denied,
    currentData: [
      { id: "space-1", kind: "team", name: "fredlab", roles: ["editor"], personal_owner: h.personal ? "priya" : null },
    ],
  }),
}));
function render() {
  return renderToStaticMarkup(
    <MemoryRouter>
      <TeamContentNavbar spaceId="space-1" />
    </MemoryRouter>,
  );
}
describe("manager scoped navigation", () => {
  it("offers only the implemented Resources destination and back navigation", () => {
    h.personal = false;
    h.denied = false;
    const html = render();
    expect(html).toContain('href="/team/space-1/resources"');
    expect(html).toContain("fredlab");
    expect(html).toContain("rework.manager.roles.editor");
    expect(html).toContain("rework.back");
    expect(html).not.toContain("/agents");
    expect(html).not.toContain("/settings");
  });
  it("uses personal presentation with the real manager identifier", () => {
    h.personal = true;
    h.denied = false;
    const html = render();
    expect(html).toContain("rework.sidebar.team.userTeam");
    expect(html).toContain('href="/team/space-1/resources"');
  });
  it("does not expose stale membership navigation after an error", () => {
    h.denied = true;
    expect(render()).not.toContain("/team/space-1/resources");
  });
});
