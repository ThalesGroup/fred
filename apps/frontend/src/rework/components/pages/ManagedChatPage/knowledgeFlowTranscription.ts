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

import { KeyCloakService } from "../../../../security/KeycloakService";

interface AudioTranscriptionResponse {
  text: string;
}

interface TranscribeAudioClipOptions {
  language?: string;
}

function isAudioTranscriptionResponse(value: unknown): value is AudioTranscriptionResponse {
  return typeof value === "object" && value !== null && "text" in value && typeof value.text === "string";
}

function errorMessageFromPayload(payload: unknown): string | null {
  if (typeof payload === "object" && payload !== null && "detail" in payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  return null;
}

/**
 * Send one recorded audio clip to Knowledge Flow and return the plain transcript.
 *
 * Why this exists:
 * - `ManagedChatPage` needs a minimal MVP dictation path before the generated
 *   Knowledge Flow client is updated in a later API regeneration pass
 *
 * How to use:
 * - pass a browser `File` produced by `MediaRecorder`
 * - optionally pass a short language hint such as `en` or `fr`
 * - the helper uses the existing Keycloak bearer token and ingress-relative API path
 */
export async function transcribeAudioClip(file: File, options: TranscribeAudioClipOptions = {}): Promise<string> {
  await KeyCloakService.ensureFreshToken(30);

  const formData = new FormData();
  formData.set("file", file);
  if (options.language) {
    formData.set("language", options.language);
  }

  const token = KeyCloakService.GetToken();
  const response = await fetch("/knowledge-flow/v1/audio/transcriptions", {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
    cache: "no-store",
  });

  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessageFromPayload(payload) ?? "Audio transcription failed.");
  }
  if (!isAudioTranscriptionResponse(payload)) {
    throw new Error("Audio transcription returned an invalid response.");
  }
  return payload.text;
}
