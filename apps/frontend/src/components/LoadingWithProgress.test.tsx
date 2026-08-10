// Copyright Thales 2025
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

// Regression coverage for the double a11y announcement found in the
// MUI-purge PR review: Spinner used to always render its own
// role="status"/aria-label="Loading" *and* this component rendered its own
// translated label next to it, so a screen reader announced "loading" twice
// (once in English, once translated). The container is now the sole
// role="status" region and Spinner is decorative.
//
// Rendered with `renderToStaticMarkup` — this repo's test environment has
// no DOM/jsdom (same convention as CapabilityTeamMatrixDrawer.test.tsx).

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import LoadingWithProgress from "./LoadingWithProgress";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

describe("LoadingWithProgress", () => {
  it("exposes exactly one status region, on the container", () => {
    const html = renderToStaticMarkup(<LoadingWithProgress />);
    const statusMatches = html.match(/role="status"/g) ?? [];
    expect(statusMatches).toHaveLength(1);
  });

  it("renders the Spinner as decorative (no aria-label of its own)", () => {
    const html = renderToStaticMarkup(<LoadingWithProgress />);
    expect(html).not.toContain('aria-label="Loading"');
  });
});
