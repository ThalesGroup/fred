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

import { handlePlatformAccessResponse } from "../../../../../common/platformAccess";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import type { ExportAnalyticsControlPlaneV1KpiAnalyticsExportGetApiArg } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { downloadFile, filenameFromDisposition } from "../../../../../utils/downloadUtils";

const EXPORT_URL = "/control-plane/v1/kpi/analytics/export";

/** Downloads the analytics workbook. A raw fetch: the generated client cannot save a binary response. */
export async function exportAnalytics(args: ExportAnalyticsControlPlaneV1KpiAnalyticsExportGetApiArg): Promise<void> {
  const params = new URLSearchParams();
  if (args.since) params.set("since", args.since);
  if (args.until) params.set("until", args.until);
  for (const teamId of args.teamIds ?? []) params.append("team_ids", teamId);
  if (args.bucket) params.set("bucket", args.bucket);
  if (args.tz) params.set("tz", args.tz);
  if (args.lang) params.set("lang", args.lang);
  if (args.userFilter) params.set("user_filter", args.userFilter);

  // Like the generated client's base query: a token expired during sleep is renewed first.
  await KeyCloakService.ensureFreshToken(30);
  const response = await fetch(`${EXPORT_URL}?${params}`, {
    headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
  });
  await handlePlatformAccessResponse(response);
  if (!response.ok) throw new Error(`Analytics export failed (HTTP ${response.status})`);

  const filename = filenameFromDisposition(response.headers.get("Content-Disposition")) ?? "analytics.xlsx";
  downloadFile(await response.blob(), filename);
}
