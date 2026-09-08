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

const h = vi.hoisted(() => ({ enabled: false, isLoading: false }));

vi.mock("@hooks/useFrontendFeatureFlag.ts", () => ({
  useFrontendFeatureFlag: () => ({ enabled: h.enabled, isLoading: h.isLoading }),
}));

import { FrontendFeatureGate } from "./FrontendFeatureGate.tsx";

const render = () =>
  renderToStaticMarkup(
    <FrontendFeatureGate flag="enableApplications" fallback={<span>not-found</span>}>
      <span>applications</span>
    </FrontendFeatureGate>,
  );

describe("FrontendFeatureGate", () => {
  beforeEach(() => {
    h.enabled = false;
    h.isLoading = false;
  });

  it("renders nothing while bootstrap is loading", () => {
    h.isLoading = true;
    expect(render()).toBe("");
  });

  it("renders the fallback and not the protected surface when disabled", () => {
    expect(render()).toContain("not-found");
    expect(render()).not.toContain("applications");
  });

  it("renders the protected surface only when explicitly enabled", () => {
    h.enabled = true;
    expect(render()).toContain("applications");
    expect(render()).not.toContain("not-found");
  });
});
