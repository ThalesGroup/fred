// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import { checkPersonalIsolation, sharedAuthorization as authorization } from "./authorization";
import { authedFetch } from "../useAuthzProbeRun";
import type { WeaverChecks } from "./checks";
vi.mock("../../../../security/KeycloakService", () => ({
  KeyCloakService: { ensureFreshToken: async () => true, GetToken: () => "session.payload.signature" },
}));
vi.mock("../useAuthzProbeRun", () => ({ authedFetch: vi.fn() }));
const context = { userId: "operator", spaceId: "selected" } as WeaverChecks;
function requests(leak = false) {
  vi.mocked(authedFetch).mockImplementation(async (path, token) => {
    if (!["session.payload.signature", "second.payload.signature"].includes(token ?? ""))
      return { status: 401, body: null };
    if (path.endsWith("/me"))
      return { status: 200, body: { user_id: token?.startsWith("second") ? "other" : "operator", platform_roles: [] } };
    if (path.endsWith("/platform-roles")) return { status: 403, body: null };
    if (path.endsWith("/authorize/space")) return { status: 200, body: { allowed: false } };
    if (path.endsWith("/me/spaces"))
      return {
        status: 200,
        body: [
          {
            id: token?.startsWith("second") ? "other-personal" : "own-personal",
            kind: "personal",
            personal_owner: true,
          },
        ],
      };
    if (path.includes("personal"))
      return {
        status:
          leak || (path.includes("own-personal") ? !token?.startsWith("second") : token?.startsWith("second"))
            ? 200
            : 403,
        body: { private: "sensitive-body" },
      };
    return { status: 403, body: null };
  });
}
describe("current authorization checks", () => {
  it("keeps the shared authorization report focused on one authenticated identity", async () => {
    requests();
    const report = vi.fn();
    await authorization(context, report, new AbortController().signal);
    expect(report).not.toHaveBeenCalledWith(expect.objectContaining({ id: "authorization-secondary" }));
    expect(report).toHaveBeenCalledWith(expect.objectContaining({ id: "authorization-admin", status: "passed" }));
    expect(report.mock.calls.some(([step]) => step.status === "failed")).toBe(false);
  });
  it("rejects a credential that does not match the selected account before reading personal spaces", async () => {
    requests();
    const report = vi.fn();
    const signal = new AbortController().signal;
    const result = await checkPersonalIsolation(
      "operator",
      "different-selection",
      "second.payload.signature",
      report,
      signal,
    );
    expect(result.identitiesVerified).toBe(false);
    expect(report).toHaveBeenLastCalledWith(expect.objectContaining({ id: "campaign-identities", status: "failed" }));
    expect(report).not.toHaveBeenCalledWith(expect.objectContaining({ id: "authorization-secondary" }));
    expect(JSON.stringify(report.mock.calls)).not.toContain("different-selection");
  });
  it("checks both directions when the selected account is authenticated", async () => {
    requests();
    const report = vi.fn();
    const result = await checkPersonalIsolation(
      "operator",
      "other",
      "second.payload.signature",
      report,
      new AbortController().signal,
    );
    expect(result.identitiesVerified).toBe(true);
    expect(report).toHaveBeenLastCalledWith(
      expect.objectContaining({ id: "authorization-secondary", status: "passed" }),
    );
    expect(authedFetch).toHaveBeenCalledWith(
      "/control-plane/v1/spaces/own-personal/entries",
      "second.payload.signature",
    );
    expect(authedFetch).toHaveBeenCalledWith(
      "/control-plane/v1/spaces/other-personal/entries",
      "session.payload.signature",
    );
  });
  it("detects personal content leakage without echoing sensitive bodies", async () => {
    requests(true);
    const report = vi.fn();
    const result = await checkPersonalIsolation(
      "operator",
      "other",
      "second.payload.signature",
      report,
      new AbortController().signal,
    );
    expect(result.identitiesVerified).toBe(true);
    expect(report).toHaveBeenLastCalledWith(
      expect.objectContaining({ id: "authorization-secondary", status: "failed" }),
    );
    expect(JSON.stringify(report.mock.calls)).not.toContain("sensitive-body");
    expect(JSON.stringify(report.mock.calls)).not.toContain("second.payload.signature");
  });
});
