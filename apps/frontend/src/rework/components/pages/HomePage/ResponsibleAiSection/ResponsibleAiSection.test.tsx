// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";
import type { AnalyticsResponse } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  context: { organizationId: "Acme" as string | undefined, loading: false, error: undefined as unknown },
  result: {
    currentData: undefined as AnalyticsResponse | undefined,
    data: undefined as AnalyticsResponse | undefined,
    isFetching: false,
    isError: false,
  },
  query: vi.fn(),
}));
vi.mock("@core/hooks/useWorkingOrganization", () => ({ useWorkingOrganization: () => h.context }));
vi.mock("../../../../../security/KeycloakService", () => ({ KeyCloakService: { GetSessionIdentity: () => "alice" } }));
vi.mock("../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  useQueryAnalyticsQuery: (args: unknown) => {
    h.query(args);
    return h.result;
  },
}));
vi.mock("../../../../../slices/legacyControlPlane/legacyControlPlaneApiEnhancements", () => ({
  useMyInactiveSessionsQuery: () => ({ data: { sessions: [] } }),
  useBulkDeleteMySessionsMutation: () => [vi.fn()],
}));
vi.mock("../../../../../hooks/useFrontendBootstrap", () => ({ useFrontendBootstrap: () => ({ availableTeams: [] }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showSuccess: vi.fn() }) }));
vi.mock("@shared/molecules/Dialog/Dialog.tsx", () => ({ Dialog: () => null }));
vi.mock("../CleanupDialog/CleanupDialog.tsx", () => ({ default: () => null }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
import ResponsibleAiSection from "./ResponsibleAiSection";

function response(tokens: string): AnalyticsResponse {
  return {
    calculation: "mixed",
    collection_completeness: "unknown",
    results: {
      usage: {
        since: "2026-01-01T00:00:00Z",
        until: "2026-01-02T00:00:00Z",
        timezone: "UTC",
        bucket: null,
        truncated: false,
        measures: [],
        rows: [
          {
            dimensions: { kind: "total" },
            values: { "usage.total_tokens": tokens },
            estimates: {
              "usage.co2e_grams": { value: null, coverage: "unavailable", fallback: false },
              "usage.energy_kwh": { value: "1.5", coverage: "partial", fallback: true },
            },
          },
        ],
      },
    },
  };
}
beforeEach(() => {
  h.context = { organizationId: "Acme", loading: false, error: undefined };
  h.result = { currentData: undefined, data: undefined, isFetching: false, isError: false };
  h.query.mockClear();
});
it("scopes home consumption to the shared organization after switching and preserves exact tokens", () => {
  for (const organizationId of ["Acme", "Globex"]) {
    h.context.organizationId = organizationId;
    h.result.currentData = response("9007199254740993");
    const html = renderToStaticMarkup(<ResponsibleAiSection period={30} />);
    expect(h.query).toHaveBeenLastCalledWith(
      expect.objectContaining({
        analyticsRequest: {
          queries: [expect.objectContaining({ scope: { kind: "self", organization_id: organizationId } })],
        },
      }),
    );
    expect(html).toContain("9,007,199,254,740,993 tokens");
    expect(html).toContain("rework.tokenUsageImpact.unavailable");
    expect(html).toContain("rework.tokenUsageImpact.partial");
    expect(html).toContain("rework.tokenUsageImpact.fallback");
  }
});
it.each([
  { organizationId: undefined, loading: false, error: undefined },
  { organizationId: "Acme", loading: true, error: undefined },
  { organizationId: "Acme", loading: false, error: new Error("revoked") },
])("does not query or show cached consumption without valid context: %j", (context) => {
  h.context = context;
  h.result.currentData = response("12345");
  const html = renderToStaticMarkup(<ResponsibleAiSection period={30} />);
  expect(h.query).toHaveBeenLastCalledWith(skipToken);
  expect(html).not.toContain("12,345 tokens");
});
it("does not display the preceding organization's response while the new one is pending", () => {
  h.context.organizationId = "Globex";
  h.result.data = response("12345");
  h.result.isFetching = true;
  const html = renderToStaticMarkup(<ResponsibleAiSection period={30} />);
  expect(html).not.toContain("12,345 tokens");
  expect(html).toContain("…");
});
