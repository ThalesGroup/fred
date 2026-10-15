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
import { describe, expect, it, vi } from "vitest";
import BootstrapGuard from "./BootstrapGuard";

const mockStatus = vi.fn();

vi.mock("../../../slices/fredManager/fredManagerApiEnhancements", () => ({
  useOnboardingStatusQuery: () => ({ data: mockStatus() }),
}));
vi.mock("@shared/layouts/MainLayout/MainLayout", () => ({ default: ({ children }) => children }));

vi.mock("@components/pages/BootstrapPage/BootstrapPage.tsx", () => ({
  default: () => <div data-testid="bootstrap-page" />,
}));

function renderGuard(): string {
  return renderToStaticMarkup(
    <BootstrapGuard>
      <div data-testid="app-children" />
    </BootstrapGuard>,
  );
}

describe("BootstrapGuard", () => {
  it("renders BootstrapPage when root_bootstrap_required is true", () => {
    mockStatus.mockReturnValue({ root_bootstrap_required: true });

    const html = renderGuard();

    expect(html).toContain("bootstrap-page");
    expect(html).not.toContain("app-children");
  });

  it("renders children when root_bootstrap_required is false", () => {
    mockStatus.mockReturnValue({ root_bootstrap_required: false });

    const html = renderGuard();

    expect(html).toContain("app-children");
    expect(html).not.toContain("bootstrap-page");
  });
});
