// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { KeyCloakService } from "../../../../security/KeycloakService";
import { knowledgeFlowApi } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { monitorApi } from "../../../../slices/monitor/monitorOpenApi";
import type { UsageResponse } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { platformSessionDeps } from "../deps/platformSession";
import { runPlatformSessionChecks } from "../scenarios/platformScenario";
import { FRESH } from "../deps/api";
import { browserSecurity } from "../deps/security";
import { resign } from "../scenarios/authorizationScenario";
import { statusOf } from "../scenarios/runScope";
import { runsActiveContent, runSecurityBaseline } from "../scenarios/securityScenario";
import { runStep, SkipStep } from "../step";
import type { Scenario } from "../types";
import { authedFetch } from "../useAuthzProbeRun";
import type { WeaverChecks } from "./checks";
import { assert, cp, ingestKnowledgeFixture, requireSpace } from "./resourceSupport";

export const sharedPlatform: Scenario<WeaverChecks> = async ({ dispatch }, report) => {
  await runStep(report, "control-plane-health", "Control Plane liveness", async () => {
    const health = await dispatch(cp.health.initiate(undefined, FRESH)).unwrap();
    assert(health.status === "ok", "Public liveness did not return a healthy result.");
    return { value: true };
  });
  await runStep(report, "knowledge-flow-health", "Knowledge Flow liveness and readiness", async () => {
    const api = knowledgeFlowApi.endpoints;
    const health = await dispatch(api.healthzKnowledgeFlowV2HealthzGet.initiate(undefined, FRESH)).unwrap();
    const ready = await dispatch(api.readyKnowledgeFlowV2ReadyGet.initiate(undefined, FRESH)).unwrap();
    assert(health?.status === "ok" && ready?.status === "ready", "Knowledge Flow reported an unhealthy dependency.");
    return { value: true };
  });
  await runPlatformSessionChecks(platformSessionDeps(dispatch), report);
};

export const organizationCatalogs: Scenario<WeaverChecks> = async (scope, report) => {
  const { dispatch } = scope;
  await runStep(report, "catalogs", "Read the organization's agent, capability and model catalogs", async () => {
    if (!scope.organizationId) throw new SkipStep("Select an organization to check its catalogs.");
    const args = { organizationId: scope.organizationId };
    try {
      const agents = await dispatch(cp.organizationAgents.initiate(args, FRESH)).unwrap();
      const capabilities = await dispatch(cp.organizationCapabilities.initiate(args, FRESH)).unwrap();
      const models = await dispatch(cp.organizationModels.initiate(args, FRESH)).unwrap();
      const offers = capabilities.flatMap((pod) => pod.capabilities);
      const advertised = offers.filter((offer) => offer.advertised).length;
      return {
        value: true,
        detail: `${agents.length} agents, ${offers.length} capability offers (${advertised} advertised), ${models.sources.length} model sources.`,
      };
    } catch (error) {
      if (statusOf(error) === 403) throw new SkipStep("This account cannot read organization configuration.");
      throw error;
    }
  });
};

export const identity: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const token = await runStep(
    report,
    "session",
    "The browser session is authenticated as the current operator",
    async () => {
      assert(await KeyCloakService.ensureFreshToken(30), "Refresh your sign-in before running this group.");
      const value = KeyCloakService.GetToken();
      assert(value, "Your session has no access token.");
      const me = await checks.dispatch(cp.me.initiate(undefined, FRESH)).unwrap();
      assert(
        me.user_id === checks.userId && me.platform_roles.includes("platform_admin"),
        "The active account or platform role changed.",
      );
      return { value };
    },
  );
  if (!token) return;
  for (const [mode, credential] of [
    ["missing", undefined],
    ["malformed", "invalid-jwt"],
    ["invalid signature", resign(token)],
  ] as const) {
    await runStep(report, `jwt-${mode}`, `Reject a credential with ${mode} authentication`, async () => {
      signal.throwIfAborted();
      if (credential === null) throw new SkipStep("The signed-in credential does not have a JWT signature.");
      const { status } = await authedFetch("/control-plane/v1/me", credential);
      assert(status === 401, `Expected HTTP 401, received ${status}.`);
      return { value: true };
    });
  }
  await runStep(report, "onboarding", "Onboarding admits the same person", async () => {
    const status = await checks.dispatch(cp.onboardingStatus.initiate(undefined, FRESH)).unwrap();
    assert(status.admitted && status.user_id === checks.userId, "Onboarding did not admit the current person.");
    return { value: true };
  });
  await runStep(report, "spaces", "Discover the signed-in person's spaces", async () => {
    const spaces = await checks.dispatch(cp.mySpaces.initiate(undefined, FRESH)).unwrap();
    assert(
      spaces.every(
        (s) => !!s.id && s.roles.length > 0 && (s.kind !== "personal" || s.personal_owner === checks.userId),
      ),
      "The caller's space list contains an unexpected membership.",
    );
    return { value: true, detail: `${spaces.length} directly accessible spaces.` };
  });
};

export const sharedSecurity: Scenario<WeaverChecks> = async (_checks, report) => {
  const browser = browserSecurity();
  // Use a valid, absent identifier on a protected route.
  await runSecurityBaseline(
    browser,
    report,
    [`/control-plane/v1/documents/${crypto.randomUUID()}/content`],
    [403, 404],
  );
};

export const documentSecurity: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const browser = browserSecurity();
  const fixture = await ingestKnowledgeFixture(checks, signal, undefined, {
    report,
    id: "security-document",
    title: "Upload a disposable text document",
  });
  if (!fixture) return;
  try {
    for (const artifact of ["content", "preview"] as const) {
      await runStep(
        report,
        artifact,
        artifact === "content" ? "Download is served as an attachment" : "Published preview is sandboxed",
        async () => {
          const token = await browser.token();
          assert(token, "Sign in again before checking document headers.");
          const { status, headers } = await browser.headersOf(
            `/control-plane/v1/documents/${fixture.documentId}/${artifact}`,
            token,
          );
          assert(status === 200 || status === 206, `Document ${artifact} returned HTTP ${status}.`);
          if (artifact === "content")
            assert(
              headers["content-disposition"]?.toLowerCase().startsWith("attachment"),
              "Raw content is not served as an attachment.",
            );
          else
            assert(
              /(?:^|;)\s*sandbox\s*(?:;|$)/i.test(headers["content-security-policy"] ?? "") &&
                !runsActiveContent(headers),
              "The preview is missing its restrictive sandbox.",
            );
          return { value: true };
        },
      );
    }
  } finally {
    await runStep(report, "cleanup-security", "Remove the security test document and folder", async () => {
      await fixture.cleanup();
      return { value: true };
    });
  }
};

function verifyUsage(usage: UsageResponse) {
  const keys = ["turns", "input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens"] as const;
  assert(
    Array.isArray(usage.series) && Array.isArray(usage.by_agent) && Array.isArray(usage.by_model),
    "Usage series or breakdowns are missing.",
  );
  const since = Date.parse(usage.since);
  const until = Date.parse(usage.until);
  assert(
    Number.isFinite(since) &&
      Number.isFinite(until) &&
      since < until &&
      ["hour", "day", "week"].includes(usage.interval),
    "Usage has an invalid reporting period.",
  );
  assert(
    [usage.totals, ...usage.series, ...usage.by_agent, ...usage.by_model].every(
      (row) => row && keys.every((key) => Number.isSafeInteger(row[key]) && row[key] >= 0),
    ),
    "Usage contains missing or invalid counters.",
  );
  const bucketSize = { hour: 3600000, day: 86400000, week: 604800000 }[usage.interval];
  let previous = -Infinity;
  for (const point of usage.series) {
    const start = Date.parse(point.start);
    assert(
      Number.isFinite(start) && start > previous && start < until && start > since - bucketSize,
      "Usage buckets are unordered, duplicated or outside the reporting period.",
    );
    previous = start;
  }
  assert(
    keys.every((key) => usage.series.reduce((sum, point) => sum + point[key], 0) === usage.totals[key]),
    "Usage totals do not match the time series.",
  );
  return { value: true, detail: `${usage.totals.turns} turns in this period.` };
}
export const sharedObservability: Scenario<WeaverChecks> = async (checks, report) => {
  const since = new Date(Date.now() - 86400000).toISOString();
  await runStep(
    report,
    "personal-usage",
    "Validate personal usage counters and time series over the last day",
    async () => verifyUsage(await checks.dispatch(cp.myUsage.initiate({ since }, FRESH)).unwrap()),
  );
  await runStep(report, "technical-status", "Verify readiness of monitored active workloads", async () => {
    try {
      const status = await checks.dispatch(monitorApi.endpoints.monitorStatus.initiate(undefined, FRESH)).unwrap();
      assert(
        !!status.observed_at && Array.isArray(status.services),
        "Technical status did not return a service snapshot.",
      );
      if (status.unavailable_sources.length || status.truncated_sources.length)
        throw new SkipStep("The snapshot has incomplete source coverage.");
      const active = status.services.filter((service) => service.desired > 0);
      assert(active.length > 0, "No active workloads were reported; readiness was not demonstrated.");
      assert(
        status.services.every(
          (service) =>
            Number.isSafeInteger(service.desired) &&
            service.desired >= 0 &&
            Number.isSafeInteger(service.ready) &&
            service.ready >= 0 &&
            (service.desired === 0
              ? service.state === "inactive"
              : service.state === "ready" && service.ready >= service.desired),
        ),
        "At least one monitored workload is not ready or has an unknown state.",
      );
      return { value: true, detail: `${active.length} active workloads ready in this snapshot.` };
    } catch (error) {
      if (statusOf(error) === 404) throw new SkipStep("Technical status is unavailable on this deployment.");
      throw error;
    }
  });
  await runStep(
    report,
    "scrape-targets",
    "Check metrics scrape targets",
    async () => {
      throw new SkipStep(
        "Technical status reports workload health; it does not expose the metrics scraper's target list.",
      );
    },
    { optional: true },
  );
};

export const spaceObservability: Scenario<WeaverChecks> = async (checks, report, signal) => {
  const since = new Date(Date.now() - 86400000).toISOString();
  await runStep(report, "space-usage", "Validate usage counters and time series in an authorized space", async () => {
    requireSpace(checks, signal);
    if (checks.spaceKind !== "team" && checks.spaceKind !== "project")
      throw new SkipStep(
        checks.spaceKind === "personal"
          ? "Personal usage is checked once in shared checks; space usage supports teams and projects."
          : "Organization space usage is unsupported; space usage supports teams and projects.",
      );
    const permission = await checks
      .dispatch(cp.authorizeSpace.initiate({ spaceCheck: { space_id: checks.spaceId, permission: "read_usage" } }))
      .unwrap();
    if (!permission.allowed) throw new SkipStep("The selected space does not grant access to usage.");
    return verifyUsage(
      await checks.dispatch(cp.spaceUsage.initiate({ since, spaceId: checks.spaceId }, FRESH)).unwrap(),
    );
  });
};
