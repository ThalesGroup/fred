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
import { identityProbeScenario } from "./identityProbeScenario";
import type { StepReport } from "../types";

const token = "header.payload.signature";
async function run(overrides: Record<string, number> = {}, directory = "local", uid = "person") {
  const steps: StepReport[] = [];
  const request = vi.fn(async (path: string, bearer?: string) => ({
    status:
      overrides[`${path}:${bearer ?? "missing"}`] ??
      (path.endsWith("/config") || path.endsWith("/healthz") || bearer === token ? 200 : 401),
    body: path.endsWith("/config")
      ? { user_auth: { enabled: true, user_directory: directory } }
      : path.endsWith("/users")
        ? [{ id: "person" }]
        : { current_user: { id: "person" } },
  }));
  await identityProbeScenario(token, uid, request, (step) => {
    const index = steps.findIndex((s) => s.id === step.id);
    if (index < 0) steps.push(step);
    else steps[index] = step;
  });
  return { steps, request };
}

describe("identity provider live diagnostic", () => {
  it("probes all three APIs with valid, absent, malformed and altered credentials", async () => {
    const { steps, request } = await run();
    expect(steps.filter((s) => s.id.startsWith("jwt-"))).toHaveLength(12);
    expect(steps.filter((s) => s.status === "failed")).toEqual([]);
    expect(request).toHaveBeenCalledWith("/fred/agents/v2/agents/sessions", "header.payload.Aignature");
    expect(request).toHaveBeenCalledWith("/control-plane/v1/frontend/config");
    expect(steps.find((s) => s.id === "identity-coverage")?.status).toBe("skipped");
  });
  it.each([200, 403, 404, 500])("does not mistake HTTP %s for rejection of an invalid token", async (status) => {
    const { steps } = await run({ "/knowledge-flow/v1/tags:invalid-jwt": status });
    expect(steps.find((s) => s.id === "jwt-/knowledge-flow/v1/tags-malformed")?.status).toBe("failed");
  });
  it("reports identity drift and does not assume the directory exists for Keycloak", async () => {
    const { steps } = await run({}, "keycloak", "other");
    expect(steps.find((s) => s.id === "identity-consistency")?.status).toBe("failed");
    expect(steps.find((s) => s.id === "local-directory")?.status).toBe("skipped");
  });
  it("reports a missing local identity", async () => {
    const { steps } = await run({}, "local", "other");
    expect(steps.find((s) => s.id === "local-directory")?.status).toBe("failed");
  });
});
