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
vi.mock("@shared/atoms/ButtonGroup/ButtonGroup.tsx", () => ({ default: () => null }));
vi.mock("./HomeSearch/HomeSearch.tsx", () => ({ default: () => null }));
vi.mock("./RecentAgents/RecentAgents.tsx", () => ({ default: () => null }));
vi.mock("./ActivityKpis/ActivityKpis.tsx", () => ({ default: () => null }));
vi.mock("./ResponsibleAiSection/ResponsibleAiSection.tsx", () => ({ default: () => null }));
vi.mock("./TopAgents/TopAgents.tsx", () => ({ default: () => null }));
vi.mock("./TopTeams/TopTeams.tsx", () => ({ default: () => null }));
vi.mock("./MarketplaceTopPrompts/MarketplaceTopPrompts.tsx", () => ({ default: () => null }));

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
