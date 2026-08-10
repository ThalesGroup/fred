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

// Regression coverage for the whitelist-rejection landing page rendering a
// broken icon (found in the MUI-purge PR review): `agentIconName` is a
// site-config string that is NOT guaranteed to be a real Material Symbol or
// custom-icon name (deployments can set anything), so the page must always
// fall back to a renderable icon instead of asking the browser to load
// `images/<agentIconName>.svg`, a file that never existed for most values.
//
// Rendered with `renderToStaticMarkup` — this repo's test environment has
// no DOM/jsdom (same convention as CapabilityTeamMatrixDrawer.test.tsx).

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ComingSoon } from "./ComingSoon";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key}:${JSON.stringify(opts)}` : key),
  }),
}));

let mockAgentIconName = "person";
let mockSiteDisplayName = "Fred";
vi.mock("../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({
    agentIconName: mockAgentIconName,
    siteDisplayName: mockSiteDisplayName,
  }),
}));

describe("ComingSoon", () => {
  it("renders a known Material Symbol icon name as-is", () => {
    mockAgentIconName = "smart_toy";
    const html = renderToStaticMarkup(<ComingSoon />);
    expect(html).toContain("smart_toy");
  });

  it("falls back to the person icon when agentIconName is not a real icon", () => {
    // A deployment can set this site-config string to anything — it is not
    // validated against the Material Symbols / custom-icon set.
    mockAgentIconName = "not-a-real-icon-name";
    const html = renderToStaticMarkup(<ComingSoon />);
    expect(html).toContain("person");
    expect(html).not.toContain("not-a-real-icon-name");
  });

  it("interpolates the configured site display name into the title", () => {
    mockAgentIconName = "person";
    mockSiteDisplayName = "Acme Corp";
    const html = renderToStaticMarkup(<ComingSoon />);
    expect(html).toContain("comingSoon.title");
    expect(html).toContain("Acme Corp");
  });
});
