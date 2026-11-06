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
import { describe, expect, it } from "vitest";
import type { AgentTemplateSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { collect, signal } from "./fakePlatform";
import { downRuntimes, platformScenario, type PlatformDeps } from "./platformScenario";

const NOW = Date.UTC(2026, 9, 20, 10, 0, 0);

function template(runtime: string, agent: string, status: "available" | "unavailable" = "available") {
  return {
    template_id: `${runtime}:${agent}`,
    source_runtime_id: runtime,
    source_agent_id: agent,
    status,
  } as AgentTemplateSummary;
}

function fakeDeps(overrides: Partial<PlatformDeps> = {}): PlatformDeps {
  return {
    controlPlaneHealth: async () => {},
    knowledgeFlowHealth: async () => {},
    platformRoles: async () => ["platform_admin"],
    frontendConfig: async () => ({
      user_auth: { enabled: true, provider: "keycloak", realm_url: "https://id.example/realms/app/" },
      root_bootstrap_completed: true,
      root_bootstrap_required: false,
    }),
    tokenClaims: () => ({ iss: "https://id.example/realms/app", iat: NOW / 1000 - 30, exp: NOW / 1000 + 300 }),
    serverDate: async () => new Date(NOW + 2000),
    templates: async () => [template("agents", "fred.github.self_test"), template("rags", "rag")],
    modelProfiles: async () => ({
      profiles: [{ profile_id: "default" } as never],
      effective_default_profile_id: "default",
    }),
    capabilities: async () => [],
    reads: [{ id: "ui-settings", title: "UI", read: async () => "read" }],
    now: () => NOW,
    ...overrides,
  };
}

async function run(deps: PlatformDeps) {
  const r = collect();
  await platformScenario(deps, r.report, signal);
  return r;
}

describe("platformScenario", () => {
  it("passes on a healthy deployment and writes nothing", async () => {
    const r = await run(fakeDeps());
    expect(r.steps.filter((s) => s.status !== "passed").map((s) => s.id)).toEqual([]);
    expect(r.status("ui-settings")).toBe("passed");
  });

  it("names the runtime whose every template is down", async () => {
    const r = await run(
      fakeDeps({
        templates: async () => [template("agents", "fred.github.self_test"), template("rags", "rag", "unavailable")],
      }),
    );
    expect(r.status("runtimes")).toBe("failed");
    expect(r.steps.find((s) => s.id === "runtimes")?.error).toContain("rags");
    expect(downRuntimes([template("a", "x", "unavailable"), template("a", "y")])).toEqual([]);
  });

  it("fails a Keycloak issuer mismatch but only skips one from a generic provider", async () => {
    const claims = () => ({ iss: "https://other.example/realms/app", iat: NOW / 1000, exp: NOW / 1000 + 60 });
    expect((await run(fakeDeps({ tokenClaims: claims }))).status("token-issuer")).toBe("failed");
    const oidc = fakeDeps({
      tokenClaims: claims,
      frontendConfig: async () => ({
        user_auth: { enabled: true, provider: "oidc", realm_url: "https://login.example/tenant/v2.0" },
        root_bootstrap_completed: true,
        root_bootstrap_required: false,
      }),
    });
    expect((await run(oidc)).status("token-issuer")).toBe("skipped");
  });

  it("fails on a server clock far from the browser, or an expired token", async () => {
    expect((await run(fakeDeps({ serverDate: async () => new Date(NOW + 600_000) }))).status("clocks")).toBe("failed");
    expect((await run(fakeDeps({ tokenClaims: () => ({ exp: NOW / 1000 - 1 }) }))).status("clocks")).toBe("failed");
  });

  it("fails when the self-test agent is missing, and when no model is offered", async () => {
    const r = await run(
      fakeDeps({ templates: async () => [template("agents", "other")], modelProfiles: async () => ({ profiles: [] }) }),
    );
    expect(r.status("harness-agent")).toBe("failed");
    expect(r.status("models")).toBe("failed");
  });

  it("reports an unreachable service and keeps going", async () => {
    const r = await run(fakeDeps({ knowledgeFlowHealth: async () => Promise.reject(new Error("HTTP 503")) }));
    expect(r.status("knowledge-flow-health")).toBe("failed");
    expect(r.status("models")).toBe("passed");
  });
});
