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
  FrontendBootstrap,
  FrontendConfig,
  UserSummary,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { runStep, SkipStep } from "../step";
import type { Reporter } from "../types";

type Request = (path: string, token?: string) => Promise<{ status: number; body: unknown }>;
const PROTECTED = [
  "/control-plane/v1/frontend/bootstrap",
  "/knowledge-flow/v1/tags",
  "/fred/agents/v2/agents/sessions",
];

/** Explicit credentials isolate rejection checks from normal SSO refresh. */
export async function identityProbeScenario(token: string, uid: string | null, request: Request, report: Reporter) {
  const signature = token.lastIndexOf(".") + 1;
  const altered =
    signature > 0 && signature < token.length
      ? token.slice(0, signature) + (token[signature] === "A" ? "B" : "A") + token.slice(signature + 1)
      : null;
  for (const path of PROTECTED) {
    for (const [mode, credential] of [
      ["valid", token],
      ["missing", undefined],
      ["malformed", "invalid-jwt"],
      ["signature", altered],
    ] as const) {
      await runStep(report, `jwt-${path}-${mode}`, `${mode} JWT: GET ${path}`, async () => {
        if (credential === null) throw new SkipStep("The session credential is not a signed JWT");
        const { status } = await request(path, credential);
        const expected = mode === "valid" ? status === 200 : status === 401;
        if (!expected) throw new Error(`HTTP ${status}; expected ${mode === "valid" ? 200 : 401}`);
        return { value: true, detail: `HTTP ${status}` };
      });
    }
  }
  const config = await runStep(report, "public-auth-config", "Public provider configuration without JWT", async () => {
    const { status, body } = await request("/control-plane/v1/frontend/config");
    if (status !== 200) throw new Error(`HTTP ${status}; expected 200`);
    const config = body as FrontendConfig;
    if (!config.user_auth?.enabled)
      throw new Error("User authentication is disabled; JWT checks require an authenticated deployment");
    return { value: config };
  });
  await runStep(report, "public-health", "Public Control Plane health without JWT", async () => {
    const { status } = await request("/control-plane/v1/healthz");
    if (status !== 200) throw new Error(`HTTP ${status}; expected 200`);
    return { value: true };
  });
  await runStep(report, "identity-consistency", "Browser and backend identity agree", async () => {
    const { status, body } = await request(PROTECTED[0], token);
    if (status !== 200) throw new Error(`HTTP ${status}`);
    const bootstrap = body as FrontendBootstrap;
    if (!uid || bootstrap.current_user?.id !== uid) throw new Error("Browser and backend user IDs differ");
    return { value: true, detail: "Configured identity claim resolves to the same Fred user" };
  });
  await runStep(report, "personal-space-identity", "Personal space uses the authenticated Fred identity", async () => {
    if (!uid) throw new Error("No browser user ID");
    const { status } = await request(`/control-plane/v1/teams/personal-${encodeURIComponent(uid)}`, token);
    if (status !== 200) throw new Error(`HTTP ${status}; expected 200 for the current user's personal space`);
    return { value: true };
  });
  await runStep(
    report,
    "local-directory",
    "Authenticated person appears in the local directory",
    async () => {
      if (!config) throw new Error("Provider configuration could not be verified");
      if (config.user_auth?.user_directory !== "local") throw new SkipStep("This provider uses the Keycloak directory");
      const { status, body } = await request("/control-plane/v1/users", token);
      if (status !== 200) throw new Error(`HTTP ${status}`);
      if (!Array.isArray(body) || !(body as UserSummary[]).some((user) => user.id === uid))
        throw new Error("Authenticated identity missing from local directory");
      return { value: true };
    },
    { optional: true },
  );
  await runStep(
    report,
    "identity-coverage",
    "Additional identity and delegation coverage",
    async () => {
      throw new SkipStep(
        "Run the functional document/agent test for delegation and document access; use a second session for account isolation. Workload JWT claims require backend tests; no service secrets are exposed here.",
      );
    },
    { optional: true },
  );
}
