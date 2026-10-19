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

import { handlePlatformAccessResponse } from "./platformAccess";
import { KeyCloakService } from "../security/KeycloakService";

/** Binary-download transport shared by generated-API adapters. */
export async function downloadAuthed(url: string, filename: string, signal?: AbortSignal): Promise<void> {
  if (!(await KeyCloakService.ensureFreshToken())) throw new Error("Authentication unavailable");
  const res = await fetch(url, {
    cache: "no-store",
    signal,
    headers: { Authorization: `Bearer ${KeyCloakService.GetToken() ?? ""}` },
  });
  await handlePlatformAccessResponse(res);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const blob = await res.blob();
  signal?.throwIfAborted();
  const objectUrl = URL.createObjectURL(blob);
  try {
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}
