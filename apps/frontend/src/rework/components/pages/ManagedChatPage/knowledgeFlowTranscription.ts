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

import type { AudioTranscriptionResponse } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

interface TranscribeAudioClipOptions {
  language?: string;
}

/**
 * The slice of the generated transcription mutation trigger this helper needs: hand it
 * multipart form data and await the unwrapped `{ text }` payload. Callers pass
 * `(form) => transcribeAudio({ bodyTranscribeAudio...: form as never }).unwrap()`.
 */
export type TranscribeAudioTrigger = (formData: FormData) => Promise<AudioTranscriptionResponse>;

function isAudioTranscriptionResponse(value: unknown): value is AudioTranscriptionResponse {
  return typeof value === "object" && value !== null && "text" in value && typeof value.text === "string";
}

/** RTK Query rejects with `{ data: { detail } }`; surface that server message when present. */
function transcriptionErrorMessage(error: unknown): string {
  const detail = (error as { data?: { detail?: string } })?.data?.detail;
  return typeof detail === "string" && detail ? detail : "Audio transcription failed.";
}

/**
 * Build one recorded audio clip into multipart form data, send it through the generated
 * Knowledge Flow transcription mutation, and return the plain transcript.
 *
 * Auth, token refresh, 401 retry and caching are owned centrally by the RTK Query base
 * query (`createDynamicBaseQuery`), so this helper only shapes the request and maps the
 * response/error for the dictation flow.
 *
 * How to use:
 * - pass the generated mutation trigger (see `TranscribeAudioTrigger`)
 * - pass a browser `File` produced by `MediaRecorder`
 * - optionally pass a short language hint such as `en` or `fr`
 */
export async function transcribeAudioClip(
  trigger: TranscribeAudioTrigger,
  file: File,
  options: TranscribeAudioClipOptions = {},
): Promise<string> {
  const formData = new FormData();
  formData.set("file", file);
  if (options.language) {
    formData.set("language", options.language);
  }

  let payload: AudioTranscriptionResponse;
  try {
    payload = await trigger(formData);
  } catch (error) {
    throw new Error(transcriptionErrorMessage(error));
  }

  if (!isAudioTranscriptionResponse(payload)) {
    throw new Error("Audio transcription returned an invalid response.");
  }
  return payload.text;
}
