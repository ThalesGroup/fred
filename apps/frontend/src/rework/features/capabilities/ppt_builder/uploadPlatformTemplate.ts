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

// Multipart upload of the platform default template: the sanctioned raw-fetch
// exception (the generated client cannot send a file), typed with the generated response.

import { handlePlatformAccessResponse } from "../../../../common/platformAccess";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { PlatformAnalysisRequest, PlatformTemplateResponse } from "./api/pptBuilderCapabilityOpenApi";

export async function uploadPlatformTemplate(
  baseUrl: string,
  file: File,
  vision: PlatformAnalysisRequest,
): Promise<PlatformTemplateResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("use_vision", String(vision.use_vision ?? true));
  if (vision.vision_profile_id) form.append("vision_profile_id", vision.vision_profile_id);

  const response = await fetch(`${baseUrl}/platform/template`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
    body: form,
  });
  await handlePlatformAccessResponse(response);
  if (!response.ok) {
    // The backend's sentence (unreadable file, size limit) is what the manager can act on;
    // without one the message stays empty and the caller shows its own.
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    throw new Error(typeof body?.detail === "string" ? body.detail : "");
  }
  return (await response.json()) as PlatformTemplateResponse;
}
