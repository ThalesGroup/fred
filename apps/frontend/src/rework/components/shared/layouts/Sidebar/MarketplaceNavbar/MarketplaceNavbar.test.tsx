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

import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({ spaces: [] as { kind: string; name: string }[] | undefined }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentIconName: "smart_toy", agentsNicknamePlural: "agents" }),
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useMySpacesQuery: () => ({ currentData: h.spaces }),
}));

import MarketplaceNavbar from "./MarketplaceNavbar";

const render = () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const host = document.createElement("div");
  const root = createRoot(host);
  act(() =>
    root.render(
      <MemoryRouter>
        <MarketplaceNavbar />
      </MemoryRouter>,
    ),
  );
  const heading = host.querySelector("h2")?.textContent;
  const eyebrow = host.querySelector("h2")?.previousElementSibling?.textContent;
  const text = host.textContent;
  const button = host.querySelector("[aria-haspopup]");
  act(() => root.unmount());
  return { heading, eyebrow, text, button };
};

describe("MarketplaceNavbar", () => {
  it("names the marketplace and the person's organization, read-only", () => {
    h.spaces = [
      { kind: "team", name: "Design" },
      { kind: "organization", name: "Acme" },
    ];
    const { heading, eyebrow, button } = render();
    expect(heading).toBe("rework.sidebar.marketplace.title");
    expect(eyebrow).toBe("Acme");
    expect(button).toBeNull();
  });

  it("keeps the marketplace name alone without an organization", () => {
    h.spaces = [];
    const { heading, eyebrow } = render();
    expect(heading).toBe("rework.sidebar.marketplace.title");
    expect(eyebrow).toBeUndefined();
  });
});
