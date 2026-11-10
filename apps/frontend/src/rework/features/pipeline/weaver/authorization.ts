// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { KeyCloakService } from "../../../../security/KeycloakService";
import { authedFetch } from "../useAuthzProbeRun";
import { resign } from "../scenarios/authorizationScenario";
import { runStep, SkipStep } from "../step";
import type { Reporter, Scenario } from "../types";
import type { WeaverChecks } from "./checks";

async function operatorToken(userId: string): Promise<string> {
  if (!(await KeyCloakService.ensureFreshToken(30).catch(() => false)))
    throw new Error("Sign in again before running checks");
  const token = KeyCloakService.GetToken();
  if (!token) throw new Error("The current identity could not be verified");
  const response = await authedFetch("/control-plane/v1/me", token).catch(() => null);
  if (response?.status !== 200 || (response.body as { user_id?: string })?.user_id !== userId)
    throw new Error("The current identity could not be verified");
  return token;
}

export const sharedAuthorization: Scenario<WeaverChecks> = async (context, report, signal) => {
  const token = await runStep(
    report,
    "authorization-session",
    "Verify the current authenticated identity",
    async () => ({ value: await operatorToken(context.userId) }),
  );
  if (!token) return;
  for (const [mode, credential] of [
    ["missing", undefined],
    ["malformed", "not-a-jwt"],
    ["signature", resign(token)],
  ] as const) {
    await runStep(report, `authorization-${mode}`, `Protected routes reject ${mode} credentials`, async () => {
      if (signal.aborted) throw new Error("Authorization checks interrupted");
      if (credential === null) throw new Error("The current credential is not a signed token");
      for (const path of ["/me", "/me/spaces", "/admin/organizations", "/users/platform-roles"]) {
        const response = await authedFetch(`/control-plane/v1${path}`, credential);
        if (response.status !== 401) throw new Error(`Protected route returned HTTP ${response.status}; expected 401`);
      }
      return { value: true, detail: "Four current routes rejected the credential" };
    });
  }
  await runStep(
    report,
    "authorization-admin",
    "Platform grant administration follows the direct platform role",
    async () => {
      const identity = await authedFetch("/control-plane/v1/me", token);
      if (identity.status !== 200) throw new Error("The current identity could not be refreshed");
      const admin =
        (identity.body as { platform_roles?: string[] })?.platform_roles?.includes("platform_admin") ?? false;
      const response = await authedFetch("/control-plane/v1/users/platform-roles", token);
      if (admin ? response.status !== 200 : response.status !== 403)
        throw new Error("Platform grant administration does not match the current role");
      return { value: true };
    },
  );
};

export async function checkPersonalIsolation(
  operatorId: string,
  testAccountId: string,
  testToken: string,
  report: Reporter,
  signal: AbortSignal,
): Promise<{ identitiesVerified: boolean }> {
  const request = (path: string, token: string) => {
    signal.throwIfAborted();
    return authedFetch(path, token).catch(() => {
      throw new Error("The personal isolation request failed");
    });
  };
  const token = await runStep(report, "campaign-identities", "Verify the selected test account", async () => {
    const identity = await request("/control-plane/v1/me", testToken);
    if (
      testAccountId === operatorId ||
      identity.status !== 200 ||
      (identity.body as { user_id?: string })?.user_id !== testAccountId
    )
      throw new Error("The signed-in test account does not match the selection");
    return { value: await operatorToken(operatorId) };
  });
  if (!token) return { identitiesVerified: false };
  await runStep(
    report,
    "authorization-secondary",
    "Verify personal content stays isolated between two real identities",
    async () => {
      for (const [owner, visitor] of [
        [token, testToken],
        [testToken, token],
      ]) {
        const response = await request("/control-plane/v1/me/spaces", owner);
        if (response.status !== 200 || !Array.isArray(response.body))
          throw new Error("Personal scope discovery failed");
        const personal = response.body.find((space) => space.kind === "personal" && space.personal_owner);
        if (!personal) throw new SkipStep("Both accounts need an existing personal space to verify isolation");
        const path = `/control-plane/v1/spaces/${encodeURIComponent(personal.id)}/entries`;
        if ((await request(path, owner)).status !== 200) throw new Error("The owner cannot read its personal content");
        if (![403, 404].includes((await request(path, visitor)).status))
          throw new Error("Personal content isolation failed");
      }
      return { value: true };
    },
  );
  return { identitiesVerified: true };
}

export const spaceAuthorization: Scenario<WeaverChecks> = async (context, report, signal) => {
  signal.throwIfAborted();
  await runStep(
    report,
    "authorization-selected-space",
    "Selected-space content follows the current read decision",
    async () => {
      if (!context.spaceId) throw new SkipStep("Select a business space to verify current content access");
      if (!(await KeyCloakService.ensureFreshToken(30)))
        throw new Error("Sign in again before checking selected-space authorization.");
      const token = KeyCloakService.GetToken();
      if (!token) throw new Error("Your session has no access token; sign in again before running this check.");
      const decision = await authedFetch("/control-plane/v1/authorize/space", token, {
        method: "POST",
        body: { space_id: context.spaceId, permission: "read" },
      });
      if (decision.status !== 200 || typeof (decision.body as { allowed?: unknown })?.allowed !== "boolean")
        throw new Error("The current read decision is unavailable");
      const response = await authedFetch(
        `/control-plane/v1/spaces/${encodeURIComponent(context.spaceId)}/entries`,
        token,
      );
      if (
        (decision.body as { allowed: boolean }).allowed
          ? response.status !== 200
          : ![403, 404].includes(response.status)
      )
        throw new Error("Content access does not match the current read decision");
      return { value: true };
    },
  );
};
