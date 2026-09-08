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
import type { FrontendFeatureFlags } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";

const h = vi.hoisted(() => ({
  bootstrap: undefined as { feature_flags: FrontendFeatureFlags } | undefined,
  isLoading: false,
}));

vi.mock("../../../hooks/useFrontendBootstrap.ts", () => ({
  useFrontendBootstrap: () => ({ bootstrap: h.bootstrap, isLoading: h.isLoading }),
}));

import {
  resolveFrontendFeatureFlag,
  useFrontendFeatureFlag,
  type FrontendFeatureFlagState,
} from "./useFrontendFeatureFlag.ts";

let latest: FrontendFeatureFlagState;

function Host() {
  latest = useFrontendFeatureFlag("enableApplications");
  return null;
}

function render() {
  renderToStaticMarkup(<Host />);
}

describe("frontend feature flags", () => {
  beforeEach(() => {
    h.bootstrap = undefined;
    h.isLoading = false;
  });

  it("resolves only an explicit true value as enabled", () => {
    expect(resolveFrontendFeatureFlag(undefined, "enableApplications")).toBe(false);
    expect(resolveFrontendFeatureFlag({}, "enableApplications")).toBe(false);
    expect(resolveFrontendFeatureFlag({ enableApplications: false }, "enableApplications")).toBe(false);
    expect(resolveFrontendFeatureFlag({ enableApplications: true }, "enableApplications")).toBe(true);
  });

  it("fails closed when bootstrap data is absent and preserves loading state", () => {
    h.isLoading = true;
    render();
    expect(latest).toEqual({ enabled: false, isLoading: true });
  });

  it("reads an enabled flag from authenticated bootstrap", () => {
    h.bootstrap = { feature_flags: { enableApplications: true } };
    render();
    expect(latest).toEqual({ enabled: true, isLoading: false });
  });
});
