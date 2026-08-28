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

import { describe, expect, it, vi } from "vitest";
import type { ApplicationSummary } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";
import type { FredApplicationRegistration } from "./applicationHost.ts";
import {
  hasCompatibleApplication,
  loadApplicationModule,
  resolveApplicationRegistration,
} from "./applicationResolution.ts";

const summary: ApplicationSummary = {
  id: "example-app",
  version: "1.0.0",
  name: "applications.example.name",
  description: "applications.example.description",
  icon: "widgets",
  host_api_version: "1",
  contract_digest: "sha256:abc",
};

function registration(over: Partial<FredApplicationRegistration> = {}): FredApplicationRegistration {
  return {
    id: "example-app",
    version: "1.0.0",
    hostApiVersion: "1",
    contractDigest: "sha256:abc",
    load: vi.fn(async () => ({ default: () => null })),
    ...over,
  };
}

describe("resolveApplicationRegistration", () => {
  it("returns the matching registration without invoking its loader", () => {
    const local = registration();
    const result = resolveApplicationRegistration(summary, { "example-app": local });

    expect(result).toEqual({ status: "ready", registration: local });
    expect(local.load).not.toHaveBeenCalled();
  });

  it.each([
    [{}, "missing-module"],
    [{ "example-app": registration({ id: "other-app" }) }, "registration-id-mismatch"],
    [{ "example-app": registration({ version: "2.0.0" }) }, "version-mismatch"],
    [{ "example-app": registration({ contractDigest: "sha256:different" }) }, "contract-mismatch"],
  ] as const)("fails closed for an incompatible registry", (registry, status) => {
    expect(resolveApplicationRegistration(summary, registry)).toEqual({ status });
  });

  it.each(["__proto__", "constructor", "toString"])("does not resolve inherited property %s", (id) => {
    expect(resolveApplicationRegistration({ ...summary, id }, {})).toEqual({ status: "missing-module" });
  });

  it("reports availability only when at least one authorized summary matches locally", () => {
    expect(hasCompatibleApplication(undefined, { "example-app": registration() })).toBe(false);
    expect(hasCompatibleApplication([summary], {})).toBe(false);
    expect(hasCompatibleApplication([summary], { "example-app": registration() })).toBe(true);
  });
});

describe("loadApplicationModule", () => {
  it("discards the loader's potentially sensitive failure message", async () => {
    const local = registration({ load: vi.fn(async () => Promise.reject(new Error("domain payload"))) });

    await expect(loadApplicationModule(local)).rejects.toMatchObject({
      name: "ApplicationModuleLoadError",
      message: "Application module could not be loaded",
    });
  });
});
