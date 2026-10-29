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
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("@core/hooks/useManagerPlatformAdmin", () => ({ useManagerPlatformAdmin: () => ({ isAdmin: true }) }));

import MainNavBar from "./MainNavBar";

const pointer = (coarse: boolean) =>
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: coarse && query === "(pointer: coarse)",
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      }) as unknown as MediaQueryList,
  );

afterEach(() => vi.restoreAllMocks());

const render = () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div");
  const root = createRoot(container);
  act(() => root.render(<MainNavBar platformArea />));
  const html = container.innerHTML;
  act(() => root.unmount());
  return html;
};

describe("MainNavBar rail", () => {
  it("shows compact icon buttons with a fine pointer", () => {
    pointer(false);
    const html = render();
    expect(html).not.toContain("data-touch");
    expect(html).toContain('aria-label="rework.mainNav.adminConsole"');
  });

  it("shows labelled touch items with the active indicator on a coarse pointer", () => {
    pointer(true);
    const html = render();
    expect(html).toContain("data-touch");
    expect(html).toMatch(/data-active="true"[^>]*aria-current="true"/);
    expect(html).toContain(">rework.mainNav.adminConsole</span>");
  });
});
