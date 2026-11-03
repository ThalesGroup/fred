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
import type {
  AgentTemplateSummary,
  AvailableModelProfileList,
  CapabilityEnablementItem,
  FrontendConfig,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import { SELF_TEST_AGENT_ID } from "./corpus";

export const MAX_CLOCK_SKEW_SECONDS = 120;

export interface TokenClaims {
  iss?: string;
  iat?: number;
  exp?: number;
}

/** Read-only probes of the deployment, as the signed-in admin. */
export interface PlatformDeps {
  controlPlaneHealth: () => Promise<void>;
  knowledgeFlowHealth: () => Promise<void>;
  platformRoles: () => Promise<string[]>;
  frontendConfig: () => Promise<FrontendConfig>;
  tokenClaims: () => TokenClaims | null;
  serverDate: () => Promise<Date | null>;
  templates: () => Promise<AgentTemplateSummary[]>;
  modelProfiles: () => Promise<AvailableModelProfileList>;
  capabilities: () => Promise<CapabilityEnablementItem[]>;
  /** Settings the admin pages read; each returns a short detail. */
  reads: Array<{ id: string; title: string; read: () => Promise<string> }>;
  now: () => number;
}

const trimSlash = (url: string) => url.replace(/\/+$/, "");

/** Runtimes whose every template is unavailable, keyed by runtime id. */
export function downRuntimes(templates: AgentTemplateSummary[]): string[] {
  const byRuntime = new Map<string, boolean>();
  for (const t of templates) {
    byRuntime.set(t.source_runtime_id, (byRuntime.get(t.source_runtime_id) ?? false) || t.status !== "unavailable");
  }
  return [...byRuntime].filter(([, up]) => !up).map(([id]) => id);
}

export const platformScenario: Scenario<PlatformDeps> = async (deps, report) => {
  await runStep(report, "control-plane-health", "Control plane is healthy and ready", async () => {
    await deps.controlPlaneHealth();
    return { value: undefined, detail: "healthz and ready answered" };
  });
  await runStep(report, "knowledge-flow-health", "Knowledge service is healthy and ready", async () => {
    await deps.knowledgeFlowHealth();
    return { value: undefined, detail: "healthz and ready answered" };
  });
  await runStep(report, "account-status", "Account status and platform roles can be read", async () => {
    const roles = await deps.platformRoles();
    return { value: undefined, detail: roles.length ? roles.join(", ") : "no platform role" };
  });

  const config = await runStep(report, "provider-config", "Public identity provider configuration", async () => {
    const value = await deps.frontendConfig();
    if (!value.user_auth.enabled) throw new SkipStep("user authentication is disabled on this deployment");
    return {
      value,
      detail: `${value.user_auth.provider ?? "keycloak"}, directory ${value.user_auth.user_directory ?? "keycloak"}`,
    };
  });
  await runStep(report, "token-issuer", "The session token comes from the configured issuer", async () => {
    if (!config) throw new SkipStep("provider configuration unavailable");
    const claims = deps.tokenClaims();
    if (!claims?.iss || !config.user_auth.realm_url) throw new SkipStep("no signed session token to compare");
    if (trimSlash(claims.iss) === trimSlash(config.user_auth.realm_url))
      return { value: undefined, detail: claims.iss };
    // Generic OIDC providers may declare an issuer distinct from the discovery URL.
    if (config.user_auth.provider === "oidc") throw new SkipStep(`issuer ${claims.iss} differs from the provider URL`);
    throw new Error(`token issuer ${claims.iss} differs from the configured realm ${config.user_auth.realm_url}`);
  });
  await runStep(report, "clocks", "Browser, token and server clocks agree", async () => {
    const now = deps.now() / 1000;
    const claims = deps.tokenClaims();
    if (claims?.iat && claims.iat - now > MAX_CLOCK_SKEW_SECONDS)
      throw new Error(`the token was issued ${Math.round(claims.iat - now)} s in the future`);
    if (claims?.exp && claims.exp < now) throw new Error("the session token is already expired");
    const server = await deps.serverDate();
    if (!server) throw new SkipStep("the server sent no Date header");
    const skew = Math.round(server.getTime() / 1000 - now);
    if (Math.abs(skew) > MAX_CLOCK_SKEW_SECONDS) throw new Error(`server clock is ${skew} s away from this browser`);
    return { value: undefined, detail: `server skew ${skew} s` };
  });

  const templates = await runStep(report, "runtimes", "Every agent runtime serves an available template", async () => {
    const value = await deps.templates();
    if (value.length === 0) throw new Error("no agent template is offered to the personal space");
    const down = downRuntimes(value);
    if (down.length) throw new Error(`runtime(s) with no available template: ${down.join(", ")}`);
    const runtimes = new Set(value.map((t) => t.source_runtime_id)).size;
    return { value, detail: `${runtimes} runtime(s), ${value.length} template(s)` };
  });
  await runStep(report, "harness-agent", "The deterministic self-test agent is available", async () => {
    if (!templates) throw new SkipStep("template catalog unavailable");
    const harness = templates.find((t) => t.source_agent_id === SELF_TEST_AGENT_ID);
    if (!harness) throw new Error(`'${SELF_TEST_AGENT_ID}' is not offered; the agent families will skip`);
    if (harness.status === "unavailable") throw new Error(`'${SELF_TEST_AGENT_ID}' is unavailable`);
    return { value: undefined, detail: harness.source_runtime_id };
  });
  await runStep(report, "models", "At least one chat model profile is offered", async () => {
    const list = await deps.modelProfiles();
    const count = list.profiles?.length ?? 0;
    if (count === 0) throw new Error("no model profile is available to the personal space");
    return { value: undefined, detail: `${count} profile(s), default ${list.effective_default_profile_id ?? "none"}` };
  });
  await runStep(report, "capabilities", "The capability catalog can be read", async () => {
    const items = await deps.capabilities();
    const suspended = items.reduce((n, c) => n + (c.suspended_instances ?? 0), 0);
    const kinds = new Map<string, number>();
    for (const c of items) kinds.set(c.kind ?? "tool", (kinds.get(c.kind ?? "tool") ?? 0) + 1);
    const summary = [...kinds].map(([k, n]) => `${n} ${k}`).join(", ");
    return { value: undefined, detail: `${summary || "empty"}; ${suspended} suspended agent instance(s)` };
  });
  for (const read of deps.reads) {
    await runStep(report, read.id, read.title, async () => ({ value: undefined, detail: await read.read() }));
  }
};
